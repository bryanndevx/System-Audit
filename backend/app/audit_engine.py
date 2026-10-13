import asyncio
import re
import time
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Literal

import psycopg
from pydantic import BaseModel, Field, field_validator
from psycopg import errors

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
from app.external_connections import SET_TRANSACTION_READ_ONLY_SQL

AUDIT_CATALOG_VERSION = "sprint3-v2"
QUERY_OPERATION_TIMEOUT_SECONDS = 6

AUDIT_TABLE_NAME_HINTS = frozenset(
    {
        "audit",
        "auditoria",
        "bitacora",
        "event",
        "evento",
        "history",
        "historial",
        "log",
        "trace",
        "traza",
    }
)
AUDIT_COLUMN_SIGNAL_GROUPS = {
    "momento": frozenset(
        {
            "audit_at",
            "created_at",
            "event_at",
            "fecha_evento",
            "logged_at",
            "occurred_at",
            "timestamp",
        }
    ),
    "actor": frozenset(
        {
            "actor",
            "actor_id",
            "changed_by",
            "user_id",
            "username",
            "usuario",
            "usuario_id",
        }
    ),
    "accion": frozenset(
        {
            "accion",
            "action",
            "event_type",
            "evento",
            "operation",
            "operacion",
        }
    ),
    "cambio_o_detalle": frozenset(
        {
            "after_data",
            "before_data",
            "details",
            "new_values",
            "old_values",
            "payload",
            "trace_id",
        }
    ),
}
CONSTRAINT_TYPES = {
    "c": "check",
    "f": "foreign_key",
    "p": "primary_key",
    "u": "unique",
    "x": "exclusion",
}

ExecutionStatus = Literal[
    "completada",
    "parcial",
    "error_tecnico",
    "sin_automatizacion_configurada",
]
EvidenceStatus = Literal["suficiente", "insuficiente", "sin_datos", "no_obtenida"]
EvidenceAvailability = Literal["disponible", "sin_datos", "no_disponible"]
EvidenceNature = Literal["exacta", "estimada", "calculada", "no_disponible"]


