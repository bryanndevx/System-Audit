import asyncio
import re
import time
import unicodedata
from datetime import UTC, datetime
from collections import defaultdict
from dataclasses import dataclass
from contextvars import ContextVar
from typing import Any, Literal
from uuid import UUID

import psycopg
from pydantic import BaseModel, Field, field_validator
from psycopg import errors

from app.ai_diagnostics import AiNarrative
from app.audit_queries import (
    ACTIVE_QUERY_SNAPSHOT_SQL,
    COLUMN_CHECK_CONSTRAINTS_SQL,
    COLUMN_DICTIONARY_SQL,
    DATABASE_SIZE_SQL,
    DATABASE_STATISTICS_CONTEXT_SQL,
    DOMAIN_CONSTRAINTS_SQL,
    ENUM_VALUES_SQL,
    ENGINE_CONFIGURATION_SQL,
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
from app.external_connections import SET_TRANSACTION_READ_ONLY_SQL

AUDIT_CATALOG_VERSION = "catalogos-postgresql-v3"
QUERY_OPERATION_TIMEOUT_SECONDS = 6
MAX_QUERY_ROWS = 5000
_query_cache: ContextVar[dict | None] = ContextVar("audit_query_cache", default=None)
_query_trace: ContextVar[list | None] = ContextVar("audit_query_trace", default=None)

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
    "n": "not_null",
    "p": "primary_key",
    "u": "unique",
    "x": "exclusion",
}

STAGING_NAME_HINTS = frozenset({"stage", "staging", "stg", "temp", "tmp", "temporal"})
CATALOG_NAME_HINTS = frozenset(
    {"catalog", "catalogo", "lookup", "parameter", "parametro", "parametria", "reference"}
)
MASTER_NAME_HINTS = frozenset({"master", "maestra", "maestro"})
CODE_COLUMN_HINTS = frozenset({"code", "codigo", "key", "clave"})
TIME_COLUMN_HINTS = frozenset(
    {"created_at", "date", "event_at", "fecha", "occurred_at", "timestamp", "updated_at"}
)
SENSITIVE_COLUMN_HINTS = {
    "pii": frozenset(
        {
            "apellido",
            "birthdate",
            "correo",
            "direccion",
            "dni",
            "documento",
            "email",
            "fecha_nacimiento",
            "phone",
            "telefono",
        }
    ),
    "salud": frozenset(
        {
            "clinical",
            "diagnosis",
            "diagnostico",
            "historia_clinica",
            "paciente",
            "patient",
            "salud",
            "tratamiento",
        }
    ),
    "financiero": frozenset(
        {
            "bank_account",
            "card_number",
            "cuenta_bancaria",
            "iban",
            "salary",
            "salario",
            "tarjeta",
        }
    ),
    "credencial": frozenset(
        {
            "api_key",
            "contrasena",
            "credential",
            "password",
            "password_hash",
            "secret",
            "token",
        }
    ),
}
DEPRECATION_HINTS = frozenset(
    {
        "deprecated",
        "deprecado",
        "desuso",
        "eliminar",
        "legacy",
        "obsolete",
        "obsoleto",
        "unused",
    }
)
FOREIGN_KEY_ACTIONS = {
    "a": "sin_accion",
    "r": "restringir",
    "c": "cascada",
    "n": "establecer_nulo",
    "d": "establecer_predeterminado",
}

ExecutionStatus = Literal[
    "completada",
    "parcial",
    "error_tecnico",
    "sin_automatizacion_configurada",
    "no_ejecutable",
]
EvidenceStatus = Literal["suficiente", "insuficiente", "sin_datos", "no_obtenida"]
EvidenceAvailability = Literal["disponible", "sin_datos", "no_disponible"]
EvidenceNature = Literal["exacta", "estimada", "calculada", "no_disponible"]


class ChecklistActivityReference(BaseModel):
    numero: str = Field(min_length=1, max_length=50)
    actividad: str = Field(min_length=1, max_length=500)
    fase: str = Field(min_length=1, max_length=250)
    entregable_esperado: str | None = Field(default=None, max_length=1000)
    prioridad: str | None = Field(default=None, max_length=50)
    numero_hoja: str | None = Field(default=None, max_length=50)

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
    entregable_esperado: str | None = None
    prioridad_original: str | None = None
    numero_hoja: str | None = None
    grado_automatizacion: Literal["total", "parcial", "no_automatizada", "error", "sin_configuracion"] | None = None
    consultas: list[dict[str, Any]] = Field(default_factory=list)
    estado_entregable: Literal["completo", "requiere_informacion_externa", "evidencia_incompleta", "error_tecnico", "sin_configuracion"] | None = None
    informacion_obtenida: list[str] = Field(default_factory=list)
    informacion_faltante: list[str] = Field(default_factory=list)
    estado_actividad: Literal['completada', 'incompleta'] | None = None
    motivo_incompleta: Literal['informacion_externa','error_tecnico','permisos','limite_recursos','ia_no_disponible','sin_configuracion','evidencia_insuficiente'] | None = None
    estado_ejecucion: ExecutionStatus
    estado_evidencia: EvidenceStatus
    evidencias: list[ActivityEvidence]
    advertencias: list[str]
    limitaciones: list[str]
    duracion_ms: int
    redaccion_ia: AiNarrative = Field(default_factory=AiNarrative)


class AuditSummary(BaseModel):
    total: int
    automatizadas: int
    parciales: int
    errores_sql: int
    sin_configuracion: int
    errores_ia: int
    porcentaje_automatizacion: float
    no_ejecutables: int = 0
    porcentaje_parcial: float = 0
    requieren_informacion_externa: int = 0
    con_evidencia_postgresql: int = 0
    completadas: int = 0
    incompletas: int = 0


class AuditStorageInfo(BaseModel):
    estado: Literal["guardada", "error", "no_guardada"] = "no_guardada"
    id: UUID | None = None
    fecha: datetime | None = None
    mensaje: str | None = None


class AuditExecutionResult(BaseModel):
    catalogo_version: str
    actividades: list[ActivityResult]
    duracion_total_ms: int
    duracion_ia_ms: int = 0
    resumen: AuditSummary | None = None
    almacenamiento: AuditStorageInfo = Field(default_factory=AuditStorageInfo)
    nombre_aplicacion: str | None = None
    entorno_auditado: str | None = None
    fecha_ejecucion: datetime | None = None
    checklist_version: str | None = None
    checklist_huella: str | None = None
    criterios_evaluacion_version: str | None = None
    duracion_ejecucion_ms: int | None = None


@dataclass(frozen=True)
class QueryOutcome:
    rows: list[tuple[Any, ...]] | None
    error: Literal["permisos", "timeout", "ejecucion", "limite"] | None = None
    columns: tuple[str, ...] = ()


async def _fetch_rows(
    connection: psycopg.AsyncConnection,
    statement: str,
) -> QueryOutcome:
    from app import audit_queries, audit_extended_queries, audit_technical_queries
    query_id = next((name.removesuffix("_SQL").lower()
                     for module in (audit_queries, audit_extended_queries, audit_technical_queries)
                     for name, sql in vars(module).items()
                     if name.endswith("_SQL") and sql == statement), None)
    if query_id is None:
        raise ValueError("Consulta fuera del catálogo revisado.")
    cache = _query_cache.get()
    trace = _query_trace.get()
    if cache is not None and statement in cache:
        outcome = cache[statement]
        if trace is not None:
            trace.append({"consulta_id": query_id, "estado": outcome.error or "completada", "filas": len(outcome.rows or []), "reutilizada": True, "duracion_ms": 0})
        return outcome
    started = time.perf_counter()
    rows: list[tuple[Any, ...]] | None = None
    query_error = None
    columns: tuple[str, ...] = ()
    try:
        async with asyncio.timeout(QUERY_OPERATION_TIMEOUT_SECONDS):
            async with connection.cursor() as cursor:
                await cursor.execute(SET_TRANSACTION_READ_ONLY_SQL)
                await cursor.execute(statement)
                columns = tuple(column.name for column in (getattr(cursor, "description", None) or ()))
                rows = list(await cursor.fetchmany(MAX_QUERY_ROWS + 1))
                if len(rows) > MAX_QUERY_ROWS:
                    rows = rows[:MAX_QUERY_ROWS]
                    query_error = "limite"
    except (TimeoutError, errors.QueryCanceled):
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
    outcome = QueryOutcome(rows=rows, error=query_error, columns=columns)
    if cache is not None:
        cache[statement] = outcome
    if trace is not None:
        trace.append({"consulta_id": query_id, "estado": query_error or "completada", "filas": len(rows or []), "reutilizada": False, "duracion_ms": round((time.perf_counter()-started)*1000)})
    return outcome


def _technical_warning(query_id: str, outcome: QueryOutcome) -> str | None:
    if outcome.error == "limite":
        return f"La comprobación {query_id} excedió {MAX_QUERY_ROWS} filas; la evidencia es parcial y sus totales corresponden al subconjunto obtenido."
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
    if successful or any(outcome.rows is not None for outcome in outcomes):
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


def _table_records(rows: list[tuple[Any, ...]] | None) -> dict[int, dict[str, Any]]:
    tables: dict[int, dict[str, Any]] = {}
    for row in rows or []:
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
                "oid": relation_oid,
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
                "claves_foraneas_salientes": [],
                "claves_foraneas_entrantes": [],
            },
        )
        if parent_name and parent_name not in table["padres"]:
            table["padres"].append(parent_name)
    return tables


def _attach_columns(
    tables: dict[int, dict[str, Any]], rows: list[tuple[Any, ...]] | None
) -> None:
    for row in rows or []:
        relation_oid, _, _, _, position, column_name, data_type, not_null = row
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


def _attach_constraints(
    tables: dict[int, dict[str, Any]], rows: list[tuple[Any, ...]] | None
) -> None:
    for relation_oid, _, name, constraint_type, columns in rows or []:
        table = tables.get(int(relation_oid))
        if table is not None:
            table["restricciones"].append(
                {
                    "nombre": name,
                    "tipo": CONSTRAINT_TYPES.get(constraint_type, constraint_type),
                    "columnas": list(columns or []),
                }
            )


def _foreign_key_records(
    rows: list[tuple[Any, ...]] | None,
) -> list[dict[str, Any]]:
    foreign_keys: list[dict[str, Any]] = []
    seen: set[int] = set()
    for row in rows or []:
        (
            constraint_oid,
            source_oid,
            target_oid,
            name,
            source_name,
            target_name,
            source_columns,
            target_columns,
            update_action,
            delete_action,
        ) = row
        constraint_oid = int(constraint_oid)
        if constraint_oid in seen:
            continue
        seen.add(constraint_oid)
        foreign_keys.append(
            {
                "oid": constraint_oid,
                "nombre": name,
                "origen_oid": int(source_oid),
                "destino_oid": int(target_oid),
                "tabla_origen": source_name,
                "tabla_destino": target_name,
                "columnas_origen": list(source_columns or []),
                "columnas_destino": list(target_columns or []),
                "accion_actualizacion": FOREIGN_KEY_ACTIONS.get(update_action, "desconocida"),
                "accion_eliminacion": FOREIGN_KEY_ACTIONS.get(delete_action, "desconocida"),
            }
        )
    return foreign_keys


def _attach_foreign_keys(
    tables: dict[int, dict[str, Any]], foreign_keys: list[dict[str, Any]]
) -> None:
    for foreign_key in foreign_keys:
        source = tables.get(foreign_key["origen_oid"])
        target = tables.get(foreign_key["destino_oid"])
        public_key = {
            key: value
            for key, value in foreign_key.items()
            if key not in {"oid", "origen_oid", "destino_oid"}
        }
        if source is not None:
            source["claves_foraneas_salientes"].append(public_key)
        if target is not None:
            target["claves_foraneas_entrantes"].append(public_key)


def _audit_indicators(table: dict[str, Any]) -> tuple[dict[str, Any], int]:
    name_hints = sorted(_identifier_tokens(table["tabla"]) & AUDIT_TABLE_NAME_HINTS)
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
    specific_column_groups = set(column_groups) - {"momento"}
    has_audit_context = bool(name_hints or specific_column_groups)
    indicator_count = int(bool(name_hints)) + len(specific_column_groups)
    if has_audit_context and "momento" in column_groups:
        indicator_count += 1
    if has_audit_context:
        indicator_count += len(structure_hints)
    return (
        {
            "nombre_tabla": name_hints,
            "grupos_columnas": column_groups,
            "restricciones_sobre_columnas_indicio": constraint_hints,
            "estructura": structure_hints,
        },
        indicator_count,
    )


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


