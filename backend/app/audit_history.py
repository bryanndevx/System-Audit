"""Historial en la base interna; no recibe credenciales de la base auditada."""

import json
import base64
import binascii
import zlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ValidationError

from app.audit_engine import AuditExecutionResult, AuditStorageInfo, AuditSummary
from app.internal_db import InternalDatabaseConfig

MAX_SAVED_RESULT_BYTES = 16 * 1024 * 1024
MAX_DECODED_RESULT_BYTES = 64 * 1024 * 1024


def storage_payload(result):
    payload = result.model_dump(mode='json')
    raw = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(raw) > MAX_DECODED_RESULT_BYTES:
        raise AuditHistoryError('El resultado supera los 64 MiB de evidencia permitidos. Se conserva en esta pantalla.')
    if len(raw) <= MAX_SAVED_RESULT_BYTES:
        return payload
    # Metadatos consultables para el listado; cuerpo íntegro, sin eliminar evidencias.
    wrapped = {key: payload.get(key) for key in ('resumen', 'duracion_total_ms', 'duracion_ia_ms', 'checklist_version', 'duracion_ejecucion_ms')}
    # Índice de identificadores para conservar la restricción JSONB histórica;
    # el contenido completo se restaura antes de construir cualquier respuesta.
    wrapped['actividades'] = [{'identificador': item['identificador']} for item in payload['actividades']]
    wrapped.update(formato_almacenamiento='zlib-json-v1',
                   resultado_comprimido=base64.b64encode(zlib.compress(raw)).decode('ascii'))
    if len(json.dumps(wrapped).encode()) > MAX_SAVED_RESULT_BYTES:
        raise AuditHistoryError('El resultado comprimido supera los 16 MiB permitidos. Se conserva en esta pantalla.')
    return wrapped


def decode_storage_payload(payload):
    if not isinstance(payload, dict) or payload.get('formato_almacenamiento') != 'zlib-json-v1':
        return payload
    try:
        encoded = payload['resultado_comprimido']
        if not isinstance(encoded, str) or len(encoded) > MAX_SAVED_RESULT_BYTES:
            raise ValueError()
        decoder = zlib.decompressobj()
        raw = decoder.decompress(base64.b64decode(encoded, validate=True), MAX_DECODED_RESULT_BYTES + 1)
        if len(raw) > MAX_DECODED_RESULT_BYTES or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError()
        return json.loads(raw)
    except (ValueError, TypeError, KeyError, zlib.error, binascii.Error):
        raise AuditHistoryError('La evidencia comprimida está dañada o supera los límites permitidos.') from None
INSERT_AUDIT_SQL = """
    INSERT INTO public.audit_runs (id, user_id, database_name, created_at, result)
    VALUES (%s, %s, %s, %s, %s)
"""
COUNT_AUDITS_SQL = "SELECT COUNT(*) FROM public.audit_runs WHERE user_id = %s"
LIST_AUDITS_SQL = """
    SELECT id, database_name, created_at, result -> 'resumen',
           result -> 'duracion_total_ms', result -> 'duracion_ia_ms', result ->> 'checklist_version'
      FROM public.audit_runs
     WHERE user_id = %s
     ORDER BY created_at DESC, id DESC
     LIMIT %s OFFSET %s
"""
SELECT_AUDIT_SQL = """
    SELECT id, database_name, created_at, result
      FROM public.audit_runs
     WHERE id = %s AND user_id = %s
"""


class AuditHistoryError(RuntimeError):
    pass


class AuditHistoryItem(BaseModel):
    id: UUID
    base_datos: str
    fecha: datetime
    resumen: AuditSummary
    duracion_sql_ms: int
    duracion_ia_ms: int
    checklist_version: str | None = None


class AuditHistoryPage(BaseModel):
    auditorias: list[AuditHistoryItem]
    total: int
    limite: int
    desplazamiento: int


class SavedAudit(BaseModel):
    id: UUID
    base_datos: str
    fecha: datetime
    resultado: AuditExecutionResult


def summarize_audit(result: AuditExecutionResult) -> AuditSummary:
    from app.checklist_versions import TECHNICAL_VERSION
    technical = result.checklist_version == TECHNICAL_VERSION
    automated = sum(
        activity.estado_actividad == 'completada' if technical else activity.grado_automatizacion == "total" if activity.grado_automatizacion is not None else
        (activity.estado_ejecucion == "completada"
        and activity.estado_evidencia in {"suficiente", "sin_datos"})
        for activity in result.actividades
    )
    errors = sum(activity.estado_ejecucion == "error_tecnico" for activity in result.actividades)
    unconfigured = sum(activity.estado_ejecucion == "sin_automatizacion_configurada" for activity in result.actividades)
    total = len(result.actividades)
    external = sum(activity.estado_ejecucion == "no_ejecutable" for activity in result.actividades)
    partial = total - automated - errors - unconfigured - external
    return AuditSummary(
        total=total, automatizadas=automated,
        parciales=partial, no_ejecutables=external,
        errores_sql=errors, sin_configuracion=unconfigured,
        errores_ia=sum(activity.redaccion_ia.estado == "error" for activity in result.actividades),
        porcentaje_automatizacion=round(automated / total * 100, 2) if total else 0,
        porcentaje_parcial=round(partial / total * 100, 2) if total else 0,
        requieren_informacion_externa=sum(a.estado_entregable == 'requiere_informacion_externa' for a in result.actividades),
        con_evidencia_postgresql=sum(any(e.disponibilidad in {'disponible', 'sin_datos'} and e.naturaleza != 'no_disponible' for e in a.evidencias) for a in result.actividades),
        completadas=automated, incompletas=total-automated,
    )


