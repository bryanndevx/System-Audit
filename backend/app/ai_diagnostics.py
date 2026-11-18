"""Redacción Gemini sobre contexto técnico agregado. No ejecuta SQL."""

from __future__ import annotations

import asyncio
import http.client
import json
import logging
import os
import random
import socket
import threading
import re
import time
from dataclasses import dataclass
from datetime import datetime, UTC, timedelta
from email.utils import parsedate_to_datetime
from weakref import WeakKeyDictionary
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.ai_context import CONTEXT_VERSION, CRITERIA_VERSION, GENERAL_CRITERIA, build_activity_context
from app.local_config import LocalConfigurationError, load_local_gemini_environment

if TYPE_CHECKING:
    from app.audit_engine import AuditExecutionResult

DEFAULT_MODEL = "gemini-3.5-flash-lite"
MAX_RESPONSE_BYTES = 256 * 1024
MAX_CONTEXT_BYTES = 96 * 1024
MAX_ERROR_BYTES = 16 * 1024
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT = 20
MAX_RETRY_WAIT = 60
logger = logging.getLogger(__name__)
# Una cola por bucle del proceso; también serializa auditorías simultáneas.
_request_gates = WeakKeyDictionary()


class AiNarrative(BaseModel):
    proveedor: Literal["gemini"] = "gemini"
    estado: Literal["generada", "error", "no_configurada", "no_aplica", "no_solicitada"] = "no_configurada"
    diagnostico: str | None = None
    recomendacion: str | None = None
    referencias_evidencia: list[int] = Field(default_factory=list)
    mensaje: str | None = None
    modelo: str | None = None
    criterios_version: str = CRITERIA_VERSION
    contexto_version: str = CONTEXT_VERSION
    tipo_error: Literal['transitorio', 'configuracion', 'respuesta_invalida', 'contexto_invalido', 'error_interno'] | None = None
    reintentar_desde: datetime | None = None


