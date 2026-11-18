import asyncio
import json
import logging
import time
from typing import Annotated
from uuid import UUID

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError, model_validator
from psycopg import errors

from app.ai_diagnostics import AiNarrative, add_ai_narratives, mark_unfinished_analysis
from app.audit_engine import (
    AuditExecutionResult,
    AuditStorageInfo,
    ChecklistActivityReference,
    execute_audit_activities,
)
from app.auth import AuthRuntimeConfig, get_current_session, get_runtime_config, require_csrf
from app.audit_history import (
    AuditHistoryError, AuditHistoryPage, SavedAudit, get_saved_audit, list_audits,
    save_audit, summarize_audit,
    acquire_ai_lock, update_audit_analysis,
)
from app.checklists import MAX_CHECKLIST_ACTIVITIES
from app.external_connections import (
    DestinationNotAllowedError,
    ExternalConnectionPolicy,
    ExternalConnectionRequest,
    InsufficientDatabasePrivilegesError,
    ElevatedPrivilegesConfirmationRequired,
    get_external_connection_policy,
    open_verified_external_connection,
)
from app.sessions import AuthenticatedSession

router = APIRouter(prefix="/api/audits", tags=["audits"])


class AuditExecutionRequest(BaseModel):
    conexion: ExternalConnectionRequest
    nombre_aplicacion: str | None = Field(default=None, max_length=120)
    entorno_auditado: str | None = Field(default=None, max_length=120)
    checklist_version: str | None = Field(default=None, max_length=80)
    actividades: list[ChecklistActivityReference] = Field(
        min_length=1,
        max_length=MAX_CHECKLIST_ACTIVITIES,
    )

    @model_validator(mode="after")
    def reject_duplicate_activity_identifiers(self) -> "AuditExecutionRequest":
        identifiers = [activity.numero for activity in self.actividades]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("El checklist contiene identificadores de actividad duplicados.")
        from app.checklist_versions import detect_version, TECHNICAL_VERSION
        detected = detect_version(self.actividades)
        if self.checklist_version is not None and self.checklist_version != detected:
            raise ValueError('Las actividades no corresponden a la versión declarada.')
        # No ejecutar una mezcla de requisitos técnicos como si fuera un checklist histórico.
        from app.checklist_versions import TECHNICAL_CATALOG, matches
        if detected != TECHNICAL_VERSION and any(a.numero in TECHNICAL_CATALOG and matches(a,TECHNICAL_CATALOG[a.numero]) for a in self.actividades):
            raise ValueError('Importe la versión técnica completa sin alterar orden o requisitos.')
        return self


async def parse_audit_execution_request(request: Request) -> AuditExecutionRequest:
    try:
        payload = await request.json()
        return AuditExecutionRequest.model_validate(payload)
    except (ValueError, TypeError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Revise la conexión y las actividades proporcionadas.",
        ) from None


@router.post("/execute", response_model=AuditExecutionResult)
async def execute_audit(
    response: Response,
    authenticated_session: Annotated[AuthenticatedSession, Depends(require_csrf)],
    policy: Annotated[ExternalConnectionPolicy, Depends(get_external_connection_policy)],
    execution_request: Annotated[
        AuditExecutionRequest,
        Depends(parse_audit_execution_request),
    ],
    runtime: Annotated[AuthRuntimeConfig, Depends(get_runtime_config)],
) -> AuditExecutionResult:
    response.headers["Cache-Control"] = "no-store"
    return await _perform_audit(execution_request, policy, authenticated_session, runtime)


