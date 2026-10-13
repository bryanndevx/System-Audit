import json
import unittest
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from app.audit_engine import AuditExecutionResult
from scripts.compare_audit_evidence import compare_audit_result, load_reference


REFERENCE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "audit_engine_manual_reference.json"
)


def audit_result() -> AuditExecutionResult:
    inventory = [
        {
            "esquema": "audit_fixture",
            "tabla": "catalog_items",
            "nombre_completo": "audit_fixture.catalog_items",
            "tipo": "tabla_ordinaria",
            "es_particion": False,
            "padres": [],
            "permiso_uso_esquema": True,
            "permiso_lectura": True,
        },
        {
            "esquema": "audit_fixture",
            "tabla": "technical_events",
            "nombre_completo": "audit_fixture.technical_events",
            "tipo": "tabla_particionada",
            "es_particion": False,
            "padres": [],
            "permiso_uso_esquema": True,
            "permiso_lectura": True,
        },
        {
            "esquema": "audit_fixture",
            "tabla": "technical_events_2025",
            "nombre_completo": "audit_fixture.technical_events_2025",
            "tipo": "tabla_ordinaria",
            "es_particion": True,
            "padres": ["audit_fixture.technical_events"],
            "permiso_uso_esquema": True,
            "permiso_lectura": True,
        },
        {
            "esquema": "audit_fixture",
            "tabla": "technical_events_2026",
            "nombre_completo": "audit_fixture.technical_events_2026",
            "tipo": "tabla_ordinaria",
            "es_particion": True,
            "padres": ["audit_fixture.technical_events"],
            "permiso_uso_esquema": True,
            "permiso_lectura": True,
        },
    ]
    metadata_inventory = [
        {
            "esquema": "audit_metadata_fixture",
            "tabla": name,
            "nombre_completo": f"audit_metadata_fixture.{name}",
            "tipo": "tabla_ordinaria",
            "es_particion": False,
            "padres": [],
            "permiso_uso_esquema": True,
            "permiso_lectura": True,
        }
        for name in ("audit_event_log", "trace_named_only", "reference_data")
    ]
    sizes = {
        "catalog_items": (16384, 32768, 49152, None),
        "technical_events": (
            0,
            0,
            0,
            {
                "datos_bytes": 32768,
                "indices_bytes": 32768,
                "total_bytes": 65536,
                "particiones_fisicas": 2,
            },
        ),
        "technical_events_2025": (16384, 16384, 32768, None),
        "technical_events_2026": (16384, 16384, 32768, None),
    }
    volumes = [
        {
            **relation,
            "datos_bytes": sizes[relation["tabla"]][0],
            "indices_bytes": sizes[relation["tabla"]][1],
            "total_bytes": sizes[relation["tabla"]][2],
            "filas_estimadas": {"valor": 0, "naturaleza": "estimada"},
            "paginas_estimadas": {"valor": 0, "naturaleza": "estimada"},
            "estadisticas": {},
            "tamano_arbol_particiones": sizes[relation["tabla"]][3],
        }
        for relation in inventory
    ]
    return AuditExecutionResult.model_validate(
        {
            "catalogo_version": "sprint3-v2",
            "duracion_total_ms": 12,
            "actividades": [
                {
                    "identificador": "2.1",
                    "numero_original": "2.1",
                    "nombre_original": "Listar tablas agrupadas por esquema/módulo",
                    "fase_original": "Revisión técnica PostgreSQL",
                    "estado_ejecucion": "completada",
                    "estado_evidencia": "suficiente",
                    "evidencias": [
                        {
                            "clave": "inventario_tablas",
                            "consulta_id": "table_inventory",
                            "disponibilidad": "disponible",
                            "naturaleza": "calculada",
                            "datos": {
                                "esquemas": [
                                    {
                                        "esquema": "audit_fixture",
                                        "permiso_uso": True,
                                        "cantidad_tablas": 4,
                                        "tablas": inventory,
                                    },
                                    {
                                        "esquema": "audit_metadata_fixture",
                                        "permiso_uso": True,
                                        "cantidad_tablas": 3,
                                        "tablas": metadata_inventory,
                                    }
                                ],
                                "total_tablas": 7,
                            },
                        }
                    ],
                    "advertencias": [],
                    "limitaciones": [],
                    "duracion_ms": 4,
                },
                {
                    "identificador": "2.3",
                    "numero_original": "2.3",
                    "nombre_original": "Volumetría y crecimiento",
                    "fase_original": "Revisión técnica PostgreSQL",
                    "estado_ejecucion": "completada",
                    "estado_evidencia": "insuficiente",
                    "evidencias": [
                        {
                            "clave": "tamano_base_datos",
                            "consulta_id": "database_size",
                            "disponibilidad": "disponible",
                            "naturaleza": "exacta",
                            "datos": {"bytes": 8492735},
                        },
                        {
                            "clave": "volumetria_actual_por_tabla",
                            "consulta_id": "table_volumetry",
                            "disponibilidad": "disponible",
                            "naturaleza": "calculada",
                            "datos": {"tablas": volumes, "total_tablas": 4},
                        },
                        {
                            "clave": "crecimiento_historico",
                            "consulta_id": "historical_growth",
                            "disponibilidad": "no_disponible",
                            "naturaleza": "no_disponible",
                            "datos": {
                                "mensaje": "Historial de crecimiento no disponible"
                            },
                        },
                    ],
                    "advertencias": [],
                    "limitaciones": ["Historial de crecimiento no disponible."],
                    "duracion_ms": 8,
                },
                {
                    "identificador": "2.6",
                    "numero_original": "2.6",
                    "nombre_original": "Identificar tablas de auditoría, log y trace",
                    "fase_original": "Revisión técnica PostgreSQL",
                    "estado_ejecucion": "completada",
                    "estado_evidencia": "suficiente",
                    "evidencias": [
                        {
                            "clave": "candidatas_auditoria_log_trace",
                            "consulta_id": "audit_table_classification",
                            "disponibilidad": "disponible",
                            "naturaleza": "calculada",
                            "datos": {
                                "tablas_analizadas": 7,
                                "candidatas": [
                                    {
                                        "esquema": "audit_metadata_fixture",
                                        "tabla": "audit_event_log",
                                        "nombre_completo": "audit_metadata_fixture.audit_event_log",
                                        "tipo": "tabla_ordinaria",
                                        "es_particion": False,
                                        "clasificacion_indicios": "sustentada",
                                        "funcion_confirmada": False,
                                        "confirmacion_funcional": "no_disponible",
                                        "indicadores_observables": {},
                                        "columnas_tecnicas": [
                                            {"posicion": position, "nombre": name, "tipo": "text", "no_nula": False}
                                            for position, name in enumerate(
                                                [
                                                    "id",
                                                    "event_at",
                                                    "actor_id",
                                                    "action",
                                                    "old_values",
                                                    "new_values",
                                                ],
                                                start=1,
                                            )
                                        ],
                                        "restricciones": [],
                                        "permiso_uso_esquema": True,
                                        "permiso_lectura": True,
                                    },
                                    {
                                        "esquema": "audit_metadata_fixture",
                                        "tabla": "trace_named_only",
                                        "nombre_completo": "audit_metadata_fixture.trace_named_only",
                                        "tipo": "tabla_ordinaria",
                                        "es_particion": False,
                                        "clasificacion_indicios": "probable",
                                        "funcion_confirmada": False,
                                        "confirmacion_funcional": "no_disponible",
                                        "indicadores_observables": {},
                                        "columnas_tecnicas": [
                                            {"posicion": 1, "nombre": "id", "tipo": "bigint", "no_nula": True}
                                        ],
                                        "restricciones": [],
                                        "permiso_uso_esquema": True,
                                        "permiso_lectura": True,
                                    },
                                    {
                                        "esquema": "otro_esquema",
                                        "tabla": "audit_extra",
                                        "nombre_completo": "otro_esquema.audit_extra",
                                        "clasificacion_indicios": "sustentada",
                                        "funcion_confirmada": False,
                                        "columnas_tecnicas": [],
                                    },
                                ],
                                "total_candidatas": 3,
                                "total_sustentadas": 2,
                                "total_probables": 1,
                                "total_funcion_confirmada": 0,
                            },
                        }
                    ],
                    "advertencias": [],
                    "limitaciones": [],
                    "duracion_ms": 3,
                },
                {
                    "identificador": "2.7",
                    "numero_original": "2.7",
                    "nombre_original": "Inventariar vistas y propósito",
                    "fase_original": "Revisión técnica PostgreSQL",
                    "estado_ejecucion": "completada",
                    "estado_evidencia": "suficiente",
                    "evidencias": [
                        {
                            "clave": "inventario_vistas",
                            "consulta_id": "view_inventory_and_dependencies",
                            "disponibilidad": "disponible",
                            "naturaleza": "calculada",
                            "datos": {
                                "vistas": [
                                    {
                                        "esquema": "audit_metadata_fixture",
                                        "nombre": "audit_event_summary",
                                        "nombre_completo": "audit_metadata_fixture.audit_event_summary",
                                        "tipo": "vista",
                                        "esta_poblada": None,
                                    },
                                    {
                                        "esquema": "audit_metadata_fixture",
                                        "nombre": "audit_event_daily",
                                        "nombre_completo": "audit_metadata_fixture.audit_event_daily",
                                        "tipo": "vista_materializada",
                                        "esta_poblada": False,
                                    },
                                    {
                                        "esquema": "otro_esquema",
                                        "nombre": "vista_extra",
                                        "nombre_completo": "otro_esquema.vista_extra",
                                        "tipo": "vista",
                                        "esta_poblada": None,
                                    },
                                ],
                                "total_vistas": 2,
                                "total_vistas_materializadas": 1,
                                "inventario_completo_verificable": True,
                            },
                        }
                    ],
                    "advertencias": [],
                    "limitaciones": [],
                    "duracion_ms": 2,
                },
                {
                    "identificador": "2.8",
                    "numero_original": "2.8",
                    "nombre_original": "Inventariar funciones, procedimientos y triggers",
                    "fase_original": "Revisión técnica PostgreSQL",
                    "estado_ejecucion": "completada",
                    "estado_evidencia": "suficiente",
                    "evidencias": [
                        {
                            "clave": "inventario_objetos_programables",
                            "consulta_id": "programmable_objects_inventory",
                            "disponibilidad": "disponible",
                            "naturaleza": "calculada",
                            "datos": {
                                "rutinas": [
                                    {"esquema": "audit_metadata_fixture", "nombre": "fixture_noop", "tipo": "procedimiento", "lenguaje": "sql"},
                                    {"esquema": "audit_metadata_fixture", "nombre": "normalize_action", "tipo": "funcion", "lenguaje": "sql"},
                                    {"esquema": "audit_metadata_fixture", "nombre": "preserve_fixture_row", "tipo": "funcion", "lenguaje": "plpgsql"},
                                    {"esquema": "otro_esquema", "nombre": "funcion_extra", "tipo": "funcion", "lenguaje": "sql"},
                                ],
                                "triggers": [
                                    {
                                        "nombre": "audit_event_log_before_insert",
                                        "clase": "trigger_relacion",
                                        "esquema_relacion": "audit_metadata_fixture",
                                        "relacion_completa": "audit_metadata_fixture.audit_event_log",
                                        "estado": "deshabilitado",
                                        "funcion_asociada": {
                                            "esquema": "audit_metadata_fixture",
                                            "nombre": "preserve_fixture_row",
                                        },
                                    },
                                    {
                                        "nombre": "trigger_extra",
                                        "clase": "trigger_relacion",
                                        "esquema_relacion": "otro_esquema",
                                        "relacion_completa": "otro_esquema.tabla",
                                        "estado": "origin_local",
                                        "funcion_asociada": {"esquema": "otro_esquema", "nombre": "funcion_extra"},
                                    },
                                ],
                                "total_funciones": 3,
                                "total_procedimientos": 1,
                                "total_triggers_relacion": 2,
                                "total_event_triggers": 0,
                                "inventario_completo_verificable": True,
                            },
                        }
                    ],
                    "advertencias": [],
                    "limitaciones": [],
                    "duracion_ms": 3,
                },
            ],
        }
    )


