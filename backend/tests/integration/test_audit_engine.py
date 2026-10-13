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


if __name__ == "__main__":
    unittest.main()