async def _perform_audit(execution_request, policy, authenticated_session, runtime, progress=None):
    started=time.perf_counter()
    try:
        async with open_verified_external_connection(
            execution_request.conexion,
            policy,
            application_name="sistema_auditoria_engine",
        ) as connection:
            if progress is None:
                result = await execute_audit_activities(connection, execution_request.actividades)
            else:
                result = await execute_audit_activities(connection, execution_request.actividades, progress)
        # Las credenciales y la conexión auditada no se pasan al servicio de IA.
        result.nombre_aplicacion = execution_request.nombre_aplicacion
        result.entorno_auditado = execution_request.entorno_auditado
        for activity in result.actividades:
            activity.redaccion_ia = AiNarrative(
                estado='no_solicitada',
                mensaje='Evidencia SQL guardada para análisis automático de IA. La etapa de redacción aún no ha terminado.',
            )
        if progress:
            await progress({"tipo": "etapa", "etapa": "Redactando diagnóstico y recomendación"})
        from app.audit_coverage import finalize_activity_states
        finalize_activity_states(result)
    except DestinationNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El destino de conexión no está permitido.",
        ) from exc
    except errors.InvalidPassword as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fue posible autenticar con las credenciales proporcionadas.",
        ) from exc
    except ElevatedPrivilegesConfirmationRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except (errors.InsufficientPrivilege, InsufficientDatabasePrivilegesError) as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no cumple los requisitos mínimos de lectura.",
        ) from exc
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible ejecutar la auditoría técnica.",
        ) from exc
    result.resumen = summarize_audit(result)
    result.duracion_ejecucion_ms=round((time.perf_counter()-started)*1000)
    if progress:
        await progress({"tipo": "etapa", "etapa": "Guardando resultados"})
    try:
        saved = await asyncio.to_thread(
            save_audit, runtime.database, authenticated_session.user_id,
            execution_request.conexion.database, result,
        )
    except AuditHistoryError as exc:
        result.almacenamiento = AuditStorageInfo(estado="error", mensaje=str(exc))
        mark_unfinished_analysis(result, 'No se inició el análisis IA porque falló el guardado de evidencia: ' + str(exc))
        result.resumen = summarize_audit(result)
        return result
    return await _analyze_saved_audit(saved.almacenamiento.id, authenticated_session, runtime, progress)


async def _analyze_saved_audit(audit_id, session, runtime, progress=None):
    lock = None
    try:
        # Comprobar propiedad antes de adquirir recursos o llamar al proveedor.
        record = await asyncio.to_thread(get_saved_audit, runtime.database, session.user_id, audit_id)
        if record is None:
            raise HTTPException(status_code=404, detail='Auditoría no encontrada.')
        acquiring = asyncio.create_task(asyncio.to_thread(acquire_ai_lock, runtime.database, session.user_id, audit_id))
        try:
            lock = await asyncio.shield(acquiring)
        except asyncio.CancelledError:
            lock = await acquiring
            raise
        if lock is None:
            raise HTTPException(status_code=409, detail='El análisis de esta auditoría ya está en curso. Consulte el historial.')
        record = await asyncio.to_thread(get_saved_audit, runtime.database, session.user_id, audit_id)
        result = record.resultado
        from app.audit_coverage import finalize_activity_states
        checkpoint_started = time.perf_counter()

        async def checkpoint(current):
            nonlocal checkpoint_started
            finalize_activity_states(current)
            current.duracion_ejecucion_ms = (current.duracion_ejecucion_ms or 0) + round((time.perf_counter() - checkpoint_started) * 1000)
            await asyncio.to_thread(update_audit_analysis, runtime.database, session.user_id, audit_id, current)
            checkpoint_started = time.perf_counter()
            if progress:
                generated = sum(a.redaccion_ia.estado == 'generada' for a in current.actividades)
                await progress({'tipo': 'etapa', 'etapa': f'Redacción IA: {generated} de {len(current.actividades)} actividades; evidencia guardada'})

        try:
            await add_ai_narratives(result, checkpoint=checkpoint)
        except AuditHistoryError:
            raise
        except Exception as exc:
            # Solo clase de excepción; ni texto, traceback, credenciales o contexto.
            logging.getLogger(__name__).error('ai_pipeline_failure type=%s', type(exc).__name__)
            mark_unfinished_analysis(result, 'El procesamiento interno de IA se interrumpió. Las evidencias SQL se conservan. Revise el registro seguro del backend; no es un fallo de PostgreSQL ni una respuesta de Gemini.')
        await checkpoint(result)
        return result
    except AuditHistoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    finally:
        if lock is not None:
            await asyncio.to_thread(lock.close)


