import json
import secrets
import unittest
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi import HTTPException, Response

from app.audit_engine import ActivityEvidence, ActivityResult, AuditExecutionResult
from app.ai_diagnostics import AiNarrative
from app.audit_history import (
    AuditHistoryError, INSERT_AUDIT_SQL, LIST_AUDITS_SQL, SELECT_AUDIT_SQL,
    get_saved_audit, list_audits, save_audit, summarize_audit,
)
from app.audits import AuditExecutionRequest, execute_audit, history, saved_audit
from app.auth import AuthRuntimeConfig
from app.external_connections import ExternalConnectionPolicy, ExternalConnectionRequest
from app.internal_db import InternalDatabaseConfig
from app.sessions import AuthConfig, AuthenticatedSession


def sample_activity(number="2.1", status="completada", evidence="suficiente"):
    return ActivityResult(
        identificador=number, numero_original=number, nombre_original="Actividad de prueba",
        fase_original="Fase de prueba", estado_ejecucion=status, estado_evidencia=evidence,
        evidencias=[ActivityEvidence(
            clave="inventario", consulta_id="predefined_test", disponibilidad="disponible",
            naturaleza="exacta", datos={"total_tablas": 2},
        )], advertencias=[], limitaciones=[], duracion_ms=12,
        redaccion_ia=AiNarrative(estado="generada", diagnostico="Diagnóstico de prueba.", recomendacion="Revisión de prueba.", referencias_evidencia=[1]),
    )


def sample_result():
    return AuditExecutionResult(catalogo_version="test", actividades=[sample_activity()], duracion_total_ms=12)


def database_config():
    return InternalDatabaseConfig("localhost", 5432, "internal", "test_operator", secrets.token_urlsafe(20))


def runtime():
    return AuthRuntimeConfig(database_config(), AuthConfig("development", "http://localhost:5173", 480))


def session(user_id=7):
    return AuthenticatedSession(user_id, "test_auditor", secrets.token_urlsafe(20), datetime.now(UTC) + timedelta(hours=1))


class SummaryTests(unittest.TestCase):
    def test_partial_evidence_and_failures_are_not_counted_as_automated(self):
        result = sample_result()
        result.actividades = [
            sample_activity(), sample_activity("2.2", evidence="sin_datos"),
            sample_activity("2.3", evidence="insuficiente"),
            sample_activity("2.4", "parcial", "insuficiente"),
            sample_activity("2.5", "error_tecnico", "no_obtenida"),
            sample_activity("99.1", "sin_automatizacion_configurada", "no_obtenida"),
        ]
        result.actividades[0].redaccion_ia = AiNarrative(estado="error", mensaje="Error IA de prueba.")
        summary = summarize_audit(result)
        self.assertEqual((summary.total, summary.automatizadas, summary.parciales), (6, 2, 2))
        self.assertEqual((summary.errores_sql, summary.sin_configuracion, summary.errores_ia), (1, 1, 1))
        self.assertEqual(summary.porcentaje_automatizacion, 33.33)

    def test_empty_result_has_zero_percentage(self):
        result = sample_result()
        result.actividades = []
        self.assertEqual(summarize_audit(result).porcentaje_automatizacion, 0)