def _classify_table(table: dict[str, Any]) -> dict[str, Any]:
    tokens = _identifier_tokens(f"{table['esquema']} {table['tabla']}")
    column_names = {
        _normalized_identifier(column["nombre"]) for column in table["columnas"]
    }
    time_columns = sorted(column_names & TIME_COLUMN_HINTS)
    code_columns = sorted(column_names & CODE_COLUMN_HINTS)
    unique_columns = {
        column
        for constraint in table["restricciones"]
        if constraint["tipo"] in {"primary_key", "unique"}
        for column in constraint["columnas"]
    }
    signals: dict[str, list[str]] = defaultdict(list)

    audit_indicators, audit_count = _audit_indicators(table)
    if audit_count:
        if audit_indicators["nombre_tabla"]:
            signals["auditoria"].append("nombre técnico de auditoría/log/trace")
        signals["auditoria"].extend(
            f"grupo de columnas: {group}"
            for group in audit_indicators["grupos_columnas"]
        )
        signals["auditoria"].extend(audit_indicators["estructura"])

    staging_names = sorted(tokens & STAGING_NAME_HINTS)
    if staging_names:
        signals["temporal_staging"].append(
            f"nombre o esquema con indicios: {', '.join(staging_names)}"
        )
    if table.get("persistencia") == "u":
        signals["temporal_staging"].append("relación UNLOGGED")

    if len(table["claves_foraneas_salientes"]) >= 2:
        signals["transaccional"].append("dos o más claves foráneas salientes")
    if time_columns:
        signals["transaccional"].append(
            f"columnas temporales técnicas: {', '.join(time_columns)}"
        )
    if table["tipo"] == "tabla_particionada" and time_columns:
        signals["transaccional"].append("particionamiento con columna temporal")

    catalog_names = sorted(tokens & CATALOG_NAME_HINTS)
    if catalog_names:
        signals["catalogo_parametria"].append(
            f"nombre o esquema con indicios: {', '.join(catalog_names)}"
        )
    unique_code_columns = sorted(set(code_columns) & unique_columns)
    if unique_code_columns:
        signals["catalogo_parametria"].append(
            f"código o clave única: {', '.join(unique_code_columns)}"
        )

    master_names = sorted(tokens & MASTER_NAME_HINTS)
    if master_names:
        signals["maestra"].append(
            f"nombre o esquema con indicios: {', '.join(master_names)}"
        )

    inbound_count = len(table["claves_foraneas_entrantes"])
    if inbound_count:
        if signals.get("catalogo_parametria"):
            signals["catalogo_parametria"].append(
                f"referenciada por {inbound_count} claves foráneas"
            )
        if signals.get("maestra"):
            signals["maestra"].append(
                f"referenciada por {inbound_count} claves foráneas"
            )

    supported = sorted(category for category, items in signals.items() if len(items) >= 2)
    possible = sorted(category for category, items in signals.items() if items)
    if len(supported) == 1:
        classification = supported[0]
        support_level = "sustentada_por_indicios"
        alternatives: list[str] = []
    elif len(supported) > 1:
        classification = "indeterminada"
        support_level = "indicios_contradictorios"
        alternatives = supported
    elif len(possible) == 1:
        classification = possible[0]
        support_level = "probable"
        alternatives = []
    else:
        classification = "indeterminada"
        support_level = "indicios_ambiguos" if possible else "sin_indicios_suficientes"
        alternatives = possible

    if not possible and inbound_count:
        alternatives = ["catalogo_parametria", "maestra"]
        support_level = "indicios_ambiguos"
        signals["indeterminada"].append(
            "las referencias entrantes no distinguen entre tabla maestra y catálogo"
        )

    return {
        "clasificacion_tecnica": classification,
        "nivel_sustento": support_level,
        "categorias_alternativas": alternatives,
        "justificacion_tecnica": dict(signals),
        "indicadores_auditoria": audit_indicators,
        "clasificacion_empresarial_confirmada": False,
        "validacion_empresarial": "pendiente",
    }