def report(result=None):
    instant = datetime(2026, 10, 13, tzinfo=UTC)
    return compare_audit_result(
        result or audit_result(),
        load_reference(REFERENCE_PATH),
        instant,
        instant,
    )


def all_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from all_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from all_keys(nested)


def activity_evidence(result, identifier, key):
    activity = next(
        item for item in result["actividades"] if item["identificador"] == identifier
    )
    return next(item for item in activity["evidencias"] if item["clave"] == key)[
        "datos"
    ]


class AuditEvidenceComparisonTests(unittest.TestCase):
    def test_matching_values_are_compared_field_by_field_without_percentage(self):
        comparison = report()

        self.assertEqual(
            comparison["comparaciones"]["inventario"]["estado"], "coincide"
        )
        catalog = comparison["comparaciones"]["tamanos_por_relacion"][
            "audit_fixture.catalog_items"
        ]
        self.assertEqual(catalog["total_bytes"]["manual_bytes"], 49152)
        self.assertEqual(catalog["total_bytes"]["automatico_bytes"], 49152)
        self.assertEqual(catalog["total_bytes"]["diferencia_bytes"], 0)
        self.assertEqual(catalog["total_bytes"]["estado"], "coincide")
        self.assertFalse(
            any("porcentaje" in key.lower() for key in all_keys(comparison))
        )

    def test_size_difference_is_pending_explanation_but_math_can_remain_valid(self):
        result = audit_result().model_dump()
        volumes = result["actividades"][1]["evidencias"][1]["datos"]["tablas"]
        catalog = next(item for item in volumes if item["tabla"] == "catalog_items")
        catalog["datos_bytes"] = 24576
        catalog["total_bytes"] = 57344

        comparison = report(result)
        data = comparison["comparaciones"]["tamanos_por_relacion"][
            "audit_fixture.catalog_items"
        ]["datos_bytes"]
        consistency = next(
            check
            for check in comparison["consistencia_matematica_automatica"]
            if check["relacion"] == "audit_fixture.catalog_items"
        )

        self.assertEqual(data["diferencia_bytes"], 8192)
        self.assertEqual(data["estado"], "variacion_pendiente_explicacion")
        self.assertEqual(consistency["estado"], "coincide")

    def test_inconsistent_relation_total_is_reported_independently(self):
        result = audit_result().model_dump()
        volumes = result["actividades"][1]["evidencias"][1]["datos"]["tablas"]
        catalog = next(item for item in volumes if item["tabla"] == "catalog_items")
        catalog["total_bytes"] = 50000

        comparison = report(result)
        consistency = next(
            check
            for check in comparison["consistencia_matematica_automatica"]
            if check["relacion"] == "audit_fixture.catalog_items"
        )

        self.assertEqual(consistency["estado"], "error_consistencia")
        self.assertNotEqual(consistency["estado"], "error_de_consistencia")
        self.assertEqual(consistency["diferencia_bytes"], 848)

    def test_metadata_activities_match_only_the_controlled_schema(self):
        comparison = report()
        activity_2_6 = comparison["comparaciones"]["actividad_2_6"]
        activity_2_7 = comparison["comparaciones"]["actividad_2_7"]
        activity_2_8 = comparison["comparaciones"]["actividad_2_8"]

        self.assertEqual(
            activity_2_6["inventario_candidatas"]["estado"], "coincide"
        )
        self.assertEqual(
            activity_2_6["tablas"]["audit_metadata_fixture.audit_event_log"][
                "clasificacion_indicios"
            ]["estado"],
            "coincide",
        )
        self.assertFalse(
            activity_2_6["tablas"]["audit_metadata_fixture.audit_event_log"][
                "funcion_confirmada"
            ]["automatico"]
        )
        self.assertEqual(
            activity_2_7["inventario_vistas"]["adicionales"], []
        )
        self.assertEqual(
            activity_2_8["inventario_rutinas"]["adicionales"], []
        )
        self.assertEqual(
            activity_2_8["inventario_triggers"]["adicionales"], []
        )
        self.assertEqual(comparison["resumen_estados"]["no_comparado"], 10)

    def test_column_order_is_not_an_accuracy_difference(self):
        result = audit_result().model_dump()
        candidates = activity_evidence(
            result, "2.6", "candidatas_auditoria_log_trace"
        )["candidatas"]
        audit_log = next(item for item in candidates if item["tabla"] == "audit_event_log")
        audit_log["columnas_tecnicas"].reverse()

        columns = report(result)["comparaciones"]["actividad_2_6"]["tablas"][
            "audit_metadata_fixture.audit_event_log"
        ]["columnas"]

        self.assertEqual(columns["estado"], "coincide")
        self.assertFalse(columns["orden_evaluado"])

    def test_column_and_rule_classification_differences_are_clear(self):
        result = audit_result().model_dump()
        candidates = activity_evidence(
            result, "2.6", "candidatas_auditoria_log_trace"
        )["candidatas"]
        audit_log = next(item for item in candidates if item["tabla"] == "audit_event_log")
        audit_log["columnas_tecnicas"].pop()
        audit_log["clasificacion_indicios"] = "probable"

        comparison = report(result)["comparaciones"]["actividad_2_6"]["tablas"][
            "audit_metadata_fixture.audit_event_log"
        ]

        self.assertEqual(
            comparison["columnas"]["faltantes"], ["new_values"]
        )
        self.assertEqual(
            comparison["columnas"]["estado"], "diferencia_requiere_revision"
        )
        self.assertEqual(
            comparison["clasificacion_indicios"]["estado"],
            "diferencia_requiere_revision",
        )
        self.assertIn(
            "reglas_tecnicas",
            comparison["naturaleza_clasificacion"],
        )

    def test_non_candidate_is_checked_without_claiming_its_columns_were_compared(self):
        result = audit_result().model_dump()
        candidates = activity_evidence(
            result, "2.6", "candidatas_auditoria_log_trace"
        )["candidatas"]
        candidates.append(
            {
                "esquema": "audit_metadata_fixture",
                "tabla": "reference_data",
                "nombre_completo": "audit_metadata_fixture.reference_data",
                "clasificacion_indicios": "probable",
                "funcion_confirmada": False,
                "columnas_tecnicas": [],
            }
        )

        comparison = report(result)["comparaciones"]["actividad_2_6"]["tablas"][
            "audit_metadata_fixture.reference_data"
        ]

        self.assertEqual(
            comparison["es_candidata"]["estado"],
            "diferencia_requiere_revision",
        )
        self.assertEqual(comparison["columnas"]["estado"], "no_comparado")

    def test_view_type_and_materialized_state_differences_are_reported(self):
        result = audit_result().model_dump()
        views = activity_evidence(result, "2.7", "inventario_vistas")["vistas"]
        daily = next(item for item in views if item["nombre"] == "audit_event_daily")
        daily["tipo"] = "vista"
        daily["esta_poblada"] = True

        comparison = report(result)["comparaciones"]["actividad_2_7"]["vistas"][
            "audit_metadata_fixture.audit_event_daily"
        ]

        self.assertEqual(comparison["tipo"]["estado"], "diferencia_requiere_revision")
        self.assertEqual(
            comparison["esta_poblada"]["estado"],
            "diferencia_requiere_revision",
        )

    def test_routine_and_trigger_differences_are_reported(self):
        result = audit_result().model_dump()
        programmable = activity_evidence(
            result, "2.8", "inventario_objetos_programables"
        )
        procedure = next(
            item for item in programmable["rutinas"] if item["nombre"] == "fixture_noop"
        )
        procedure["tipo"] = "funcion"
        trigger = next(
            item
            for item in programmable["triggers"]
            if item["nombre"] == "audit_event_log_before_insert"
        )
        trigger["estado"] = "origin_local"
        trigger["funcion_asociada"]["nombre"] = "otra_funcion"

        comparison = report(result)["comparaciones"]["actividad_2_8"]

        self.assertEqual(
            comparison["rutinas"]["fixture_noop"]["tipo"]["estado"],
            "diferencia_requiere_revision",
        )
        trigger_comparison = comparison["triggers"][
            "audit_event_log_before_insert"
        ]
        self.assertEqual(
            trigger_comparison["estado"]["estado"],
            "diferencia_requiere_revision",
        )
        self.assertEqual(trigger_comparison["estado"]["valor_catalogo_manual"], "D")
        self.assertEqual(
            trigger_comparison["funcion_asociada"]["nombre"]["estado"],
            "diferencia_requiere_revision",
        )

    def test_partition_aggregate_is_checked_against_automatic_children(self):
        result = audit_result().model_dump()
        volumes = result["actividades"][1]["evidencias"][1]["datos"]["tablas"]
        parent = next(item for item in volumes if item["tabla"] == "technical_events")
        parent["tamano_arbol_particiones"]["total_bytes"] = 70000

        comparison = report(result)
        consistency = next(
            check
            for check in comparison["consistencia_matematica_automatica"]
            if check["comprobacion"]
            == "agregado_particiones_igual_suma_particiones_fisicas"
        )

        self.assertEqual(consistency["estado"], "error_consistencia")
        self.assertEqual(
            consistency["calculado_desde_particiones"]["total_bytes"], 65536
        )
        self.assertEqual(
            consistency["reportado_por_motor"]["total_bytes"], 70000
        )

    def test_inventory_differences_are_not_treated_as_size_variations(self):
        result = audit_result().model_dump()
        tables = result["actividades"][0]["evidencias"][0]["datos"]["esquemas"][0][
            "tablas"
        ]
        tables.pop()
        tables[0]["tipo"] = "tabla_externa"

        comparison = report(result)["comparaciones"]["inventario"]

        self.assertEqual(comparison["estado"], "diferencia_requiere_revision")
        self.assertEqual(
            comparison["faltantes"], ["audit_fixture.technical_events_2026"]
        )
        self.assertEqual(len(comparison["diferencias_tipo_particion"]), 1)

    def test_report_marks_uncompared_fields_and_contains_no_sensitive_values(self):
        comparison = report()
        serialized = json.dumps(comparison)

        self.assertFalse(comparison["es_evidencia_auditoria"])
        self.assertEqual(
            comparison["cobertura"]["crecimiento_historico"],
            "Historial de crecimiento no disponible",
        )
        for sensitive_name in ("password", "contraseña", "token", "connection_string"):
            self.assertNotIn(sensitive_name, serialized.lower())

    def test_reference_cannot_be_declared_as_audit_evidence(self):
        reference = deepcopy(load_reference(REFERENCE_PATH))
        reference["es_evidencia_auditoria"] = True
        temporary = REFERENCE_PATH.parent / "invalid_reference_for_test.json"
        try:
            temporary.write_text(json.dumps(reference), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_reference(temporary)
        finally:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
