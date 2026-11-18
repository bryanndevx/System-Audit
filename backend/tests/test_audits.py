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
    ACTIVE_QUERY_SNAPSHOT_SQL,
    COLUMN_CHECK_CONSTRAINTS_SQL,
    COLUMN_DICTIONARY_SQL,
    DATABASE_SIZE_SQL,
    DATABASE_STATISTICS_CONTEXT_SQL,
    DOMAIN_CONSTRAINTS_SQL,
    ENUM_VALUES_SQL,
    EVENT_TRIGGER_INVENTORY_SQL,
    INDEX_INVENTORY_SQL,
    KEY_CONSTRAINT_PROPERTIES_SQL,
    PARTITION_CONFIGURATION_SQL,
    QUERY_OBSERVABILITY_SQL,
    ROUTINE_DEPENDENCIES_SQL,
    ROUTINE_INVENTORY_SQL,
    TABLE_COLUMNS_SQL,
    TABLE_COMMENTS_SQL,
    TABLE_CONSTRAINTS_SQL,
    TABLE_FOREIGN_KEYS_SQL,
    TABLE_INVENTORY_SQL,
    TABLE_RELATION_PROPERTIES_SQL,
    TABLE_ROUTINE_DEPENDENCIES_SQL,
    TABLE_TRIGGER_INVENTORY_SQL,
    TABLE_USAGE_STATISTICS_SQL,
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
from app.sessions import AuthenticatedSession, AuthConfig
from app.auth import AuthRuntimeConfig
from app.internal_db import InternalDatabaseConfig


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


def column_dictionary_row(
    oid: int,
    table: str,
    position: int,
    column: str,
    formatted_type: str,
    *,
    type_oid: int = 23,
    type_modifier: int = -1,
    not_null: bool = False,
    default_expression: str | None = None,
    identity_kind: str = "",
    generated_kind: str = "",
    type_schema: str = "pg_catalog",
    type_name: str = "int4",
    type_kind: str = "b",
    domain_base_type: str | None = None,
    comment: str | None = None,
):
    return (
        oid,
        "aplicacion",
        table,
        f"aplicacion.{table}",
        "r",
        position,
        column,
        formatted_type,
        type_oid,
        type_modifier,
        not_null,
        default_expression,
        identity_kind,
        generated_kind,
        type_schema,
        type_name,
        type_kind,
        domain_base_type,
        None,
        None,
        comment,
        True,
        0,
        True,
        True,
    )