class GeneratedNarrative(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str = Field(min_length=1, max_length=50)
    diagnostico: str = Field(min_length=1, max_length=1500)
    recomendacion: str = Field(min_length=1, max_length=1500)
    referencias_evidencia: list[int] = Field(min_length=1, max_length=100)

    @field_validator("diagnostico", "recomendacion")
    @classmethod
    def reject_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("La redacción está vacía.")
        return value.strip()


class GeneratedBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    actividades: list[GeneratedNarrative] = Field(min_length=1, max_length=100)


class GeminiError(RuntimeError):
    def __init__(self, message: str, *, diagnostic_detail: str | None = None,
                 transient: bool = False, status: int | None = None, retry_after: float = 0):
        super().__init__(message)
        # Solo el comando local muestra este detalle; nunca va al frontend.
        self.diagnostic_detail = diagnostic_detail
        self.transient = transient
        self.status = status
        self.retry_after = retry_after


def retry_after_seconds(value) -> float:
    if not isinstance(value, str):
        return 0
    try:
        seconds = float(value)
        return max(0, seconds) if seconds < float('inf') else 0
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return 0


def provider_error(response: http.client.HTTPResponse, api_key: str) -> GeminiError:
    """Clasifica errores sin devolver mensajes, URLs o metadatos del proveedor."""
    status = response.status
    code = None
    reasons = set()
    message = ""
    diagnostic_detail = None
    allowed_codes = {
        "INVALID_ARGUMENT", "FAILED_PRECONDITION", "UNAUTHENTICATED", "PERMISSION_DENIED",
        "NOT_FOUND", "RESOURCE_EXHAUSTED", "INTERNAL", "UNAVAILABLE", "DEADLINE_EXCEEDED",
    }
    try:
        raw = response.read(MAX_ERROR_BYTES + 1)
        if len(raw) <= MAX_ERROR_BYTES:
            error = json.loads(raw).get("error", {})
            candidate = error.get("status")
            if isinstance(candidate, str) and candidate in allowed_codes:
                code = candidate
            original = error.get("message", "")
            if isinstance(original, str):
                # El detalle corresponde a una solicitud técnica; no volcar la
                # respuesta completa ni las cabeceras/metadatos del proveedor.
                diagnostic_detail = original.replace(api_key, "[CLAVE OCULTA]") if api_key else original
                diagnostic_detail = re.sub(r"AIza[A-Za-z0-9_-]+", "[CLAVE OCULTA]", diagnostic_detail)
                diagnostic_detail = re.sub(r"https?://[^\s<>]+", "[URL OCULTA]", diagnostic_detail)
                diagnostic_detail = re.sub(r"[\w.+-]+@[\w.-]+", "[CORREO OCULTO]", diagnostic_detail)
                diagnostic_detail = re.sub(r"projects/[^/\s\"']+", "projects/[PROYECTO OCULTO]", diagnostic_detail)
                diagnostic_detail = " ".join(diagnostic_detail.split())[:1200]
                message = original.casefold()
            for detail in error.get("details", []):
                if isinstance(detail, dict) and isinstance(detail.get("reason"), str):
                    reasons.add(detail["reason"])
    except (ValueError, TypeError, AttributeError, OSError, http.client.HTTPException):
        pass
    prefix = f"Gemini (HTTP {status}" + (f", {code}" if code else "") + "): "

    def failure(summary: str) -> GeminiError:
        return GeminiError(prefix + summary, diagnostic_detail=diagnostic_detail,
                           status=status, transient=status in {408, 429, 500, 502, 503, 504},
                           retry_after=retry_after_seconds(response.getheader('Retry-After')))

    if reasons & {"API_KEY_INVALID", "API_KEY_EXPIRED", "API_KEY_LEAKED"} or any(
        marker in message for marker in ("api key not valid", "api key expired", "api key was reported as leaked")
    ):
        return failure("la clave API no es válida, expiró o fue bloqueada. Vuelva a configurarla localmente.")
    if status in {401, 403}:
        return failure("rechazó la clave o los permisos de la API. Revise las restricciones de la clave y el proyecto en AI Studio.")
    if status == 404:
        return failure("el modelo configurado no está disponible para esta API o proyecto. Revise GEMINI_MODEL con los modelos disponibles de su cuenta.")
    if status == 400:
        if code == "FAILED_PRECONDITION":
            return failure("el proyecto no cumple los requisitos del servicio. Compruebe la disponibilidad del nivel gratuito para su cuenta y región.")
        if any(field in message for field in ("response_json_schema", "responsejsonschema", "response_schema", "generation_config", "generationconfig")):
            return failure("rechazó los parámetros de generación o el esquema JSON de la solicitud. Se requiere revisar la compatibilidad con el modelo.")
        return failure("rechazó la solicitud por parámetros inválidos. Consulte el detalle técnico del diagnóstico local.")
    if status == 429:
        return failure("agotó la cuota o el límite de solicitudes. El análisis queda pendiente si se agotan los reintentos limitados.")
    if status in {500, 502, 503, 504}:
        return failure("hay un fallo de disponibilidad del servicio. Espere antes de volver a probar.")
    return failure("no pudo procesar la solicitud. Revise la disponibilidad y configuración del servicio.")


@dataclass(frozen=True, repr=False)
class GeminiConfig:
    api_key: str
    model: str

    @classmethod
    def from_environment(cls) -> GeminiConfig | None:
        try:
            load_local_gemini_environment()
        except LocalConfigurationError as exc:
            raise GeminiError(str(exc)) from None
        enabled = os.getenv("GEMINI_ENABLED", "0").strip()
        if enabled == "0":
            return None
        if enabled != "1":
            raise GeminiError("GEMINI_ENABLED debe ser 0 o 1.")
        key = os.getenv("GEMINI_API_KEY", "").strip()
        model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip()
        if not key or any(ord(character) < 33 or ord(character) > 126 for character in key):
            raise GeminiError("Configure GEMINI_API_KEY en el entorno del backend.")
        if not re.fullmatch(r"gemini-[a-z0-9.-]{1,70}", model) or any(
            value in model for value in ("preview", "experimental", "exp-")
        ):
            raise GeminiError("GEMINI_MODEL debe identificar un modelo Gemini estable.")
        return cls(api_key=key, model=model)


def request_gemini(config: GeminiConfig, contexts: list[dict]) -> dict[str, GeneratedNarrative]:
    context = json.dumps({
        "criterios_version": CRITERIA_VERSION, "contexto_version": CONTEXT_VERSION,
        "actividades": contexts,
    }, ensure_ascii=False)
    if len(context.encode("utf-8")) > MAX_CONTEXT_BYTES:
        raise GeminiError("El resumen técnico supera el límite de envío a IA.")
    payload = {
        "systemInstruction": {"parts": [{"text": (
            "Redacta en español diagnóstico y recomendación breves por actividad. "
            "Devuelve exactamente los identificadores recibidos, sin cambiar estados. "
            "Interpreta los hallazgos técnicos ya calculados y explica su alcance y limitaciones. "
            "La recomendación debe responder a esos hallazgos e indicar qué validar, sin acciones automáticas. "
            "Cada actividad contiene id, diagnostico, recomendacion y referencias_evidencia "
            "(lista de números de referencia existentes en las evidencias de esa actividad). "
            + GENERAL_CRITERIA
        )}]},
        "contents": [{"role": "user", "parts": [{"text": context}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            # Subconjunto OpenAPI de Gemini. Los límites, campos adicionales y
            # correspondencia de IDs se validan después con GeneratedBatch.
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "actividades": {
                        "type": "ARRAY",
                        "items": {
                            "type": "OBJECT",
                            "properties": {
                                "id": {"type": "STRING"},
                                "diagnostico": {"type": "STRING"},
                                "recomendacion": {"type": "STRING"},
                                "referencias_evidencia": {"type": "ARRAY", "items": {"type": "INTEGER"}},
                            },
                            "required": ["id", "diagnostico", "recomendacion", "referencias_evidencia"],
                        },
                    },
                },
                "required": ["actividades"],
            },
            "maxOutputTokens": min(16000, max(2048, len(contexts) * 450)),
        },
    }
    connection = http.client.HTTPSConnection("generativelanguage.googleapis.com", timeout=REQUEST_TIMEOUT)
    transport = None
    expired = threading.Event()
    def abort_request():
        expired.set()
        try:
            active_socket = transport if transport is not None else connection.sock
            if active_socket is not None:
                active_socket.shutdown(socket.SHUT_RDWR)
            connection.close()
        except OSError:
            pass
    deadline = threading.Timer(30, abort_request)
    deadline.daemon = True
    deadline.start()
    try:
        connection.request(
            "POST", f"/v1beta/models/{config.model}:generateContent",
            body=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "x-goog-api-key": config.api_key},
        )
        # Conservar el transporte también si HTTPResponse retiene un socket
        # que HTTPConnection desvincula al recibir Connection: close.
        transport = connection.sock
        response = connection.getresponse()
        if response.status != 200:
            raise provider_error(response, config.api_key)
        raw = response.read(MAX_RESPONSE_BYTES + 1)
        if expired.is_set():
            raise GeminiError('Gemini superó el tiempo máximo de redacción.', transient=True)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise GeminiError("La respuesta de Gemini supera el tamaño permitido.")
        body = json.loads(raw)
        candidates = body.get("candidates", [])
        if len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
            raise GeminiError("Gemini devolvió una respuesta bloqueada o incompleta.")
        parts = candidates[0]["content"]["parts"]
        text = "".join(part["text"] for part in parts if not part.get("thought", False))
        batch = GeneratedBatch.model_validate_json(text)
        identifiers = [item.id for item in batch.actividades]
        if len(set(identifiers)) != len(identifiers) or set(identifiers) != {item["id"] for item in contexts}:
            raise GeminiError("La respuesta de Gemini no corresponde a las actividades solicitadas.")
        references = {item["id"]: {evidence["referencia"] for evidence in item["evidencias"]} for item in contexts}
        for item in batch.actividades:
            if len(set(item.referencias_evidencia)) != len(item.referencias_evidencia) or not set(item.referencias_evidencia) <= references[item.id]:
                raise GeminiError("La redacción de Gemini cita evidencias inexistentes o repetidas.")
        return {item.id: item for item in batch.actividades}
    except GeminiError:
        raise
    except (OSError, http.client.HTTPException):
        raise GeminiError("No se pudo contactar a Gemini o se agotó el tiempo de conexión.", transient=True) from None
    except (ValueError, KeyError, TypeError, AttributeError, ValidationError):
        if expired.is_set():
            raise GeminiError('Gemini superó el tiempo máximo de redacción.', transient=True) from None
        raise GeminiError("Gemini devolvió una respuesta con formato inválido.") from None
    finally:
        deadline.cancel()
        connection.close()