class StorageTests(unittest.TestCase):
    @patch("app.audit_history._connect")
    def test_saves_whitelisted_result_and_preserves_order_evidence_and_ai(self, connect):
        original = sample_result()
        original.actividades += [sample_activity("3.1"), sample_activity("2.2")]
        config = database_config()
        saved = save_audit(config, 7, "audited_test", original)
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        query, params = cursor.execute.call_args.args
        self.assertEqual(query, INSERT_AUDIT_SQL)
        self.assertEqual(params[1:3], (7, "audited_test"))
        payload = params[4].obj
        self.assertEqual([item["identificador"] for item in payload["actividades"]], ["2.1", "3.1", "2.2"])
        self.assertEqual(payload["actividades"][0]["evidencias"], original.actividades[0].model_dump()["evidencias"])
        self.assertEqual(payload["actividades"][0]["redaccion_ia"]["diagnostico"], "Diagnóstico de prueba.")
        self.assertNotIn("conexion", payload)
        self.assertNotIn(config.password, str(payload))
        self.assertEqual(saved.almacenamiento.estado, "guardada")
        self.assertEqual(original.almacenamiento.estado, "no_guardada")

    @patch("app.audit_history._connect")
    def test_failed_commit_does_not_return_saved_result(self, connect):
        connect.return_value.__exit__.side_effect = psycopg.OperationalError("private-driver-detail")
        with self.assertRaises(AuditHistoryError) as raised:
            save_audit(database_config(), 7, "audited_test", sample_result())
        self.assertNotIn("private-driver-detail", str(raised.exception))

    @patch("app.audit_history._connect")
    def test_missing_migration_is_actionable(self, connect):
        connect.side_effect = psycopg.errors.UndefinedTable()
        with self.assertRaisesRegex(AuditHistoryError, "migración 003"):
            list_audits(database_config(), 7, 20, 0)

    @patch("app.audit_history._connect")
    def test_detail_query_requires_owner_and_id(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None
        audit_id = uuid4()
        self.assertIsNone(get_saved_audit(database_config(), 7, audit_id))
        cursor.execute.assert_called_once_with(SELECT_AUDIT_SQL, (audit_id, 7))

    @patch("app.audit_history._connect")
    def test_listing_is_paginated_and_does_not_read_full_evidence(self, connect):
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (1,)
        cursor.fetchall.return_value = [(uuid4(), "audited_test", datetime.now(UTC), summarize_audit(sample_result()).model_dump(), 12, 4)]
        page = list_audits(database_config(), 7, 20, 0)
        self.assertEqual(page.total, 1)
        self.assertEqual(page.auditorias[0].resumen.automatizadas, 1)
        self.assertEqual(cursor.execute.call_args.args, (LIST_AUDITS_SQL, (7, 20, 0)))
        self.assertNotIn("evidencias", json.dumps(page.model_dump(mode="json")))

    @patch("app.audit_history._connect")
    def test_large_evidence_is_not_silently_truncated_or_stored(self, connect):
        with patch("app.audit_history.MAX_SAVED_RESULT_BYTES", 1):
            with self.assertRaises(AuditHistoryError):
                save_audit(database_config(), 7, "audited_test", sample_result())
        connect.assert_not_called()

    def test_migration_is_additive_and_has_owner_foreign_key(self):
        sql = (Path(__file__).resolve().parents[1] / "sql/migrations/003_create_audit_runs.sql").read_text(encoding="utf-8")
        self.assertIn("REFERENCES public.users(id)", sql)
        self.assertIn("user_id, created_at DESC, id DESC", sql)
        self.assertNotIn("DROP ", sql.upper())
        self.assertNotIn("TRUNCATE", sql.upper())


class EndpointTests(unittest.TestCase):
    @patch("app.audits.get_saved_audit", return_value=None)
    @patch("app.audits.add_ai_narratives")
    @patch("app.audits.open_verified_external_connection")
    def test_missing_or_other_user_detail_is_404_without_rerunning_anything(self, external, ai, read):
        response = Response()
        audit_id = uuid4()
        config = runtime()
        with self.assertRaises(HTTPException) as raised:
            saved_audit(audit_id, response, session(), config)
        self.assertEqual(raised.exception.status_code, 404)
        read.assert_called_once_with(config.database, 7, audit_id)
        ai.assert_not_called()
        external.assert_not_called()
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    @patch("app.audits.list_audits", side_effect=AuditHistoryError("Historial no disponible."))
    def test_history_storage_failure_is_503(self, read):
        with self.assertRaises(HTTPException) as raised:
            history(Response(), session(), runtime(), 20, 0)
        self.assertEqual(raised.exception.status_code, 503)


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_failure_preserves_live_result_and_reports_failure(self):
        @asynccontextmanager
        async def external(*args, **kwargs):
            yield object()

        connection = ExternalConnectionRequest(host="localhost", port=5432, database="audited_test", username="test_reader", password=secrets.token_urlsafe(20))
        request = AuditExecutionRequest(conexion=connection, actividades=[{"numero": "2.1", "actividad": "Inventario", "fase": "Fase"}])
        result = sample_result()

        async def redact(value):
            return value

        with (
            patch("app.audits.open_verified_external_connection", external),
            patch("app.audits.execute_audit_activities", return_value=result),
            patch("app.audits.add_ai_narratives", side_effect=redact),
            patch("app.audits.save_audit", side_effect=AuditHistoryError("Guardado no disponible.")) as save,
        ):
            updated = await execute_audit(
                Response(), session(), ExternalConnectionPolicy("development", frozenset({"localhost"}), (), frozenset({5432}), "disable", None), request, runtime(),
            )
        self.assertIs(updated, result)
        self.assertEqual(updated.almacenamiento.estado, "error")
        self.assertTrue(updated.actividades[0].evidencias)
        self.assertEqual(updated.actividades[0].redaccion_ia.tipo_error, 'error_interno')
        self.assertIn('guardado', updated.actividades[0].redaccion_ia.mensaje)
        self.assertEqual(updated.resumen.automatizadas, 1)
        self.assertEqual(save.call_args.args[1:3], (7, "audited_test"))
        self.assertNotIn(connection.password.get_secret_value(), str(save.call_args.args[2:]))