@router.post('/{audit_id}/retry-ai', response_model=AuditExecutionResult)
async def retry_ai(
    audit_id: UUID,
    response: Response,
    authenticated_session: Annotated[AuthenticatedSession, Depends(require_csrf)],
    runtime: Annotated[AuthRuntimeConfig, Depends(get_runtime_config)],
):
    response.headers['Cache-Control'] = 'no-store'
    return await _analyze_saved_audit(audit_id, authenticated_session, runtime)


@router.post("/execute-stream")
async def execute_audit_stream(
    authenticated_session: Annotated[AuthenticatedSession, Depends(require_csrf)],
    policy: Annotated[ExternalConnectionPolicy, Depends(get_external_connection_policy)],
    execution_request: Annotated[AuditExecutionRequest, Depends(parse_audit_execution_request)],
    runtime: Annotated[AuthRuntimeConfig, Depends(get_runtime_config)],
):
    async def events():
        queue = asyncio.Queue(maxsize=8)

        async def run():
            try:
                result = await _perform_audit(execution_request, policy, authenticated_session, runtime, queue.put)
                await queue.put({"tipo": "resultado", "resultado": result.model_dump(mode="json")})
            except HTTPException as exc:
                await queue.put({"tipo": "error", "mensaje": exc.detail})
            except Exception:
                await queue.put({"tipo": "error", "mensaje": "No fue posible completar la auditoría. Revise el servicio backend."})

        task = asyncio.create_task(run())
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=10)
                except TimeoutError:
                    event = {"tipo": "espera"}
                yield json.dumps(event, ensure_ascii=False) + "\n"
                if event["tipo"] in {"resultado", "error"}:
                    break
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(events(), media_type="application/x-ndjson", headers={
        "Cache-Control": "no-store", "X-Accel-Buffering": "no", "X-Content-Type-Options": "nosniff",
    })


@router.get("", response_model=AuditHistoryPage)
def history(
    response: Response,
    authenticated_session: Annotated[AuthenticatedSession, Depends(get_current_session)],
    runtime: Annotated[AuthRuntimeConfig, Depends(get_runtime_config)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditHistoryPage:
    response.headers["Cache-Control"] = "no-store"
    try:
        return list_audits(runtime.database, authenticated_session.user_id, limit, offset)
    except AuditHistoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Cache-Control": "no-store"}) from None


@router.get("/{audit_id}", response_model=SavedAudit)
def saved_audit(
    audit_id: UUID,
    response: Response,
    authenticated_session: Annotated[AuthenticatedSession, Depends(get_current_session)],
    runtime: Annotated[AuthRuntimeConfig, Depends(get_runtime_config)],
) -> SavedAudit:
    response.headers["Cache-Control"] = "no-store"
    try:
        record = get_saved_audit(runtime.database, authenticated_session.user_id, audit_id)
    except AuditHistoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Cache-Control": "no-store"}) from None
    if record is None:
        raise HTTPException(status_code=404, detail="Auditoría no encontrada.", headers={"Cache-Control": "no-store"})
    return record


@router.get("/{audit_id}/pdf")
def export_pdf(
    audit_id: UUID,
    authenticated_session: Annotated[AuthenticatedSession, Depends(get_current_session)],
    runtime: Annotated[AuthRuntimeConfig, Depends(get_runtime_config)],
) -> Response:
    from app.audit_pdf import render_audit_pdf
    try:
        record = get_saved_audit(runtime.database, authenticated_session.user_id, audit_id)
    except AuditHistoryError as exc:
        raise HTTPException(status_code=503, detail=str(exc), headers={"Cache-Control": "no-store"}) from None
    if record is None:
        raise HTTPException(status_code=404, detail="Auditoría no encontrada.", headers={"Cache-Control": "no-store"})
    from reportlab.platypus.doctemplate import LayoutError
    try:
        document = render_audit_pdf(record)
    except (LayoutError, ValueError, TypeError, OSError):
        raise HTTPException(status_code=503, detail="No fue posible componer el PDF de esta auditoría. La evidencia guardada se conserva.", headers={"Cache-Control": "no-store"}) from None
    return Response(document, media_type="application/pdf", headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Disposition": f'attachment; filename="auditoria-{audit_id}.pdf"',
    })