async def request_with_retries(config, batch):
    loop = asyncio.get_running_loop()
    gate = _request_gates.setdefault(loop, asyncio.Lock())
    async with gate:
        remaining = getattr(gate, 'retry_not_before', 0) - time.monotonic()
        if remaining > MAX_RETRY_WAIT:
            raise GeminiError('Gemini solicita una espera prolongada. Reintente el análisis más tarde.',
                              transient=True, retry_after=remaining)
        if remaining > 0:
            await asyncio.sleep(remaining)
        gate.retry_not_before = 0
        for attempt in range(MAX_ATTEMPTS):
            task = asyncio.create_task(asyncio.to_thread(request_gemini, config, batch))
            try:
                async with asyncio.timeout(30):
                    return await asyncio.shield(task)
            except (TimeoutError, asyncio.CancelledError) as exc:
                # to_thread no detiene el socket. Mantener el turno hasta que cierre
                # evita solapar una solicitud abandonada con el siguiente intento.
                try:
                    await task
                except Exception:
                    pass
                if isinstance(exc, asyncio.CancelledError):
                    raise
                error = GeminiError('Gemini superó el tiempo máximo de redacción.', transient=True)
            except GeminiError as exc:
                error = exc
            logger.warning('gemini_failure status=%s transient=%s attempt=%s',
                           error.status, error.transient, attempt + 1)
            if not error.transient or attempt == MAX_ATTEMPTS - 1:
                if error.retry_after:
                    gate.retry_not_before = time.monotonic() + error.retry_after
                raise error
            delay = max(error.retry_after, 2 ** (attempt + 1) + random.uniform(0, 1))
            if delay > MAX_RETRY_WAIT:
                gate.retry_not_before = time.monotonic() + delay
                # No ignorar un Retry-After largo ni mantener una petición abierta indefinidamente.
                raise GeminiError('Gemini solicita una espera prolongada. Reintente el análisis más tarde.',
                                  transient=True, status=error.status, retry_after=delay)
            await asyncio.sleep(delay)