async def _execute_table_classification(
    connection: psycopg.AsyncConnection,
    activity: ChecklistActivityReference,
) -> ActivityResult:
    started = time.perf_counter()
    tables_outcome = await _fetch_rows(connection, TABLE_INVENTORY_SQL)
    columns_outcome = await _fetch_rows(connection, TABLE_COLUMNS_SQL)
    constraints_outcome = await _fetch_rows(connection, TABLE_CONSTRAINTS_SQL)
    foreign_keys_outcome = await _fetch_rows(connection, TABLE_FOREIGN_KEYS_SQL)
    properties_outcome = await _fetch_rows(connection, TABLE_RELATION_PROPERTIES_SQL)
    outcomes = [
        tables_outcome,
        columns_outcome,
        constraints_outcome,
        foreign_keys_outcome,
        properties_outcome,
    ]
    query_outcomes = (
        ("table_inventory", tables_outcome),
        ("table_columns", columns_outcome),
        ("table_constraints", constraints_outcome),
        ("table_foreign_keys", foreign_keys_outcome),
        ("table_relation_properties", properties_outcome),
    )
    warnings = [
        warning
        for query_id, outcome in query_outcomes
        if (warning := _technical_warning(query_id, outcome)) is not None
    ]
    limitations = [
        "La clasificación es técnica y conservadora; no confirma el propósito empresarial de las tablas.",
        "Los nombres, tamaños y estructuras son indicios y no pruebas funcionales por sí solos.",
        "Las categorías ambiguas o contradictorias permanecen indeterminadas hasta validación empresarial.",
    ]

    tables = _table_records(tables_outcome.rows)
    _attach_columns(tables, columns_outcome.rows)
    _attach_constraints(tables, constraints_outcome.rows)
    foreign_keys = _foreign_key_records(foreign_keys_outcome.rows)
    _attach_foreign_keys(tables, foreign_keys)
    for relation_oid, persistence in properties_outcome.rows or []:
        table = tables.get(int(relation_oid))
        if table is not None:
            table["persistencia"] = persistence

    matrix: list[dict[str, Any]] = []
    by_name = {table["nombre_completo"]: table for table in tables.values()}
    classifications = {
        relation_oid: _classify_table(table) for relation_oid, table in tables.items()
    }
    for relation_oid, table in tables.items():
        classification = classifications[relation_oid]
        if table["es_particion"] and table["padres"]:
            parent = by_name.get(table["padres"][0])
            if parent is not None:
                inherited = classifications[parent["oid"]]
                classification = {
                    **inherited,
                    "nivel_sustento": "heredada_de_padre",
                    "justificacion_tecnica": {
                        "herencia": [f"clasificación heredada de {parent['nombre_completo']}"]
                    },
                }
        matrix.append(
            {
                "esquema": table["esquema"],
                "tabla": table["tabla"],
                "nombre_completo": table["nombre_completo"],
                "tipo": table["tipo"],
                "es_particion": table["es_particion"],
                "padres": table["padres"],
                **classification,
                "permiso_uso_esquema": table["permiso_uso_esquema"],
                "permiso_lectura": table["permiso_lectura"],
            }
        )
    matrix.sort(key=lambda item: item["nombre_completo"])

    status = _activity_status(outcomes)
    evidence: list[ActivityEvidence] = []
    if tables_outcome.rows is not None:
        evidence.append(
            ActivityEvidence(
                clave="matriz_clasificacion",
                consulta_id="table_classification_evidence",
                disponibilidad="disponible" if matrix else "sin_datos",
                naturaleza="calculada",
                datos={
                    "tablas": matrix,
                    "total_tablas": len(matrix),
                    "total_indeterminadas": sum(
                        item["clasificacion_tecnica"] == "indeterminada"
                        for item in matrix
                    ),
                    "clasificaciones_empresariales_confirmadas": 0,
                    "cobertura_entregable": "parcial",
                },
            )
        )
    if status == "error_tecnico":
        evidence_status: EvidenceStatus = "no_obtenida"
    elif status == "parcial":
        evidence_status = "insuficiente"
    elif not matrix:
        evidence_status = "sin_datos"
    else:
        evidence_status = "insuficiente"
    return ActivityResult(
        identificador="2.2",
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


async def _execute_table_retirement_candidates(
    connection: psycopg.AsyncConnection,
    activity: ChecklistActivityReference,
) -> ActivityResult:
    started = time.perf_counter()
    tables_outcome = await _fetch_rows(connection, TABLE_INVENTORY_SQL)
    statistics_context_outcome = await _fetch_rows(
        connection, DATABASE_STATISTICS_CONTEXT_SQL
    )
    usage_outcome = await _fetch_rows(connection, TABLE_USAGE_STATISTICS_SQL)
    foreign_keys_outcome = await _fetch_rows(connection, TABLE_FOREIGN_KEYS_SQL)
    view_dependencies_outcome = await _fetch_rows(connection, VIEW_DEPENDENCIES_SQL)
    triggers_outcome = await _fetch_rows(connection, TABLE_TRIGGER_INVENTORY_SQL)
    routine_dependencies_outcome = await _fetch_rows(
        connection, TABLE_ROUTINE_DEPENDENCIES_SQL
    )
    outcomes = [
        tables_outcome,
        statistics_context_outcome,
        usage_outcome,
        foreign_keys_outcome,
        view_dependencies_outcome,
        triggers_outcome,
        routine_dependencies_outcome,
    ]
    query_outcomes = (
        ("table_inventory", tables_outcome),
        ("statistics_context", statistics_context_outcome),
        ("table_usage_statistics", usage_outcome),
        ("table_foreign_keys", foreign_keys_outcome),
        ("view_dependencies", view_dependencies_outcome),
        ("table_trigger_inventory", triggers_outcome),
        ("table_routine_dependencies", routine_dependencies_outcome),
    )
    warnings = [
        warning
        for query_id, outcome in query_outcomes
        if (warning := _technical_warning(query_id, outcome)) is not None
    ]
    limitations = [
        "Los contadores acumulativos no demuestran uso histórico ni uso desde código externo.",
        "Una tabla sin actividad observada o dependencias catalogadas no está confirmada como obsoleta o huérfana.",
        "No existe todavía una ventana representativa aprobada ni mediciones históricas comparables.",
        "No se propone ni ejecuta eliminación automática de objetos.",
    ]

    tables = _table_records(tables_outcome.rows)
    foreign_keys = _foreign_key_records(foreign_keys_outcome.rows)
    _attach_foreign_keys(tables, foreign_keys)
    dependencies: dict[int, set[str]] = defaultdict(set)
    for foreign_key in foreign_keys:
        dependencies[foreign_key["origen_oid"]].add(
            f"fk_saliente:{foreign_key['nombre']}"
        )
        dependencies[foreign_key["destino_oid"]].add(
            f"fk_entrante:{foreign_key['nombre']}"
        )
    for view_oid, relation_oid, *_ in view_dependencies_outcome.rows or []:
        dependencies[int(relation_oid)].add(f"vista_dependiente_oid:{int(view_oid)}")
    table_oid_by_name = {
        table["nombre_completo"]: relation_oid for relation_oid, table in tables.items()
    }
    for row in triggers_outcome.rows or []:
        trigger_oid, _, _, qualified_name, trigger_name, *_ = row
        relation_oid = table_oid_by_name.get(qualified_name)
        if relation_oid is not None:
            dependencies[relation_oid].add(
                f"trigger:{trigger_name}:{int(trigger_oid)}"
            )
    for relation_oid, routine_oid, schema, name, arguments, _ in (
        routine_dependencies_outcome.rows or []
    ):
        dependencies[int(relation_oid)].add(
            f"rutina:{schema}.{name}({arguments}):{int(routine_oid)}"
        )

    usage_by_oid: dict[int, dict[str, Any]] = {}
    children: dict[int, list[int]] = defaultdict(list)
    for row in usage_outcome.rows or []:
        (
            relation_oid,
            schema,
            name,
            qualified_name,
            relkind,
            is_partition,
            parent_oid,
            seq_scan,
            idx_scan,
            inserted,
            updated,
            deleted,
            live_rows,
            dead_rows,
            last_vacuum,
            last_autovacuum,
            last_analyze,
            last_autoanalyze,
        ) = row
        relation_oid = int(relation_oid)
        normalized_parent = int(parent_oid) if parent_oid is not None else None
        usage_by_oid[relation_oid] = {
            "oid": relation_oid,
            "parent_oid": normalized_parent,
            "esquema": schema,
            "tabla": name,
            "nombre_completo": qualified_name,
            "tipo": _relation_type(relkind),
            "es_particion": bool(is_partition),
            "contadores_propios": {
                "seq_scan": seq_scan,
                "idx_scan": idx_scan,
                "insertadas": inserted,
                "actualizadas": updated,
                "eliminadas": deleted,
            },
            "filas_estimadas": {"vivas": live_rows, "muertas": dead_rows},
            "mantenimiento": {
                "ultimo_vacuum": last_vacuum,
                "ultimo_autovacuum": last_autovacuum,
                "ultimo_analyze": last_analyze,
                "ultimo_autoanalyze": last_autoanalyze,
            },
        }
        if normalized_parent is not None:
            children[normalized_parent].append(relation_oid)

    counter_names = ("seq_scan", "idx_scan", "insertadas", "actualizadas", "eliminadas")

    def aggregate_counters(relation_oid: int, visited: set[int]) -> dict[str, int | None]:
        relation = usage_by_oid[relation_oid]
        related = [relation]
        for child_oid in children.get(relation_oid, []):
            if child_oid in visited or child_oid not in usage_by_oid:
                continue
            visited.add(child_oid)
            child_aggregate = aggregate_counters(child_oid, visited)
            related.append({"contadores_propios": child_aggregate})
        result: dict[str, int | None] = {}
        for counter_name in counter_names:
            values = [
                item["contadores_propios"].get(counter_name) for item in related
            ]
            known_values = [int(value) for value in values if value is not None]
            result[counter_name] = sum(known_values) if known_values else None
        return result

    context = (
        statistics_context_outcome.rows[0]
        if statistics_context_outcome.rows
        else None
    )
    track_counts = context[0] if context else None
    stats_reset = context[1] if context else None
    if track_counts is not True:
        warnings.append(
            "No se confirmó track_counts activo; los contadores de uso no son concluyentes."
        )
    if stats_reset is None:
        warnings.append(
            "No se conoce el inicio de la ventana estadística; no puede evaluarse su representatividad."
        )
    warnings.append(
        "No hay un criterio temporal aprobado para declarar representativa la ventana estadística."
    )

    usage_results: list[dict[str, Any]] = []
    review_tables: list[dict[str, Any]] = []
    for relation_oid, table in sorted(
        tables.items(), key=lambda item: item[1]["nombre_completo"]
    ):
        usage = usage_by_oid.get(relation_oid)
        aggregate = (
            aggregate_counters(relation_oid, {relation_oid}) if usage is not None else None
        )
        values = list(aggregate.values()) if aggregate else []
        activity_observed = any(value is not None and value > 0 for value in values)
        if activity_observed:
            usage_state = "actividad_observada"
        else:
            usage_state = "evidencia_de_uso_no_concluyente"
        technical_dependencies = sorted(dependencies.get(relation_oid, set()))
        isolated = not technical_dependencies and not table["padres"]
        item = {
            "esquema": table["esquema"],
            "tabla": table["tabla"],
            "nombre_completo": table["nombre_completo"],
            "tipo": table["tipo"],
            "es_particion": table["es_particion"],
            "estado_uso": usage_state,
            "contadores_con_particiones": aggregate,
            "contadores_propios": usage["contadores_propios"] if usage else None,
            "filas_estimadas": usage["filas_estimadas"] if usage else None,
            "mantenimiento": usage["mantenimiento"] if usage else None,
            "dependencias_tecnicas": technical_dependencies,
            "aislamiento_tecnico_observado": isolated,
            "ventana_representativa": False,
            "candidata_baja": False,
            "validacion_requerida": True,
        }
        usage_results.append(item)
        if usage_state == "evidencia_de_uso_no_concluyente" and isolated:
            review_tables.append(
                {
                    "nombre_completo": table["nombre_completo"],
                    "estado": "requiere_revision",
                    "motivo": "sin actividad observada y sin dependencias técnicas detectadas, con ventana no validada",
                    "candidata_baja": False,
                }
            )

    status = _activity_status(outcomes)
    evidence: list[ActivityEvidence] = []
    if statistics_context_outcome.rows is not None:
        evidence.append(
            ActivityEvidence(
                clave="contexto_estadisticas_uso",
                consulta_id="statistics_context",
                disponibilidad="disponible" if context else "sin_datos",
                naturaleza="exacta",
                datos={
                    "track_counts": track_counts,
                    "estadisticas_reiniciadas_en": stats_reset,
                    "ventana_representativa": False,
                    "motivo_no_representativa": "no existe un criterio temporal aprobado",
                },
            )
        )
    if tables_outcome.rows is not None:
        evidence.append(
            ActivityEvidence(
                clave="evaluacion_uso_y_dependencias",
                consulta_id="table_usage_and_dependencies",
                disponibilidad="disponible" if usage_results else "sin_datos",
                naturaleza="calculada",
                datos={
                    "tablas": usage_results,
                    "tablas_para_revision": review_tables,
                    "candidatas_baja": [],
                    "total_candidatas_baja": 0,
                    "cobertura_entregable": "parcial",
                },
            )
        )
    if status == "error_tecnico":
        evidence_status: EvidenceStatus = "no_obtenida"
    elif status == "parcial":
        evidence_status = "insuficiente"
    elif not tables:
        evidence_status = "sin_datos"
    else:
        evidence_status = "insuficiente"
    return ActivityResult(
        identificador="2.4",
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


async def _execute_table_module_matrix(
    connection: psycopg.AsyncConnection,
    activity: ChecklistActivityReference,
) -> ActivityResult:
    started = time.perf_counter()
    tables_outcome = await _fetch_rows(connection, TABLE_INVENTORY_SQL)
    foreign_keys_outcome = await _fetch_rows(connection, TABLE_FOREIGN_KEYS_SQL)
    views_outcome = await _fetch_rows(connection, VIEW_INVENTORY_SQL)
    view_dependencies_outcome = await _fetch_rows(connection, VIEW_DEPENDENCIES_SQL)
    triggers_outcome = await _fetch_rows(connection, TABLE_TRIGGER_INVENTORY_SQL)
    comments_outcome = await _fetch_rows(connection, TABLE_COMMENTS_SQL)
    routine_dependencies_outcome = await _fetch_rows(
        connection, TABLE_ROUTINE_DEPENDENCIES_SQL
    )
    outcomes = [
        tables_outcome,
        foreign_keys_outcome,
        views_outcome,
        view_dependencies_outcome,
        triggers_outcome,
        comments_outcome,
        routine_dependencies_outcome,
    ]
    query_outcomes = (
        ("table_inventory", tables_outcome),
        ("table_foreign_keys", foreign_keys_outcome),
        ("view_inventory", views_outcome),
        ("view_dependencies", view_dependencies_outcome),
        ("table_trigger_inventory", triggers_outcome),
        ("table_comments", comments_outcome),
        ("table_routine_dependencies", routine_dependencies_outcome),
    )
    warnings = [
        warning
        for query_id, outcome in query_outcomes
        if (warning := _technical_warning(query_id, outcome)) is not None
    ]
    limitations = [
        "Los esquemas y dependencias técnicas no demuestran módulos o funcionalidades empresariales.",
        "Las dependencias catalogadas no incluyen necesariamente SQL dinámico ni referencias desde código externo.",
        "Los comentarios son documentación opcional y requieren validación funcional.",
    ]

    tables = _table_records(tables_outcome.rows)
    foreign_keys = _foreign_key_records(foreign_keys_outcome.rows)
    _attach_foreign_keys(tables, foreign_keys)
    comments: dict[int, dict[str, Any]] = defaultdict(
        lambda: {"tabla": None, "columnas": []}
    )
    for relation_oid, table_comment, _, column_name, column_comment in (
        comments_outcome.rows or []
    ):
        relation_comments = comments[int(relation_oid)]
        relation_comments["tabla"] = table_comment
        if column_name is not None and column_comment is not None:
            relation_comments["columnas"].append(
                {"columna": column_name, "comentario": column_comment}
            )

    view_names = {
        int(row[0]): row[3]
        for row in views_outcome.rows or []
    }
    dependent_views: dict[int, set[str]] = defaultdict(set)
    for view_oid, relation_oid, *_ in view_dependencies_outcome.rows or []:
        dependent_views[int(relation_oid)].add(
            view_names.get(int(view_oid), f"oid:{int(view_oid)}")
        )

    table_oid_by_name = {
        table["nombre_completo"]: relation_oid for relation_oid, table in tables.items()
    }
    triggers: dict[int, dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in triggers_outcome.rows or []:
        (
            trigger_oid,
            _,
            _,
            qualified_name,
            trigger_name,
            _,
            enabled,
            internal,
            _,
            _,
            function_schema,
            function_name,
            function_arguments,
            _,
        ) = row
        relation_oid = table_oid_by_name.get(qualified_name)
        if relation_oid is not None:
            triggers[relation_oid][int(trigger_oid)] = {
                "nombre": trigger_name,
                "estado": _trigger_state(enabled),
                "interno": bool(internal),
                "funcion": f"{function_schema}.{function_name}({function_arguments})",
            }

    routines: dict[int, set[tuple[str, str, str, int]]] = defaultdict(set)
    for relation_oid, routine_oid, schema, name, arguments, _dependency_type in (
        routine_dependencies_outcome.rows or []
    ):
        routines[int(relation_oid)].add(
            (schema, name, arguments, int(routine_oid))
        )

    matrix: list[dict[str, Any]] = []
    for relation_oid, table in sorted(
        tables.items(), key=lambda item: item[1]["nombre_completo"]
    ):
        routine_items = [
            {
                "esquema": schema,
                "nombre": name,
                "firma_argumentos": arguments,
                "oid": routine_oid,
            }
            for schema, name, arguments, routine_oid in sorted(routines[relation_oid])
        ]
        matrix.append(
            {
                "esquema_tecnico": table["esquema"],
                "tabla": table["tabla"],
                "nombre_completo": table["nombre_completo"],
                "modulo_confirmado": None,
                "estado_correspondencia": "pendiente_validacion",
                "claves_foraneas_salientes": table["claves_foraneas_salientes"],
                "claves_foraneas_entrantes": table["claves_foraneas_entrantes"],
                "vistas_dependientes": sorted(dependent_views[relation_oid]),
                "triggers": list(triggers[relation_oid].values()),
                "rutinas_con_dependencia_catalogada": routine_items,
                "comentario_tabla": comments[relation_oid]["tabla"],
                "comentarios_columnas": comments[relation_oid]["columnas"],
                "padres": table["padres"],
                "permiso_uso_esquema": table["permiso_uso_esquema"],
                "permiso_lectura": table["permiso_lectura"],
            }
        )

    status = _activity_status(outcomes)
    evidence: list[ActivityEvidence] = []
    if tables_outcome.rows is not None:
        evidence.append(
            ActivityEvidence(
                clave="matriz_tabla_modulo",
                consulta_id="table_module_technical_matrix",
                disponibilidad="disponible" if matrix else "sin_datos",
                naturaleza="calculada",
                datos={
                    "tablas": matrix,
                    "total_tablas": len(matrix),
                    "correspondencias_confirmadas": 0,
                    "correspondencias_pendientes": len(matrix),
                    "cobertura_entregable": "parcial",
                },
            )
        )
    if status == "error_tecnico":
        evidence_status: EvidenceStatus = "no_obtenida"
    elif status == "parcial":
        evidence_status = "insuficiente"
    elif not matrix:
        evidence_status = "sin_datos"
    else:
        evidence_status = "insuficiente"
    return ActivityResult(
        identificador="2.5",
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

    tables = _table_records(tables_outcome.rows)
    _attach_columns(tables, columns_outcome.rows)
    _attach_constraints(tables, constraints_outcome.rows)

    candidates: list[dict[str, Any]] = []
    for table in tables.values():
        indicators, indicator_count = _audit_indicators(table)
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
                "indicadores_observables": indicators,
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


def _column_dictionary_records(
    rows: list[tuple[Any, ...]] | None,
) -> list[dict[str, Any]]:
    type_kinds = {
        "b": "base",
        "c": "compuesto",
        "d": "dominio",
        "e": "enum",
        "m": "multirango",
        "p": "pseudo",
        "r": "rango",
    }
    identity_kinds = {"a": "siempre", "d": "por_defecto"}
    generated_kinds = {"s": "almacenado", "v": "virtual"}
    records: list[dict[str, Any]] = []
    for row in rows or []:
        (
            relation_oid,
            schema_name,
            table_name,
            qualified_name,
            relkind,
            position,
            column_name,
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
            collation_schema,
            collation_name,
            comment,
            is_local,
            inheritance_count,
            has_schema_usage,
            has_select,
        ) = row
        records.append(
            {
                "tabla_oid": int(relation_oid),
                "esquema": schema_name,
                "tabla": table_name,
                "nombre_completo": qualified_name,
                "tipo_tabla": _relation_type(relkind),
                "orden": int(position),
                "campo": column_name,
                "tipo_formateado": formatted_type,
                "tipo_oid": int(type_oid),
                "modificador_tipo": int(type_modifier),
                "obligatorio": bool(not_null),
                "expresion_predeterminada": default_expression,
                "identidad": identity_kinds.get(identity_kind),
                "generacion": generated_kinds.get(generated_kind),
                "esquema_tipo": type_schema,
                "nombre_tipo": type_name,
                "naturaleza_tipo": type_kinds.get(type_kind, "desconocida"),
                "tipo_base_dominio": domain_base_type,
                "colacion": (
                    f"{collation_schema}.{collation_name}"
                    if collation_schema and collation_name
                    else None
                ),
                "comentario": comment,
                "es_local": bool(is_local),
                "cantidad_herencias": int(inheritance_count),
                "permiso_uso_esquema": bool(has_schema_usage),
                "permiso_lectura": bool(has_select),
            }
        )
    return records


def _group_column_evidence(
    columns: list[dict[str, Any]],
    selected_fields: tuple[str, ...],
) -> list[dict[str, Any]]:
    tables: dict[int, dict[str, Any]] = {}
    for column in columns:
        table = tables.setdefault(
            column["tabla_oid"],
            {
                "esquema": column["esquema"],
                "tabla": column["tabla"],
                "nombre_completo": column["nombre_completo"],
                "tipo_tabla": column["tipo_tabla"],
                "permiso_uso_esquema": column["permiso_uso_esquema"],
                "permiso_lectura": column["permiso_lectura"],
                "campos": [],
            },
        )
        table["campos"].append(
            {field: column[field] for field in selected_fields}
        )
    return sorted(tables.values(), key=lambda item: item["nombre_completo"])


async def _execute_column_dictionary_activity(
    connection: psycopg.AsyncConnection,
    activity: ChecklistActivityReference,
) -> ActivityResult:
    started = time.perf_counter()
    columns_outcome = await _fetch_rows(connection, COLUMN_DICTIONARY_SQL)
    outcomes = [columns_outcome]
    query_outcomes: list[tuple[str, QueryOutcome]] = [
        ("column_dictionary", columns_outcome)
    ]

    checks_outcome: QueryOutcome | None = None
    domains_outcome: QueryOutcome | None = None
    enums_outcome: QueryOutcome | None = None
    foreign_keys_outcome: QueryOutcome | None = None
    if activity.numero in {"3.4", "3.6"}:
        checks_outcome = await _fetch_rows(connection, COLUMN_CHECK_CONSTRAINTS_SQL)
        domains_outcome = await _fetch_rows(connection, DOMAIN_CONSTRAINTS_SQL)
        enums_outcome = await _fetch_rows(connection, ENUM_VALUES_SQL)
        foreign_keys_outcome = await _fetch_rows(connection, TABLE_FOREIGN_KEYS_SQL)
        extra_outcomes = [
            ("column_check_constraints", checks_outcome),
            ("domain_constraints", domains_outcome),
            ("enum_values", enums_outcome),
            ("table_foreign_keys", foreign_keys_outcome),
        ]
        query_outcomes.extend(extra_outcomes)
        outcomes.extend(outcome for _, outcome in extra_outcomes)

    warnings = [
        warning
        for query_id, outcome in query_outcomes
        if (warning := _technical_warning(query_id, outcome)) is not None
    ]
    columns = _column_dictionary_records(columns_outcome.rows)
    without_schema_usage = sum(
        not column["permiso_uso_esquema"] for column in columns
    )
    if without_schema_usage:
        warnings.append(
            "Existen campos en esquemas sin permiso USAGE; la cobertura no puede considerarse completa."
        )

    evidence: list[ActivityEvidence] = []
    limitations: list[str]
    if activity.numero == "3.1":
        tables = _group_column_evidence(
            columns,
            ("orden", "campo", "es_local", "cantidad_herencias", "comentario"),
        )
        evidence.append(
            ActivityEvidence(
                clave="diccionario_datos_base",
                consulta_id="column_dictionary",
                disponibilidad="disponible" if columns else "sin_datos",
                naturaleza="exacta",
                datos={"tablas": tables, "total_campos": len(columns)},
            )
        )
        limitations = [
            "El origen corresponde al objeto PostgreSQL que contiene el campo; no identifica el sistema externo que pudo haberlo creado.",
            "La cobertura se limita a tablas ordinarias, particionadas y foráneas visibles en los catálogos.",
        ]
    elif activity.numero == "3.2":
        tables = _group_column_evidence(
            columns,
            (
                "orden",
                "campo",
                "tipo_formateado",
                "esquema_tipo",
                "nombre_tipo",
                "naturaleza_tipo",
                "tipo_base_dominio",
                "modificador_tipo",
                "colacion",
            ),
        )
        evidence.append(
            ActivityEvidence(
                clave="diccionario_tipos",
                consulta_id="column_dictionary",
                disponibilidad="disponible" if columns else "sin_datos",
                naturaleza="exacta",
                datos={"tablas": tables, "total_campos": len(columns)},
            )
        )
        limitations = [
            "El tipo formateado refleja longitud o precisión declarada por PostgreSQL; no valida formatos empresariales almacenados dentro del valor.",
            "La semántica empresarial de cada tipo requiere documentación externa.",
        ]
    elif activity.numero == "3.3":
        tables = _group_column_evidence(
            columns,
            ("orden", "campo", "obligatorio"),
        )
        evidence.append(
            ActivityEvidence(
                clave="diccionario_obligatoriedad",
                consulta_id="column_dictionary",
                disponibilidad="disponible" if columns else "sin_datos",
                naturaleza="exacta",
                datos={
                    "tablas": tables,
                    "total_campos": len(columns),
                    "campos_obligatorios": sum(
                        column["obligatorio"] for column in columns
                    ),
                    "campos_opcionales": sum(
                        not column["obligatorio"] for column in columns
                    ),
                },
            )
        )
        limitations = [
            "NOT NULL describe obligatoriedad técnica en PostgreSQL y no demuestra que el valor sea válido para el negocio.",
        ]
    elif activity.numero == "3.4":
        enum_values: dict[int, dict[str, Any]] = {}
        for type_oid, schema_name, type_name, label in (
            enums_outcome.rows if enums_outcome and enums_outcome.rows else []
        ):
            enum_record = enum_values.setdefault(
                int(type_oid),
                {
                    "esquema": schema_name,
                    "tipo": type_name,
                    "valores": [],
                },
            )
            enum_record["valores"].append(label)
        table_names = {
            column["tabla_oid"]: column["nombre_completo"] for column in columns
        }
        checks = [
            {
                "tabla": table_names.get(int(relation_oid)),
                "nombre": name,
                "definicion": definition,
                "campos": list(check_columns or []),
            }
            for relation_oid, _, name, definition, check_columns in (
                checks_outcome.rows if checks_outcome and checks_outcome.rows else []
            )
        ]
        domain_constraints = [
            {
                "tipo_oid": int(type_oid),
                "esquema": schema_name,
                "dominio": type_name,
                "nombre": constraint_name,
                "definicion": definition,
            }
            for type_oid, schema_name, type_name, _, constraint_name, definition in (
                domains_outcome.rows
                if domains_outcome and domains_outcome.rows
                else []
            )
        ]
        foreign_keys = _foreign_key_records(
            foreign_keys_outcome.rows if foreign_keys_outcome else None
        )
        evidence.append(
            ActivityEvidence(
                clave="diccionario_dominios_y_valores_permitidos",
                consulta_id="column_dictionary_constraints_enums_foreign_keys",
                disponibilidad="disponible" if columns else "sin_datos",
                naturaleza="calculada",
                datos={
                    "valores_predeterminados": [
                        {
                            "tabla": column["nombre_completo"],
                            "campo": column["campo"],
                            "expresion": column["expresion_predeterminada"],
                        }
                        for column in columns
                        if column["expresion_predeterminada"] is not None
                    ],
                    "tipos_enum": sorted(
                        enum_values.values(),
                        key=lambda item: (item["esquema"], item["tipo"]),
                    ),
                    "dominios_usados": [
                        {
                            "tabla": column["nombre_completo"],
                            "campo": column["campo"],
                            "esquema": column["esquema_tipo"],
                            "dominio": column["nombre_tipo"],
                            "tipo_base": column["tipo_base_dominio"],
                        }
                        for column in columns
                        if column["naturaleza_tipo"] == "dominio"
                    ],
                    "restricciones_dominio": domain_constraints,
                    "restricciones_check": checks,
                    "referencias_fk_posibles_catalogos": [
                        {
                            "nombre": foreign_key["nombre"],
                            "tabla_origen": foreign_key["tabla_origen"],
                            "columnas_origen": foreign_key["columnas_origen"],
                            "tabla_referenciada": foreign_key["tabla_destino"],
                            "columnas_referenciadas": foreign_key[
                                "columnas_destino"
                            ],
                            "proposito_catalogo_confirmado": False,
                        }
                        for foreign_key in foreign_keys
                    ],
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "Las claves foráneas muestran referencias técnicas, pero no confirman que la tabla destino sea un catálogo empresarial.",
            "No se consultan filas de tablas de catálogo ni datos de negocio para enumerar valores permitidos.",
            "Las reglas aplicadas exclusivamente en la aplicación no son visibles desde PostgreSQL.",
        ]
    elif activity.numero == "3.5":
        generated_columns = [
            {
                "tabla": column["nombre_completo"],
                "campo": column["campo"],
                "tipo_generacion": column["generacion"],
                "expresion": column["expresion_predeterminada"],
            }
            for column in columns
            if column["generacion"] is not None
        ]
        identity_columns = [
            {
                "tabla": column["nombre_completo"],
                "campo": column["campo"],
                "tipo_identidad": column["identidad"],
            }
            for column in columns
            if column["identidad"] is not None
        ]
        evidence.append(
            ActivityEvidence(
                clave="campos_generados_detectables",
                consulta_id="column_dictionary",
                disponibilidad="disponible" if columns else "sin_datos",
                naturaleza="exacta",
                datos={
                    "campos_generados": generated_columns,
                    "campos_identidad_contexto": identity_columns,
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "PostgreSQL permite identificar columnas generadas declaradas, pero no cálculos realizados por el backend, ORM o procesos externos.",
            "Una columna de identidad se informa como contexto y no se clasifica automáticamente como campo calculado.",
            "La condición de solo lectura empresarial no puede inferirse únicamente de los permisos del usuario auditor.",
        ]
    elif activity.numero == "3.6":
        table_names = {
            column["tabla_oid"]: column["nombre_completo"] for column in columns
        }
        technical_rules = [
            {
                "fuente": "valor_predeterminado",
                "tabla": column["nombre_completo"],
                "campo": column["campo"],
                "definicion": column["expresion_predeterminada"],
                "regla_empresarial_confirmada": False,
            }
            for column in columns
            if column["expresion_predeterminada"] is not None
        ]
        technical_rules.extend(
            {
                "fuente": "comentario_columna",
                "tabla": column["nombre_completo"],
                "campo": column["campo"],
                "definicion": column["comentario"],
                "regla_empresarial_confirmada": False,
            }
            for column in columns
            if column["comentario"]
        )
        technical_rules.extend(
            {
                "fuente": "restriccion_check",
                "tabla": table_names.get(int(relation_oid)),
                "campos": list(check_columns or []),
                "nombre": name,
                "definicion": definition,
                "regla_empresarial_confirmada": False,
            }
            for relation_oid, _, name, definition, check_columns in (
                checks_outcome.rows if checks_outcome and checks_outcome.rows else []
            )
        )
        technical_rules.extend(
            {
                "fuente": "restriccion_dominio",
                "tipo": f"{schema_name}.{type_name}",
                "nombre": constraint_name,
                "definicion": definition,
                "regla_empresarial_confirmada": False,
            }
            for _, schema_name, type_name, _, constraint_name, definition in (
                domains_outcome.rows
                if domains_outcome and domains_outcome.rows
                else []
            )
        )
        technical_rules.extend(
            {
                "fuente": "clave_foranea",
                "tabla": foreign_key["tabla_origen"],
                "campos": foreign_key["columnas_origen"],
                "tabla_referenciada": foreign_key["tabla_destino"],
                "campos_referenciados": foreign_key["columnas_destino"],
                "regla_empresarial_confirmada": False,
            }
            for foreign_key in _foreign_key_records(
                foreign_keys_outcome.rows if foreign_keys_outcome else None
            )
        )
        evidence.append(
            ActivityEvidence(
                clave="indicios_reglas_por_campo",
                consulta_id="column_dictionary_constraints_foreign_keys",
                disponibilidad="disponible" if columns else "sin_datos",
                naturaleza="calculada",
                datos={
                    "reglas_tecnicas_observables": technical_rules,
                    "reglas_empresariales_confirmadas": 0,
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "Las restricciones, valores predeterminados, comentarios y FK son reglas técnicas observables; no confirman por sí solos la regla de negocio.",
            "Las validaciones implementadas en backend, frontend, ORM o integraciones requieren evidencia externa.",
        ]
    elif activity.numero == "3.7":
        candidates: list[dict[str, Any]] = []
        for column in columns:
            normalized_name = _normalized_identifier(column["campo"])
            tokens = _identifier_tokens(column["campo"])
            categories = sorted(
                category
                for category, hints in SENSITIVE_COLUMN_HINTS.items()
                if normalized_name in hints or bool(tokens & hints)
            )
            if categories:
                candidates.append(
                    {
                        "tabla": column["nombre_completo"],
                        "campo": column["campo"],
                        "categorias_probables": categories,
                        "criterio": "nombre_tecnico_del_campo",
                        "sensibilidad_confirmada": False,
                        "requiere_validacion": True,
                    }
                )
        evidence.append(
            ActivityEvidence(
                clave="candidatos_datos_sensibles",
                consulta_id="column_dictionary",
                disponibilidad="disponible" if columns else "sin_datos",
                naturaleza="calculada",
                datos={
                    "campos_candidatos": candidates,
                    "campos_sensibles_confirmados": 0,
                    "contenido_datos_inspeccionado": False,
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "La detección utiliza únicamente nombres técnicos y produce candidatos; no confirma que una columna contenga PII, datos financieros, de salud o credenciales.",
            "No se inspeccionan valores ni registros de negocio.",
            "La clasificación definitiva requiere diccionario empresarial, responsables de datos y criterios normativos.",
        ]
    elif activity.numero == "3.8":
        naming_records = []
        for column in columns:
            snake_case = re.fullmatch(
                r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*",
                column["campo"],
            ) is not None
            naming_records.append(
                {
                    "tabla": column["nombre_completo"],
                    "campo": column["campo"],
                    "snake_case_minusculas": snake_case,
                    "tokens": sorted(_identifier_tokens(column["campo"])),
                }
            )
        evidence.append(
            ActivityEvidence(
                clave="evidencia_nomenclatura_campos",
                consulta_id="column_dictionary",
                disponibilidad="disponible" if columns else "sin_datos",
                naturaleza="calculada",
                datos={
                    "campos": naming_records,
                    "total_campos": len(columns),
                    "total_snake_case_minusculas": sum(
                        item["snake_case_minusculas"] for item in naming_records
                    ),
                    "convencion_aprobada_disponible": False,
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "Se observan patrones sintácticos, pero PostgreSQL no conoce la convención aprobada, el idioma requerido ni las excepciones del proyecto.",
            "El motor no renombra campos ni propone automáticamente nombres empresariales.",
        ]
    else:
        deprecated_candidates = []
        for column in columns:
            name_tokens = _identifier_tokens(column["campo"])
            normalized_comment = _normalized_identifier(column["comentario"] or "")
            name_indications = {
                hint
                for hint in DEPRECATION_HINTS
                if hint in name_tokens
            }
            comment_indications = {
                hint for hint in DEPRECATION_HINTS if hint in normalized_comment
            }
            indications = sorted(name_indications | comment_indications)
            if indications:
                deprecated_candidates.append(
                    {
                        "tabla": column["nombre_completo"],
                        "campo": column["campo"],
                        "indicios": indications,
                        "fuentes": [
                            source
                            for source, available in (
                                ("nombre_tecnico", bool(name_indications)),
                                ("comentario", bool(comment_indications)),
                            )
                            if available
                        ],
                        "deprecacion_confirmada": False,
                    }
                )
        evidence.append(
            ActivityEvidence(
                clave="candidatos_campos_deprecados",
                consulta_id="column_dictionary",
                disponibilidad="disponible" if columns else "sin_datos",
                naturaleza="calculada",
                datos={
                    "campos_candidatos": deprecated_candidates,
                    "campos_deprecados_confirmados": 0,
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "Los nombres y comentarios explícitos son indicios; no demuestran que el campo esté fuera de uso en la aplicación.",
            "La confirmación requiere revisar código, consultas, integraciones, historial de cambios y responsables funcionales.",
            "No se propone eliminar ni modificar columnas.",
        ]

    status = _activity_status(outcomes)
    if status == "error_tecnico":
        evidence_status: EvidenceStatus = "no_obtenida"
    elif status == "parcial":
        evidence_status = "insuficiente"
    elif not columns:
        evidence_status = "sin_datos"
    elif activity.numero in {"3.4", "3.5", "3.6", "3.7", "3.8", "3.9"}:
        evidence_status = "insuficiente"
    else:
        evidence_status = "suficiente"
    return ActivityResult(
        identificador=activity.numero,
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


def _index_records(rows: list[tuple[Any, ...]] | None) -> list[dict[str, Any]]:
    records = []
    for row in rows or []:
        (
            table_oid,
            schema_name,
            table_name,
            qualified_name,
            index_oid,
            index_name,
            access_method,
            is_primary,
            is_unique,
            is_exclusion,
            is_valid,
            is_ready,
            is_live,
            key_count,
            attribute_count,
            key_columns,
            key_elements,
            included_columns,
            predicate,
            expressions,
            size_bytes,
            scan_count,
            last_scan,
        ) = row
        records.append(
            {
                "tabla_oid": int(table_oid),
                "esquema": schema_name,
                "tabla": table_name,
                "nombre_tabla": qualified_name,
                "indice_oid": int(index_oid),
                "indice": index_name,
                "metodo": access_method,
                "es_primario": bool(is_primary),
                "es_unico": bool(is_unique),
                "es_exclusion": bool(is_exclusion),
                "valido": bool(is_valid),
                "listo": bool(is_ready),
                "activo_catalogo": bool(is_live),
                "cantidad_claves": int(key_count),
                "cantidad_atributos": int(attribute_count),
                "columnas_clave": list(key_columns or []),
                "elementos_clave": list(key_elements or []),
                "columnas_incluidas": list(included_columns or []),
                "predicado": predicate,
                "expresiones": expressions,
                "tamano_bytes": int(size_bytes),
                "lecturas_indice": int(scan_count) if scan_count is not None else None,
                "ultima_lectura": last_scan,
            }
        )
    return records


async def _execute_index_activity(
    connection: psycopg.AsyncConnection,
    activity: ChecklistActivityReference,
) -> ActivityResult:
    started = time.perf_counter()
    indexes_outcome = await _fetch_rows(connection, INDEX_INVENTORY_SQL)
    outcomes = [indexes_outcome]
    query_outcomes: list[tuple[str, QueryOutcome]] = [
        ("index_inventory", indexes_outcome)
    ]
    inventory_outcome: QueryOutcome | None = None
    constraints_outcome: QueryOutcome | None = None
    foreign_keys_outcome: QueryOutcome | None = None
    properties_outcome: QueryOutcome | None = None
    if activity.numero == "4.2":
        inventory_outcome = await _fetch_rows(connection, TABLE_INVENTORY_SQL)
        constraints_outcome = await _fetch_rows(connection, TABLE_CONSTRAINTS_SQL)
        foreign_keys_outcome = await _fetch_rows(connection, TABLE_FOREIGN_KEYS_SQL)
        properties_outcome = await _fetch_rows(
            connection, KEY_CONSTRAINT_PROPERTIES_SQL
        )
        extra_outcomes = [
            ("table_inventory", inventory_outcome),
            ("table_constraints", constraints_outcome),
            ("table_foreign_keys", foreign_keys_outcome),
            ("key_constraint_properties", properties_outcome),
        ]
        query_outcomes.extend(extra_outcomes)
        outcomes.extend(outcome for _, outcome in extra_outcomes)
    elif activity.numero == "4.4":
        foreign_keys_outcome = await _fetch_rows(connection, TABLE_FOREIGN_KEYS_SQL)
        query_outcomes.append(("table_foreign_keys", foreign_keys_outcome))
        outcomes.append(foreign_keys_outcome)

    warnings = [
        warning
        for query_id, outcome in query_outcomes
        if (warning := _technical_warning(query_id, outcome)) is not None
    ]
    indexes = _index_records(indexes_outcome.rows)
    evidence: list[ActivityEvidence] = []
    limitations: list[str]

    if activity.numero == "4.1":
        tables: dict[str, dict[str, Any]] = {}
        for index in indexes:
            table = tables.setdefault(
                index["nombre_tabla"],
                {
                    "esquema": index["esquema"],
                    "tabla": index["tabla"],
                    "nombre_completo": index["nombre_tabla"],
                    "indices": [],
                },
            )
            public_index = dict(index)
            public_index.pop("tabla_oid")
            public_index.pop("indice_oid")
            public_index.pop("esquema")
            public_index.pop("tabla")
            public_index.pop("nombre_tabla")
            table["indices"].append(public_index)
        evidence.append(
            ActivityEvidence(
                clave="inventario_indices",
                consulta_id="index_inventory",
                disponibilidad="disponible" if indexes else "sin_datos",
                naturaleza="exacta",
                datos={
                    "tablas": sorted(tables.values(), key=lambda item: item["nombre_completo"]),
                    "total_indices": len(indexes),
                },
            )
        )
        limitations = [
            "Los contadores de uso dependen de estadísticas acumulativas y no demuestran por sí solos que un índice sea necesario o prescindible.",
        ]
    elif activity.numero == "4.2":
        table_names = {
            int(row[0]): row[3]
            for row in (inventory_outcome.rows if inventory_outcome and inventory_outcome.rows else [])
        }
        properties = {
            int(row[0]): {
                "validada": bool(row[4]),
                "diferible": bool(row[5]),
                "inicialmente_diferida": bool(row[6]),
            }
            for row in (
                properties_outcome.rows
                if properties_outcome and properties_outcome.rows
                else []
            )
        }
        primary_keys = [
            {
                "tabla": table_names.get(int(relation_oid)),
                "nombre": name,
                "columnas": list(columns or []),
                **properties.get(int(constraint_oid), {}),
            }
            for relation_oid, constraint_oid, name, constraint_type, columns in (
                constraints_outcome.rows
                if constraints_outcome and constraints_outcome.rows
                else []
            )
            if constraint_type == "p"
        ]
        foreign_keys = []
        for foreign_key in _foreign_key_records(
            foreign_keys_outcome.rows if foreign_keys_outcome else None
        ):
            foreign_keys.append(
                {
                    "nombre": foreign_key["nombre"],
                    "tabla_origen": foreign_key["tabla_origen"],
                    "columnas_origen": foreign_key["columnas_origen"],
                    "tabla_destino": foreign_key["tabla_destino"],
                    "columnas_destino": foreign_key["columnas_destino"],
                    "accion_actualizacion": foreign_key["accion_actualizacion"],
                    "accion_eliminacion": foreign_key["accion_eliminacion"],
                    **properties.get(foreign_key["oid"], {}),
                }
            )
        evidence.append(
            ActivityEvidence(
                clave="matriz_llaves_pk_fk",
                consulta_id="constraints_foreign_keys_properties",
                disponibilidad=(
                    "disponible" if primary_keys or foreign_keys else "sin_datos"
                ),
                naturaleza="exacta",
                datos={
                    "llaves_primarias": primary_keys,
                    "llaves_foraneas": foreign_keys,
                    "total_pk": len(primary_keys),
                    "total_fk": len(foreign_keys),
                },
            )
        )
        limitations = [
            "La matriz documenta restricciones declaradas en PostgreSQL; no identifica relaciones implementadas únicamente en código sin FK formal.",
        ]
    elif activity.numero == "4.3":
        exact_groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
        for index in indexes:
            signature = (
                index["tabla_oid"],
                index["metodo"],
                tuple(index["elementos_clave"]),
                tuple(index["columnas_incluidas"]),
                index["predicado"],
                index["es_unico"],
                index["es_exclusion"],
            )
            exact_groups[signature].append(index)
        exact_duplicates = [
            {
                "tabla": group[0]["nombre_tabla"],
                "indices": sorted(item["indice"] for item in group),
                "elementos_clave": group[0]["elementos_clave"],
                "columnas_incluidas": group[0]["columnas_incluidas"],
                "predicado": group[0]["predicado"],
                "requiere_revision": True,
            }
            for group in exact_groups.values()
            if len(group) > 1
        ]
        prefix_candidates = []
        for shorter in indexes:
            if shorter["es_primario"] or shorter["es_unico"] or shorter["es_exclusion"]:
                continue
            short_keys = shorter["elementos_clave"]
            for longer in indexes:
                if shorter["indice_oid"] == longer["indice_oid"]:
                    continue
                if shorter["tabla_oid"] != longer["tabla_oid"]:
                    continue
                if shorter["metodo"] != longer["metodo"]:
                    continue
                if shorter["predicado"] != longer["predicado"]:
                    continue
                long_keys = longer["elementos_clave"]
                if len(short_keys) < len(long_keys) and long_keys[: len(short_keys)] == short_keys:
                    prefix_candidates.append(
                        {
                            "tabla": shorter["nombre_tabla"],
                            "indice_corto": shorter["indice"],
                            "indice_amplio": longer["indice"],
                            "prefijo": short_keys,
                            "clasificacion": "posible_redundancia_por_prefijo",
                            "requiere_revision_carga": True,
                        }
                    )
                    break
        evidence.append(
            ActivityEvidence(
                clave="candidatos_indices_redundantes",
                consulta_id="index_inventory",
                disponibilidad="disponible" if indexes else "sin_datos",
                naturaleza="calculada",
                datos={
                    "duplicados_exactos": exact_duplicates,
                    "posibles_redundancias_prefijo": prefix_candidates,
                    "eliminaciones_recomendadas": [],
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "La equivalencia estructural no prueba redundancia operativa; deben revisarse restricciones, carga, planes y ventanas de estadísticas.",
            "Los contadores en cero no se interpretan automáticamente como falta de uso.",
            "El motor no recomienda ni ejecuta DROP INDEX.",
        ]
    else:
        foreign_keys = _foreign_key_records(
            foreign_keys_outcome.rows if foreign_keys_outcome else None
        )
        indexes_by_table: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for index in indexes:
            if index["valido"] and index["listo"] and index["activo_catalogo"]:
                indexes_by_table[index["tabla_oid"]].append(index)
        candidates = []
        for foreign_key in foreign_keys:
            fk_columns = foreign_key["columnas_origen"]
            supporting = [
                index["indice"]
                for index in indexes_by_table[foreign_key["origen_oid"]]
                if index["columnas_clave"][: len(fk_columns)] == fk_columns
            ]
            if not supporting:
                candidates.append(
                    {
                        "tabla": foreign_key["tabla_origen"],
                        "restriccion_fk": foreign_key["nombre"],
                        "columnas": fk_columns,
                        "motivo": "sin_indice_valido_con_prefijo_fk",
                        "indice_recomendado_confirmado": False,
                    }
                )
        evidence.append(
            ActivityEvidence(
                clave="candidatos_indices_faltantes",
                consulta_id="index_inventory_foreign_keys",
                disponibilidad="disponible" if foreign_keys or indexes else "sin_datos",
                naturaleza="calculada",
                datos={
                    "fk_sin_indice_prefijo": candidates,
                    "campos_busqueda_aplicacion_evaluados": False,
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "La comprobación cubre FK sin índice de prefijo compatible; no conoce todos los campos usados para búsqueda o filtrado por la aplicación.",
            "Un candidato requiere validar selectividad, carga, planes y costo de escritura antes de crear un índice.",
            "El motor no ejecuta CREATE INDEX.",
        ]

    status = _activity_status(outcomes)
    if status == "error_tecnico":
        evidence_status: EvidenceStatus = "no_obtenida"
    elif status == "parcial":
        evidence_status = "insuficiente"
    elif not indexes and activity.numero != "4.2":
        evidence_status = "sin_datos"
    elif activity.numero in {"4.3", "4.4"}:
        evidence_status = "insuficiente"
    else:
        evidence_status = "suficiente"
    return ActivityResult(
        identificador=activity.numero,
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


async def _execute_advanced_performance_activity(
    connection: psycopg.AsyncConnection,
    activity: ChecklistActivityReference,
) -> ActivityResult:
    started = time.perf_counter()
    evidence: list[ActivityEvidence] = []
    query_outcomes: list[tuple[str, QueryOutcome]] = []
    limitations: list[str] = []

    if activity.numero in {"4.5", "6.1"}:
        observability_outcome = await _fetch_rows(
            connection,
            QUERY_OBSERVABILITY_SQL,
        )
        snapshot_outcome = await _fetch_rows(
            connection,
            ACTIVE_QUERY_SNAPSHOT_SQL,
        )
        query_outcomes = [
            ("query_observability", observability_outcome),
            ("active_query_snapshot", snapshot_outcome),
        ]
        context: dict[str, Any] = {
            "track_activities_activo": None,
            "track_counts_activo": None,
            "compute_query_id": None,
            "estadisticas_reiniciadas_en": None,
            "pg_stat_statements_instalada": False,
            "pg_stat_statements_esquema": None,
            "permiso_uso_esquema_extension": False,
            "permiso_lectura_estadisticas_consultas": False,
        }
        if observability_outcome.rows:
            (
                track_activities,
                track_counts,
                compute_query_id,
                stats_reset,
                statements_installed,
                statements_schema,
                has_schema_usage,
                has_statements_select,
            ) = observability_outcome.rows[0]
            context = {
                "track_activities_activo": bool(track_activities),
                "track_counts_activo": bool(track_counts),
                "compute_query_id": compute_query_id,
                "estadisticas_reiniciadas_en": stats_reset,
                "pg_stat_statements_instalada": bool(statements_installed),
                "pg_stat_statements_esquema": statements_schema,
                "permiso_uso_esquema_extension": bool(has_schema_usage),
                "permiso_lectura_estadisticas_consultas": bool(
                    has_statements_select
                ),
            }
        snapshot = [
            {
                "query_id": query_id,
                "estado": state,
                "tipo_espera": wait_event_type,
                "evento_espera": wait_event,
                "sesiones_observadas": int(session_count),
                "duracion_maxima_ms": (
                    int(max_duration_ms) if max_duration_ms is not None else None
                ),
            }
            for (
                query_id,
                state,
                wait_event_type,
                wait_event,
                session_count,
                max_duration_ms,
            ) in (snapshot_outcome.rows or [])
        ]
        evidence.extend(
            [
                ActivityEvidence(
                    clave="contexto_observabilidad_consultas",
                    consulta_id="query_observability",
                    disponibilidad=(
                        "disponible"
                        if observability_outcome.rows
                        else "no_disponible"
                    ),
                    naturaleza="exacta",
                    datos=context,
                ),
                ActivityEvidence(
                    clave="instantanea_consultas_activas",
                    consulta_id="active_query_snapshot",
                    disponibilidad="disponible" if snapshot else "sin_datos",
                    naturaleza="exacta",
                    datos={
                        "consultas_activas": snapshot,
                        "incluye_texto_sql": False,
                        "demuestra_frecuencia_historica": False,
                        "consultas_criticas_confirmadas": [],
                    },
                ),
            ]
        )
        limitations = [
            "La instantánea de pg_stat_activity no demuestra cuáles consultas son frecuentes o pesadas históricamente.",
            "No se extrae texto SQL ni se ejecutan EXPLAIN sobre consultas de la aplicación.",
            (
                "La causa raíz requiere estadísticas históricas comparables, texto SQL sanitizado y planes de ejecución suministrados para revisión."
                if activity.numero == "6.1"
                else "El entregable requiere estadísticas históricas comparables de pg_stat_statements, logs revisados o planes suministrados externamente."
            ),
        ]
    elif activity.numero == "4.6":
        indexes_outcome = await _fetch_rows(connection, INDEX_INVENTORY_SQL)
        volumetry_outcome = await _fetch_rows(connection, TABLE_VOLUMETRY_SQL)
        query_outcomes = [
            ("index_inventory", indexes_outcome),
            ("table_volumetry", volumetry_outcome),
        ]
        table_statistics = {
            int(row[0]): {
                "filas_vivas_estimadas": row[12],
                "filas_muertas_estimadas": row[13],
                "modificaciones_desde_analisis": row[14],
                "ultimo_vacuum": row[15],
                "ultimo_autovacuum": row[16],
                "ultimo_analisis": row[17],
                "ultimo_autoanalisis": row[18],
            }
            for row in (volumetry_outcome.rows or [])
        }
        indicators = []
        for index in _index_records(indexes_outcome.rows):
            indicators.append(
                {
                    "tabla": index["nombre_tabla"],
                    "indice": index["indice"],
                    "tamano_bytes": index["tamano_bytes"],
                    "valido": index["valido"],
                    "listo": index["listo"],
                    "activo_catalogo": index["activo_catalogo"],
                    "lecturas_indice": index["lecturas_indice"],
                    "ultima_lectura": index["ultima_lectura"],
                    **table_statistics.get(index["tabla_oid"], {}),
                    "fragmentacion_medida": False,
                    "mantenimiento_confirmado": False,
                    "requiere_revision_tecnica": not (
                        index["valido"]
                        and index["listo"]
                        and index["activo_catalogo"]
                    ),
                }
            )
        evidence.append(
            ActivityEvidence(
                clave="indicadores_mantenimiento_indices",
                consulta_id="index_inventory_table_volumetry",
                disponibilidad="disponible" if indicators else "sin_datos",
                naturaleza="calculada",
                datos={
                    "indices": indicators,
                    "fragmentacion_exacta_disponible": False,
                    "acciones_rebuild_reorganize_recomendadas": [],
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "PostgreSQL no expone en catálogos centrales una medida exacta de fragmentación o bloat por índice.",
            "REBUILD y REORGANIZE son conceptos de otros motores; en PostgreSQL el mantenimiento debe evaluarse con evidencia adicional y herramientas aprobadas.",
            "Los contadores acumulativos y las tuplas muertas no confirman por sí solos la necesidad de REINDEX.",
        ]
    elif activity.numero == "4.7":
        indexes_outcome = await _fetch_rows(connection, INDEX_INVENTORY_SQL)
        foreign_keys_outcome = await _fetch_rows(
            connection,
            TABLE_FOREIGN_KEYS_SQL,
        )
        query_outcomes = [
            ("index_inventory", indexes_outcome),
            ("table_foreign_keys", foreign_keys_outcome),
        ]
        indexes = _index_records(indexes_outcome.rows)
        indexes_by_table: dict[int, list[dict[str, Any]]] = defaultdict(list)
        existing = []
        for index in indexes:
            indexes_by_table[index["tabla_oid"]].append(index)
            if index["cantidad_claves"] > 1 or index["columnas_incluidas"]:
                existing.append(
                    {
                        "tabla": index["nombre_tabla"],
                        "indice": index["indice"],
                        "elementos_clave": index["elementos_clave"],
                        "columnas_incluidas": index["columnas_incluidas"],
                        "predicado": index["predicado"],
                        "lecturas_indice": index["lecturas_indice"],
                    }
                )
        candidates = []
        for foreign_key in _foreign_key_records(foreign_keys_outcome.rows):
            columns = foreign_key["columnas_origen"]
            if len(columns) < 2:
                continue
            supporting = [
                index["indice"]
                for index in indexes_by_table[foreign_key["origen_oid"]]
                if index["valido"]
                and index["listo"]
                and index["columnas_clave"][: len(columns)] == columns
            ]
            if not supporting:
                candidates.append(
                    {
                        "tabla": foreign_key["tabla_origen"],
                        "restriccion_fk": foreign_key["nombre"],
                        "columnas": columns,
                        "clasificacion": "candidato_tecnico_por_fk_compuesta",
                        "propuesta_confirmada": False,
                    }
                )
        evidence.append(
            ActivityEvidence(
                clave="evaluacion_indices_compuestos_cubrientes",
                consulta_id="index_inventory_foreign_keys",
                disponibilidad=(
                    "disponible"
                    if indexes or foreign_keys_outcome.rows
                    else "sin_datos"
                ),
                naturaleza="calculada",
                datos={
                    "indices_compuestos_o_con_includes_existentes": existing,
                    "candidatos_tecnicos": candidates,
                    "propuestas_indices_confirmadas": [],
                    "patrones_consulta_evaluados": False,
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "Una FK compuesta sin índice compatible es un indicio técnico, no una propuesta confirmada de índice.",
            "La necesidad, orden y cobertura de columnas requieren consultas representativas, selectividad y planes de ejecución.",
            "El motor no genera ni ejecuta CREATE INDEX.",
        ]
    else:
        partition_outcome = await _fetch_rows(
            connection,
            PARTITION_CONFIGURATION_SQL,
        )
        volumetry_outcome = await _fetch_rows(connection, TABLE_VOLUMETRY_SQL)
        query_outcomes = [
            ("partition_configuration", partition_outcome),
            ("table_volumetry", volumetry_outcome),
        ]
        strategies = {"r": "rango", "l": "lista", "h": "hash"}
        partitioned: dict[int, dict[str, Any]] = {}
        for row in partition_outcome.rows or []:
            (
                parent_oid,
                schema_name,
                table_name,
                qualified_name,
                strategy,
                partition_key,
                child_oid,
                child_schema,
                child_name,
                child_qualified_name,
                partition_bound,
                has_schema_usage,
                has_select,
            ) = row
            parent = partitioned.setdefault(
                int(parent_oid),
                {
                    "esquema": schema_name,
                    "tabla": table_name,
                    "nombre_completo": qualified_name,
                    "estrategia": strategies.get(strategy, strategy),
                    "clave_particionamiento": partition_key,
                    "permiso_uso_esquema": bool(has_schema_usage),
                    "permiso_lectura": bool(has_select),
                    "particiones": [],
                },
            )
            if child_oid is not None:
                parent["particiones"].append(
                    {
                        "oid": int(child_oid),
                        "esquema": child_schema,
                        "tabla": child_name,
                        "nombre_completo": child_qualified_name,
                        "limite": partition_bound,
                    }
                )
        unpartitioned_by_size = []
        for row in volumetry_outcome.rows or []:
            relkind = row[4]
            is_partition = bool(row[5])
            total_bytes = row[9]
            if relkind == "r" and not is_partition and total_bytes is not None:
                unpartitioned_by_size.append(
                    {
                        "nombre_completo": row[3],
                        "tamano_total_bytes": int(total_bytes),
                        "filas_estimadas": row[10],
                    }
                )
        unpartitioned_by_size.sort(
            key=lambda item: item["tamano_total_bytes"],
            reverse=True,
        )
        evidence_key = (
            "evaluacion_particionamiento_archivado"
            if activity.numero == "6.2"
            else "nota_tecnica_particionamiento"
        )
        evidence.append(
            ActivityEvidence(
                clave=evidence_key,
                consulta_id="partition_configuration_table_volumetry",
                disponibilidad=(
                    "disponible"
                    if partitioned or unpartitioned_by_size
                    else "sin_datos"
                ),
                naturaleza="calculada",
                datos={
                    "tablas_particionadas": list(partitioned.values()),
                    "tablas_no_particionadas_ordenadas_por_tamano": (
                        unpartitioned_by_size
                    ),
                    "candidatas_particionamiento_confirmadas": [],
                    "estrategia_futura_confirmada": False,
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "El tamaño y la estimación de filas permiten ordenar tablas para revisión, pero no definen un umbral universal de alto volumen.",
            "Una estrategia futura requiere patrones de crecimiento, retención, consultas y reglas de negocio que PostgreSQL no confirma por sí solo.",
            (
                "No se propone archivado sin una política aprobada de retención y acceso histórico."
                if activity.numero == "6.2"
                else "No se crean, adjuntan ni modifican particiones."
            ),
        ]

    outcomes = [outcome for _, outcome in query_outcomes]
    warnings = [
        warning
        for query_id, outcome in query_outcomes
        if (warning := _technical_warning(query_id, outcome)) is not None
    ]
    status = _activity_status(outcomes)
    evidence_status: EvidenceStatus = (
        "no_obtenida" if status == "error_tecnico" else "insuficiente"
    )
    return ActivityResult(
        identificador=activity.numero,
        numero_original=activity.numero,
        nombre_original=activity.actividad,
        fase_original=activity.fase,
        estado_ejecucion=status,
        estado_evidencia=evidence_status,
        evidencias=evidence if status != "error_tecnico" else [],
        advertencias=warnings,
        limitaciones=limitations,
        duracion_ms=round((time.perf_counter() - started) * 1000),
    )


def _constraint_column_sets(
    table: dict[str, Any],
    accepted_types: set[str],
) -> list[list[str]]:
    return [
        list(constraint["columnas"])
        for constraint in table["restricciones"]
        if constraint["tipo"] in accepted_types
    ]


def _bridge_table_indicators(
    tables: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = []
    for table in tables.values():
        foreign_keys = table["claves_foraneas_salientes"]
        if len(foreign_keys) < 2:
            continue
        foreign_key_columns = {
            column
            for foreign_key in foreign_keys
            for column in foreign_key["columnas_origen"]
        }
        unique_sets = _constraint_column_sets(
            table,
            {"primary_key", "unique"},
        )
        supporting_constraint = next(
            (
                columns
                for columns in unique_sets
                if set(columns) == foreign_key_columns
            ),
            None,
        )
        if supporting_constraint is None:
            continue
        candidates.append(
            {
                "tabla": table["nombre_completo"],
                "claves_foraneas": [
                    foreign_key["nombre"] for foreign_key in foreign_keys
                ],
                "columnas_relacion": sorted(foreign_key_columns),
                "restriccion_unica": supporting_constraint,
                "clasificacion": "tabla_puente_tecnica_probable",
                "proposito_empresarial_confirmado": False,
            }
        )
    return sorted(candidates, key=lambda item: item["tabla"])


async def _execute_data_model_activity(
    connection: psycopg.AsyncConnection,
    activity: ChecklistActivityReference,
) -> ActivityResult:
    started = time.perf_counter()
    query_outcomes: list[tuple[str, QueryOutcome]] = []

    inventory_outcome: QueryOutcome | None = None
    columns_outcome: QueryOutcome | None = None
    constraints_outcome: QueryOutcome | None = None
    foreign_keys_outcome: QueryOutcome | None = None
    dictionary_outcome: QueryOutcome | None = None

    if activity.numero != "5.8":
        inventory_outcome = await _fetch_rows(connection, TABLE_INVENTORY_SQL)
        query_outcomes.append(("table_inventory", inventory_outcome))
    if activity.numero in {"5.2", "5.3", "5.4"}:
        columns_outcome = await _fetch_rows(connection, TABLE_COLUMNS_SQL)
        query_outcomes.append(("table_columns", columns_outcome))
    if activity.numero in {"5.2", "5.4", "5.6", "5.7"}:
        constraints_outcome = await _fetch_rows(
            connection,
            TABLE_CONSTRAINTS_SQL,
        )
        query_outcomes.append(("table_constraints", constraints_outcome))
    if activity.numero != "5.7":
        foreign_keys_outcome = await _fetch_rows(
            connection,
            TABLE_FOREIGN_KEYS_SQL,
        )
        query_outcomes.append(("table_foreign_keys", foreign_keys_outcome))
    if activity.numero in {"5.5", "5.7", "5.8"}:
        dictionary_outcome = await _fetch_rows(
            connection,
            COLUMN_DICTIONARY_SQL,
        )
        query_outcomes.append(("column_dictionary", dictionary_outcome))

    tables = _table_records(inventory_outcome.rows if inventory_outcome else None)
    if columns_outcome is not None:
        _attach_columns(tables, columns_outcome.rows)
    if constraints_outcome is not None:
        _attach_constraints(tables, constraints_outcome.rows)
    foreign_keys = _foreign_key_records(
        foreign_keys_outcome.rows if foreign_keys_outcome else None
    )
    _attach_foreign_keys(tables, foreign_keys)
    dictionary = _column_dictionary_records(
        dictionary_outcome.rows if dictionary_outcome else None
    )
    dictionary_by_key = {
        (column["tabla_oid"], column["campo"]): column for column in dictionary
    }

    evidence: list[ActivityEvidence] = []
    limitations: list[str] = []

    if activity.numero == "5.1":
        entities = [
            {
                "oid": table["oid"],
                "esquema": table["esquema"],
                "tabla": table["tabla"],
                "nombre_completo": table["nombre_completo"],
                "tipo": table["tipo"],
                "permiso_lectura": table["permiso_lectura"],
            }
            for table in sorted(
                tables.values(),
                key=lambda item: item["nombre_completo"],
            )
        ]
        relationships = [
            {
                "restriccion": foreign_key["nombre"],
                "tabla_origen": foreign_key["tabla_origen"],
                "columnas_origen": foreign_key["columnas_origen"],
                "tabla_destino": foreign_key["tabla_destino"],
                "columnas_destino": foreign_key["columnas_destino"],
            }
            for foreign_key in foreign_keys
        ]
        evidence.append(
            ActivityEvidence(
                clave="base_tecnica_diagrama_entidad_relacion",
                consulta_id="table_inventory_foreign_keys",
                disponibilidad="disponible" if entities else "sin_datos",
                naturaleza="calculada",
                datos={
                    "entidades": entities,
                    "relaciones_fk": relationships,
                    "total_entidades": len(entities),
                    "total_relaciones_fk": len(relationships),
                    "diagrama_visual_generado": False,
                    "relaciones_sin_fk_incluidas": False,
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "La evidencia constituye la base técnica del diagrama, pero no genera ni valida por sí sola el diagrama ER completo.",
            "PostgreSQL solo confirma relaciones formalizadas mediante restricciones; las relaciones lógicas sin FK requieren validación externa.",
        ]
    elif activity.numero == "5.2":
        indicators = []
        for table in sorted(
            tables.values(),
            key=lambda item: item["nombre_completo"],
        ):
            array_or_document_columns = [
                column["nombre"]
                for column in table["columnas"]
                if column["tipo"].endswith("[]")
                or column["tipo"] in {"json", "jsonb", "xml"}
            ]
            indicators.append(
                {
                    "tabla": table["nombre_completo"],
                    "cantidad_columnas": len(table["columnas"]),
                    "cantidad_fk_salientes": len(
                        table["claves_foraneas_salientes"]
                    ),
                    "claves_candidatas": _constraint_column_sets(
                        table,
                        {"primary_key", "unique"},
                    ),
                    "columnas_arreglo_o_documento": array_or_document_columns,
                    "nivel_normalizacion_confirmado": None,
                    "redundancia_evitables_confirmadas": [],
                    "requiere_revision_semantica": True,
                }
            )
        evidence.append(
            ActivityEvidence(
                clave="indicadores_estructurales_normalizacion",
                consulta_id="inventory_columns_constraints_foreign_keys",
                disponibilidad="disponible" if indicators else "sin_datos",
                naturaleza="calculada",
                datos={
                    "tablas": indicators,
                    "violaciones_normalizacion_confirmadas": [],
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "Los catálogos no describen dependencias funcionales ni semántica empresarial, necesarias para confirmar formas normales.",
            "Una columna JSON, XML o arreglo no constituye por sí sola una violación de normalización.",
            "No se consultan registros para buscar valores repetidos o anomalías de actualización.",
        ]
    elif activity.numero == "5.3":
        formal_source_columns = {
            (foreign_key["origen_oid"], column)
            for foreign_key in foreign_keys
            for column in foreign_key["columnas_origen"]
        }
        candidates = []
        for table in tables.values():
            for column in table["columnas"]:
                normalized = _normalized_identifier(column["nombre"])
                if not normalized.endswith("_id"):
                    continue
                if (table["oid"], column["nombre"]) in formal_source_columns:
                    continue
                candidates.append(
                    {
                        "tabla": table["nombre_completo"],
                        "columna": column["nombre"],
                        "tipo": column["tipo"],
                        "indicio": "nombre_de_columna_con_sufijo_id_sin_fk",
                        "tabla_destino_confirmada": None,
                        "relacion_huerfana_confirmada": False,
                    }
                )
        evidence.append(
            ActivityEvidence(
                clave="indicios_relaciones_sin_fk",
                consulta_id="inventory_columns_foreign_keys",
                disponibilidad="disponible" if tables else "sin_datos",
                naturaleza="calculada",
                datos={
                    "candidatas_revision": sorted(
                        candidates,
                        key=lambda item: (item["tabla"], item["columna"]),
                    ),
                    "relaciones_huerfanas_confirmadas": [],
                    "registros_evaluados": False,
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "El sufijo _id es solo un indicio de nomenclatura y no confirma una relación ni su tabla destino.",
            "Detectar registros huérfanos requeriría consultar datos mediante comprobaciones específicas previamente aprobadas.",
            "Las relaciones implementadas únicamente en el código de aplicación no son observables en los catálogos de PostgreSQL.",
        ]
    elif activity.numero == "5.4":
        relationships = []
        for foreign_key in foreign_keys:
            source = tables.get(foreign_key["origen_oid"])
            unique_source = False
            source_not_null = False
            if source is not None:
                unique_source = any(
                    columns == foreign_key["columnas_origen"]
                    for columns in _constraint_column_sets(
                        source,
                        {"primary_key", "unique"},
                    )
                )
                column_nullability = {
                    column["nombre"]: column["no_nula"]
                    for column in source["columnas"]
                }
                source_not_null = all(
                    column_nullability.get(column, False)
                    for column in foreign_key["columnas_origen"]
                )
            relationships.append(
                {
                    "restriccion": foreign_key["nombre"],
                    "tabla_origen": foreign_key["tabla_origen"],
                    "tabla_destino": foreign_key["tabla_destino"],
                    "columnas_origen": foreign_key["columnas_origen"],
                    "columnas_destino": foreign_key["columnas_destino"],
                    "cardinalidad_estructural": (
                        "uno_a_uno" if unique_source else "muchos_a_uno"
                    ),
                    "participacion_origen": (
                        "obligatoria" if source_not_null else "opcional"
                    ),
                    "cardinalidad_empresarial_confirmada": False,
                }
            )
        evidence.append(
            ActivityEvidence(
                clave="matriz_cardinalidad_tecnica",
                consulta_id="inventory_columns_constraints_foreign_keys",
                disponibilidad="disponible" if foreign_keys else "sin_datos",
                naturaleza="calculada",
                datos={
                    "relaciones": relationships,
                    "tablas_puente_probables": _bridge_table_indicators(tables),
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "La matriz expresa cardinalidad impuesta por UNIQUE, PK, FK y NOT NULL, no la cardinalidad conceptual del negocio.",
            "Las relaciones N:M se infieren solo cuando existe una estructura de tabla puente verificable.",
        ]
    elif activity.numero == "5.5":
        cross_schema = []
        for foreign_key in foreign_keys:
            source_schema = foreign_key["tabla_origen"].split(".", 1)[0]
            target_schema = foreign_key["tabla_destino"].split(".", 1)[0]
            if source_schema == target_schema:
                continue
            cross_schema.append(
                {
                    "restriccion": foreign_key["nombre"],
                    "tabla_origen": foreign_key["tabla_origen"],
                    "tabla_destino": foreign_key["tabla_destino"],
                    "columnas_origen": foreign_key["columnas_origen"],
                    "columnas_destino": foreign_key["columnas_destino"],
                    "modulos_confirmados": False,
                }
            )
        evidence.append(
            ActivityEvidence(
                clave="relaciones_tecnicas_entre_esquemas",
                consulta_id="inventory_foreign_keys_column_dictionary",
                disponibilidad="disponible" if tables else "sin_datos",
                naturaleza="calculada",
                datos={
                    "relaciones_fk_entre_esquemas": cross_schema,
                    "esquemas_observados": sorted(
                        {table["esquema"] for table in tables.values()}
                    ),
                    "inconsistencias_intermodulos_confirmadas": [],
                    "correspondencia_esquema_modulo_confirmada": False,
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "Un esquema PostgreSQL no equivale necesariamente a un módulo funcional.",
            "La consistencia entre módulos requiere arquitectura y reglas empresariales validadas externamente.",
            "El diccionario técnico no contiene una correspondencia confirmada entre esquemas y módulos.",
        ]
    elif activity.numero == "5.6":
        evidence.append(
            ActivityEvidence(
                clave="evaluacion_tecnica_tablas_puente",
                consulta_id="inventory_constraints_foreign_keys",
                disponibilidad="disponible" if tables else "sin_datos",
                naturaleza="calculada",
                datos={
                    "tablas_puente_probables_existentes": (
                        _bridge_table_indicators(tables)
                    ),
                    "tablas_puente_faltantes_confirmadas": [],
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "Los catálogos permiten reconocer estructuras puente existentes, pero no relaciones N:M previstas y todavía no implementadas.",
            "No se propone crear tablas sin un modelo conceptual o requisito empresarial validado.",
        ]
    elif activity.numero == "5.7":
        primary_keys = []
        patterns: set[str] = set()
        for table in sorted(
            tables.values(),
            key=lambda item: item["nombre_completo"],
        ):
            primary_key = next(
                (
                    constraint
                    for constraint in table["restricciones"]
                    if constraint["tipo"] == "primary_key"
                ),
                None,
            )
            if primary_key is None:
                primary_keys.append(
                    {
                        "tabla": table["nombre_completo"],
                        "tiene_llave_primaria": False,
                        "columnas": [],
                        "patron": "sin_llave_primaria",
                    }
                )
                patterns.add("sin_llave_primaria")
                continue
            columns = [
                dictionary_by_key.get((table["oid"], column_name))
                for column_name in primary_key["columnas"]
            ]
            if len(primary_key["columnas"]) > 1:
                pattern = "compuesta"
            elif columns and columns[0] is not None:
                column = columns[0]
                default = column["expresion_predeterminada"] or ""
                if column["identidad"]:
                    pattern = "identidad"
                elif column["nombre_tipo"] == "uuid":
                    pattern = "uuid"
                elif "nextval(" in default:
                    pattern = "secuencia"
                else:
                    pattern = "simple_otro"
            else:
                pattern = "no_determinado"
            patterns.add(pattern)
            primary_keys.append(
                {
                    "tabla": table["nombre_completo"],
                    "tiene_llave_primaria": True,
                    "columnas": [
                        {
                            "nombre": column_name,
                            "tipo": (
                                column["tipo_formateado"]
                                if column is not None
                                else None
                            ),
                            "identidad": (
                                column["identidad"]
                                if column is not None
                                else None
                            ),
                            "tiene_predeterminado": bool(
                                column
                                and column["expresion_predeterminada"]
                            ),
                        }
                        for column_name, column in zip(
                            primary_key["columnas"],
                            columns,
                            strict=True,
                        )
                    ],
                    "patron": pattern,
                }
            )
        evidence.append(
            ActivityEvidence(
                clave="nota_tecnica_convenciones_llaves_primarias",
                consulta_id="inventory_constraints_column_dictionary",
                disponibilidad="disponible" if tables else "sin_datos",
                naturaleza="calculada",
                datos={
                    "tablas": primary_keys,
                    "patrones_observados": sorted(patterns),
                    "convencion_documentada_disponible": False,
                    "coherencia_normativa_confirmada": False,
                    "cobertura_entregable": "parcial",
                },
            )
        )
        limitations = [
            "La uniformidad observable no demuestra conformidad sin una convención de llaves aprobada.",
            "El motor documenta identidad, UUID, secuencia y llaves compuestas sin recomendar una estrategia universal.",
        ]
    else:
        comparisons = []
        for foreign_key in foreign_keys:
            column_pairs = []
            for source_name, target_name in zip(
                foreign_key["columnas_origen"],
                foreign_key["columnas_destino"],
                strict=True,
            ):
                source = dictionary_by_key.get(
                    (foreign_key["origen_oid"], source_name)
                )
                target = dictionary_by_key.get(
                    (foreign_key["destino_oid"], target_name)
                )
                exact_match = bool(
                    source
                    and target
                    and source["tipo_oid"] == target["tipo_oid"]
                    and source["modificador_tipo"] == target["modificador_tipo"]
                    and source["esquema_tipo"] == target["esquema_tipo"]
                    and source["nombre_tipo"] == target["nombre_tipo"]
                )
                column_pairs.append(
                    {
                        "columna_origen": source_name,
                        "tipo_origen": (
                            source["tipo_formateado"] if source else None
                        ),
                        "columna_destino": target_name,
                        "tipo_destino": (
                            target["tipo_formateado"] if target else None
                        ),
                        "coincidencia_tipo_exacta": exact_match,
                        "metadatos_completos": source is not None
                        and target is not None,
                    }
                )
            comparisons.append(
                {
                    "restriccion": foreign_key["nombre"],
                    "tabla_origen": foreign_key["tabla_origen"],
                    "tabla_destino": foreign_key["tabla_destino"],
                    "columnas": column_pairs,
                    "todos_tipos_exactamente_iguales": bool(column_pairs)
                    and all(
                        pair["coincidencia_tipo_exacta"]
                        for pair in column_pairs
                    ),
                }
            )
        mismatches = [
            comparison
            for comparison in comparisons
            if not comparison["todos_tipos_exactamente_iguales"]
        ]
        evidence.append(
            ActivityEvidence(
                clave="consistencia_tipos_fk",
                consulta_id="foreign_keys_column_dictionary",
                disponibilidad="disponible" if foreign_keys else "sin_datos",
                naturaleza="calculada",
                datos={
                    "relaciones": comparisons,
                    "diferencias_tipo_exacto": mismatches,
                    "total_fk": len(comparisons),
                    "total_fk_con_diferencias": len(mismatches),
                    "cobertura_entregable": "completa_metadatos_disponibles",
                },
            )
        )
        limitations = [
            "Una diferencia de tipo exacto es un hallazgo técnico, pero PostgreSQL puede admitir una FK mediante operadores compatibles.",
            "No se consultan valores para evaluar conversiones, rangos efectivos ni reglas empresariales.",
        ]

    outcomes = [outcome for _, outcome in query_outcomes]
    warnings = [
        warning
        for query_id, outcome in query_outcomes
        if (warning := _technical_warning(query_id, outcome)) is not None
    ]
    status = _activity_status(outcomes)
    if status == "error_tecnico":
        evidence_status: EvidenceStatus = "no_obtenida"
    elif status == "parcial":
        evidence_status = "insuficiente"
    elif activity.numero == "5.8" and not foreign_keys:
        evidence_status = "sin_datos"
    elif activity.numero == "5.8":
        evidence_status = "suficiente"
    else:
        evidence_status = "insuficiente"
    return ActivityResult(
        identificador=activity.numero,
        numero_original=activity.numero,
        nombre_original=activity.actividad,
        fase_original=activity.fase,
        estado_ejecucion=status,
        estado_evidencia=evidence_status,
        evidencias=evidence if status != "error_tecnico" else [],
        advertencias=warnings,
        limitaciones=limitations,
        duracion_ms=round((time.perf_counter() - started) * 1000),
    )


async def _execute_optimization_activity(
    connection: psycopg.AsyncConnection,
    activity: ChecklistActivityReference,
) -> ActivityResult:
    if activity.numero in {"6.1", "6.2"}:
        return await _execute_advanced_performance_activity(
            connection,
            activity,
        )

    if activity.numero == "6.3":
        inventory = await _execute_view_inventory(connection, activity)
        if inventory.estado_ejecucion != "error_tecnico":
            inventory.evidencias.append(
                ActivityEvidence(
                    clave="evaluacion_necesidad_vistas_materializadas",
                    consulta_id="view_inventory_and_dependencies",
                    disponibilidad="no_disponible",
                    naturaleza="no_disponible",
                    datos={
                        "necesidades_reporteria_evaluadas": False,
                        "carga_consultas_evaluada": False,
                        "propuestas_confirmadas": [],
                        "cobertura_entregable": "parcial",
                    },
                )
            )
        inventory.identificador = activity.numero
        inventory.estado_evidencia = (
            "no_obtenida"
            if inventory.estado_ejecucion == "error_tecnico"
            else "insuficiente"
        )
        inventory.limitaciones.extend(
            [
                "La existencia de vistas no demuestra la necesidad de materializarlas.",
                "La propuesta requiere consultas de reportería, frecuencia, latencia y tolerancia a datos no actualizados.",
                "No se crean ni refrescan vistas materializadas.",
            ]
        )
        return inventory

    if activity.numero == "6.4":
        inventory = await _execute_programmable_inventory(connection, activity)
        if inventory.estado_ejecucion != "error_tecnico":
            inventory.evidencias.append(
                ActivityEvidence(
                    clave="evaluacion_optimizacion_rutinas",
                    consulta_id="programmable_objects_inventory",
                    disponibilidad="no_disponible",
                    naturaleza="no_disponible",
                    datos={
                        "cuerpos_extraidos": False,
                        "rutinas_ejecutadas": False,
                        "planes_ejecucion_disponibles": False,
                        "optimizaciones_confirmadas": [],
                        "cobertura_entregable": "parcial",
                    },
                )
            )
        inventory.identificador = activity.numero
        inventory.estado_evidencia = (
            "no_obtenida"
            if inventory.estado_ejecucion == "error_tecnico"
            else "insuficiente"
        )
        inventory.limitaciones.extend(
            [
                "El inventario técnico no permite determinar cuáles rutinas son críticas ni si necesitan optimización.",
                "La revisión requiere cuerpos aprobados, llamadas representativas y planes de ejecución sanitizados.",
                "El motor no ejecuta funciones ni procedimientos auditados.",
            ]
        )
        return inventory

    started = time.perf_counter()
    configuration_outcome = await _fetch_rows(
        connection,
        ENGINE_CONFIGURATION_SQL,
    )
    settings = [
        {
            "parametro": name,
            "valor": value,
            "unidad": unit,
            "tipo": value_type,
            "contexto": context,
            "origen": source,
            "reinicio_pendiente": bool(pending_restart),
        }
        for (
            name,
            value,
            unit,
            value_type,
            context,
            source,
            pending_restart,
        ) in (configuration_outcome.rows or [])
    ]
    status = _activity_status([configuration_outcome])
    warnings = [
        warning
        for warning in [
            _technical_warning("engine_configuration", configuration_outcome)
        ]
        if warning is not None
    ]
    evidence = []
    if status != "error_tecnico":
        evidence.append(
            ActivityEvidence(
                clave="configuracion_motor_postgresql",
                consulta_id="engine_configuration",
                disponibilidad="disponible" if settings else "sin_datos",
                naturaleza="exacta",
                datos={
                    "parametros": settings,
                    "pool_conexiones_aplicacion_evaluado": False,
                    "dimensionamiento_servidor_disponible": False,
                    "recomendaciones_confirmadas": [],
                    "cobertura_entregable": "parcial",
                },
            )
        )
    return ActivityResult(
        identificador=activity.numero,
        numero_original=activity.numero,
        nombre_original=activity.actividad,
        fase_original=activity.fase,
        estado_ejecucion=status,
        estado_evidencia=(
            "no_obtenida" if status == "error_tecnico" else "insuficiente"
        ),
        evidencias=evidence,
        advertencias=warnings,
        limitaciones=[
            "Los valores se documentan sin asumir que exista una configuración óptima universal.",
            "La evaluación requiere memoria, CPU, almacenamiento, concurrencia y carga representativa del entorno.",
            "El pool de conexiones pertenece normalmente a la aplicación o a infraestructura externa y no se observa en pg_settings.",
            "No se modifica ningún parámetro del servidor.",
        ],
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


async def _execute_audit_activities(
    connection: psycopg.AsyncConnection,
    activities: list[ChecklistActivityReference],
    progress=None,
) -> AuditExecutionResult:
    started = time.perf_counter()
    results: list[ActivityResult] = []
    from app.audit_catalog import CATALOG, COMPLETE_DELIVERABLES, EXTERNAL_REQUIREMENTS, definition_matches
    from app.audit_extended import execute_extended_activity
    for activity in activities:
        trace: list[dict] = []
        _query_trace.set(trace)
        from app.checklist_versions import TECHNICAL_CATALOG, matches
        technical = activity.numero in TECHNICAL_CATALOG and matches(activity, TECHNICAL_CATALOG[activity.numero])
        if technical:
            from app.audit_technical import execute_technical_activity
            result = await execute_technical_activity(connection, activity)
        elif activity.numero == "2.1":
            result = await _execute_table_inventory(connection, activity)
        elif activity.numero == "2.2":
            result = await _execute_table_classification(connection, activity)
        elif activity.numero == "2.3":
            result = await _execute_volumetry(connection, activity)
        elif activity.numero == "2.4":
            result = await _execute_table_retirement_candidates(connection, activity)
        elif activity.numero == "2.5":
            result = await _execute_table_module_matrix(connection, activity)
        elif activity.numero == "2.6":
            result = await _execute_audit_table_candidates(connection, activity)
        elif activity.numero == "2.7":
            result = await _execute_view_inventory(connection, activity)
        elif activity.numero == "2.8":
            result = await _execute_programmable_inventory(connection, activity)
        elif activity.numero in {
            "3.1",
            "3.2",
            "3.3",
            "3.4",
            "3.5",
            "3.6",
            "3.7",
            "3.8",
            "3.9",
        }:
            result = await _execute_column_dictionary_activity(connection, activity)
        elif activity.numero in {"4.1", "4.2", "4.3", "4.4"}:
            result = await _execute_index_activity(connection, activity)
        elif activity.numero in {"4.5", "4.6", "4.7", "4.8"}:
            result = await _execute_advanced_performance_activity(
                connection,
                activity,
            )
        elif activity.numero in {
            "5.1",
            "5.2",
            "5.3",
            "5.4",
            "5.5",
            "5.6",
            "5.7",
            "5.8",
        }:
            result = await _execute_data_model_activity(connection, activity)
        elif activity.numero in {"6.1", "6.2", "6.3", "6.4", "6.7"}:
            result = await _execute_optimization_activity(connection, activity)
        elif activity.numero in CATALOG:
            result = await execute_extended_activity(connection, activity)
        else:
            result = _unsupported_activity(activity)
        result.identificador = activity.numero
        result.entregable_esperado = activity.entregable_esperado
        result.prioridad_original = activity.prioridad
        result.numero_hoja = activity.numero_hoja
        result.consultas = trace
        if any(item["estado"] != "completada" for item in trace):
            obtained = any(item["estado"] == "completada" or item["filas"] > 0 for item in trace)
            result.estado_ejecucion = "parcial" if obtained else "error_tecnico"
            result.estado_evidencia = "insuficiente" if obtained else "no_obtenida"
        if any(item["estado"] == "limite" for item in trace):
            result.limitaciones.append(f"Evidencia truncada a {MAX_QUERY_ROWS} filas por consulta; ningún total del subconjunto representa el inventario completo.")
        if result.estado_ejecucion == "error_tecnico":
            result.grado_automatizacion = "error"
        elif result.estado_ejecucion == "no_ejecutable":
            result.grado_automatizacion = "no_automatizada"
        elif result.estado_ejecucion == "sin_automatizacion_configurada":
            result.grado_automatizacion = "sin_configuracion"
        else:
            result.grado_automatizacion = "parcial"
            if activity.numero in COMPLETE_DELIVERABLES and definition_matches(activity) and result.estado_ejecucion == "completada" and result.estado_evidencia in {"suficiente", "sin_datos"}:
                result.grado_automatizacion = "total"
            if not technical and not definition_matches(activity):
                result.limitaciones.append("El nombre, fase o entregable no coincide íntegramente con el catálogo revisado; la cobertura completa no está acreditada.")
            requirement = EXTERNAL_REQUIREMENTS.get(activity.numero)
            if not technical and requirement and requirement not in result.limitaciones:
                result.limitaciones.append(requirement)
        if technical:
            result.grado_automatizacion = 'total' if result.estado_evidencia in {'suficiente','sin_datos'} and result.estado_ejecucion == 'completada' else 'error' if result.estado_ejecucion=='error_tecnico' else 'parcial'
            result.estado_entregable = 'completo' if result.grado_automatizacion=='total' else 'error_tecnico' if result.grado_automatizacion=='error' else 'evidencia_incompleta'
            result.estado_actividad = 'incompleta'  # Falta la etapa de diagnóstico/recomendación.
        else:
            from app.audit_coverage import describe_deliverable
            describe_deliverable(result)
        results.append(result)
        if progress is not None:
            await progress({"tipo": "actividad", "identificador": activity.numero,
                            "procesadas": len(results), "total": len(activities),
                            "estado": result.estado_ejecucion, "grado": result.grado_automatizacion})

    if results and all(a.numero in TECHNICAL_CATALOG and matches(a,TECHNICAL_CATALOG[a.numero]) for a in activities):
        from app.audit_technical import consolidate_findings
        consolidate_findings(results)
    return AuditExecutionResult(
        catalogo_version=AUDIT_CATALOG_VERSION,
        actividades=results,
        duracion_total_ms=round((time.perf_counter() - started) * 1000),
    )


async def execute_audit_activities(connection, activities, progress=None) -> AuditExecutionResult:
    execution_date = datetime.now(UTC)
    cache_token = _query_cache.set({})
    trace_token = _query_trace.set(None)
    try:
        result = await _execute_audit_activities(connection, activities, progress)
        result.fecha_ejecucion = execution_date
        from app.checklist_versions import detect_version, fingerprint, TECHNICAL_VERSION, TECHNICAL_CRITERIA
        result.checklist_version = detect_version(activities)
        result.checklist_huella = fingerprint(result.checklist_version)
        if result.checklist_version == TECHNICAL_VERSION:
            result.criterios_evaluacion_version = TECHNICAL_CRITERIA
        return result
    finally:
        _query_cache.reset(cache_token)
        _query_trace.reset(trace_token)
