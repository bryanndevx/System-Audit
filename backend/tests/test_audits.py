import secrets
import unittest
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException, Response
from psycopg import errors

from app.audit_engine import (
    AUDIT_CATALOG_VERSION,
    ChecklistActivityReference,
    execute_audit_activities,
)
from app.audit_queries import (
    DATABASE_SIZE_SQL,
    DATABASE_STATISTICS_CONTEXT_SQL,
    EVENT_TRIGGER_INVENTORY_SQL,
    ROUTINE_DEPENDENCIES_SQL,
    ROUTINE_INVENTORY_SQL,
    TABLE_COLUMNS_SQL,
    TABLE_CONSTRAINTS_SQL,
    TABLE_INVENTORY_SQL,
    TABLE_TRIGGER_INVENTORY_SQL,
    TABLE_VOLUMETRY_SQL,
    USER_SCHEMAS_SQL,
    VIEW_DEPENDENCIES_SQL,
    VIEW_INVENTORY_SQL,
)
from app.audits import (
    AuditExecutionRequest,
    execute_audit,
    parse_audit_execution_request,
)
from app.external_connections import (
    SET_TRANSACTION_READ_ONLY_SQL,
    ExternalConnectionPolicy,
    ExternalConnectionRequest,
)
from app.sessions import AuthenticatedSession


def activity(number: str, name: str = "Actividad") -> ChecklistActivityReference:
    return ChecklistActivityReference(
        numero=number,
        actividad=name,
        fase="Fase técnica",
    )


def connection_request() -> ExternalConnectionRequest:
    return ExternalConnectionRequest(
        host="localhost",
        port=5432,
        database="audit_test",
        username="audit_reader",
        password=secrets.token_urlsafe(18),
    )


def policy() -> ExternalConnectionPolicy:
    return ExternalConnectionPolicy(
        environment="development",
        allowed_hosts=frozenset({"localhost"}),
        allowed_networks=(),
        allowed_ports=frozenset({5432}),
        ssl_mode="disable",
        ssl_root_cert=None,
    )


def session() -> AuthenticatedSession:
    return AuthenticatedSession(
        user_id=1,
        username="test_user",
        csrf_token=secrets.token_urlsafe(32),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def volume_row(
    oid: int,
    name: str,
    relkind: str,
    *,
    parent_oid: int | None = None,
    data_bytes: int | None = 100,
    index_bytes: int | None = 20,
    total_bytes: int | None = 120,
    has_select: bool = True,
):
    return (
        oid,
        "aplicacion",
        name,
        f"aplicacion.{name}",
        relkind,
        parent_oid is not None,
        parent_oid,
        data_bytes,
        index_bytes,
        total_bytes,
        10,
        1,
        10,
        0,
        0,
        None,
        None,
        None,
        None,
        True,
        has_select,
    )


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False

    async def execute(self, statement):
        self.connection.executed.append(statement)
        if statement == SET_TRANSACTION_READ_ONLY_SQL:
            return
        response = self.connection.responses[statement]
        if isinstance(response, BaseException):
            raise response
        self.rows = response

    async def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, responses):
        self.responses = responses
        self.executed = []
        self.rollback_count = 0

    def cursor(self):
        return FakeCursor(self)

    async def rollback(self):
        self.rollback_count += 1


def successful_responses():
    return {
        USER_SCHEMAS_SQL: [(10, "aplicacion", True)],
        TABLE_INVENTORY_SQL: [
            (20, "aplicacion", "clientes", "aplicacion.clientes", "r", False, None, True, True)
        ],
        DATABASE_SIZE_SQL: [(4096,)],
        DATABASE_STATISTICS_CONTEXT_SQL: [(True, None)],
        TABLE_VOLUMETRY_SQL: [volume_row(20, "clientes", "r")],
    }