async def add_ai_narratives(result: AuditExecutionResult, checkpoint=None) -> AuditExecutionResult:
    started = time.perf_counter()
    # Respetar la espera del proveedor también al reabrir el historial/reiniciar.
    if any(a.redaccion_ia.reintentar_desde and a.redaccion_ia.reintentar_desde > datetime.now(UTC)
           for a in result.actividades):
        return result
    eligible = []
    contexts = []
    for activity in result.actividades:
        if valid_narrative(activity):
            continue
        try:
            context = build_activity_context(activity)
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
            logger.error('gemini_context_failure activity=%s', activity.identificador)
            activity.redaccion_ia = AiNarrative(
                estado='error', tipo_error='contexto_invalido',
                mensaje='No se pudo preparar el contexto técnico de esta actividad para IA. La evidencia SQL se conserva; no se envió este contexto a Gemini.',
            )
            continue
        if context is None:
            activity.redaccion_ia = AiNarrative(
                estado="no_aplica", mensaje="No hay evidencia técnica procesable para redactar esta actividad.",
            )
        else:
            eligible.append(activity)
            contexts.append(context)
    if not eligible:
        return result
    model = None
    attempted_ids: set[str] = set()
    try:
        config = GeminiConfig.from_environment()
        if config is None:
            for activity in eligible:
                activity.redaccion_ia = AiNarrative(
                    mensaje="La redacción con Gemini no está habilitada en el backend.",
                )
            return result
        model = config.model
        # Lotes acotados evitan truncar la salida de las 67 actividades.
        # Solo pendientes; el modelo configurado se conserva en todos los intentos.
        for offset in range(0, len(contexts), 12):
            batch = contexts[offset:offset + 12]
            attempted_ids.update(context["id"] for context in batch)
            generated = await request_with_retries(config, batch)
            for activity in eligible[offset:offset + 12]:
                narrative = generated[activity.identificador]
                activity.redaccion_ia = AiNarrative(
                    estado="generada", modelo=model,
                    diagnostico=narrative.diagnostico, recomendacion=narrative.recomendacion,
                    referencias_evidencia=narrative.referencias_evidencia,
                )
            if checkpoint:
                result.duracion_ia_ms += round((time.perf_counter() - started) * 1000)
                await checkpoint(result)
                started = time.perf_counter()
    except (GeminiError, TimeoutError) as exc:
        message = str(exc) if isinstance(exc, GeminiError) else "Gemini superó el tiempo máximo de redacción."
        for activity in eligible:
            if not valid_narrative(activity):
                if attempted_ids and activity.identificador not in attempted_ids:
                    activity.redaccion_ia = AiNarrative(
                        estado="no_solicitada", modelo=model,
                        mensaje="Esta actividad no se envió a Gemini porque se detuvieron los lotes restantes tras un error anterior. Su evidencia SQL se conserva.",
                    )
                else:
                    activity.redaccion_ia = AiNarrative(
                        estado="error", mensaje=message, modelo=model,
                        tipo_error=('transitorio' if isinstance(exc, GeminiError) and exc.transient
                                    else 'configuracion' if isinstance(exc, GeminiError) and exc.status in {400, 401, 403, 404}
                                    else 'respuesta_invalida'),
                        reintentar_desde=(datetime.now(UTC) + timedelta(seconds=exc.retry_after)
                                          if isinstance(exc, GeminiError) and exc.retry_after else None),
                    )
    finally:
        result.duracion_ia_ms += round((time.perf_counter() - started) * 1000)
    return result


def mark_unfinished_analysis(result, message):
    """Un fallo previo al proveedor nunca debe dejar narrativas sin causa registrada."""
    for activity in result.actividades:
        if not valid_narrative(activity) and activity.redaccion_ia.estado != 'no_aplica':
            activity.redaccion_ia = AiNarrative(estado='error', tipo_error='error_interno', mensaje=message)


def valid_narrative(activity):
    ai = activity.redaccion_ia
    return (ai.estado == 'generada' and bool((ai.diagnostico or '').strip())
            and bool((ai.recomendacion or '').strip()) and bool(ai.referencias_evidencia)
            and len(set(ai.referencias_evidencia)) == len(ai.referencias_evidencia)
            and all(1 <= reference <= len(activity.evidencias) for reference in ai.referencias_evidencia))
