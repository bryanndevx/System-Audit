import argparse
import asyncio
import getpass
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.audit_engine import (
    AuditExecutionResult,
    ChecklistActivityReference,
    execute_audit_activities,
)
from app.event_loop import create_psycopg_compatible_event_loop
from app.external_connections import (
    DestinationNotAllowedError,
    ExternalConnectionConfigurationError,
    ExternalConnectionPolicy,
    ExternalConnectionRequest,
    InsufficientDatabasePrivilegesError,
    open_verified_external_connection,
)


DEFAULT_REFERENCE = (
    BACKEND_ROOT
    / "tests"
    / "fixtures"
    / "audit_engine_manual_reference.json"
)


def load_reference(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as reference_file:
        reference = json.load(reference_file)
    if reference.get("es_evidencia_auditoria") is not False:
        raise ValueError(
            "La referencia debe declararse exclusivamente como dato de validación local."
        )
    return reference


def _find_activity(result: dict[str, Any], identifier: str) -> dict[str, Any]:
    for activity in result["actividades"]:
        if activity["identificador"] == identifier:
            return activity
    raise ValueError(f"No se obtuvo la actividad requerida {identifier}.")


def _find_evidence(activity: dict[str, Any], key: str) -> dict[str, Any]:
    for evidence in activity["evidencias"]:
        if evidence["clave"] == key:
            return evidence
    raise ValueError(
        f"La actividad {activity['identificador']} no contiene la evidencia requerida {key}."
    )


def compare_byte_value(manual: int, automatic: int | None) -> dict[str, Any]:
    if automatic is None:
        return {
            "manual_bytes": manual,
            "automatico_bytes": None,
            "diferencia_bytes": None,
            "estado": "diferencia_requiere_revision",
        }
    difference = automatic - manual
    return {
        "manual_bytes": manual,
        "automatico_bytes": automatic,
        "diferencia_bytes": difference,
        "estado": (
            "coincide" if difference == 0 else "variacion_pendiente_explicacion"
        ),
    }


def compare_value(manual: Any, automatic: Any) -> dict[str, Any]:
    return {
        "manual": manual,
        "automatico": automatic,
        "estado": (
            "coincide" if manual == automatic else "diferencia_requiere_revision"
        ),
    }


def compare_name_inventory(
    expected: set[str], automatic: set[str]
) -> dict[str, Any]:
    missing = sorted(expected - automatic)
    additional = sorted(automatic - expected)
    return {
        "esperados": sorted(expected),
        "automaticos": sorted(automatic),
        "faltantes": missing,
        "adicionales": additional,
        "estado": (
            "coincide" if not missing and not additional else "diferencia_requiere_revision"
        ),
    }


def compare_columns(
    manual: list[str], automatic: list[str] | None
) -> dict[str, Any]:
    automatic = [] if automatic is None else automatic
    manual_names = set(manual)
    automatic_names = set(automatic)
    missing = sorted(manual_names - automatic_names)
    additional = sorted(automatic_names - manual_names)
    same_count = len(manual) == len(automatic)
    return {
        "manual": manual,
        "automatico": automatic,
        "cantidad_manual": len(manual),
        "cantidad_automatica": len(automatic),
        "faltantes": missing,
        "adicionales": additional,
        "orden_evaluado": False,
        "estado": (
            "coincide"
            if not missing and not additional and same_count
            else "diferencia_requiere_revision"
        ),
    }


def _inventory_tables(inventory: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        table["nombre_completo"]: table
        for schema in inventory.get("esquemas", [])
        for table in schema.get("tablas", [])
    }


def _compare_inventory(
    manual_relations: dict[str, dict[str, Any]],
    automatic_relations: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    manual_names = set(manual_relations)
    automatic_names = set(automatic_relations)
    metadata_differences = []
    for name in sorted(manual_names & automatic_names):
        manual = manual_relations[name]
        automatic = automatic_relations[name]
        if (
            manual["tipo"] != automatic.get("tipo")
            or manual["es_particion"] != automatic.get("es_particion")
        ):
            metadata_differences.append(
                {
                    "relacion": name,
                    "manual": {
                        "tipo": manual["tipo"],
                        "es_particion": manual["es_particion"],
                    },
                    "automatico": {
                        "tipo": automatic.get("tipo"),
                        "es_particion": automatic.get("es_particion"),
                    },
                }
            )
    missing = sorted(manual_names - automatic_names)
    unexpected = sorted(automatic_names - manual_names)
    return {
        "cantidad_manual": len(manual_names),
        "cantidad_automatica": len(automatic_names),
        "faltantes": missing,
        "adicionales": unexpected,
        "diferencias_tipo_particion": metadata_differences,
        "estado": (
            "coincide"
            if not missing and not unexpected and not metadata_differences
            else "diferencia_requiere_revision"
        ),
    }


def _physical_descendants(
    parent: str,
    inventory: dict[str, dict[str, Any]],
    visited: set[str] | None = None,
) -> list[str]:
    visited = set() if visited is None else visited
    leaves: list[str] = []
    for name, relation in inventory.items():
        if parent not in relation.get("padres", []) or name in visited:
            continue
        visited.add(name)
        if relation.get("tipo") == "tabla_particionada":
            leaves.extend(_physical_descendants(name, inventory, visited))
        else:
            leaves.append(name)
    return leaves


def _consistency_checks(
    target_schema: str,
    inventory: dict[str, dict[str, Any]],
    volumes: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for name, volume in sorted(volumes.items()):
        if volume.get("esquema") != target_schema:
            continue
        data = volume.get("datos_bytes")
        indexes = volume.get("indices_bytes")
        total = volume.get("total_bytes")
        is_consistent = (
            data is not None
            and indexes is not None
            and total is not None
            and data + indexes == total
        )
        checks.append(
            {
                "comprobacion": "total_relacion_igual_datos_mas_indices",
                "relacion": name,
                "datos_bytes": data,
                "indices_bytes": indexes,
                "total_bytes": total,
                "diferencia_bytes": (
                    total - data - indexes
                    if data is not None and indexes is not None and total is not None
                    else None
                ),
                "estado": "coincide" if is_consistent else "error_consistencia",
            }
        )

    for name, relation in sorted(inventory.items()):
        if (
            relation.get("esquema") != target_schema
            or relation.get("tipo") != "tabla_particionada"
            or name not in volumes
        ):
            continue
        leaves = _physical_descendants(name, inventory)
        measurable = [volumes[leaf] for leaf in leaves if leaf in volumes]
        calculated = {
            "particiones_fisicas": len(measurable),
            "datos_bytes": sum(item.get("datos_bytes") or 0 for item in measurable),
            "indices_bytes": sum(item.get("indices_bytes") or 0 for item in measurable),
            "total_bytes": sum(item.get("total_bytes") or 0 for item in measurable),
        }
        reported = volumes[name].get("tamano_arbol_particiones")
        is_consistent = reported is not None and all(
            reported.get(key) == value for key, value in calculated.items()
        )
        checks.append(
            {
                "comprobacion": "agregado_particiones_igual_suma_particiones_fisicas",
                "relacion": name,
                "particiones": leaves,
                "calculado_desde_particiones": calculated,
                "reportado_por_motor": reported,
                "estado": "coincide" if is_consistent else "error_consistencia",
            }
        )
    return checks


def _not_compared(fields: list[str]) -> dict[str, Any]:
    return {"campos": fields, "estado": "no_comparado"}


def _compare_activity_2_6(
    activity: dict[str, Any],
    reference: dict[str, Any],
    complete_inventory: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    data = _find_evidence(activity, "candidatas_auditoria_log_trace")["datos"]
    target_schema = reference["esquema"]
    manual_tables = reference["tablas"]
    candidates = {
        item["nombre_completo"]: item
        for item in data.get("candidatas", [])
        if item.get("esquema") == target_schema
    }
    expected_candidates = {
        name for name, table in manual_tables.items() if table["es_candidata"]
    }
    inventory_comparison = compare_name_inventory(
        expected_candidates, set(candidates)
    )
    statuses = [inventory_comparison["estado"]]
    table_comparisons: dict[str, Any] = {}

    for name, manual in sorted(manual_tables.items()):
        automatic = candidates.get(name)
        if manual["es_candidata"]:
            automatic_columns = (
                [column["nombre"] for column in automatic.get("columnas_tecnicas", [])]
                if automatic is not None
                else None
            )
            fields = {
                "es_candidata": compare_value(True, automatic is not None),
                "columnas": compare_columns(manual["columnas"], automatic_columns),
                "clasificacion_indicios": compare_value(
                    manual["clasificacion_indicios"],
                    automatic.get("clasificacion_indicios") if automatic else None,
                ),
                "funcion_confirmada": compare_value(
                    manual["funcion_confirmada"],
                    automatic.get("funcion_confirmada") if automatic else None,
                ),
                "naturaleza_clasificacion": (
                    "resultado_de_reglas_tecnicas_no_confirmacion_empresarial"
                ),
                "campos_sin_referencia_manual": _not_compared(
                    [
                        "tipo",
                        "es_particion",
                        "indicadores_observables",
                        "restricciones",
                        "permisos",
                    ]
                ),
            }
            statuses.extend(
                fields[key]["estado"]
                for key in (
                    "es_candidata",
                    "columnas",
                    "clasificacion_indicios",
                    "funcion_confirmada",
                    "campos_sin_referencia_manual",
                )
            )
        else:
            existence = compare_value(True, name in complete_inventory)
            candidate_absence = compare_value(False, name in candidates)
            fields = {
                "existe_en_inventario_2_1": existence,
                "es_candidata": candidate_absence,
                "columnas": {
                    "manual": manual["columnas"],
                    "automatico": None,
                    "motivo": (
                        "La evidencia 2.6 solo detalla las tablas clasificadas como candidatas."
                    ),
                    "estado": "no_comparado",
                },
            }
            statuses.extend(
                (
                    existence["estado"],
                    candidate_absence["estado"],
                    fields["columnas"]["estado"],
                )
            )
        table_comparisons[name] = fields

    return (
        {
            "esquema": target_schema,
            "inventario_candidatas": inventory_comparison,
            "tablas": table_comparisons,
        },
        statuses,
    )


def _compare_activity_2_7(
    activity: dict[str, Any], reference: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    data = _find_evidence(activity, "inventario_vistas")["datos"]
    target_schema = reference["esquema"]
    manual_views = reference["vistas"]
    automatic_views = {
        item["nombre_completo"]: item
        for item in data.get("vistas", [])
        if item.get("esquema") == target_schema
    }
    inventory_comparison = compare_name_inventory(
        set(manual_views), set(automatic_views)
    )
    statuses = [inventory_comparison["estado"]]
    view_comparisons: dict[str, Any] = {}
    for name, manual in sorted(manual_views.items()):
        automatic = automatic_views.get(name, {})
        fields = {
            "tipo": compare_value(manual["tipo"], automatic.get("tipo")),
        }
        statuses.append(fields["tipo"]["estado"])
        if "esta_poblada" in manual:
            fields["esta_poblada"] = compare_value(
                manual["esta_poblada"], automatic.get("esta_poblada")
            )
            statuses.append(fields["esta_poblada"]["estado"])
        fields["campos_sin_referencia_manual"] = _not_compared(
            [
                "definicion",
                "dependencias_relacionales",
                "proposito_documentado",
                "proposito_funcional_inferido",
                "permisos",
                "cobertura",
            ]
        )
        statuses.append(fields["campos_sin_referencia_manual"]["estado"])
        view_comparisons[name] = fields
    return (
        {
            "esquema": target_schema,
            "inventario_vistas": inventory_comparison,
            "vistas": view_comparisons,
        },
        statuses,
    )


def _objects_by_name(
    objects: list[dict[str, Any]], *, schema_key: str, target_schema: str
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in objects:
        if item.get(schema_key) == target_schema:
            grouped.setdefault(item["nombre"], []).append(item)
    unique = {name: items[0] for name, items in grouped.items()}
    duplicated = sorted(name for name, items in grouped.items() if len(items) > 1)
    return unique, duplicated


def _compare_activity_2_8(
    activity: dict[str, Any], reference: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    data = _find_evidence(activity, "inventario_objetos_programables")["datos"]
    target_schema = reference["esquema"]
    routines, duplicate_routines = _objects_by_name(
        data.get("rutinas", []), schema_key="esquema", target_schema=target_schema
    )
    triggers, duplicate_triggers = _objects_by_name(
        [
            trigger
            for trigger in data.get("triggers", [])
            if trigger.get("clase") == "trigger_relacion"
        ],
        schema_key="esquema_relacion",
        target_schema=target_schema,
    )

    routine_inventory = compare_name_inventory(set(reference["rutinas"]), set(routines))
    trigger_inventory = compare_name_inventory(set(reference["triggers"]), set(triggers))
    if duplicate_routines:
        routine_inventory["nombres_ambiguos_por_sobrecarga"] = duplicate_routines
        routine_inventory["estado"] = "diferencia_requiere_revision"
    if duplicate_triggers:
        trigger_inventory["nombres_duplicados"] = duplicate_triggers
        trigger_inventory["estado"] = "diferencia_requiere_revision"
    statuses = [routine_inventory["estado"], trigger_inventory["estado"]]

    routine_comparisons: dict[str, Any] = {}
    for name, manual in sorted(reference["rutinas"].items()):
        automatic = routines.get(name, {})
        type_comparison = compare_value(manual["tipo"], automatic.get("tipo"))
        language_comparison = compare_value(
            manual["lenguaje"].casefold(),
            (
                automatic.get("lenguaje", "").casefold()
                if automatic.get("lenguaje") is not None
                else None
            ),
        )
        unreferenced = _not_compared(
            [
                "firma_argumentos",
                "tipo_retorno",
                "security_definer",
                "volatilidad",
                "ejecucion_paralela",
                "permiso_ejecucion",
                "origen",
                "extension",
                "dependencias_catalogadas",
            ]
        )
        routine_comparisons[name] = {
            "tipo": type_comparison,
            "lenguaje": language_comparison,
            "campos_sin_referencia_manual": unreferenced,
        }
        statuses.extend(
            (type_comparison["estado"], language_comparison["estado"], unreferenced["estado"])
        )

    trigger_comparisons: dict[str, Any] = {}
    for name, manual in sorted(reference["triggers"].items()):
        automatic = triggers.get(name, {})
        relation_comparison = compare_value(
            manual["relacion_completa"], automatic.get("relacion_completa")
        )
        state_comparison = compare_value(
            manual["estado_motor_esperado"], automatic.get("estado")
        )
        automatic_function = automatic.get("funcion_asociada") or {}
        function_schema = compare_value(
            manual["funcion_asociada"]["esquema"], automatic_function.get("esquema")
        )
        function_name = compare_value(
            manual["funcion_asociada"]["nombre"], automatic_function.get("nombre")
        )
        unreferenced = _not_compared(
            [
                "eventos",
                "momento",
                "nivel",
                "es_interno",
                "es_clon_particion",
                "trigger_padre",
                "origen",
                "extension",
            ]
        )
        trigger_comparisons[name] = {
            "relacion_completa": relation_comparison,
            "estado": {
                **state_comparison,
                "valor_catalogo_manual": manual["estado_catalogo_manual"],
            },
            "funcion_asociada": {
                "esquema": function_schema,
                "nombre": function_name,
            },
            "campos_sin_referencia_manual": unreferenced,
        }
        statuses.extend(
            (
                relation_comparison["estado"],
                state_comparison["estado"],
                function_schema["estado"],
                function_name["estado"],
                unreferenced["estado"],
            )
        )

    return (
        {
            "esquema": target_schema,
            "inventario_rutinas": routine_inventory,
            "rutinas": routine_comparisons,
            "inventario_triggers": trigger_inventory,
            "triggers": trigger_comparisons,
            "event_triggers": _not_compared(
                ["No existe una referencia manual para event triggers globales."]
            ),
        },
        statuses + ["no_comparado"],
    )


def compare_audit_result(
    result: AuditExecutionResult | dict[str, Any],
    reference: dict[str, Any],
    measured_from: datetime,
    measured_to: datetime,
) -> dict[str, Any]:
    serialized = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    inventory_activity = _find_activity(serialized, "2.1")
    volume_activity = _find_activity(serialized, "2.3")
    candidates_activity = _find_activity(serialized, "2.6")
    views_activity = _find_activity(serialized, "2.7")
    programmable_activity = _find_activity(serialized, "2.8")
    inventory_data = _find_evidence(inventory_activity, "inventario_tablas")["datos"]
    volume_data = _find_evidence(
        volume_activity, "volumetria_actual_por_tabla"
    )["datos"]
    database_size = _find_evidence(volume_activity, "tamano_base_datos")["datos"].get(
        "bytes"
    )
    growth = _find_evidence(volume_activity, "crecimiento_historico")["datos"]

    target_schema = reference["esquema"]
    manual_measurement = reference["medicion_manual"]
    manual_relations = manual_measurement["relaciones"]
    complete_inventory = _inventory_tables(inventory_data)
    schema_inventory = {
        name: relation
        for name, relation in complete_inventory.items()
        if relation.get("esquema") == target_schema
    }
    all_volumes = {
        relation["nombre_completo"]: relation
        for relation in volume_data.get("tablas", [])
    }

    size_comparisons: dict[str, Any] = {}
    statuses: list[str] = []
    inventory_comparison = _compare_inventory(manual_relations, schema_inventory)
    statuses.append(inventory_comparison["estado"])
    for name, manual in sorted(manual_relations.items()):
        automatic = all_volumes.get(name, {})
        fields = {
            field: compare_byte_value(manual[field], automatic.get(field))
            for field in ("datos_bytes", "indices_bytes", "total_bytes")
        }
        statuses.extend(comparison["estado"] for comparison in fields.values())
        size_comparisons[name] = fields

    database_comparison = compare_byte_value(
        manual_measurement["tamano_base_bytes"], database_size
    )
    statuses.append(database_comparison["estado"])

    partition_comparisons: dict[str, Any] = {}
    for parent, manual in sorted(reference["agregados_particiones"].items()):
        automatic = all_volumes.get(parent, {}).get("tamano_arbol_particiones") or {}
        fields = {
            field: compare_byte_value(manual[field], automatic.get(field))
            for field in ("datos_bytes", "indices_bytes", "total_bytes")
        }
        physical_partitions_match = (
            manual["particiones_fisicas"] == automatic.get("particiones_fisicas")
        )
        statuses.extend(comparison["estado"] for comparison in fields.values())
        partition_count_status = (
            "coincide" if physical_partitions_match else "diferencia_requiere_revision"
        )
        statuses.append(partition_count_status)
        partition_comparisons[parent] = {
            **fields,
            "particiones_fisicas": {
                "manual": manual["particiones_fisicas"],
                "automatico": automatic.get("particiones_fisicas"),
                "estado": partition_count_status,
            },
        }

    consistency = _consistency_checks(
        target_schema, complete_inventory, all_volumes
    )
    statuses.extend(check["estado"] for check in consistency)

    activity_references = reference["referencias_actividades"]
    comparison_2_6, statuses_2_6 = _compare_activity_2_6(
        candidates_activity,
        activity_references["2.6"],
        complete_inventory,
    )
    comparison_2_7, statuses_2_7 = _compare_activity_2_7(
        views_activity, activity_references["2.7"]
    )
    comparison_2_8, statuses_2_8 = _compare_activity_2_8(
        programmable_activity, activity_references["2.8"]
    )
    statuses.extend(statuses_2_6)
    statuses.extend(statuses_2_7)
    statuses.extend(statuses_2_8)

    return {
        "proposito": reference["uso"],
        "es_evidencia_auditoria": False,
        "ventana_medicion_automatica_utc": {
            "desde": measured_from.astimezone(UTC).isoformat(),
            "hasta": measured_to.astimezone(UTC).isoformat(),
        },
        "catalogo_motor": serialized["catalogo_version"],
        "estados_actividades": {
            "2.1": inventory_activity["estado_ejecucion"],
            "2.3": volume_activity["estado_ejecucion"],
            "2.6": candidates_activity["estado_ejecucion"],
            "2.7": views_activity["estado_ejecucion"],
            "2.8": programmable_activity["estado_ejecucion"],
        },
        "comparaciones": {
            "inventario": inventory_comparison,
            "tamano_base_datos": database_comparison,
            "tamanos_por_relacion": size_comparisons,
            "agregados_particiones": partition_comparisons,
            "actividad_2_6": comparison_2_6,
            "actividad_2_7": comparison_2_7,
            "actividad_2_8": comparison_2_8,
        },
        "consistencia_matematica_automatica": consistency,
        "cobertura": {
            "crecimiento_historico": growth.get("mensaje"),
            "campos_sin_referencia_manual": [
                "filas_estimadas",
                "paginas_estimadas",
                "estadisticas",
                "permisos",
                "duraciones",
            ],
            "nota": (
                "No se calcula un porcentaje general de exactitud. Cada campo se "
                "evalúa únicamente cuando existe una referencia manual explícita."
            ),
            "entorno_controlado": (
                "Las referencias 2.6, 2.7 y 2.8 validan el funcionamiento del motor "
                "únicamente sobre el esquema ficticio audit_metadata_fixture."
            ),
        },
        "resumen_estados": dict(sorted(Counter(statuses).items())),
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compara evidencias del motor para 2.1, 2.3, 2.6, 2.7 y 2.8 "
            "con una referencia manual local."
        )
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--database", default="auditoria_prueba")
    parser.add_argument("--user", default="auditor_lectura")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    return parser.parse_args()


async def _run(arguments: argparse.Namespace, password: str) -> dict[str, Any]:
    reference = load_reference(arguments.reference)
    policy = ExternalConnectionPolicy.from_environment()
    request = ExternalConnectionRequest(
        host=arguments.host,
        port=arguments.port,
        database=arguments.database,
        username=arguments.user,
        password=password,
    )
    activities = [
        ChecklistActivityReference(
            numero="2.1",
            actividad="Listar tablas agrupadas por esquema/módulo",
            fase="Revisión técnica PostgreSQL",
        ),
        ChecklistActivityReference(
            numero="2.3",
            actividad="Volumetría y crecimiento",
            fase="Revisión técnica PostgreSQL",
        ),
        ChecklistActivityReference(
            numero="2.6",
            actividad="Identificar tablas de auditoría, log y trace",
            fase="Revisión técnica PostgreSQL",
        ),
        ChecklistActivityReference(
            numero="2.7",
            actividad="Inventariar vistas y propósito",
            fase="Revisión técnica PostgreSQL",
        ),
        ChecklistActivityReference(
            numero="2.8",
            actividad="Inventariar funciones, procedimientos y triggers",
            fase="Revisión técnica PostgreSQL",
        ),
    ]
    measured_from = datetime.now(UTC)
    async with open_verified_external_connection(
        request,
        policy,
        application_name="sistema_auditoria_local_evidence_comparison",
    ) as connection:
        result = await execute_audit_activities(connection, activities)
    measured_to = datetime.now(UTC)
    return compare_audit_result(result, reference, measured_from, measured_to)


def main() -> int:
    arguments = _arguments()
    password = getpass.getpass("Contraseña temporal de PostgreSQL auditado: ")
    if not password:
        print("La contraseña es obligatoria.", file=sys.stderr)
        return 2
    try:
        report = asyncio.run(
            _run(arguments, password),
            loop_factory=create_psycopg_compatible_event_loop,
        )
    except ExternalConnectionConfigurationError:
        print("La política de conexión externa no está configurada.", file=sys.stderr)
        return 2
    except (ValueError, OSError, json.JSONDecodeError):
        print("No fue posible cargar o validar la referencia local.", file=sys.stderr)
        return 2
    except (DestinationNotAllowedError, InsufficientDatabasePrivilegesError):
        print("La conexión no cumple la política de seguridad requerida.", file=sys.stderr)
        return 1
    except psycopg.Error:
        print("No fue posible ejecutar la comparación técnica.", file=sys.stderr)
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