def index_inventory_row(
    table_oid: int,
    table: str,
    index_oid: int,
    index: str,
    key_columns: list[str | None],
    *,
    key_elements: list[str] | None = None,
    included_columns: list[str | None] | None = None,
    primary: bool = False,
    unique: bool = False,
    predicate: str | None = None,
    scan_count: int | None = 0,
):
    included = included_columns or []
    return (
        table_oid,
        "aplicacion",
        table,
        f"aplicacion.{table}",
        index_oid,
        index,
        "btree",
        primary,
        unique,
        False,
        True,
        True,
        True,
        len(key_columns),
        len(key_columns) + len(included),
        key_columns,
        key_elements or [column or "expresion" for column in key_columns],
        included,
        predicate,
        None,
        8192,
        scan_count,
        None,
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

    async def fetchmany(self, size):
        return self.rows[:size]


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
            COLUMN_DICTIONARY_SQL,
            COLUMN_CHECK_CONSTRAINTS_SQL,
            DOMAIN_CONSTRAINTS_SQL,
            ENUM_VALUES_SQL,
            INDEX_INVENTORY_SQL,
            KEY_CONSTRAINT_PROPERTIES_SQL,
            TABLE_VOLUMETRY_SQL,
            TABLE_COLUMNS_SQL,
            TABLE_COMMENTS_SQL,
            TABLE_CONSTRAINTS_SQL,
            TABLE_FOREIGN_KEYS_SQL,
            TABLE_RELATION_PROPERTIES_SQL,
            TABLE_ROUTINE_DEPENDENCIES_SQL,
            VIEW_INVENTORY_SQL,
            VIEW_DEPENDENCIES_SQL,
            ROUTINE_INVENTORY_SQL,
            ROUTINE_DEPENDENCIES_SQL,
            TABLE_TRIGGER_INVENTORY_SQL,
            TABLE_USAGE_STATISTICS_SQL,
            EVENT_TRIGGER_INVENTORY_SQL,
            QUERY_OBSERVABILITY_SQL,
            ACTIVE_QUERY_SNAPSHOT_SQL,
            PARTITION_CONFIGURATION_SQL,
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

    async def test_table_classification_is_conservative_and_keeps_ambiguity(self):
        responses = {
            TABLE_INVENTORY_SQL: [
                (100, "app", "sales_transaction", "app.sales_transaction", "r", False, None, True, True),
                (101, "app", "customer_master", "app.customer_master", "r", False, None, True, True),
                (102, "staging", "audit_stage", "staging.audit_stage", "r", False, None, True, True),
            ],
            TABLE_COLUMNS_SQL: [
                (100, "app", "sales_transaction", "app.sales_transaction", 1, "id", "bigint", True),
                (100, "app", "sales_transaction", "app.sales_transaction", 2, "customer_id", "bigint", True),
                (100, "app", "sales_transaction", "app.sales_transaction", 3, "status_id", "bigint", True),
                (100, "app", "sales_transaction", "app.sales_transaction", 4, "created_at", "timestamp with time zone", True),
                (101, "app", "customer_master", "app.customer_master", 1, "id", "bigint", True),
                (102, "staging", "audit_stage", "staging.audit_stage", 1, "event_at", "timestamp with time zone", True),
            ],
            TABLE_CONSTRAINTS_SQL: [
                (100, 1000, "sales_transaction_pkey", "p", ["id"]),
                (
                    100,
                    1004,
                    "sales_transaction_created_at_not_null",
                    "n",
                    ["created_at"],
                ),
                (101, 1001, "customer_master_pkey", "p", ["id"]),
            ],
            TABLE_FOREIGN_KEYS_SQL: [
                (2000, 100, 101, "sales_customer_fk", "app.sales_transaction", "app.customer_master", ["customer_id"], ["id"], "a", "a"),
                (2001, 100, 103, "sales_status_fk", "app.sales_transaction", "app.status_catalog", ["status_id"], ["id"], "a", "a"),
            ],
            TABLE_RELATION_PROPERTIES_SQL: [(100, "p"), (101, "p"), (102, "u")],
        }
        connection = FakeConnection(responses)

        result = await execute_audit_activities(connection, [activity("2.2")])

        activity_result = result.actividades[0]
        matrix = {
            item["tabla"]: item
            for item in activity_result.evidencias[0].datos["tablas"]
        }
        self.assertEqual(
            matrix["sales_transaction"]["clasificacion_tecnica"],
            "transaccional",
        )
        self.assertEqual(matrix["customer_master"]["clasificacion_tecnica"], "maestra")
        self.assertEqual(matrix["audit_stage"]["clasificacion_tecnica"], "indeterminada")
        self.assertEqual(
            matrix["audit_stage"]["categorias_alternativas"],
            ["auditoria", "temporal_staging"],
        )
        self.assertFalse(
            matrix["sales_transaction"]["clasificacion_empresarial_confirmada"]
        )
        self.assertEqual(activity_result.estado_ejecucion, "completada")
        self.assertEqual(activity_result.estado_evidencia, "insuficiente")

    async def test_table_classification_preserves_partial_evidence(self):
        connection = FakeConnection(
            {
                TABLE_INVENTORY_SQL: [
                    (100, "app", "unknown", "app.unknown", "r", False, None, True, True)
                ],
                TABLE_COLUMNS_SQL: errors.InsufficientPrivilege(),
                TABLE_CONSTRAINTS_SQL: [],
                TABLE_FOREIGN_KEYS_SQL: [],
                TABLE_RELATION_PROPERTIES_SQL: [(100, "p")],
            }
        )

        result = await execute_audit_activities(connection, [activity("2.2")])

        self.assertEqual(result.actividades[0].estado_ejecucion, "parcial")
        self.assertEqual(result.actividades[0].estado_evidencia, "insuficiente")
        self.assertTrue(result.actividades[0].evidencias)

    async def test_partition_inherits_parent_classification(self):
        connection = FakeConnection(
            {
                TABLE_INVENTORY_SQL: [
                    (100, "app", "sales_transaction", "app.sales_transaction", "p", False, None, True, True),
                    (101, "app", "sales_transaction_2026", "app.sales_transaction_2026", "r", True, "app.sales_transaction", True, True),
                ],
                TABLE_COLUMNS_SQL: [
                    (100, "app", "sales_transaction", "app.sales_transaction", 1, "customer_id", "bigint", True),
                    (100, "app", "sales_transaction", "app.sales_transaction", 2, "status_id", "bigint", True),
                    (100, "app", "sales_transaction", "app.sales_transaction", 3, "created_at", "timestamp with time zone", True),
                ],
                TABLE_CONSTRAINTS_SQL: [],
                TABLE_FOREIGN_KEYS_SQL: [
                    (2000, 100, 200, "sales_customer_fk", "app.sales_transaction", "app.customer", ["customer_id"], ["id"], "a", "a"),
                    (2001, 100, 201, "sales_status_fk", "app.sales_transaction", "app.status", ["status_id"], ["id"], "a", "a"),
                ],
                TABLE_RELATION_PROPERTIES_SQL: [(100, "p"), (101, "p")],
            }
        )

        result = await execute_audit_activities(connection, [activity("2.2")])

        tables = {
            item["tabla"]: item for item in result.actividades[0].evidencias[0].datos["tablas"]
        }
        self.assertEqual(
            tables["sales_transaction_2026"]["clasificacion_tecnica"],
            tables["sales_transaction"]["clasificacion_tecnica"],
        )
        self.assertEqual(
            tables["sales_transaction_2026"]["nivel_sustento"],
            "heredada_de_padre",
        )

    async def test_zero_usage_is_not_automatically_a_retirement_candidate(self):
        usage_row = (
            100, "app", "legacy_table", "app.legacy_table", "r", False, None,
            0, 0, 0, 0, 0, 0, 0, None, None, None, None,
        )
        connection = FakeConnection(
            {
                TABLE_INVENTORY_SQL: [
                    (100, "app", "legacy_table", "app.legacy_table", "r", False, None, True, True)
                ],
                DATABASE_STATISTICS_CONTEXT_SQL: [(True, datetime.now(UTC) - timedelta(days=30))],
                TABLE_USAGE_STATISTICS_SQL: [usage_row],
                TABLE_FOREIGN_KEYS_SQL: [],
                VIEW_DEPENDENCIES_SQL: [],
                TABLE_TRIGGER_INVENTORY_SQL: [],
                TABLE_ROUTINE_DEPENDENCIES_SQL: [],
            }
        )

        result = await execute_audit_activities(connection, [activity("2.4")])

        activity_result = result.actividades[0]
        evaluation = next(
            item for item in activity_result.evidencias
            if item.clave == "evaluacion_uso_y_dependencias"
        ).datos
        table = evaluation["tablas"][0]
        self.assertEqual(table["estado_uso"], "evidencia_de_uso_no_concluyente")
        self.assertFalse(table["ventana_representativa"])
        self.assertFalse(table["candidata_baja"])
        self.assertEqual(evaluation["candidatas_baja"], [])
        self.assertEqual(evaluation["tablas_para_revision"][0]["estado"], "requiere_revision")
        self.assertEqual(activity_result.estado_evidencia, "insuficiente")

    async def test_partition_activity_is_aggregated_into_parent(self):
        connection = FakeConnection(
            {
                TABLE_INVENTORY_SQL: [
                    (100, "app", "events", "app.events", "p", False, None, True, True),
                    (101, "app", "events_2026", "app.events_2026", "r", True, "app.events", True, True),
                ],
                DATABASE_STATISTICS_CONTEXT_SQL: [(True, datetime.now(UTC) - timedelta(days=30))],
                TABLE_USAGE_STATISTICS_SQL: [
                    (100, "app", "events", "app.events", "p", False, None, 0, 0, 0, 0, 0, 0, 0, None, None, None, None),
                    (101, "app", "events_2026", "app.events_2026", "r", True, 100, 1, 0, 0, 0, 0, 0, 0, None, None, None, None),
                ],
                TABLE_FOREIGN_KEYS_SQL: [],
                VIEW_DEPENDENCIES_SQL: [],
                TABLE_TRIGGER_INVENTORY_SQL: [],
                TABLE_ROUTINE_DEPENDENCIES_SQL: [],
            }
        )

        result = await execute_audit_activities(connection, [activity("2.4")])

        evaluation = next(
            item for item in result.actividades[0].evidencias
            if item.clave == "evaluacion_uso_y_dependencias"
        ).datos
        parent = next(item for item in evaluation["tablas"] if item["tabla"] == "events")
        self.assertEqual(parent["estado_uso"], "actividad_observada")
        self.assertEqual(parent["contadores_con_particiones"]["seq_scan"], 1)
        self.assertFalse(parent["candidata_baja"])

    async def test_table_module_matrix_deduplicates_technical_relationships(self):
        connection = FakeConnection(
            {
                TABLE_INVENTORY_SQL: [
                    (100, "app", "orders", "app.orders", "r", False, None, True, True),
                    (101, "app", "customers", "app.customers", "r", False, None, True, True),
                ],
                TABLE_FOREIGN_KEYS_SQL: [
                    (2000, 100, 101, "orders_customer_fk", "app.orders", "app.customers", ["customer_id"], ["id"], "a", "a"),
                ],
                VIEW_INVENTORY_SQL: [
                    (300, "app", "order_summary", "app.order_summary", "v", True, None, None, True, True),
                ],
                VIEW_DEPENDENCIES_SQL: [
                    (300, 100, "app", "orders", "app.orders", "r", False),
                    (300, 100, "app", "orders", "app.orders", "r", False),
                ],
                TABLE_TRIGGER_INVENTORY_SQL: [
                    (400, "app", "orders", "app.orders", "orders_before", 7, "O", False, 0, None, "app", "prepare_order", "", None),
                    (400, "app", "orders", "app.orders", "orders_before", 7, "O", False, 0, None, "app", "prepare_order", "", None),
                ],
                TABLE_COMMENTS_SQL: [
                    (100, "Tabla técnica de pedidos", 1, "id", None),
                    (101, None, 1, "id", None),
                ],
                TABLE_ROUTINE_DEPENDENCIES_SQL: [
                    (100, 500, "app", "summarize_orders", "", "n"),
                    (100, 500, "app", "summarize_orders", "", "n"),
                ],
            }
        )

        result = await execute_audit_activities(connection, [activity("2.5")])

        activity_result = result.actividades[0]
        matrix = {
            item["tabla"]: item
            for item in activity_result.evidencias[0].datos["tablas"]
        }
        orders = matrix["orders"]
        self.assertIsNone(orders["modulo_confirmado"])
        self.assertEqual(orders["estado_correspondencia"], "pendiente_validacion")
        self.assertEqual(orders["vistas_dependientes"], ["app.order_summary"])
        self.assertEqual(len(orders["triggers"]), 1)
        self.assertEqual(len(orders["rutinas_con_dependencia_catalogada"]), 1)
        self.assertEqual(orders["comentario_tabla"], "Tabla técnica de pedidos")
        self.assertEqual(activity_result.estado_ejecucion, "completada")
        self.assertEqual(activity_result.estado_evidencia, "insuficiente")

    async def test_table_module_matrix_keeps_evidence_after_partial_failure(self):
        connection = FakeConnection(
            {
                TABLE_INVENTORY_SQL: [
                    (100, "app", "orders", "app.orders", "r", False, None, True, True)
                ],
                TABLE_FOREIGN_KEYS_SQL: [],
                VIEW_INVENTORY_SQL: [],
                VIEW_DEPENDENCIES_SQL: [],
                TABLE_TRIGGER_INVENTORY_SQL: [],
                TABLE_COMMENTS_SQL: errors.InsufficientPrivilege(),
                TABLE_ROUTINE_DEPENDENCIES_SQL: [],
            }
        )

        result = await execute_audit_activities(connection, [activity("2.5")])

        activity_result = result.actividades[0]
        self.assertEqual(activity_result.estado_ejecucion, "parcial")
        self.assertEqual(activity_result.estado_evidencia, "insuficiente")
        self.assertEqual(
            activity_result.evidencias[0].datos["tablas"][0]["estado_correspondencia"],
            "pendiente_validacion",
        )

    async def test_column_dictionary_activities_use_catalog_metadata(self):
        columns = [
            column_dictionary_row(
                100,
                "orders",
                1,
                "id",
                "bigint",
                type_oid=20,
                type_name="int8",
                not_null=True,
                identity_kind="a",
            ),
            column_dictionary_row(
                100,
                "orders",
                2,
                "status",
                "aplicacion.order_status",
                type_oid=500,
                type_schema="aplicacion",
                type_name="order_status",
                type_kind="e",
            ),
            column_dictionary_row(
                100,
                "orders",
                3,
                "total",
                "numeric(12,2)",
                type_oid=1700,
                type_modifier=786438,
                type_name="numeric",
                generated_kind="s",
                default_expression="(quantity * unit_price)",
            ),
        ]
        connection = FakeConnection({COLUMN_DICTIONARY_SQL: columns})

        result = await execute_audit_activities(
            connection,
            [activity("3.1"), activity("3.2"), activity("3.3"), activity("3.5")],
        )

        self.assertEqual(
            [item.estado_evidencia for item in result.actividades],
            ["suficiente", "suficiente", "suficiente", "insuficiente"],
        )
        base = result.actividades[0].evidencias[0].datos
        self.assertEqual(base["total_campos"], 3)
        self.assertEqual(
            [field["orden"] for field in base["tablas"][0]["campos"]],
            [1, 2, 3],
        )
        types = result.actividades[1].evidencias[0].datos["tablas"][0]["campos"]
        self.assertEqual(types[2]["tipo_formateado"], "numeric(12,2)")
        required = result.actividades[2].evidencias[0].datos
        self.assertEqual(required["campos_obligatorios"], 1)
        self.assertEqual(required["campos_opcionales"], 2)
        generated = result.actividades[3].evidencias[0].datos
        self.assertEqual(generated["campos_generados"][0]["campo"], "total")
        self.assertEqual(generated["campos_identidad_contexto"][0]["campo"], "id")

    async def test_domain_activity_separates_technical_values_from_business_catalogs(self):
        columns = [
            column_dictionary_row(
                100,
                "orders",
                1,
                "status",
                "aplicacion.order_status",
                type_oid=500,
                type_schema="aplicacion",
                type_name="order_status",
                type_kind="e",
                default_expression="'new'::aplicacion.order_status",
            ),
            column_dictionary_row(
                100,
                "orders",
                2,
                "code",
                "aplicacion.positive_code",
                type_oid=501,
                type_schema="aplicacion",
                type_name="positive_code",
                type_kind="d",
                domain_base_type="integer",
            ),
        ]
        connection = FakeConnection(
            {
                COLUMN_DICTIONARY_SQL: columns,
                COLUMN_CHECK_CONSTRAINTS_SQL: [
                    (100, 600, "orders_code_check", "CHECK ((code > 0))", ["code"])
                ],
                DOMAIN_CONSTRAINTS_SQL: [
                    (501, "aplicacion", "positive_code", 601, "positive_code_check", "CHECK ((VALUE > 0))")
                ],
                ENUM_VALUES_SQL: [
                    (500, "aplicacion", "order_status", "new"),
                    (500, "aplicacion", "order_status", "closed"),
                ],
                TABLE_FOREIGN_KEYS_SQL: [
                    (700, 100, 101, "orders_catalog_fk", "aplicacion.orders", "aplicacion.status_catalog", ["status_id"], ["id"], "a", "a")
                ],
            }
        )

        result = await execute_audit_activities(connection, [activity("3.4")])

        activity_result = result.actividades[0]
        data = activity_result.evidencias[0].datos
        self.assertEqual(activity_result.estado_ejecucion, "completada")
        self.assertEqual(activity_result.estado_evidencia, "insuficiente")
        self.assertEqual(data["tipos_enum"][0]["valores"], ["new", "closed"])
        self.assertEqual(data["dominios_usados"][0]["dominio"], "positive_code")
        self.assertFalse(
            data["referencias_fk_posibles_catalogos"][0][
                "proposito_catalogo_confirmado"
            ]
        )
        self.assertEqual(data["cobertura_entregable"], "parcial")

    async def test_column_dictionary_keeps_partial_status_after_permission_failure(self):
        connection = FakeConnection({COLUMN_DICTIONARY_SQL: errors.InsufficientPrivilege()})

        result = await execute_audit_activities(connection, [activity("3.1")])

        self.assertEqual(result.actividades[0].estado_ejecucion, "error_tecnico")
        self.assertEqual(result.actividades[0].estado_evidencia, "no_obtenida")
        self.assertIn("falta de permisos", " ".join(result.actividades[0].advertencias))

    async def test_partial_column_analysis_does_not_confirm_business_meaning(self):
        columns = [
            column_dictionary_row(
                100,
                "users",
                1,
                "id",
                "bigint",
                not_null=True,
                default_expression="nextval('users_id_seq'::regclass)",
            ),
            column_dictionary_row(
                100,
                "users",
                2,
                "password_hash",
                "text",
                type_oid=25,
                type_name="text",
            ),
            column_dictionary_row(
                100,
                "users",
                3,
                "displayName",
                "text",
                type_oid=25,
                type_name="text",
            ),
            column_dictionary_row(
                100,
                "users",
                4,
                "legacy_code",
                "text",
                type_oid=25,
                type_name="text",
                comment="Deprecated; pendiente de validación funcional.",
            ),
        ]
        connection = FakeConnection(
            {
                COLUMN_DICTIONARY_SQL: columns,
                COLUMN_CHECK_CONSTRAINTS_SQL: [
                    (100, 600, "users_id_check", "CHECK ((id > 0))", ["id"])
                ],
                DOMAIN_CONSTRAINTS_SQL: [],
                ENUM_VALUES_SQL: [],
                TABLE_FOREIGN_KEYS_SQL: [],
            }
        )

        result = await execute_audit_activities(
            connection,
            [activity("3.6"), activity("3.7"), activity("3.8"), activity("3.9")],
        )

        self.assertEqual(
            [item.estado_ejecucion for item in result.actividades],
            ["completada"] * 4,
        )
        self.assertEqual(
            [item.estado_evidencia for item in result.actividades],
            ["insuficiente"] * 4,
        )
        rules = result.actividades[0].evidencias[0].datos
        self.assertTrue(rules["reglas_tecnicas_observables"])
        self.assertEqual(rules["reglas_empresariales_confirmadas"], 0)
        sensitive = result.actividades[1].evidencias[0].datos
        self.assertEqual(sensitive["campos_candidatos"][0]["campo"], "password_hash")
        self.assertFalse(
            sensitive["campos_candidatos"][0]["sensibilidad_confirmada"]
        )
        naming = result.actividades[2].evidencias[0].datos
        self.assertEqual(naming["total_snake_case_minusculas"], 3)
        self.assertFalse(naming["convencion_aprobada_disponible"])
        deprecated = result.actividades[3].evidencias[0].datos
        self.assertEqual(deprecated["campos_candidatos"][0]["campo"], "legacy_code")
        self.assertFalse(
            deprecated["campos_candidatos"][0]["deprecacion_confirmada"]
        )

    async def test_index_activities_keep_inventory_and_candidates_separate(self):
        indexes = [
            index_inventory_row(
                100,
                "orders",
                800,
                "orders_pkey",
                ["id"],
                primary=True,
                unique=True,
            ),
            index_inventory_row(
                100,
                "orders",
                801,
                "orders_customer_idx",
                ["customer_id"],
            ),
            index_inventory_row(
                100,
                "orders",
                802,
                "orders_customer_duplicate_idx",
                ["customer_id"],
            ),
            index_inventory_row(
                100,
                "orders",
                803,
                "orders_status_idx",
                ["status_id"],
            ),
            index_inventory_row(
                100,
                "orders",
                804,
                "orders_status_created_idx",
                ["status_id", "created_at"],
            ),
        ]
        foreign_keys = [
            (700, 100, 101, "orders_customer_fk", "aplicacion.orders", "aplicacion.customers", ["customer_id"], ["id"], "a", "a"),
            (701, 100, 102, "orders_product_fk", "aplicacion.orders", "aplicacion.products", ["product_id"], ["id"], "a", "a"),
        ]
        connection = FakeConnection(
            {
                INDEX_INVENTORY_SQL: indexes,
                TABLE_INVENTORY_SQL: [
                    (100, "aplicacion", "orders", "aplicacion.orders", "r", False, None, True, True),
                    (101, "aplicacion", "customers", "aplicacion.customers", "r", False, None, True, True),
                ],
                TABLE_CONSTRAINTS_SQL: [
                    (100, 900, "orders_pkey", "p", ["id"]),
                ],
                TABLE_FOREIGN_KEYS_SQL: foreign_keys,
                KEY_CONSTRAINT_PROPERTIES_SQL: [
                    (900, 100, "orders_pkey", "p", True, False, False),
                    (700, 100, "orders_customer_fk", "f", True, False, False),
                    (701, 100, "orders_product_fk", "f", True, False, False),
                ],
            }
        )

        result = await execute_audit_activities(
            connection,
            [activity("4.1"), activity("4.2"), activity("4.3"), activity("4.4")],
        )

        self.assertEqual(
            [item.estado_ejecucion for item in result.actividades],
            ["completada"] * 4,
        )
        self.assertEqual(
            [item.estado_evidencia for item in result.actividades],
            ["suficiente", "suficiente", "insuficiente", "insuficiente"],
        )
        inventory = result.actividades[0].evidencias[0].datos
        self.assertEqual(inventory["total_indices"], 5)
        keys = result.actividades[1].evidencias[0].datos
        self.assertEqual(keys["total_pk"], 1)
        self.assertEqual(keys["total_fk"], 2)
        self.assertTrue(keys["llaves_foraneas"][0]["validada"])
        redundant = result.actividades[2].evidencias[0].datos
        self.assertEqual(len(redundant["duplicados_exactos"]), 1)
        self.assertEqual(len(redundant["posibles_redundancias_prefijo"]), 1)
        self.assertEqual(redundant["eliminaciones_recomendadas"], [])
        missing = result.actividades[3].evidencias[0].datos
        self.assertEqual(
            [item["restriccion_fk"] for item in missing["fk_sin_indice_prefijo"]],
            ["orders_product_fk"],
        )
        self.assertFalse(missing["campos_busqueda_aplicacion_evaluados"])

    async def test_advanced_performance_activities_preserve_technical_limits(self):
        connection = FakeConnection(
            {
                QUERY_OBSERVABILITY_SQL: [
                    (True, True, "auto", None, False, None, False, False),
                ],
                ACTIVE_QUERY_SNAPSHOT_SQL: [
                    ("987654", "active", None, None, 1, 2500),
                ],
                INDEX_INVENTORY_SQL: [
                    index_inventory_row(
                        100,
                        "orders",
                        800,
                        "orders_tenant_created_idx",
                        ["tenant_id", "created_at"],
                        included_columns=["status_id"],
                    ),
                ],
                TABLE_VOLUMETRY_SQL: [
                    volume_row(
                        100,
                        "orders",
                        "r",
                        data_bytes=8192,
                        index_bytes=8192,
                        total_bytes=16384,
                    ),
                ],
                TABLE_FOREIGN_KEYS_SQL: [
                    (
                        700,
                        100,
                        101,
                        "orders_tenant_customer_fk",
                        "aplicacion.orders",
                        "aplicacion.customers",
                        ["tenant_id", "customer_id"],
                        ["tenant_id", "id"],
                        "a",
                        "a",
                    ),
                ],
                PARTITION_CONFIGURATION_SQL: [
                    (
                        200,
                        "aplicacion",
                        "events",
                        "aplicacion.events",
                        "r",
                        "RANGE (created_at)",
                        201,
                        "aplicacion",
                        "events_2026",
                        "aplicacion.events_2026",
                        "FOR VALUES FROM ('2026-01-01') TO ('2027-01-01')",
                        True,
                        True,
                    ),
                ],
            }
        )

        result = await execute_audit_activities(
            connection,
            [activity("4.5"), activity("4.6"), activity("4.7"), activity("4.8")],
        )

        self.assertEqual(
            [item.estado_ejecucion for item in result.actividades],
            ["completada"] * 4,
        )
        self.assertEqual(
            [item.estado_evidencia for item in result.actividades],
            ["insuficiente"] * 4,
        )

        query_analysis = result.actividades[0]
        query_snapshot = query_analysis.evidencias[1].datos
        self.assertFalse(query_snapshot["incluye_texto_sql"])
        self.assertFalse(query_snapshot["demuestra_frecuencia_historica"])
        self.assertEqual(query_snapshot["consultas_criticas_confirmadas"], [])
        self.assertNotIn("query_text", repr(query_analysis.evidencias).lower())

        maintenance = result.actividades[1].evidencias[0].datos
        self.assertFalse(maintenance["fragmentacion_exacta_disponible"])
        self.assertEqual(
            maintenance["acciones_rebuild_reorganize_recomendadas"],
            [],
        )

        compound_indexes = result.actividades[2].evidencias[0].datos
        self.assertEqual(
            len(compound_indexes["indices_compuestos_o_con_includes_existentes"]),
            1,
        )
        self.assertEqual(len(compound_indexes["candidatos_tecnicos"]), 1)
        self.assertFalse(
            compound_indexes["candidatos_tecnicos"][0]["propuesta_confirmada"]
        )
        self.assertEqual(compound_indexes["propuestas_indices_confirmadas"], [])

        partitioning = result.actividades[3].evidencias[0].datos
        self.assertEqual(partitioning["tablas_particionadas"][0]["estrategia"], "rango")
        self.assertEqual(
            partitioning["tablas_particionadas"][0]["particiones"][0]["tabla"],
            "events_2026",
        )
        self.assertFalse(partitioning["estrategia_futura_confirmada"])
        self.assertEqual(partitioning["candidatas_particionamiento_confirmadas"], [])

    async def test_advanced_performance_empty_results_are_not_technical_errors(self):
        connection = FakeConnection(
            {
                QUERY_OBSERVABILITY_SQL: [],
                ACTIVE_QUERY_SNAPSHOT_SQL: [],
                PARTITION_CONFIGURATION_SQL: [],
                TABLE_VOLUMETRY_SQL: [],
            }
        )

        result = await execute_audit_activities(
            connection,
            [activity("4.5"), activity("4.8")],
        )

        self.assertEqual(
            [item.estado_ejecucion for item in result.actividades],
            ["completada", "completada"],
        )
        self.assertEqual(
            [item.estado_evidencia for item in result.actividades],
            ["insuficiente", "insuficiente"],
        )
        self.assertEqual(
            result.actividades[0].evidencias[1].disponibilidad,
            "sin_datos",
        )
        self.assertEqual(
            result.actividades[1].evidencias[0].disponibilidad,
            "sin_datos",
        )

    async def test_data_model_activities_separate_metadata_from_business_claims(self):
        inventory = [
            (100, "aplicacion", "orders", "aplicacion.orders", "r", False, None, True, True),
            (101, "aplicacion", "customers", "aplicacion.customers", "r", False, None, True, True),
            (102, "aplicacion", "order_tags", "aplicacion.order_tags", "r", False, None, True, True),
            (103, "aplicacion", "tags", "aplicacion.tags", "r", False, None, True, True),
        ]
        columns = [
            (100, "aplicacion", "orders", "aplicacion.orders", 1, "id", "bigint", True),
            (100, "aplicacion", "orders", "aplicacion.orders", 2, "customer_id", "bigint", True),
            (100, "aplicacion", "orders", "aplicacion.orders", 3, "legacy_customer_id", "bigint", False),
            (101, "aplicacion", "customers", "aplicacion.customers", 1, "id", "bigint", True),
            (102, "aplicacion", "order_tags", "aplicacion.order_tags", 1, "order_id", "bigint", True),
            (102, "aplicacion", "order_tags", "aplicacion.order_tags", 2, "tag_id", "integer", True),
            (103, "aplicacion", "tags", "aplicacion.tags", 1, "id", "bigint", True),
        ]
        constraints = [
            (100, 800, "orders_pkey", "p", ["id"]),
            (101, 801, "customers_pkey", "p", ["id"]),
            (102, 802, "order_tags_pkey", "p", ["order_id", "tag_id"]),
            (103, 803, "tags_pkey", "p", ["id"]),
        ]
        foreign_keys = [
            (900, 100, 101, "orders_customer_fk", "aplicacion.orders", "aplicacion.customers", ["customer_id"], ["id"], "a", "a"),
            (901, 102, 100, "order_tags_order_fk", "aplicacion.order_tags", "aplicacion.orders", ["order_id"], ["id"], "a", "a"),
            (902, 102, 103, "order_tags_tag_fk", "aplicacion.order_tags", "aplicacion.tags", ["tag_id"], ["id"], "a", "a"),
        ]
        dictionary = [
            column_dictionary_row(
                100,
                "orders",
                1,
                "id",
                "bigint",
                type_oid=20,
                type_name="int8",
                identity_kind="d",
            ),
            column_dictionary_row(
                100,
                "orders",
                2,
                "customer_id",
                "bigint",
                type_oid=20,
                type_name="int8",
            ),
            column_dictionary_row(
                100,
                "orders",
                3,
                "legacy_customer_id",
                "bigint",
                type_oid=20,
                type_name="int8",
            ),
            column_dictionary_row(
                101,
                "customers",
                1,
                "id",
                "bigint",
                type_oid=20,
                type_name="int8",
                identity_kind="d",
            ),
            column_dictionary_row(
                102,
                "order_tags",
                1,
                "order_id",
                "bigint",
                type_oid=20,
                type_name="int8",
            ),
            column_dictionary_row(
                102,
                "order_tags",
                2,
                "tag_id",
                "integer",
                type_oid=23,
                type_name="int4",
            ),
            column_dictionary_row(
                103,
                "tags",
                1,
                "id",
                "bigint",
                type_oid=20,
                type_name="int8",
                identity_kind="d",
            ),
        ]
        connection = FakeConnection(
            {
                TABLE_INVENTORY_SQL: inventory,
                TABLE_COLUMNS_SQL: columns,
                TABLE_CONSTRAINTS_SQL: constraints,
                TABLE_FOREIGN_KEYS_SQL: foreign_keys,
                COLUMN_DICTIONARY_SQL: dictionary,
            }
        )

        result = await execute_audit_activities(
            connection,
            [activity(f"5.{number}") for number in range(1, 9)],
        )

        self.assertEqual(
            [item.estado_ejecucion for item in result.actividades],
            ["completada"] * 8,
        )
        self.assertEqual(
            [item.estado_evidencia for item in result.actividades],
            ["insuficiente"] * 7 + ["suficiente"],
        )

        er_model = result.actividades[0].evidencias[0].datos
        self.assertEqual(er_model["total_entidades"], 4)
        self.assertEqual(er_model["total_relaciones_fk"], 3)
        self.assertFalse(er_model["diagrama_visual_generado"])

        normalization = result.actividades[1].evidencias[0].datos
        self.assertEqual(normalization["violaciones_normalizacion_confirmadas"], [])

        missing_relations = result.actividades[2].evidencias[0].datos
        self.assertEqual(
            missing_relations["candidatas_revision"][0]["columna"],
            "legacy_customer_id",
        )
        self.assertFalse(
            missing_relations["candidatas_revision"][0][
                "relacion_huerfana_confirmada"
            ]
        )

        cardinality = result.actividades[3].evidencias[0].datos
        self.assertEqual(
            cardinality["relaciones"][0]["cardinalidad_estructural"],
            "muchos_a_uno",
        )
        self.assertEqual(len(cardinality["tablas_puente_probables"]), 1)

        modules = result.actividades[4].evidencias[0].datos
        self.assertFalse(modules["correspondencia_esquema_modulo_confirmada"])
        self.assertEqual(modules["inconsistencias_intermodulos_confirmadas"], [])

        bridges = result.actividades[5].evidencias[0].datos
        self.assertEqual(len(bridges["tablas_puente_probables_existentes"]), 1)
        self.assertEqual(bridges["tablas_puente_faltantes_confirmadas"], [])

        keys = result.actividades[6].evidencias[0].datos
        self.assertIn("identidad", keys["patrones_observados"])
        self.assertIn("compuesta", keys["patrones_observados"])
        self.assertFalse(keys["coherencia_normativa_confirmada"])

        type_consistency = result.actividades[7].evidencias[0].datos
        self.assertEqual(type_consistency["total_fk"], 3)
        self.assertEqual(type_consistency["total_fk_con_diferencias"], 1)
        self.assertEqual(
            type_consistency["diferencias_tipo_exacto"][0]["restriccion"],
            "order_tags_tag_fk",
        )

    async def test_audit_table_candidates_separate_indications_from_confirmation(self):
        responses = {
            TABLE_INVENTORY_SQL: [
                (100, "audit_meta", "audit_log", "audit_meta.audit_log", "r", False, None, True, True),
                (101, "audit_meta", "customers", "audit_meta.customers", "r", False, None, True, True),
                (102, "audit_meta", "trace_archive", "audit_meta.trace_archive", "r", False, None, True, False),
                (103, "audit_meta", "operations", "audit_meta.operations", "r", False, None, True, True),
            ],
            TABLE_COLUMNS_SQL: [
                (100, "audit_meta", "audit_log", "audit_meta.audit_log", 1, "event_at", "timestamp with time zone", True),
                (100, "audit_meta", "audit_log", "audit_meta.audit_log", 2, "actor_id", "bigint", False),
                (100, "audit_meta", "audit_log", "audit_meta.audit_log", 3, "action", "text", True),
                (101, "audit_meta", "customers", "audit_meta.customers", 1, "id", "bigint", True),
                (102, "audit_meta", "trace_archive", "audit_meta.trace_archive", 1, "id", "bigint", True),
                (103, "audit_meta", "operations", "audit_meta.operations", 1, "created_at", "timestamp with time zone", True),
            ],
            TABLE_CONSTRAINTS_SQL: [
                (100, 200, "audit_log_event_key", "u", ["event_at", "actor_id"]),
                (101, 201, "customers_pkey", "p", ["id"]),
                (102, 202, "trace_archive_pkey", "p", ["id"]),
                (103, 203, "operations_created_at_not_null", "n", ["created_at"]),
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


@patch("app.audits.acquire_ai_lock")
@patch("app.audits.update_audit_analysis", new=lambda config, owner, audit_id, result: result)
@patch("app.audits.get_saved_audit")
class AuditEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_audited_connection_is_closed_before_ai_redaction(self, read, lock):
        connection = FakeConnection(successful_responses())
        is_open = False

        @asynccontextmanager
        async def open_connection(*args, **kwargs):
            nonlocal is_open
            is_open = True
            try:
                yield connection
            finally:
                is_open = False

        async def redact(result, checkpoint=None):
            self.assertFalse(is_open)
            self.assertTrue(result.actividades[0].evidencias)
            return result

        from types import SimpleNamespace
        def save(config, owner, database, result):
            from app.audit_engine import AuditStorageInfo
            from uuid import uuid4
            result.almacenamiento = AuditStorageInfo(estado='guardada', id=uuid4())
            read.return_value = SimpleNamespace(resultado=result)
            return result

        with (
            patch("app.audits.open_verified_external_connection", open_connection),
            patch("app.audits.add_ai_narratives", side_effect=redact) as generate,
            patch("app.audits.save_audit", side_effect=save),
        ):
            await execute_audit(
                response=Response(), authenticated_session=session(), policy=policy(),
                runtime=AuthRuntimeConfig(
                    database=InternalDatabaseConfig("localhost", 5432, "internal", "test_operator", secrets.token_urlsafe(20)),
                    auth=AuthConfig("development", "http://localhost:5173", 480),
                ),
                execution_request=AuditExecutionRequest(
                    conexion=connection_request(), actividades=[activity("2.1")],
                ),
            )
        generate.assert_awaited_once()

    async def test_invalid_request_does_not_echo_password(self, read, lock):
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

    def test_request_representation_redacts_password(self, read, lock):
        request = AuditExecutionRequest(
            conexion=connection_request(),
            actividades=[activity("2.1")],
        )

        self.assertNotIn(
            request.conexion.password.get_secret_value(),
            repr(request),
        )

    @patch("app.ai_diagnostics.GeminiConfig.from_environment", return_value=None)
    async def test_endpoint_uses_verified_connection_and_disables_caching(self, config, read, lock):
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
        ), patch('app.audits.save_audit') as save:
            from types import SimpleNamespace
            def save_result(config, owner, database, current):
                from app.audit_engine import AuditStorageInfo
                from uuid import uuid4
                current.almacenamiento = AuditStorageInfo(estado='guardada', id=uuid4())
                read.return_value = SimpleNamespace(resultado=current)
                return current
            save.side_effect = save_result
            result = await execute_audit(
                response=response,
                authenticated_session=session(),
                policy=policy(),
                execution_request=request,
                runtime=AuthRuntimeConfig(
                    database=InternalDatabaseConfig("localhost", 5432, "internal", "test_operator", secrets.token_urlsafe(20)),
                    auth=AuthConfig("development", "http://localhost:5173", 480),
                ),
            )

        self.assertEqual(result.actividades[0].estado_ejecucion, "completada")
        self.assertEqual(response.headers["Cache-Control"], "no-store")


if __name__ == "__main__":
    unittest.main()
