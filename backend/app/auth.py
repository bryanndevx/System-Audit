import hmac
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.internal_db import (
    InternalDatabaseConfig,
    InternalDatabaseConfigurationError,
)
from app.sessions import (
    SESSION_COOKIE_NAME,
    AuthConfig,
    AuthConfigurationError,
    AuthenticatedSession,
    AuthenticationStorageError,
    InvalidCredentialsError,
    authenticate_and_create_session,
    delete_session,
    get_session,
)

LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW_SECONDS = 15 * 60
MAX_TRACKED_LOGIN_KEYS = 10_000
GENERIC_CREDENTIALS_MESSAGE = "Usuario o contraseña incorrectos."

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=1024)


class AuthenticatedUserResponse(BaseModel):
    id: int
    username: str


class AuthStateResponse(BaseModel):
    user: AuthenticatedUserResponse
    csrf_token: str


@dataclass(frozen=True)
class AuthRuntimeConfig:
    database: InternalDatabaseConfig
    auth: AuthConfig


class LoginAttemptLimiter:
    def __init__(self) -> None:
        self._attempts: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.Lock()

    def _active_attempts(self, key: tuple[str, str], now: float) -> deque[float]:
        attempts = self._attempts.setdefault(key, deque())
        cutoff = now - LOGIN_ATTEMPT_WINDOW_SECONDS
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        if not attempts:
            self._attempts.pop(key, None)
            attempts = deque()
        return attempts

    def is_blocked(self, key: tuple[str, str], now: float | None = None) -> bool:
        current_time = time.monotonic() if now is None else now
        with self._lock:
            attempts = self._active_attempts(key, current_time)
            return len(attempts) >= LOGIN_ATTEMPT_LIMIT

    def record_failure(self, key: tuple[str, str], now: float | None = None) -> None:
        current_time = time.monotonic() if now is None else now
        with self._lock:
            attempts = self._active_attempts(key, current_time)
            if len(self._attempts) >= MAX_TRACKED_LOGIN_KEYS and key not in self._attempts:
                oldest_key = min(
                    self._attempts,
                    key=lambda tracked_key: self._attempts[tracked_key][-1],
                )
                self._attempts.pop(oldest_key, None)
            attempts.append(current_time)
            self._attempts[key] = attempts

    def clear(self, key: tuple[str, str]) -> None:
        with self._lock:
            self._attempts.pop(key, None)


login_attempt_limiter = LoginAttemptLimiter()


def get_runtime_config() -> AuthRuntimeConfig:
    try:
        return AuthRuntimeConfig(
            database=InternalDatabaseConfig.from_environment(),
            auth=AuthConfig.from_environment(),
        )
    except (InternalDatabaseConfigurationError, AuthConfigurationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El servicio de autenticación no está configurado correctamente.",
        ) from exc


def _require_trusted_origin(request: Request, auth_config: AuthConfig) -> None:
    if auth_config.environment == "production" and request.url.scheme != "https":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HTTPS es obligatorio en producción.",
        )
    if request.headers.get("origin") != auth_config.origin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origen de solicitud no permitido.",
        )


def _storage_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="El servicio de autenticación no está disponible.",
    )


def _auth_response(session: AuthenticatedSession) -> AuthStateResponse:
    return AuthStateResponse(
        user=AuthenticatedUserResponse(
            id=session.user_id,
            username=session.username,
        ),
        csrf_token=session.csrf_token,
    )


def get_current_session(
    request: Request,
    runtime: Annotated[AuthRuntimeConfig, Depends(get_runtime_config)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> AuthenticatedSession:
    if runtime.auth.environment == "production" and request.url.scheme != "https":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="HTTPS es obligatorio en producción.",
        )
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida.",
        )
    try:
        session = get_session(runtime.database, session_token)
    except AuthenticationStorageError as exc:
        raise _storage_unavailable() from exc
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión no es válida o ha vencido.",
        )
    return session


def require_csrf(
    request: Request,
    runtime: Annotated[AuthRuntimeConfig, Depends(get_runtime_config)],
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
) -> AuthenticatedSession:
    _require_trusted_origin(request, runtime.auth)
    supplied_token = request.headers.get("x-csrf-token", "")
    if not supplied_token or not hmac.compare_digest(
        supplied_token,
        session.csrf_token,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token CSRF no válido.",
        )
    return session


@router.post("/login", response_model=AuthStateResponse)
def login(
    credentials: LoginRequest,
    request: Request,
    response: Response,
    runtime: Annotated[AuthRuntimeConfig, Depends(get_runtime_config)],
) -> AuthStateResponse:
    _require_trusted_origin(request, runtime.auth)
    client_address = request.client.host if request.client else "unknown"
    limiter_key = (client_address, credentials.username.casefold())
    if login_attempt_limiter.is_blocked(limiter_key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Demasiados intentos. Intente nuevamente más tarde.",
            headers={"Retry-After": str(LOGIN_ATTEMPT_WINDOW_SECONDS)},
        )

    try:
        session = authenticate_and_create_session(
            runtime.database,
            runtime.auth,
            credentials.username,
            credentials.password,
        )
    except InvalidCredentialsError as exc:
        login_attempt_limiter.record_failure(limiter_key)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=GENERIC_CREDENTIALS_MESSAGE,
        ) from exc
    except AuthenticationStorageError as exc:
        raise _storage_unavailable() from exc

    login_attempt_limiter.clear(limiter_key)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session.session_token,
        max_age=runtime.auth.session_ttl_minutes * 60,
        expires=session.expires_at,
        path="/",
        secure=runtime.auth.secure_cookie,
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
    return _auth_response(session)


@router.get("/me", response_model=AuthStateResponse)
def current_user(
    response: Response,
    session: Annotated[AuthenticatedSession, Depends(get_current_session)],
) -> AuthStateResponse:
    response.headers["Cache-Control"] = "no-store"
    return _auth_response(session)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    runtime: Annotated[AuthRuntimeConfig, Depends(get_runtime_config)],
    session: Annotated[AuthenticatedSession, Depends(require_csrf)],
    session_token: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> None:
    del session
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación requerida.",
        )
    try:
        delete_session(runtime.database, session_token)
    except AuthenticationStorageError as exc:
        raise _storage_unavailable() from exc
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=runtime.auth.secure_cookie,
        httponly=True,
        samesite="lax",
    )
    response.headers["Cache-Control"] = "no-store"