def _connect(config: InternalDatabaseConfig):
    return psycopg.connect(
        host=config.host, port=config.port, dbname=config.database,
        user=config.user, password=config.password, connect_timeout=5,
        options="-c statement_timeout=5000",
    )


def _history_error(error: psycopg.Error) -> AuditHistoryError:
    if isinstance(error, psycopg.errors.UndefinedTable):
        return AuditHistoryError("El historial no está preparado. Aplique la migración 003 en la base interna.")
    return AuditHistoryError("No fue posible acceder al historial de auditorías. Revise la base interna y sus permisos.")


def save_audit(
    config: InternalDatabaseConfig, user_id: int, database_name: str,
    result: AuditExecutionResult,
) -> AuditExecutionResult:
    saved = result.model_copy(deep=True)
    saved.resumen = summarize_audit(saved)
    saved.almacenamiento = AuditStorageInfo(estado="guardada", id=uuid4(), fecha=datetime.now(UTC))
    payload = storage_payload(saved)
    try:
        with _connect(config) as connection:
            with connection.cursor() as cursor:
                cursor.execute(INSERT_AUDIT_SQL, (
                    saved.almacenamiento.id, user_id, database_name,
                    saved.almacenamiento.fecha, Jsonb(payload),
                ))
    except psycopg.Error as exc:
        raise _history_error(exc) from None
    return saved


def list_audits(config: InternalDatabaseConfig, user_id: int, limit: int, offset: int) -> AuditHistoryPage:
    try:
        with _connect(config) as connection:
            with connection.cursor() as cursor:
                cursor.execute(COUNT_AUDITS_SQL, (user_id,))
                total = cursor.fetchone()[0]
                cursor.execute(LIST_AUDITS_SQL, (user_id, limit, offset))
                rows = cursor.fetchall()
        return AuditHistoryPage(
            auditorias=[AuditHistoryItem(
                id=row[0], base_datos=row[1], fecha=row[2], resumen=row[3],
                duracion_sql_ms=row[4], duracion_ia_ms=row[5],
                checklist_version=row[6] if len(row)>6 else None,
            ) for row in rows],
            total=total, limite=limit, desplazamiento=offset,
        )
    except psycopg.Error as exc:
        raise _history_error(exc) from None
    except (ValidationError, TypeError, IndexError):
        raise AuditHistoryError("El historial contiene un registro con formato inválido.") from None


def get_saved_audit(config: InternalDatabaseConfig, user_id: int, audit_id: UUID) -> SavedAudit | None:
    try:
        with _connect(config) as connection:
            with connection.cursor() as cursor:
                cursor.execute(SELECT_AUDIT_SQL, (audit_id, user_id))
                row = cursor.fetchone()
        if row is None:
            return None
        return SavedAudit(id=row[0], base_datos=row[1], fecha=row[2], resultado=decode_storage_payload(row[3]))
    except psycopg.Error as exc:
        raise _history_error(exc) from None
    except (ValidationError, TypeError, IndexError):
        raise AuditHistoryError("La auditoría guardada tiene un formato inválido.") from None


def acquire_ai_lock(config, user_id, audit_id):
    """Exclusión entre procesos; el cierre de conexión libera el bloqueo de sesión."""
    connection = None
    try:
        connection = _connect(config)
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_try_advisory_lock(hashtextextended(%s, 0))',
                           (f'audit-ai:{user_id}:{audit_id}',))
            acquired = cursor.fetchone()[0]
        connection.rollback()
        if not acquired:
            connection.close()
            return None
        return connection
    except psycopg.Error as exc:
        if connection is not None:
            connection.close()
        raise _history_error(exc) from None


def update_audit_analysis(config, user_id, audit_id, result):
    """Actualiza el mismo registro interno; no recibe conexión ni credenciales auditadas."""
    result.resumen = summarize_audit(result)
    payload = storage_payload(result)
    try:
        with _connect(config) as connection:
            with connection.cursor() as cursor:
                cursor.execute('UPDATE public.audit_runs SET result = %s WHERE id = %s AND user_id = %s',
                               (Jsonb(payload), audit_id, user_id))
                if cursor.rowcount != 1:
                    raise AuditHistoryError('No fue posible actualizar esta auditoría.')
    except psycopg.Error as exc:
        raise _history_error(exc) from None
    return result
