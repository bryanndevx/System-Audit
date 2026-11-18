import asyncio
import json
import os
import secrets
import unittest
from unittest.mock import AsyncMock, patch

from app.ai_context import build_activity_context
from app.ai_diagnostics import (
    DEFAULT_MODEL,
    MAX_RESPONSE_BYTES,
    GeminiConfig,
    GeminiError,
    GeneratedNarrative,
    add_ai_narratives,
    request_gemini,
    provider_error,
)
from app.audit_engine import ActivityEvidence, ActivityResult, AuditExecutionResult


def activity(identifier="2.1", status="completada"):
    return ActivityResult(
        identificador=identifier, numero_original=identifier,
        nombre_original="private-checklist-instructions", fase_original="private-phase",
        estado_ejecucion=status, estado_evidencia="suficiente",
        evidencias=[ActivityEvidence(
            clave="private-evidence", consulta_id="private-query",
            disponibilidad="disponible", naturaleza="calculada",
            datos={
                "total_tablas": 3, "esquemas": ["private-schema"],
                "tablas": [{"nombre": "private-table", "email": "private-email"}],
                "comentario": "private-comment", "password": secrets.token_urlsafe(20),
                "total_campos": "private-string-in-numeric-field",
                "ventana_representativa": False,
                "parametros": [{"valor": "private-setting"}],
            },
        )],
        advertencias=["private-warning"], limitaciones=["private-limitation"], duracion_ms=12,
    )


def result(activities=None):
    return AuditExecutionResult(
        catalogo_version="test", actividades=activities or [activity()], duracion_total_ms=12,
    )


def narrative(identifier="2.1"):
    return GeneratedNarrative(
        id=identifier, diagnostico="Inventario limitado a la evidencia disponible.",
        recomendacion="Revisar el alcance con el auditor.",
        referencias_evidencia=[1],
    )


def envelope(items=None, finish="STOP"):
    return json.dumps({"candidates": [{
        "finishReason": finish, "content": {"parts": [{"text": json.dumps({
            "actividades": items if items is not None else [narrative().model_dump()],
        })}]},
    }]}).encode()


class ContextTests(unittest.TestCase):
    def test_technical_findings_include_permission_limits_without_names(self):
        item = activity()
        item.evidencias[0].datos = {
            "esquemas": [{"esquema": "private-schema", "permiso_uso": False, "tablas": [
                {"tabla": "private-table", "permiso_lectura": False},
                {"tabla": "private-table-2", "permiso_lectura": True},
            ]}],
            "total_tablas": 2, "cobertura_entregable": "parcial",
        }
        context = build_activity_context(item)
        findings = {finding["codigo"]: finding["valor"] for finding in context["evidencias"][0]["hallazgos"]}
        self.assertEqual(findings["tablas_sin_permiso_lectura"], 1)
        self.assertEqual(findings["esquemas_sin_permiso_uso"], 1)
        self.assertEqual(context["evidencias"][0]["cobertura_entregable"], "parcial")
        self.assertNotIn("private-", json.dumps(context))

    def test_python_computes_pattern_findings_and_supplies_activity_specific_criteria(self):
        item = activity("3.8")
        item.evidencias[0].datos = {"total_campos": 10, "total_snake_case_minusculas": 7}
        context = build_activity_context(item)
        self.assertEqual(context["evidencias"][0]["agregados"]["campos_fuera_patron_snake_case"], 3)
        self.assertIn("convención aprobada", context["criterios"])
        item.evidencias[0].datos["total_snake_case_minusculas"] = 12
        context = build_activity_context(item)
        self.assertNotIn("campos_fuera_patron_snake_case", context["evidencias"][0]["agregados"])

    def test_candidate_findings_do_not_confirm_automatic_actions(self):
        item = activity("4.3")
        item.evidencias[0].datos = {"duplicados_exactos": [{"tabla": "private-table"}]}
        context = build_activity_context(item)
        finding = context["evidencias"][0]["hallazgos"][0]
        self.assertEqual(finding["valor"], 1)
        self.assertIn("requieren revisión", finding["descripcion"])
        self.assertNotIn("private-", json.dumps(context))

    def test_only_allowlisted_aggregates_leave_the_application(self):
        context = build_activity_context(activity())
        self.assertNotIn("private-", json.dumps(context))
        aggregates = context["evidencias"][0]["agregados"]
        self.assertEqual(aggregates["total_tablas"], 3)
        self.assertEqual(aggregates["elementos_tablas"], 1)
        self.assertEqual(aggregates["elementos_esquemas"], 1)
        self.assertEqual(aggregates["elementos_parametros"], 1)
        self.assertFalse(aggregates["ventana_representativa"])
        self.assertNotIn("total_campos", aggregates)

    def test_failed_unmapped_and_empty_activities_are_not_sent(self):
        self.assertIsNone(build_activity_context(activity(status="error_tecnico")))
        self.assertIsNone(build_activity_context(activity("99.1")))
        item = activity()
        item.evidencias = []
        self.assertIsNone(build_activity_context(item))

    def test_partial_evidence_keeps_its_status_in_context(self):
        item = activity(status="parcial")
        item.estado_evidencia = "insuficiente"
        context = build_activity_context(item)
        self.assertEqual(context["estado_sql"], "parcial")
        self.assertEqual(context["estado_evidencia"], "insuficiente")