class AuditEngineTests(unittest.IsolatedAsyncioTestCase):
    def test_catalog_queries_are_predefined_select_only_statements(self):
        statements = (
            USER_SCHEMAS_SQL,
            TABLE_INVENTORY_SQL,
            DATABASE_SIZE_SQL,
            DATABASE_STATISTICS_CONTEXT_SQL,
            TABLE_VOLUMETRY_SQL,
            TABLE_COLUMNS_SQL,
            TABLE_CONSTRAINTS_SQL,
            VIEW_INVENTORY_SQL,
            VIEW_DEPENDENCIES_SQL,
            ROUTINE_INVENTORY_SQL,
            ROUTINE_DEPENDENCIES_SQL,
            TABLE_TRIGGER_INVENTORY_SQL,
            EVENT_TRIGGER_INVENTORY_SQL,
        )

        for statement in statements:
            normalized = " ".join(statement.upper().split())
            with self.subTest(statement=normalized[:50]):
                self.assertTrue(normalized.startswith("SELECT "))
                for forbidden_keyword in (
                    " INSERT ",
                    " UPDATE ",
                    " DELETE ",
                    " TRUNCATE ",
                    " ALTER ",
                    " CREATE ",
                    " DROP ",
                    " GRANT ",
                    " REVOKE ",
                ):
                    self.assertNotIn(forbidden_keyword, f" {normalized} ")

    async def test_executes_supported_activities_sequentially_in_checklist_order(self):
        connection = FakeConnection(successful_responses())

        result = await execute_audit_activities(
            connection,
            [activity("2.3", "Volumetría"), activity("2.1", "Inventario")],
        )

        self.assertEqual(result.catalogo_version, AUDIT_CATALOG_VERSION)
        self.assertEqual(
            [item.identificador for item in result.actividades],
            ["2.3", "2.1"],
        )
        executed_queries = [
            statement
            for statement in connection.executed
            if statement != SET_TRANSACTION_READ_ONLY_SQL
        ]
        self.assertEqual(
            executed_queries,
            [
                DATABASE_SIZE_SQL,
                DATABASE_STATISTICS_CONTEXT_SQL,
                TABLE_VOLUMETRY_SQL,
                USER_SCHEMAS_SQL,
                TABLE_INVENTORY_SQL,
            ],
        )

    async def test_inventory_keeps_tables_without_select_and_deduplicates_relations(self):
        responses = successful_responses()
        responses[USER_SCHEMAS_SQL] = [
            (10, "aplicacion", True),
            (11, "restringido", False),
        ]
        responses[TABLE_INVENTORY_SQL] = [
            (20, "aplicacion", "eventos", "aplicacion.eventos", "p", False, None, True, False),
            (21, "aplicacion", "eventos_2026", "aplicacion.eventos_2026", "r", True, "aplicacion.eventos", True, True),
            (21, "aplicacion", "eventos_2026", "aplicacion.eventos_2026", "r", True, "aplicacion.eventos", True, True),
        ]
        connection = FakeConnection(responses)

        result = await execute_audit_activities(connection, [activity("2.1")])

        activity_result = result.actividades[0]
        inventory = next(
            evidence for evidence in activity_result.evidencias if evidence.clave == "inventario_tablas"
        )
        self.assertEqual(inventory.datos["total_tablas"], 2)
        self.assertIn("sin permiso SELECT", " ".join(activity_result.advertencias))
        self.assertIn("sin permiso USAGE", " ".join(activity_result.advertencias))
        self.assertIn("metadatos visibles", " ".join(activity_result.limitaciones))

    async def test_partition_parent_has_separate_tree_aggregation(self):
        responses = successful_responses()
        responses[TABLE_VOLUMETRY_SQL] = [
            volume_row(30, "ventas", "p", data_bytes=0, index_bytes=0, total_bytes=0),
            volume_row(31, "ventas_2025", "r", parent_oid=30, data_bytes=100, index_bytes=20, total_bytes=120),
            volume_row(32, "ventas_2026", "r", parent_oid=30, data_bytes=200, index_bytes=40, total_bytes=240),
        ]
        connection = FakeConnection(responses)

        result = await execute_audit_activities(connection, [activity("2.3")])

        volumetry = next(
            evidence for evidence in result.actividades[0].evidencias if evidence.clave == "volumetria_actual_por_tabla"
        )
        parent = next(table for table in volumetry.datos["tablas"] if table["tabla"] == "ventas")
        self.assertEqual(parent["tamano_arbol_particiones"]["total_bytes"], 360)
        self.assertEqual(parent["tamano_arbol_particiones"]["particiones_fisicas"], 2)
        self.assertEqual(parent["total_bytes"], 0)

    async def test_failure_in_one_activity_preserves_other_activity_evidence(self):
        responses = successful_responses()
        responses[TABLE_INVENTORY_SQL] = errors.InsufficientPrivilege()
        connection = FakeConnection(responses)

        result = await execute_audit_activities(
            connection,
            [activity("2.1"), activity("2.3")],
        )

        self.assertEqual(result.actividades[0].estado_ejecucion, "parcial")
        self.assertEqual(result.actividades[1].estado_ejecucion, "completada")
        self.assertTrue(result.actividades[1].evidencias)

    async def test_similar_title_does_not_select_a_catalog_activity(self):
        connection = FakeConnection({})

        result = await execute_audit_activities(
            connection,
            [activity("9.9", "Listar tablas agrupadas por esquema")],
        )

        self.assertEqual(
            result.actividades[0].estado_ejecucion,
            "sin_automatizacion_configurada",
        )
        self.assertEqual(connection.executed, [])

    async def test_empty_inventory_is_valid_and_not_a_technical_error(self):
        responses = successful_responses()
        responses[USER_SCHEMAS_SQL] = []
        responses[TABLE_INVENTORY_SQL] = []
        connection = FakeConnection(responses)

        result = await execute_audit_activities(connection, [activity("2.1")])

        self.assertEqual(result.actividades[0].estado_ejecucion, "completada")
        self.assertEqual(result.actividades[0].estado_evidencia, "sin_datos")

    async def test_growth_is_separate_and_explicitly_unavailable(self):
        connection = FakeConnection(successful_responses())

        result = await execute_audit_activities(connection, [activity("2.3")])

        activity_result = result.actividades[0]
        growth = next(
            evidence for evidence in activity_result.evidencias if evidence.clave == "crecimiento_historico"
        )
        self.assertEqual(growth.disponibilidad, "no_disponible")
        self.assertEqual(
            growth.datos["mensaje"],
            "Historial de crecimiento no disponible",
        )
        self.assertEqual(activity_result.estado_evidencia, "insuficiente")

    async def test_audit_table_candidates_separate_indications_from_confirmation(self):
        responses = {
            TABLE_INVENTORY_SQL: [
                (100, "audit_meta", "audit_log", "audit_meta.audit_log", "r", False, None, True, True),
                (101, "audit_meta", "customers", "audit_meta.customers", "r", False, None, True, True),
                (102, "audit_meta", "trace_archive", "audit_meta.trace_archive", "r", False, None, True, False),
            ],
            TABLE_COLUMNS_SQL: [
                (100, "audit_meta", "audit_log", "audit_meta.audit_log", 1, "event_at", "timestamp with time zone", True),
                (100, "audit_meta", "audit_log", "audit_meta.audit_log", 2, "actor_id", "bigint", False),
                (100, "audit_meta", "audit_log", "audit_meta.audit_log", 3, "action", "text", True),
                (101, "audit_meta", "customers", "audit_meta.customers", 1, "id", "bigint", True),
                (102, "audit_meta", "trace_archive", "audit_meta.trace_archive", 1, "id", "bigint", True),
            ],
            TABLE_CONSTRAINTS_SQL: [
                (100, 200, "audit_log_event_key", "u", ["event_at", "actor_id"]),
                (101, 201, "customers_pkey", "p", ["id"]),
                (102, 202, "trace_archive_pkey", "p", ["id"]),
            ],
        }
        connection = FakeConnection(responses)

        result = await execute_audit_activities(connection, [activity("2.6")])

        activity_result = result.actividades[0]
        evidence = activity_result.evidencias[0].datos
        candidates = {item["tabla"]: item for item in evidence["candidatas"]}
        self.assertEqual(set(candidates), {"audit_log", "trace_archive"})
        self.assertEqual(
            candidates["audit_log"]["clasificacion_indicios"], "sustentada"
        )
        self.assertEqual(
            candidates["trace_archive"]["clasificacion_indicios"], "probable"
        )
        self.assertFalse(candidates["audit_log"]["funcion_confirmada"])
        self.assertEqual(evidence["total_funcion_confirmada"], 0)
        self.assertIn("no confirma", " ".join(activity_result.limitaciones))
        self.assertIn("sin permiso SELECT", " ".join(activity_result.advertencias))

    async def test_audit_table_candidate_metadata_failure_is_partial(self):
        responses = {
            TABLE_INVENTORY_SQL: [
                (100, "audit_meta", "audit_log", "audit_meta.audit_log", "r", False, None, True, True)
            ],
            TABLE_COLUMNS_SQL: errors.InsufficientPrivilege(),
            TABLE_CONSTRAINTS_SQL: [],
        }
        connection = FakeConnection(responses)

        result = await execute_audit_activities(connection, [activity("2.6")])

        self.assertEqual(result.actividades[0].estado_ejecucion, "parcial")
        self.assertEqual(result.actividades[0].estado_evidencia, "insuficiente")
        self.assertIn("falta de permisos", " ".join(result.actividades[0].advertencias))

    async def test_empty_view_inventory_is_valid(self):
        connection = FakeConnection(
            {VIEW_INVENTORY_SQL: [], VIEW_DEPENDENCIES_SQL: []}
        )

        result = await execute_audit_activities(connection, [activity("2.7")])

        activity_result = result.actividades[0]
        self.assertEqual(activity_result.estado_ejecucion, "completada")
        self.assertEqual(activity_result.estado_evidencia, "sin_datos")
        self.assertEqual(activity_result.evidencias[0].disponibilidad, "sin_datos")

    async def test_view_inventory_reports_inaccessible_metadata_and_dependencies(self):
        responses = {
            VIEW_INVENTORY_SQL: [
                (300, "audit_meta", "event_summary", "audit_meta.event_summary", "v", True, None, None, False, False),
                (301, "audit_meta", "daily_events", "audit_meta.daily_events", "m", False, "SELECT 1", "Resumen técnico", True, True),
            ],
            VIEW_DEPENDENCIES_SQL: [
                (301, 100, "audit_meta", "audit_log", "audit_meta.audit_log", "r", False),
                (301, 100, "audit_meta", "audit_log", "audit_meta.audit_log", "r", False),
            ],
        }
        connection = FakeConnection(responses)

        result = await execute_audit_activities(connection, [activity("2.7")])

        activity_result = result.actividades[0]
        evidence = activity_result.evidencias[0].datos
        materialized = next(
            item for item in evidence["vistas"] if item["nombre"] == "daily_events"
        )
        self.assertFalse(evidence["inventario_completo_verificable"])
        self.assertEqual(activity_result.estado_evidencia, "insuficiente")
        self.assertEqual(len(materialized["dependencias_relacionales"]), 1)
        self.assertIsNone(materialized["proposito_funcional_inferido"])
        self.assertIn("definición", " ".join(activity_result.advertencias))
        self.assertIn("sin permiso USAGE", " ".join(activity_result.advertencias))

    async def test_programmable_inventory_does_not_include_routine_bodies(self):
        responses = {
            ROUTINE_INVENTORY_SQL: [
                (400, "audit_meta", "normalize_event", "audit_meta.normalize_event", "f", "sql", "value integer", "integer", False, "i", "s", True, None),
                (401, "audit_meta", "refresh_summary", "audit_meta.refresh_summary", "p", "plpgsql", "", None, True, "v", "u", False, "fixture_extension"),
            ],
            ROUTINE_DEPENDENCIES_SQL: [
                (400, "n", "pg_type", "type integer"),
                (400, "n", "pg_type", "type integer"),
            ],
            TABLE_TRIGGER_INVENTORY_SQL: [
                (500, "audit_meta", "audit_log", "audit_meta.audit_log", "audit_log_before", 23, "D", False, 0, None, "audit_meta", "normalize_event", "value integer", None),
            ],
            EVENT_TRIGGER_INVENTORY_SQL: [
                (501, "ddl_audit", "ddl_command_end", "O", ["CREATE TABLE"], "audit_meta", "normalize_event", "value integer", None),
            ],
        }
        connection = FakeConnection(responses)

        result = await execute_audit_activities(connection, [activity("2.8")])

        activity_result = result.actividades[0]
        evidence = activity_result.evidencias[0].datos
        function = next(
            item for item in evidence["rutinas"] if item["nombre"] == "normalize_event"
        )
        procedure = next(
            item for item in evidence["rutinas"] if item["nombre"] == "refresh_summary"
        )
        relation_trigger = next(
            item for item in evidence["triggers"] if item["clase"] == "trigger_relacion"
        )
        self.assertEqual(function["tipo"], "funcion")
        self.assertEqual(len(function["dependencias_catalogadas"]), 1)
        self.assertEqual(procedure["tipo"], "procedimiento")
        self.assertEqual(procedure["origen"], "extension")
        self.assertEqual(relation_trigger["eventos"], ["insert", "update"])
        self.assertEqual(relation_trigger["momento"], "before")
        self.assertEqual(relation_trigger["nivel"], "fila")
        self.assertEqual(relation_trigger["estado"], "deshabilitado")
        self.assertNotIn("cuerpo", repr(evidence).lower())
        self.assertNotIn("prosrc", repr(evidence).lower())

    async def test_programmable_inventory_preserves_evidence_when_one_query_fails(self):
        responses = {
            ROUTINE_INVENTORY_SQL: [],
            ROUTINE_DEPENDENCIES_SQL: errors.InsufficientPrivilege(),
            TABLE_TRIGGER_INVENTORY_SQL: [],
            EVENT_TRIGGER_INVENTORY_SQL: [],
        }
        connection = FakeConnection(responses)

        result = await execute_audit_activities(connection, [activity("2.8")])

        activity_result = result.actividades[0]
        self.assertEqual(activity_result.estado_ejecucion, "parcial")
        self.assertEqual(activity_result.estado_evidencia, "insuficiente")
        self.assertFalse(
            activity_result.evidencias[0].datos["inventario_completo_verificable"]
        )
        self.assertIn("dependencias", " ".join(activity_result.advertencias))

    async def test_programmable_inventory_uses_existing_no_obtenida_state(self):
        failure = errors.InsufficientPrivilege()
        connection = FakeConnection(
            {
                ROUTINE_INVENTORY_SQL: failure,
                ROUTINE_DEPENDENCIES_SQL: failure,
                TABLE_TRIGGER_INVENTORY_SQL: failure,
                EVENT_TRIGGER_INVENTORY_SQL: failure,
            }
        )

        result = await execute_audit_activities(connection, [activity("2.8")])

        activity_result = result.actividades[0]
        self.assertEqual(activity_result.estado_ejecucion, "error_tecnico")
        self.assertEqual(activity_result.estado_evidencia, "no_obtenida")
        self.assertEqual(activity_result.evidencias, [])


class AuditEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_request_does_not_echo_password(self):
        password = secrets.token_urlsafe(800)
        request = AsyncMock()
        request.json.return_value = {
            "conexion": {
                "host": "localhost",
                "port": 5432,
                "database": "audit_test",
                "username": "audit_reader",
                "password": password,
            },
            "actividades": [],
        }

        with self.assertRaises(HTTPException) as context:
            await parse_audit_execution_request(request)

        self.assertEqual(context.exception.status_code, 422)
        self.assertNotIn(password, context.exception.detail)

    def test_request_representation_redacts_password(self):
        request = AuditExecutionRequest(
            conexion=connection_request(),
            actividades=[activity("2.1")],
        )

        self.assertNotIn(
            request.conexion.password.get_secret_value(),
            repr(request),
        )

    async def test_endpoint_uses_verified_connection_and_disables_caching(self):
        connection = FakeConnection(successful_responses())

        @asynccontextmanager
        async def open_connection(*args, **kwargs):
            self.assertEqual(kwargs["application_name"], "sistema_auditoria_engine")
            yield connection

        response = Response()
        request = AuditExecutionRequest(
            conexion=connection_request(),
            actividades=[activity("2.1")],
        )
        with patch(
            "app.audits.open_verified_external_connection",
            open_connection,
        ):
            result = await execute_audit(
                response=response,
                authenticated_session=session(),
                policy=policy(),
                execution_request=request,
            )

        self.assertEqual(result.actividades[0].estado_ejecucion, "completada")
        self.assertEqual(response.headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
