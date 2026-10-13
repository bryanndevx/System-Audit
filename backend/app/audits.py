from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, ValidationError, model_validator
from psycopg import errors

from app.audit_engine import (
    AuditExecutionResult,
    ChecklistActivityReference,
    execute_audit_activities,
)
from app.auth import require_csrf
from app.external_connections import (
    DestinationNotAllowedError,
    ExternalConnectionPolicy,
    ExternalConnectionRequest,
    InsufficientDatabasePrivilegesError,
    get_external_connection_policy,
    open_verified_external_connection,
)
from app.sessions import AuthenticatedSession

router = APIRouter(prefix="/api/audits", tags=["audits"])


class AuditExecutionRequest(BaseModel):
    conexion: ExternalConnectionRequest
    actividades: list[ChecklistActivityReference] = Field(
        min_length=1,
        max_length=100,
    )

    @model_validator(mode="after")
    def reject_duplicate_activity_identifiers(self) -> "AuditExecutionRequest":
        identifiers = [activity.numero for activity in self.actividades]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("El checklist contiene identificadores de actividad duplicados.")
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
) -> AuditExecutionResult:
    del authenticated_session
    response.headers["Cache-Control"] = "no-store"
    try:
        async with open_verified_external_connection(
            execution_request.conexion,
            policy,
            application_name="sistema_auditoria_engine",
        ) as connection:
            return await execute_audit_activities(
                connection,
                execution_request.actividades,
            )
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