@patch("app.ai_diagnostics.load_local_gemini_environment", new=lambda: None)
class ConfigTests(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(GeminiConfig.from_environment())

    def test_missing_key_is_an_error_when_enabled(self):
        with patch.dict(os.environ, {"GEMINI_ENABLED": "1"}, clear=True):
            with self.assertRaisesRegex(GeminiError, "GEMINI_API_KEY"):
                GeminiConfig.from_environment()

    def test_key_is_not_in_configuration_representation(self):
        key = secrets.token_urlsafe(25)
        with patch.dict(os.environ, {"GEMINI_ENABLED": "1", "GEMINI_API_KEY": key}, clear=True):
            config = GeminiConfig.from_environment()
        self.assertEqual(config.model, DEFAULT_MODEL)
        self.assertNotIn(key, repr(config))

    def test_rejects_preview_and_path_injection(self):
        for model in ("gemini-preview", "gemini-test/../../", "https://private-host"):
            with self.subTest(model=model), patch.dict(os.environ, {
                "GEMINI_ENABLED": "1", "GEMINI_API_KEY": secrets.token_urlsafe(25),
                "GEMINI_MODEL": model,
            }, clear=True):
                with self.assertRaises(GeminiError):
                    GeminiConfig.from_environment()


class TransportTests(unittest.TestCase):
    def test_local_diagnostic_detail_masks_key_urls_and_identifiers(self):
        from unittest.mock import Mock
        key = secrets.token_urlsafe(25)
        response = Mock(status=400)
        response.read.return_value = json.dumps({"error": {
            "status": "INVALID_ARGUMENT",
            "message": f"Unknown name responseJsonSchema. {key} https://example.test/?key={key} user@example.test projects/private-project",
        }}).encode()
        error = provider_error(response, key)
        self.assertIn("Unknown name responseJsonSchema", error.diagnostic_detail)
        self.assertNotIn(key, error.diagnostic_detail)
        self.assertNotIn("https://", error.diagnostic_detail)
        self.assertNotIn("user@example", error.diagnostic_detail)
        self.assertNotIn("private-project", error.diagnostic_detail)
        self.assertNotIn("Unknown name", str(error))

    @patch("app.ai_diagnostics.http.client.HTTPSConnection")
    def test_http_errors_report_safe_actionable_causes(self, connect):
        config = GeminiConfig(secrets.token_urlsafe(25), DEFAULT_MODEL)
        for status, payload, expected in (
            (404, {"status": "NOT_FOUND", "message": "private-model"}, "GEMINI_MODEL"),
            (400, {"status": "INVALID_ARGUMENT", "message": "generation_config.response_json_schema private-value"}, "esquema JSON"),
            (400, {"status": "FAILED_PRECONDITION", "message": "private-project"}, "nivel gratuito"),
            (400, {"status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}, "clave API"),
            (400, {"status": "INVALID_ARGUMENT", "message": "API key expired. Please renew the API key."}, "clave API"),
            (503, {"status": "UNAVAILABLE", "message": "private-detail"}, "disponibilidad"),
            (400, {"status": "private-status", "message": config.api_key}, "parámetros inválidos"),
        ):
            with self.subTest(status=status, expected=expected):
                response = connect.return_value.getresponse.return_value
                response.status = status
                response.read.return_value = json.dumps({"error": payload}).encode()
                with self.assertRaises(GeminiError) as raised:
                    request_gemini(config, [build_activity_context(activity())])
                text = str(raised.exception)
                self.assertIn(f"HTTP {status}", text)
                self.assertIn(expected, text)
                self.assertNotIn("private-", text)
                self.assertNotIn(config.api_key, text)

    @patch("app.ai_diagnostics.http.client.HTTPSConnection")
    def test_header_auth_fixed_destination_and_structured_response(self, connect):
        config = GeminiConfig(secrets.token_urlsafe(25), DEFAULT_MODEL)
        connection = connect.return_value
        response = connection.getresponse.return_value
        response.status = 200
        response.read.return_value = envelope()
        generated = request_gemini(config, [build_activity_context(activity())])
        self.assertEqual(generated["2.1"].diagnostico, narrative().diagnostico)
        self.assertEqual(connect.call_args.args[0], "generativelanguage.googleapis.com")
        args = connection.request.call_args
        self.assertEqual(args.kwargs["headers"]["x-goog-api-key"], config.api_key)
        self.assertNotIn(config.api_key, args.args[1])
        payload = json.loads(args.kwargs["body"])
        self.assertNotIn("private-", json.dumps(payload))
        self.assertNotIn(config.api_key, json.dumps(payload))
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")
        schema = payload["generationConfig"]["responseSchema"]
        self.assertEqual(schema["properties"]["actividades"]["items"]["required"], ["id", "diagnostico", "recomendacion", "referencias_evidencia"])
        self.assertNotIn("responseJsonSchema", payload["generationConfig"])
        for unsupported in ("$defs", "$ref", "maxLength", "minLength", "additionalProperties"):
            self.assertNotIn(unsupported, json.dumps(schema))
        self.assertNotIn("tools", payload)
        connection.close.assert_called_once()

    @patch("app.ai_diagnostics.http.client.HTTPSConnection")
    def test_provider_errors_are_safe_and_not_retried(self, connect):
        config = GeminiConfig(secrets.token_urlsafe(25), DEFAULT_MODEL)
        for status, message in ((429, "cuota"), (403, "clave"), (500, "disponibilidad"), (302, "disponibilidad")):
            with self.subTest(status=status):
                connect.reset_mock()
                connect.return_value.getresponse.return_value.status = status
                with self.assertRaisesRegex(GeminiError, message):
                    request_gemini(config, [build_activity_context(activity())])
                connect.return_value.request.assert_called_once()
                connect.return_value.close.assert_called_once()

    @patch("app.ai_diagnostics.http.client.HTTPSConnection")
    def test_malformed_blocked_truncated_and_wrong_activity_responses_fail(self, connect):
        config = GeminiConfig(secrets.token_urlsafe(25), DEFAULT_MODEL)
        invalid = [
            b"private-provider-error", b"[]", json.dumps({"candidates": []}).encode(),
            envelope(finish="MAX_TOKENS"), envelope([narrative("2.2").model_dump()]),
            envelope([narrative().model_dump(), narrative().model_dump()]),
            envelope([{**narrative().model_dump(), "diagnostico": " "}]),
            envelope([{**narrative().model_dump(), "sql": "unexpected"}]),
            envelope([{**narrative().model_dump(), "diagnostico": "a" * 1501}]),
            envelope([{**narrative().model_dump(), "referencias_evidencia": [99]}]),
            envelope([{**narrative().model_dump(), "referencias_evidencia": [1, 1]}]),
            envelope([{**narrative().model_dump(), "referencias_evidencia": []}]),
            envelope([{**narrative().model_dump(), "referencias_evidencia": [True]}]),
            b"x" * (MAX_RESPONSE_BYTES + 1),
        ]
        for raw in invalid:
            with self.subTest(size=len(raw)):
                response = connect.return_value.getresponse.return_value
                response.status = 200
                response.read.return_value = raw
                with self.assertRaises(GeminiError) as raised:
                    request_gemini(config, [build_activity_context(activity())])
                self.assertNotIn("private-provider-error", str(raised.exception))

    @patch("app.ai_diagnostics.http.client.HTTPSConnection")
    def test_socket_errors_do_not_expose_provider_details(self, connect):
        connect.return_value.request.side_effect = TimeoutError("private-host-info")
        with self.assertRaises(GeminiError) as raised:
            request_gemini(GeminiConfig(secrets.token_urlsafe(25), DEFAULT_MODEL), [])
        self.assertNotIn("private-host-info", str(raised.exception))
        connect.return_value.close.assert_called_once()


@patch("app.ai_diagnostics.load_local_gemini_environment", new=lambda: None)
class IntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_overall_timeout_preserves_evidence_and_reports_ai_error(self):
        with (
            patch.dict(os.environ, {"GEMINI_ENABLED": "1", "GEMINI_API_KEY": secrets.token_urlsafe(25)}, clear=True),
            patch("app.ai_diagnostics.request_gemini", side_effect=GeminiError('Gemini superó el tiempo máximo de redacción.', transient=True)),
            patch("app.ai_diagnostics.asyncio.sleep", new_callable=AsyncMock),
        ):
            updated = await add_ai_narratives(result())
        self.assertEqual(updated.actividades[0].redaccion_ia.estado, "error")
        self.assertIn("tiempo máximo", updated.actividades[0].redaccion_ia.mensaje)
        self.assertEqual(updated.actividades[0].estado_ejecucion, "completada")
        self.assertTrue(updated.actividades[0].evidencias)

    @patch("app.ai_diagnostics.request_gemini")
    async def test_disabled_ai_does_not_call_provider(self, request):
        with patch.dict(os.environ, {}, clear=True):
            updated = await add_ai_narratives(result())
        self.assertEqual(updated.actividades[0].redaccion_ia.estado, "no_configurada")
        request.assert_not_called()

    @patch("app.ai_diagnostics.request_gemini")
    async def test_one_batch_preserves_sql_evidence_status_and_timing(self, request):
        original = result([activity(), activity("2.2", "parcial"), activity("99.1", "sin_automatizacion_configurada")])
        before = [item.model_dump(exclude={"redaccion_ia"}) for item in original.actividades]
        request.return_value = {"2.1": narrative(), "2.2": narrative("2.2")}
        with patch.dict(os.environ, {"GEMINI_ENABLED": "1", "GEMINI_API_KEY": secrets.token_urlsafe(25)}, clear=True):
            updated = await add_ai_narratives(original)
        request.assert_called_once()
        self.assertEqual(len(request.call_args.args[1]), 2)
        self.assertEqual([item.redaccion_ia.estado for item in updated.actividades], ["generada", "generada", "no_aplica"])
        self.assertEqual([item.model_dump(exclude={"redaccion_ia"}) for item in updated.actividades], before)
        self.assertEqual(updated.duracion_total_ms, 12)

    @patch("app.ai_diagnostics.request_gemini", side_effect=GeminiError("Cuota agotada."))
    async def test_ai_failure_is_separate_from_sql_failure(self, request):
        original = result([activity(), activity("2.2", "error_tecnico")])
        with patch.dict(os.environ, {"GEMINI_ENABLED": "1", "GEMINI_API_KEY": secrets.token_urlsafe(25)}, clear=True):
            updated = await add_ai_narratives(original)
        self.assertEqual(updated.actividades[0].estado_ejecucion, "completada")
        self.assertEqual(updated.actividades[0].redaccion_ia.estado, "error")
        self.assertTrue(updated.actividades[0].evidencias)
        self.assertEqual(updated.actividades[1].estado_ejecucion, "error_tecnico")
        self.assertEqual(updated.actividades[1].redaccion_ia.estado, "no_aplica")

    @patch("app.ai_diagnostics.request_gemini")
    async def test_incomplete_configuration_is_reported_as_ai_error(self, request):
        with patch.dict(os.environ, {"GEMINI_ENABLED": "1"}, clear=True):
            updated = await add_ai_narratives(result())
        self.assertEqual(updated.actividades[0].redaccion_ia.estado, "error")
        request.assert_not_called()