class ChecklistActivityReference(BaseModel):
    numero: str = Field(min_length=1, max_length=50)
    actividad: str = Field(min_length=1, max_length=500)
    fase: str = Field(min_length=1, max_length=250)

    @field_validator("numero", "actividad", "fase")
    @classmethod
    def reject_outer_whitespace(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("El valor no puede tener espacios al inicio o al final.")
        return value


class ActivityEvidence(BaseModel):
    clave: str
    consulta_id: str
    disponibilidad: EvidenceAvailability
    naturaleza: EvidenceNature
    datos: Any


class ActivityResult(BaseModel):
    identificador: str
    numero_original: str
    nombre_original: str
    fase_original: str
    estado_ejecucion: ExecutionStatus
    estado_evidencia: EvidenceStatus
    evidencias: list[ActivityEvidence]
    advertencias: list[str]
    limitaciones: list[str]
    duracion_ms: int


class AuditExecutionResult(BaseModel):
    catalogo_version: str
    actividades: list[ActivityResult]
    duracion_total_ms: int


@dataclass(frozen=True)
class QueryOutcome:
    rows: list[tuple[Any, ...]] | None
    error: Literal["permisos", "timeout", "ejecucion"] | None = None


async def _fetch_rows(
    connection: psycopg.AsyncConnection,
    statement: str,
) -> QueryOutcome:
    rows: list[tuple[Any, ...]] | None = None
    query_error: Literal["permisos", "timeout", "ejecucion"] | None = None
    try:
        async with asyncio.timeout(QUERY_OPERATION_TIMEOUT_SECONDS):
            async with connection.cursor() as cursor:
                await cursor.execute(SET_TRANSACTION_READ_ONLY_SQL)
                await cursor.execute(statement)
                rows = list(await cursor.fetchall())
    except TimeoutError:
        query_error = "timeout"
    except errors.InsufficientPrivilege:
        query_error = "permisos"
    except psycopg.Error:
        query_error = "ejecucion"
    finally:
        try:
            await connection.rollback()
        except psycopg.Error:
            rows = None
            query_error = query_error or "ejecucion"
    return QueryOutcome(rows=rows, error=query_error)


def _technical_warning(query_id: str, outcome: QueryOutcome) -> str | None:
    if outcome.error == "permisos":
        return f"La comprobación {query_id} no pudo ejecutarse por falta de permisos."
    if outcome.error == "timeout":
        return f"La comprobación {query_id} superó el tiempo máximo permitido."
    if outcome.error == "ejecucion":
        return f"La comprobación {query_id} no pudo ejecutarse."
    return None


def _relation_type(relkind: str) -> str:
    return {
        "r": "tabla_ordinaria",
        "p": "tabla_particionada",
        "f": "tabla_externa",
    }[relkind]


def _activity_status(outcomes: list[QueryOutcome]) -> ExecutionStatus:
    successful = sum(outcome.error is None for outcome in outcomes)
    if successful == len(outcomes):
        return "completada"
    if successful:
        return "parcial"
    return "error_tecnico"


def _normalized_identifier(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _identifier_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", _normalized_identifier(value))
        if token
    }


async def _execute_table_inventory(
    connection: psycopg.AsyncConnection,
    activity: ChecklistActivityReference,
) -> ActivityResult:
    started = time.perf_counter()
    schemas_outcome = await _fetch_rows(connection, USER_SCHEMAS_SQL)
    tables_outcome = await _fetch_rows(connection, TABLE_INVENTORY_SQL)
    outcomes = [schemas_outcome, tables_outcome]
    evidence: list[ActivityEvidence] = []
    warnings = [
        warning
        for query_id, outcome in (
            ("user_schemas", schemas_outcome),
            ("table_inventory", tables_outcome),
        )
        if (warning := _technical_warning(query_id, outcome)) is not None
    ]
    limitations = [
        "La cobertura se limita a los metadatos visibles para el rol conectado; no se presenta como inventario absoluto si existen objetos ocultos por permisos.",
        "Los esquemas agrupan objetos técnicos y no demuestran por sí solos una asociación con módulos de negocio.",
    ]

    schemas: dict[str, dict[str, Any]] = {}
    if schemas_outcome.rows is not None:
        for _, schema_name, has_usage in schemas_outcome.rows:
            schemas[schema_name] = {
                "esquema": schema_name,
                "permiso_uso": bool(has_usage),
                "cantidad_tablas": 0,
                "tablas": [],
            }

    tables_by_oid: dict[int, dict[str, Any]] = {}
    if tables_outcome.rows is not None:
        for row in tables_outcome.rows:
            (
                relation_oid,
                schema_name,
                table_name,
                qualified_name,
                relkind,
                is_partition,
                parent_name,
                has_schema_usage,
                has_select,
            ) = row
            relation_oid = int(relation_oid)
            table = tables_by_oid.setdefault(
                relation_oid,
                {
                    "esquema": schema_name,
                    "tabla": table_name,
                    "nombre_completo": qualified_name,
                    "tipo": _relation_type(relkind),
                    "es_particion": bool(is_partition),
                    "padres": [],
                    "permiso_uso_esquema": bool(has_schema_usage),
                    "permiso_lectura": bool(has_select),
                },
            )
            if parent_name and parent_name not in table["padres"]:
                table["padres"].append(parent_name)

        for table in tables_by_oid.values():
            schema = schemas.setdefault(
                table["esquema"],
                {
                    "esquema": table["esquema"],
                    "permiso_uso": table["permiso_uso_esquema"],
                    "cantidad_tablas": 0,
                    "tablas": [],
                },
            )
            schema["tablas"].append(table)

        for schema in schemas.values():
            schema["tablas"].sort(key=lambda table: table["nombre_completo"])
            schema["cantidad_tablas"] = len(schema["tablas"])

        without_select = sum(
            not table["permiso_lectura"] for table in tables_by_oid.values()
        )
        without_usage = sum(not schema["permiso_uso"] for schema in schemas.values())
        if without_select:
            warnings.append(
                f"Se inventariaron {without_select} tablas sin permiso SELECT para el rol conectado."
            )
        if without_usage:
            warnings.append(
                f"Se detectaron {without_usage} esquemas sin permiso USAGE para el rol conectado."
            )

    if schemas_outcome.rows is not None:
        evidence.append(
            ActivityEvidence(
                clave="esquemas_usuario",
                consulta_id="user_schemas",
                disponibilidad="disponible" if schemas else "sin_datos",
                naturaleza="exacta",
                datos={"esquemas": sorted(schemas)},
            )
        )
    if tables_outcome.rows is not None:
        ordered_schemas = sorted(schemas.values(), key=lambda schema: schema["esquema"])
        evidence.append(
            ActivityEvidence(
                clave="inventario_tablas",
                consulta_id="table_inventory",
                disponibilidad="disponible" if tables_by_oid else "sin_datos",
                naturaleza="calculada",
                datos={
                    "esquemas": ordered_schemas,
                    "total_tablas": len(tables_by_oid),
                },
            )
        )

    status = _activity_status(outcomes)
    if status == "error_tecnico":
        evidence_status: EvidenceStatus = "no_obtenida"
    elif not tables_by_oid:
        evidence_status = "sin_datos"
    elif status == "parcial":
        evidence_status = "insuficiente"
    else:
        evidence_status = "suficiente"

    return ActivityResult(
        identificador="2.1",
        numero_original=activity.numero,
        nombre_original=activity.actividad,
        fase_original=activity.fase,
        estado_ejecucion=status,
        estado_evidencia=evidence_status,
        evidencias=evidence,
        advertencias=warnings,
        limitaciones=limitations,
        duracion_ms=round((time.perf_counter() - started) * 1000),
    )


def _partition_tree_sizes(relations: list[dict[str, Any]]) -> None:
    by_oid = {relation["oid"]: relation for relation in relations}
    children: dict[int, list[int]] = defaultdict(list)
    for relation in relations:
        parent_oid = relation["parent_oid"]
        if parent_oid is not None:
            children[parent_oid].append(relation["oid"])

    def physical_descendants(root_oid: int, visited: set[int]) -> list[dict[str, Any]]:
        descendants: list[dict[str, Any]] = []
        for child_oid in children.get(root_oid, []):
            if child_oid in visited:
                continue
            visited.add(child_oid)
            child = by_oid.get(child_oid)
            if child is None:
                continue
            if child["tipo"] == "tabla_particionada":
                descendants.extend(physical_descendants(child_oid, visited))
            else:
                descendants.append(child)
        return descendants

    for relation in relations:
        if relation["tipo"] != "tabla_particionada":
            relation["tamano_arbol_particiones"] = None
            continue
        descendants = physical_descendants(relation["oid"], {relation["oid"]})
        measurable = [item for item in descendants if item["total_bytes"] is not None]
        relation["tamano_arbol_particiones"] = {
            "datos_bytes": sum(item["datos_bytes"] or 0 for item in measurable),
            "indices_bytes": sum(item["indices_bytes"] or 0 for item in measurable),
            "total_bytes": sum(item["total_bytes"] or 0 for item in measurable),
            "particiones_fisicas": len(measurable),
        }


async def _execute_volumetry(
    connection: psycopg.AsyncConnection,
    activity: ChecklistActivityReference,
) -> ActivityResult:
    started = time.perf_counter()
    size_outcome = await _fetch_rows(connection, DATABASE_SIZE_SQL)
    statistics_outcome = await _fetch_rows(
        connection,
        DATABASE_STATISTICS_CONTEXT_SQL,
    )
    tables_outcome = await _fetch_rows(connection, TABLE_VOLUMETRY_SQL)
    outcomes = [size_outcome, statistics_outcome, tables_outcome]
    evidence: list[ActivityEvidence] = []
    warnings = [
        warning
        for query_id, outcome in (
            ("database_size", size_outcome),
            ("statistics_context", statistics_outcome),
            ("table_volumetry", tables_outcome),
        )
        if (warning := _technical_warning(query_id, outcome)) is not None
    ]
    limitations = [
        "La volumetría corresponde al momento de consulta y puede variar por actividad concurrente.",
        "La cobertura por tabla se limita a relaciones visibles para el rol conectado.",
        "Los agregados de tablas particionadas no deben sumarse nuevamente con sus particiones.",
        "Historial de crecimiento no disponible.",
    ]

    if size_outcome.rows is not None:
        database_size = size_outcome.rows[0][0] if size_outcome.rows else None
        evidence.append(
            ActivityEvidence(
                clave="tamano_base_datos",
                consulta_id="database_size",
                disponibilidad="disponible" if database_size is not None else "sin_datos",
                naturaleza="exacta",
                datos={"bytes": database_size},
            )
        )

    if statistics_outcome.rows is not None:
        statistics_context = statistics_outcome.rows[0] if statistics_outcome.rows else None
        evidence.append(
            ActivityEvidence(
                clave="contexto_estadisticas",
                consulta_id="statistics_context",
                disponibilidad="disponible" if statistics_context else "sin_datos",
                naturaleza="exacta",
                datos=(
                    {
                        "track_counts": statistics_context[0],
                        "estadisticas_reiniciadas_en": statistics_context[1],
                    }
                    if statistics_context
                    else None
                ),
            )
        )
        if statistics_context and statistics_context[0] is not True:
            warnings.append(
                "track_counts está deshabilitado; las estimaciones acumulativas pueden no estar disponibles."
            )

    relations: list[dict[str, Any]] = []
    if tables_outcome.rows is not None:
        for row in tables_outcome.rows:
            (
                relation_oid,
                schema_name,
                table_name,
                qualified_name,
                relkind,
                is_partition,
                parent_oid,
                data_bytes,
                index_bytes,
                total_bytes,
                estimated_rows,
                estimated_pages,
                estimated_live_rows,
                estimated_dead_rows,
                modified_since_analyze,
                last_vacuum,
                last_autovacuum,
                last_analyze,
                last_autoanalyze,
                has_schema_usage,
                has_select,
            ) = row
            relations.append(
                {
                    "oid": int(relation_oid),
                    "parent_oid": int(parent_oid) if parent_oid is not None else None,
                    "esquema": schema_name,
                    "tabla": table_name,
                    "nombre_completo": qualified_name,
                    "tipo": _relation_type(relkind),
                    "es_particion": bool(is_partition),
                    "datos_bytes": data_bytes,
                    "indices_bytes": index_bytes,
                    "total_bytes": total_bytes,
                    "filas_estimadas": {
                        "valor": estimated_rows,
                        "naturaleza": "estimada",
                        "fuente": "pg_class.reltuples",
                    },
                    "paginas_estimadas": {
                        "valor": estimated_pages,
                        "naturaleza": "estimada",
                        "fuente": "pg_class.relpages",
                    },
                    "estadisticas": {
                        "filas_vivas_estimadas": estimated_live_rows,
                        "filas_muertas_estimadas": estimated_dead_rows,
                        "modificaciones_desde_analyze_estimadas": modified_since_analyze,
                        "ultimo_vacuum": last_vacuum,
                        "ultimo_autovacuum": last_autovacuum,
                        "ultimo_analyze": last_analyze,
                        "ultimo_autoanalyze": last_autoanalyze,
                    },
                    "permiso_uso_esquema": bool(has_schema_usage),
                    "permiso_lectura": bool(has_select),
                }
            )

        _partition_tree_sizes(relations)
        without_select = sum(not relation["permiso_lectura"] for relation in relations)
        if without_select:
            warnings.append(
                f"Se detectaron {without_select} tablas sin permiso SELECT para el rol conectado."
            )
        public_relations = []
        for relation in relations:
            public_relation = dict(relation)
            public_relation.pop("oid")
            public_relation.pop("parent_oid")
            public_relations.append(public_relation)
        evidence.append(
            ActivityEvidence(
                clave="volumetria_actual_por_tabla",
                consulta_id="table_volumetry",
                disponibilidad="disponible" if relations else "sin_datos",
                naturaleza="calculada",
                datos={"tablas": public_relations, "total_tablas": len(relations)},
            )
        )

    evidence.append(
        ActivityEvidence(
            clave="crecimiento_historico",
            consulta_id="historical_growth",
            disponibilidad="no_disponible",
            naturaleza="no_disponible",
            datos={"mensaje": "Historial de crecimiento no disponible"},
        )
    )

    status = _activity_status(outcomes)
    evidence_status: EvidenceStatus = (
        "no_obtenida" if status == "error_tecnico" else "insuficiente"
    )
    return ActivityResult(
        identificador="2.3",
        numero_original=activity.numero,
        nombre_original=activity.actividad,
        fase_original=activity.fase,
        estado_ejecucion=status,
        estado_evidencia=evidence_status,
        evidencias=evidence,
        advertencias=warnings,
        limitaciones=limitations,
        duracion_ms=round((time.perf_counter() - started) * 1000),
    )


async def _execute_audit_table_candidates(
    connection: psycopg.AsyncConnection,
    activity: ChecklistActivityReference,
) -> ActivityResult:
    started = time.perf_counter()
    tables_outcome = await _fetch_rows(connection, TABLE_INVENTORY_SQL)
    columns_outcome = await _fetch_rows(connection, TABLE_COLUMNS_SQL)
    constraints_outcome = await _fetch_rows(connection, TABLE_CONSTRAINTS_SQL)
    outcomes = [tables_outcome, columns_outcome, constraints_outcome]
    warnings = [
        warning
        for query_id, outcome in (
            ("table_inventory", tables_outcome),
            ("table_columns", columns_outcome),
            ("table_constraints", constraints_outcome),
        )
        if (warning := _technical_warning(query_id, outcome)) is not None
    ]
    limitations = [
        "La clasificación se basa en indicios técnicos deterministas; no confirma el propósito empresarial de ninguna tabla.",
        "Una clasificación sustentada significa que coinciden varios indicios, no que la función de auditoría haya sido validada funcionalmente.",
        "La cobertura se limita a objetos y metadatos visibles para el rol conectado.",
    ]

    tables: dict[int, dict[str, Any]] = {}
    if tables_outcome.rows is not None:
        for row in tables_outcome.rows:
            (
                relation_oid,
                schema_name,
                table_name,
                qualified_name,
                relkind,
                is_partition,
                parent_name,
                has_schema_usage,
                has_select,
            ) = row
            relation_oid = int(relation_oid)
            table = tables.setdefault(
                relation_oid,
                {
                    "esquema": schema_name,
                    "tabla": table_name,
                    "nombre_completo": qualified_name,
                    "tipo": _relation_type(relkind),
                    "es_particion": bool(is_partition),
                    "padres": [],
                    "permiso_uso_esquema": bool(has_schema_usage),
                    "permiso_lectura": bool(has_select),
                    "columnas": [],
                    "restricciones": [],
                },
            )
            if parent_name and parent_name not in table["padres"]:
                table["padres"].append(parent_name)

    if columns_outcome.rows is not None:
        for row in columns_outcome.rows:
            (
                relation_oid,
                _,
                _,
                _,
                position,
                column_name,
                data_type,
                not_null,
            ) = row
            table = tables.get(int(relation_oid))
            if table is not None:
                table["columnas"].append(
                    {
                        "posicion": int(position),
                        "nombre": column_name,
                        "tipo": data_type,
                        "no_nula": bool(not_null),
                    }
                )

    if constraints_outcome.rows is not None:
        for relation_oid, _, name, constraint_type, columns in constraints_outcome.rows:
            table = tables.get(int(relation_oid))
            if table is not None:
                table["restricciones"].append(
                    {
                        "nombre": name,
                        "tipo": CONSTRAINT_TYPES.get(constraint_type, constraint_type),
                        "columnas": list(columns or []),
                    }
                )

    candidates: list[dict[str, Any]] = []
    for table in tables.values():
        name_hints = sorted(
            _identifier_tokens(table["tabla"]) & AUDIT_TABLE_NAME_HINTS
        )
        column_groups: dict[str, list[str]] = {}
        signal_columns: set[str] = set()
        for column in table["columnas"]:
            normalized_name = _normalized_identifier(column["nombre"])
            for group, accepted_names in AUDIT_COLUMN_SIGNAL_GROUPS.items():
                if normalized_name in accepted_names:
                    column_groups.setdefault(group, []).append(column["nombre"])
                    signal_columns.add(column["nombre"])

        constraint_hints = [
            constraint["nombre"]
            for constraint in table["restricciones"]
            if set(constraint["columnas"]) & signal_columns
        ]
        structure_hints = []
        if table["tipo"] == "tabla_particionada" and "momento" in column_groups:
            structure_hints.append("tabla_particionada_con_columna_temporal")

        indicator_count = (
            int(bool(name_hints))
            + len(column_groups)
            + int(bool(constraint_hints))
            + len(structure_hints)
        )
        if indicator_count == 0:
            continue
        classification = "sustentada" if indicator_count >= 2 else "probable"
        candidates.append(
            {
                "esquema": table["esquema"],
                "tabla": table["tabla"],
                "nombre_completo": table["nombre_completo"],
                "tipo": table["tipo"],
                "es_particion": table["es_particion"],
                "clasificacion_indicios": classification,
                "funcion_confirmada": False,
                "confirmacion_funcional": "no_disponible",
                "indicadores_observables": {
                    "nombre_tabla": name_hints,
                    "grupos_columnas": column_groups,
                    "restricciones_sobre_columnas_indicio": constraint_hints,
                    "estructura": structure_hints,
                },
                "columnas_tecnicas": table["columnas"],
                "restricciones": table["restricciones"],
                "permiso_uso_esquema": table["permiso_uso_esquema"],
                "permiso_lectura": table["permiso_lectura"],
            }
        )

    candidates.sort(key=lambda item: item["nombre_completo"])
    if any(not table["permiso_uso_esquema"] for table in tables.values()):
        warnings.append(
            "Se detectaron esquemas sin permiso USAGE; la cobertura funcional no puede considerarse completa."
        )
    if any(not table["permiso_lectura"] for table in tables.values()):
        warnings.append(
            "Se analizaron metadatos de tablas sin permiso SELECT; no se confirma acceso a sus datos."
        )

    evidence: list[ActivityEvidence] = []
    if tables_outcome.rows is not None:
        evidence.append(
            ActivityEvidence(
                clave="candidatas_auditoria_log_trace",
                consulta_id="audit_table_classification",
                disponibilidad="disponible" if candidates else "sin_datos",
                naturaleza="calculada",
                datos={
                    "tablas_analizadas": len(tables),
                    "candidatas": candidates,
                    "total_candidatas": len(candidates),
                    "total_sustentadas": sum(
                        item["clasificacion_indicios"] == "sustentada"
                        for item in candidates
                    ),
                    "total_probables": sum(
                        item["clasificacion_indicios"] == "probable"
                        for item in candidates
                    ),
                    "total_funcion_confirmada": 0,
                },
            )
        )

    status = _activity_status(outcomes)
    if status == "error_tecnico":
        evidence_status: EvidenceStatus = "no_obtenida"
    elif status == "parcial":
        evidence_status = "insuficiente"
    elif not candidates:
        evidence_status = "sin_datos"
    else:
        evidence_status = "suficiente"
    return ActivityResult(
        identificador="2.6",
        numero_original=activity.numero,
        nombre_original=activity.actividad,
        fase_original=activity.fase,
        estado_ejecucion=status,
        estado_evidencia=evidence_status,
        evidencias=evidence,
        advertencias=warnings,
        limitaciones=limitations,
        duracion_ms=round((time.perf_counter() - started) * 1000),
    )


async def _execute_view_inventory(
    connection: psycopg.AsyncConnection,
    activity: ChecklistActivityReference,
) -> ActivityResult:
    started = time.perf_counter()
    inventory_outcome = await _fetch_rows(connection, VIEW_INVENTORY_SQL)
    dependencies_outcome = await _fetch_rows(connection, VIEW_DEPENDENCIES_SQL)
    outcomes = [inventory_outcome, dependencies_outcome]
    warnings = [
        warning
        for query_id, outcome in (
            ("view_inventory", inventory_outcome),
            ("view_dependencies", dependencies_outcome),
        )
        if (warning := _technical_warning(query_id, outcome)) is not None
    ]
    limitations = [
        "El propósito funcional no se infiere desde nombres o definiciones; solo se presenta documentación observable.",
        "Las dependencias corresponden a relaciones registradas en los catálogos y visibles para el rol conectado.",
        "El estado poblado de una vista materializada no demuestra que sus datos estén actualizados.",
    ]

    dependencies: dict[int, list[dict[str, Any]]] = defaultdict(list)
    if dependencies_outcome.rows is not None:
        seen_dependencies: set[tuple[int, int]] = set()
        for row in dependencies_outcome.rows:
            view_oid, referenced_oid, schema, name, qualified_name, relkind, is_system = row
            key = (int(view_oid), int(referenced_oid))
            if key in seen_dependencies:
                continue
            seen_dependencies.add(key)
            dependencies[int(view_oid)].append(
                {
                    "esquema": schema,
                    "nombre": name,
                    "nombre_completo": qualified_name,
                    "tipo_relacion": relkind,
                    "es_sistema": bool(is_system),
                }
            )

    views: list[dict[str, Any]] = []
    if inventory_outcome.rows is not None:
        for row in inventory_outcome.rows:
            (
                view_oid,
                schema,
                name,
                qualified_name,
                relkind,
                populated,
                definition,
                documented_purpose,
                has_schema_usage,
                has_select,
            ) = row
            views.append(
                {
                    "esquema": schema,
                    "nombre": name,
                    "nombre_completo": qualified_name,
                    "tipo": "vista" if relkind == "v" else "vista_materializada",
                    "esta_poblada": bool(populated) if relkind == "m" else None,
                    "definicion_accesible": definition is not None,
                    "definicion": definition,
                    "dependencias_relacionales": dependencies.get(int(view_oid), []),
                    "dependencias_verificadas": dependencies_outcome.error is None,
                    "proposito_documentado": documented_purpose,
                    "proposito_funcional_inferido": None,
                    "permiso_uso_esquema": bool(has_schema_usage),
                    "permiso_lectura": bool(has_select),
                }
            )

    inaccessible_definitions = sum(not view["definicion_accesible"] for view in views)
    without_schema_usage = sum(not view["permiso_uso_esquema"] for view in views)
    without_select = sum(not view["permiso_lectura"] for view in views)
    if inaccessible_definitions:
        warnings.append(
            f"No fue posible obtener la definición de {inaccessible_definitions} vistas visibles."
        )
    if without_schema_usage:
        warnings.append(
            f"Se detectaron {without_schema_usage} vistas en esquemas sin permiso USAGE."
        )
    if without_select:
        warnings.append(
            f"Se inventariaron {without_select} vistas sin permiso SELECT para el rol conectado."
        )

    coverage_verified = (
        inventory_outcome.error is None
        and dependencies_outcome.error is None
        and not inaccessible_definitions
        and not without_schema_usage
        and not without_select
    )
    evidence: list[ActivityEvidence] = []
    if inventory_outcome.rows is not None:
        evidence.append(
            ActivityEvidence(
                clave="inventario_vistas",
                consulta_id="view_inventory_and_dependencies",
                disponibilidad="disponible" if views else "sin_datos",
                naturaleza="calculada",
                datos={
                    "vistas": views,
                    "total_vistas": sum(view["tipo"] == "vista" for view in views),
                    "total_vistas_materializadas": sum(
                        view["tipo"] == "vista_materializada" for view in views
                    ),
                    "inventario_completo_verificable": coverage_verified,
                },
            )
        )

    status = _activity_status(outcomes)
    if status == "error_tecnico":
        evidence_status: EvidenceStatus = "no_obtenida"
    elif status == "parcial" or not coverage_verified:
        evidence_status = "insuficiente"
    elif not views:
        evidence_status = "sin_datos"
    else:
        evidence_status = "suficiente"
    return ActivityResult(
        identificador="2.7",
        numero_original=activity.numero,
        nombre_original=activity.actividad,
        fase_original=activity.fase,
        estado_ejecucion=status,
        estado_evidencia=evidence_status,
        evidencias=evidence,
        advertencias=warnings,
        limitaciones=limitations,
        duracion_ms=round((time.perf_counter() - started) * 1000),
    )


def _trigger_events(trigger_type: int) -> list[str]:
    event_bits = ((4, "insert"), (8, "delete"), (16, "update"), (32, "truncate"))
    return [name for bit, name in event_bits if trigger_type & bit]


def _trigger_timing(trigger_type: int) -> str:
    if trigger_type & 2:
        return "before"
    if trigger_type & 64:
        return "instead_of"
    return "after"


def _trigger_state(value: str) -> str:
    return {
        "O": "origin_local",
        "D": "deshabilitado",
        "R": "replica",
        "A": "siempre",
    }.get(value, "desconocido")


async def _execute_programmable_inventory(
    connection: psycopg.AsyncConnection,
    activity: ChecklistActivityReference,
) -> ActivityResult:
    started = time.perf_counter()
    routines_outcome = await _fetch_rows(connection, ROUTINE_INVENTORY_SQL)
    dependencies_outcome = await _fetch_rows(connection, ROUTINE_DEPENDENCIES_SQL)
    triggers_outcome = await _fetch_rows(connection, TABLE_TRIGGER_INVENTORY_SQL)
    event_triggers_outcome = await _fetch_rows(connection, EVENT_TRIGGER_INVENTORY_SQL)
    outcomes = [
        routines_outcome,
        dependencies_outcome,
        triggers_outcome,
        event_triggers_outcome,
    ]
    warnings = [
        warning
        for query_id, outcome in (
            ("routine_inventory", routines_outcome),
            ("routine_dependencies", dependencies_outcome),
            ("table_trigger_inventory", triggers_outcome),
            ("event_trigger_inventory", event_triggers_outcome),
        )
        if (warning := _technical_warning(query_id, outcome)) is not None
    ]
    limitations = [
        "Las rutinas y triggers se inventarían sin ejecutar sus funciones ni extraer sus cuerpos.",
        "Las dependencias son únicamente las registradas por PostgreSQL; SQL dinámico y referencias resueltas en ejecución pueden no aparecer.",
        "La cobertura se limita a objetos y metadatos visibles para el rol conectado.",
    ]

    dependencies: dict[int, list[dict[str, str]]] = defaultdict(list)
    if dependencies_outcome.rows is not None:
        seen_dependencies: set[tuple[int, str, str, str]] = set()
        for routine_oid, dependency_type, catalog, description in dependencies_outcome.rows:
            key = (int(routine_oid), dependency_type, catalog, description)
            if key in seen_dependencies:
                continue
            seen_dependencies.add(key)
            dependencies[int(routine_oid)].append(
                {
                    "tipo_dependencia": dependency_type,
                    "catalogo": catalog,
                    "objeto": description,
                }
            )

    routine_types = {"f": "funcion", "p": "procedimiento", "w": "funcion_ventana"}
    volatility = {"i": "inmutable", "s": "estable", "v": "volatil"}
    parallel = {"s": "segura", "r": "restringida", "u": "insegura"}
    routines: list[dict[str, Any]] = []
    if routines_outcome.rows is not None:
        for row in routines_outcome.rows:
            (
                routine_oid,
                schema,
                name,
                qualified_name,
                kind,
                language,
                arguments,
                result_type,
                security_definer,
                volatility_code,
                parallel_code,
                has_execute,
                extension,
            ) = row
            routines.append(
                {
                    "esquema": schema,
                    "nombre": name,
                    "nombre_completo": qualified_name,
                    "firma_argumentos": arguments,
                    "tipo": routine_types[kind],
                    "lenguaje": language,
                    "tipo_retorno": result_type,
                    "security_definer": bool(security_definer),
                    "volatilidad": volatility.get(volatility_code, "desconocida"),
                    "ejecucion_paralela": parallel.get(parallel_code, "desconocida"),
                    "permiso_ejecucion": bool(has_execute),
                    "origen": "extension" if extension else "propio",
                    "extension": extension,
                    "dependencias_catalogadas": dependencies.get(int(routine_oid), []),
                    "dependencias_verificadas": dependencies_outcome.error is None,
                }
            )

    triggers: list[dict[str, Any]] = []
    if triggers_outcome.rows is not None:
        for row in triggers_outcome.rows:
            (
                _,
                schema,
                relation,
                qualified_relation,
                name,
                trigger_type,
                enabled,
                is_internal,
                parent_oid,
                parent_name,
                function_schema,
                function_name,
                function_arguments,
                extension,
            ) = row
            trigger_type = int(trigger_type)
            triggers.append(
                {
                    "nombre": name,
                    "clase": "trigger_relacion",
                    "esquema_relacion": schema,
                    "relacion": relation,
                    "relacion_completa": qualified_relation,
                    "funcion_asociada": {
                        "esquema": function_schema,
                        "nombre": function_name,
                        "firma_argumentos": function_arguments,
                    },
                    "eventos": _trigger_events(trigger_type),
                    "momento": _trigger_timing(trigger_type),
                    "nivel": "fila" if trigger_type & 1 else "sentencia",
                    "estado": _trigger_state(enabled),
                    "es_interno": bool(is_internal),
                    "es_clon_particion": bool(parent_oid),
                    "trigger_padre": parent_name,
                    "origen": "extension" if extension else "propio",
                    "extension": extension,
                }
            )

    if event_triggers_outcome.rows is not None:
        for row in event_triggers_outcome.rows:
            (
                _,
                name,
                event,
                enabled,
                tags,
                function_schema,
                function_name,
                function_arguments,
                extension,
            ) = row
            triggers.append(
                {
                    "nombre": name,
                    "clase": "event_trigger",
                    "esquema_relacion": None,
                    "relacion": None,
                    "relacion_completa": None,
                    "funcion_asociada": {
                        "esquema": function_schema,
                        "nombre": function_name,
                        "firma_argumentos": function_arguments,
                    },
                    "eventos": [event],
                    "etiquetas_comando": list(tags) if tags is not None else None,
                    "momento": None,
                    "nivel": "base_datos",
                    "estado": _trigger_state(enabled),
                    "es_interno": False,
                    "es_clon_particion": False,
                    "trigger_padre": None,
                    "origen": "extension" if extension else "propio",
                    "extension": extension,
                }
            )

    without_execute = sum(not routine["permiso_ejecucion"] for routine in routines)
    if without_execute:
        warnings.append(
            f"Se inventariaron {without_execute} rutinas sin permiso EXECUTE para el rol conectado; no fueron ejecutadas."
        )
    coverage_verified = all(outcome.error is None for outcome in outcomes)
    if dependencies_outcome.error is not None:
        warnings.append(
            "No pudo verificarse la cobertura de dependencias de las rutinas inventariadas."
        )
    evidence: list[ActivityEvidence] = []
    if any(
        outcome.rows is not None
        for outcome in (routines_outcome, triggers_outcome, event_triggers_outcome)
    ):
        evidence.append(
            ActivityEvidence(
                clave="inventario_objetos_programables",
                consulta_id="programmable_objects_inventory",
                disponibilidad="disponible" if routines or triggers else "sin_datos",
                naturaleza="calculada",
                datos={
                    "rutinas": routines,
                    "triggers": triggers,
                    "total_funciones": sum(
                        routine["tipo"] in {"funcion", "funcion_ventana"}
                        for routine in routines
                    ),
                    "total_procedimientos": sum(
                        routine["tipo"] == "procedimiento" for routine in routines
                    ),
                    "total_triggers_relacion": sum(
                        trigger["clase"] == "trigger_relacion" for trigger in triggers
                    ),
                    "total_event_triggers": sum(
                        trigger["clase"] == "event_trigger" for trigger in triggers
                    ),
                    "inventario_completo_verificable": coverage_verified,
                },
            )
        )

    status = _activity_status(outcomes)
    if status == "error_tecnico":
        evidence_status: EvidenceStatus = "no_obtenida"
    elif status == "parcial" or not coverage_verified:
        evidence_status = "insuficiente"
    elif not routines and not triggers:
        evidence_status = "sin_datos"
    else:
        evidence_status = "suficiente"
    return ActivityResult(
        identificador="2.8",
        numero_original=activity.numero,
        nombre_original=activity.actividad,
        fase_original=activity.fase,
        estado_ejecucion=status,
        estado_evidencia=evidence_status,
        evidencias=evidence,
        advertencias=warnings,
        limitaciones=limitations,
        duracion_ms=round((time.perf_counter() - started) * 1000),
    )


def _unsupported_activity(activity: ChecklistActivityReference) -> ActivityResult:
    return ActivityResult(
        identificador=activity.numero,
        numero_original=activity.numero,
        nombre_original=activity.actividad,
        fase_original=activity.fase,
        estado_ejecucion="sin_automatizacion_configurada",
        estado_evidencia="no_obtenida",
        evidencias=[],
        advertencias=[],
        limitaciones=["No existe una automatización configurada para este identificador."],
        duracion_ms=0,
    )


async def execute_audit_activities(
    connection: psycopg.AsyncConnection,
    activities: list[ChecklistActivityReference],
) -> AuditExecutionResult:
    started = time.perf_counter()
    results: list[ActivityResult] = []
    for activity in activities:
        if activity.numero == "2.1":
            result = await _execute_table_inventory(connection, activity)
        elif activity.numero == "2.3":
            result = await _execute_volumetry(connection, activity)
        elif activity.numero == "2.6":
            result = await _execute_audit_table_candidates(connection, activity)
        elif activity.numero == "2.7":
            result = await _execute_view_inventory(connection, activity)
        elif activity.numero == "2.8":
            result = await _execute_programmable_inventory(connection, activity)
        else:
            result = _unsupported_activity(activity)
        results.append(result)

    return AuditExecutionResult(
        catalogo_version=AUDIT_CATALOG_VERSION,
        actividades=results,
        duracion_total_ms=round((time.perf_counter() - started) * 1000),
    )
