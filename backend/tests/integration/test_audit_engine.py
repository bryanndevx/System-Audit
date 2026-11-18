import asyncio
import os
import unittest

from app.audit_engine import ChecklistActivityReference, execute_audit_activities
from app.event_loop import create_psycopg_compatible_event_loop
from app.external_connections import (
    ExternalConnectionPolicy,
    ExternalConnectionRequest,
    open_verified_external_connection,
)


@unittest.skipUnless(
    os.getenv("RUN_AUDIT_INTEGRATION") == "1",
    "La integración PostgreSQL requiere autorización y configuración explícitas.",
)
class AuditEngineIntegrationTests(unittest.TestCase):
    def test_inventory_and_volumetry_against_local_fixture(self):
        asyncio.run(
            self._run_inventory_and_volumetry(),
            loop_factory=create_psycopg_compatible_event_loop,
        )

    def test_metadata_activities_against_isolated_fixture(self):
        asyncio.run(
            self._run_metadata_activities(),
            loop_factory=create_psycopg_compatible_event_loop,
        )

    def test_table_analysis_activities_against_isolated_fixture(self):
        asyncio.run(
            self._run_table_analysis_activities(),
            loop_factory=create_psycopg_compatible_event_loop,
        )

    def test_column_dictionary_activities_against_isolated_fixture(self):
        asyncio.run(
            self._run_column_dictionary_activities(),
            loop_factory=create_psycopg_compatible_event_loop,
        )

    def test_index_activities_against_isolated_fixture(self):
        asyncio.run(
            self._run_index_activities(),
            loop_factory=create_psycopg_compatible_event_loop,
        )

    async def _run_inventory_and_volumetry(self):
        password = os.environ["AUDIT_TEST_PASSWORD"]
        host = os.getenv("AUDIT_TEST_HOST", "127.0.0.1")
        port = int(os.getenv("AUDIT_TEST_PORT", "5432"))
        request = ExternalConnectionRequest(
            host=host,
            port=port,
            database=os.getenv("AUDIT_TEST_DATABASE", "auditoria_prueba"),
            username=os.getenv("AUDIT_TEST_USER", "auditor_lectura"),
            password=password,
        )
        policy = ExternalConnectionPolicy(
            environment="development",
            allowed_hosts=frozenset({host}),
            allowed_networks=(),
            allowed_ports=frozenset({port}),
            ssl_mode="disable",
            ssl_root_cert=None,
        )
        activities = [
            ChecklistActivityReference(
                numero="2.1",
                actividad="Listar tablas agrupadas por esquema/módulo",
                fase="Arquitectura de datos",
            ),
            ChecklistActivityReference(
                numero="2.3",
                actividad="Volumetría y crecimiento",
                fase="Arquitectura de datos",
            ),
        ]

        async with open_verified_external_connection(
            request,
            policy,
            application_name="sistema_auditoria_integration_test",
        ) as connection:
            result = await execute_audit_activities(connection, activities)

        self.assertEqual(
            [activity.estado_ejecucion for activity in result.actividades],
            ["completada", "completada"],
        )
        inventory = next(
            evidence
            for evidence in result.actividades[0].evidencias
            if evidence.clave == "inventario_tablas"
        )
        fixture_schema = next(
            schema
            for schema in inventory.datos["esquemas"]
            if schema["esquema"] == "audit_fixture"
        )
        self.assertEqual(
            {table["tabla"] for table in fixture_schema["tablas"]},
            {
                "catalog_items",
                "technical_events",
                "technical_events_2025",
                "technical_events_2026",
            },
        )

        volumetry = next(
            evidence
            for evidence in result.actividades[1].evidencias
            if evidence.clave == "volumetria_actual_por_tabla"
        )
        partitioned_parent = next(
            table
            for table in volumetry.datos["tablas"]
            if table["nombre_completo"] == "audit_fixture.technical_events"
        )
        self.assertEqual(
            partitioned_parent["tamano_arbol_particiones"]["particiones_fisicas"],
            2,
        )

    async def _run_metadata_activities(self):
        password = os.environ["AUDIT_TEST_PASSWORD"]
        host = os.getenv("AUDIT_TEST_HOST", "127.0.0.1")
        port = int(os.getenv("AUDIT_TEST_PORT", "5432"))
        request = ExternalConnectionRequest(
            host=host,
            port=port,
            database=os.getenv("AUDIT_TEST_DATABASE", "auditoria_prueba"),
            username=os.getenv("AUDIT_TEST_USER", "auditor_lectura"),
            password=password,
        )
        policy = ExternalConnectionPolicy(
            environment="development",
            allowed_hosts=frozenset({host}),
            allowed_networks=(),
            allowed_ports=frozenset({port}),
            ssl_mode="disable",
            ssl_root_cert=None,
        )
        activities = [
            ChecklistActivityReference(
                numero="2.6",
                actividad="Identificar tablas de auditoría, log y trace",
                fase="Arquitectura de datos",
            ),
            ChecklistActivityReference(
                numero="2.7",
                actividad="Inventariar vistas y propósito",
                fase="Arquitectura de datos",
            ),
            ChecklistActivityReference(
                numero="2.8",
                actividad="Inventariar funciones, procedimientos y triggers",
                fase="Arquitectura de datos",
            ),
        ]

        async with open_verified_external_connection(
            request,
            policy,
            application_name="sistema_auditoria_metadata_integration_test",
        ) as connection:
            result = await execute_audit_activities(connection, activities)

        self.assertEqual(
            [activity.estado_ejecucion for activity in result.actividades],
            ["completada", "completada", "completada"],
        )
        candidates = next(
            evidence
            for evidence in result.actividades[0].evidencias
            if evidence.clave == "candidatas_auditoria_log_trace"
        )
        fixture_candidates = {
            table["nombre_completo"]: table
            for table in candidates.datos["candidatas"]
            if table["esquema"] == "audit_metadata_fixture"
        }
        self.assertIn(
            "audit_metadata_fixture.audit_event_log", fixture_candidates
        )
        self.assertEqual(
            fixture_candidates["audit_metadata_fixture.audit_event_log"][
                "clasificacion_indicios"
            ],
            "sustentada",
        )
        self.assertFalse(
            fixture_candidates["audit_metadata_fixture.audit_event_log"][
                "funcion_confirmada"
            ]
        )
        self.assertEqual(
            fixture_candidates["audit_metadata_fixture.trace_named_only"][
                "clasificacion_indicios"
            ],
            "probable",
        )

        views = next(
            evidence
            for evidence in result.actividades[1].evidencias
            if evidence.clave == "inventario_vistas"
        )
        fixture_views = {
            view["nombre_completo"]: view
            for view in views.datos["vistas"]
            if view["esquema"] == "audit_metadata_fixture"
        }
        self.assertEqual(
            fixture_views["audit_metadata_fixture.audit_event_summary"]["tipo"],
            "vista",
        )
        self.assertEqual(
            fixture_views["audit_metadata_fixture.audit_event_daily"]["tipo"],
            "vista_materializada",
        )
        self.assertFalse(
            fixture_views["audit_metadata_fixture.audit_event_daily"][
                "esta_poblada"
            ]
        )

        programmable = next(
            evidence
            for evidence in result.actividades[2].evidencias
            if evidence.clave == "inventario_objetos_programables"
        )
        fixture_routines = {
            (routine["nombre"], routine["tipo"])
            for routine in programmable.datos["rutinas"]
            if routine["esquema"] == "audit_metadata_fixture"
        }
        self.assertIn(("normalize_action", "funcion"), fixture_routines)
        self.assertIn(("fixture_noop", "procedimiento"), fixture_routines)
        fixture_triggers = [
            trigger
            for trigger in programmable.datos["triggers"]
            if trigger["relacion_completa"]
            == "audit_metadata_fixture.audit_event_log"
        ]
        self.assertTrue(
            any(
                trigger["nombre"] == "audit_event_log_before_insert"
                and trigger["estado"] == "deshabilitado"
                for trigger in fixture_triggers
            )
        )

    async def _run_table_analysis_activities(self):
        password = os.environ["AUDIT_TEST_PASSWORD"]
        host = os.getenv("AUDIT_TEST_HOST", "127.0.0.1")
        port = int(os.getenv("AUDIT_TEST_PORT", "5432"))
        request = ExternalConnectionRequest(
            host=host,
            port=port,
            database=os.getenv("AUDIT_TEST_DATABASE", "auditoria_prueba"),
            username=os.getenv("AUDIT_TEST_USER", "auditor_lectura"),
            password=password,
        )
        policy = ExternalConnectionPolicy(
            environment="development",
            allowed_hosts=frozenset({host}),
            allowed_networks=(),
            allowed_ports=frozenset({port}),
            ssl_mode="disable",
            ssl_root_cert=None,
        )
        activities = [
            ChecklistActivityReference(
                numero="2.2",
                actividad="Clasificar cada tabla: maestra, transaccional, catálogo/parametría, auditoría, temporal/staging",
                fase="Arquitectura de datos",
            ),
            ChecklistActivityReference(
                numero="2.4",
                actividad="Identificar tablas obsoletas, huérfanas o sin uso activo en la aplicación",
                fase="Arquitectura de datos",
            ),
            ChecklistActivityReference(
                numero="2.5",
                actividad="Documentar la relación tabla ↔ módulo/funcionalidad de negocio que la origina",
                fase="Arquitectura de datos",
            ),
        ]

        async with open_verified_external_connection(
            request,
            policy,
            application_name="sistema_auditoria_table_analysis_integration_test",
        ) as connection:
            result = await execute_audit_activities(connection, activities)

        self.assertEqual(
            [activity.estado_ejecucion for activity in result.actividades],
            ["completada", "completada", "completada"],
        )
        classification = next(
            evidence
            for evidence in result.actividades[0].evidencias
            if evidence.clave == "matriz_clasificacion"
        )
        fixture_classifications = {
            table["nombre_completo"]: table
            for table in classification.datos["tablas"]
            if table["esquema"] == "audit_table_analysis_fixture"
        }
        self.assertEqual(
            fixture_classifications[
                "audit_table_analysis_fixture.sales_transaction"
            ]["clasificacion_tecnica"],
            "transaccional",
        )
        self.assertEqual(
            fixture_classifications[
                "audit_table_analysis_fixture.ambiguous_entity"
            ]["clasificacion_tecnica"],
            "indeterminada",
        )

        retirement = next(
            evidence
            for evidence in result.actividades[1].evidencias
            if evidence.clave == "evaluacion_uso_y_dependencias"
        )
        self.assertEqual(retirement.datos["candidatas_baja"], [])
        self.assertTrue(
            all(
                not table["candidata_baja"]
                for table in retirement.datos["tablas"]
                if table["esquema"] == "audit_table_analysis_fixture"
            )
        )

        module_matrix = next(
            evidence
            for evidence in result.actividades[2].evidencias
            if evidence.clave == "matriz_tabla_modulo"
        )
        fixture_tables = [
            table
            for table in module_matrix.datos["tablas"]
            if table["esquema_tecnico"] == "audit_table_analysis_fixture"
        ]
        self.assertTrue(fixture_tables)
        self.assertTrue(
            all(table["modulo_confirmado"] is None for table in fixture_tables)
        )
        self.assertTrue(
            all(
                table["estado_correspondencia"] == "pendiente_validacion"
                for table in fixture_tables
            )
        )

    async def _run_column_dictionary_activities(self):
        password = os.environ["AUDIT_TEST_PASSWORD"]
        host = os.getenv("AUDIT_TEST_HOST", "127.0.0.1")
        port = int(os.getenv("AUDIT_TEST_PORT", "5432"))
        request = ExternalConnectionRequest(
            host=host,
            port=port,
            database=os.getenv("AUDIT_TEST_DATABASE", "auditoria_prueba"),
            username=os.getenv("AUDIT_TEST_USER", "auditor_lectura"),
            password=password,
        )
        policy = ExternalConnectionPolicy(
            environment="development",
            allowed_hosts=frozenset({host}),
            allowed_networks=(),
            allowed_ports=frozenset({port}),
            ssl_mode="disable",
            ssl_root_cert=None,
        )
        activities = [
            ChecklistActivityReference(
                numero=identifier,
                actividad=f"Actividad de diccionario {identifier}",
                fase="Documentación de Campos (Diccionario de Datos)",
            )
            for identifier in (
                "3.1",
                "3.2",
                "3.3",
                "3.4",
                "3.5",
                "3.6",
                "3.7",
                "3.8",
                "3.9",
            )
        ]

        async with open_verified_external_connection(
            request,
            policy,
            application_name="sistema_auditoria_column_dictionary_integration_test",
        ) as connection:
            result = await execute_audit_activities(connection, activities)

        self.assertEqual(
            [activity.estado_ejecucion for activity in result.actividades],
            ["completada"] * 9,
        )
        self.assertEqual(
            [activity.estado_evidencia for activity in result.actividades],
            ["suficiente", "suficiente", "suficiente"] + ["insuficiente"] * 6,
        )
        base_tables = result.actividades[0].evidencias[0].datos["tablas"]
        sales_transaction = next(
            table
            for table in base_tables
            if table["nombre_completo"]
            == "audit_table_analysis_fixture.sales_transaction"
        )
        self.assertEqual(
            [field["campo"] for field in sales_transaction["campos"]],
            ["id", "customer_id", "status_id", "created_at"],
        )
        required_tables = result.actividades[2].evidencias[0].datos["tablas"]
        required_sales = next(
            table
            for table in required_tables
            if table["nombre_completo"]
            == "audit_table_analysis_fixture.sales_transaction"
        )
        self.assertTrue(all(field["obligatorio"] for field in required_sales["campos"]))
        generated_data = result.actividades[4].evidencias[0].datos
        self.assertEqual(generated_data["cobertura_entregable"], "parcial")
        sensitive_data = result.actividades[6].evidencias[0].datos
        self.assertFalse(sensitive_data["contenido_datos_inspeccionado"])

    async def _run_index_activities(self):
        password = os.environ["AUDIT_TEST_PASSWORD"]
        host = os.getenv("AUDIT_TEST_HOST", "127.0.0.1")
        port = int(os.getenv("AUDIT_TEST_PORT", "5432"))
        request = ExternalConnectionRequest(
            host=host,
            port=port,
            database=os.getenv("AUDIT_TEST_DATABASE", "auditoria_prueba"),
            username=os.getenv("AUDIT_TEST_USER", "auditor_lectura"),
            password=password,
        )
        policy = ExternalConnectionPolicy(
            environment="development",
            allowed_hosts=frozenset({host}),
            allowed_networks=(),
            allowed_ports=frozenset({port}),
            ssl_mode="disable",
            ssl_root_cert=None,
        )
        activities = [
            ChecklistActivityReference(
                numero=identifier,
                actividad=f"Actividad de índices {identifier}",
                fase="Índices y Rendimiento",
            )
            for identifier in ("4.1", "4.2", "4.3", "4.4")
        ]

        async with open_verified_external_connection(
            request,
            policy,
            application_name="sistema_auditoria_index_integration_test",
        ) as connection:
            result = await execute_audit_activities(connection, activities)

        self.assertEqual(
            [activity.estado_ejecucion for activity in result.actividades],
            ["completada"] * 4,
        )
        self.assertEqual(
            [activity.estado_evidencia for activity in result.actividades],
            ["suficiente", "suficiente", "insuficiente", "insuficiente"],
        )
        inventory = result.actividades[0].evidencias[0].datos
        fixture_indexes = {
            index["indice"]
            for table in inventory["tablas"]
            if table["esquema"] == "audit_table_analysis_fixture"
            for index in table["indices"]
        }
        self.assertIn("sales_transaction_pkey", fixture_indexes)
        keys = result.actividades[1].evidencias[0].datos
        fixture_foreign_keys = {
            foreign_key["nombre"]
            for foreign_key in keys["llaves_foraneas"]
            if foreign_key["tabla_origen"]
            == "audit_table_analysis_fixture.sales_transaction"
        }
        self.assertEqual(
            fixture_foreign_keys,
            {
                "sales_transaction_customer_id_fkey",
                "sales_transaction_status_id_fkey",
            },
        )
        missing = result.actividades[3].evidencias[0].datos
        missing_fixture_foreign_keys = {
            candidate["restriccion_fk"]
            for candidate in missing["fk_sin_indice_prefijo"]
            if candidate["tabla"]
            == "audit_table_analysis_fixture.sales_transaction"
        }
        self.assertEqual(missing_fixture_foreign_keys, fixture_foreign_keys)


if __name__ == "__main__":
    unittest.main()
