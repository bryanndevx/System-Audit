import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

import psycopg
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from psycopg import Error as PsycopgError

from app.internal_db import InternalDatabaseConfig

SESSION_COOKIE_NAME = "audit_session"
SELECT_USER_SQL = """
    SELECT id, username, password_hash, is_active
      FROM public.users
     WHERE username = %s
"""
INSERT_SESSION_SQL = """
    INSERT INTO public.user_sessions (user_id, token_hash, csrf_token, expires_at)
    VALUES (%s, %s, %s, %s)
"""
SELECT_SESSION_SQL = """
    SELECT users.id, users.username, sessions.csrf_token, sessions.expires_at
      FROM public.user_sessions AS sessions
      JOIN public.users AS users ON users.id = sessions.user_id
     WHERE sessions.token_hash = %s
       AND sessions.expires_at > NOW()
       AND users.is_active = TRUE
"""
DELETE_SESSION_SQL = """
    DELETE FROM public.user_sessions
     WHERE token_hash = %s
"""

password_hasher = PasswordHasher()
_dummy_password_hash = password_hasher.hash(secrets.token_urlsafe(32))


class AuthConfigurationError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
    pass


class AuthenticationStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class AuthConfig:
    environment: str
    origin: str
    session_ttl_minutes: int

    @property
    def secure_cookie(self) -> bool:
        return self.environment == "production"

    @classmethod
    def from_environment(cls) -> "AuthConfig":
        environment = os.getenv("APP_ENV", "").strip().lower()
        origin = os.getenv("APP_ORIGIN", "").strip()
        raw_ttl = os.getenv("SESSION_TTL_MINUTES", "").strip()

        if environment not in {"development", "production"}:
            raise AuthConfigurationError(
                "APP_ENV debe configurarse como development o production."
            )
        if not origin:
            raise AuthConfigurationError("APP_ORIGIN es obligatorio.")

        parsed_origin = urlsplit(origin)
        if (
            parsed_origin.scheme not in {"http", "https"}
            or not parsed_origin.hostname
            or parsed_origin.username
            or parsed_origin.password
            or parsed_origin.path not in {"", "/"}
            or parsed_origin.query
            or parsed_origin.fragment
        ):
            raise AuthConfigurationError(
                "APP_ORIGIN debe ser un origen HTTP(S) válido, sin ruta, consulta ni credenciales."
            )
        if environment == "production" and parsed_origin.scheme != "https":
            raise AuthConfigurationError(
                "APP_ORIGIN debe utilizar HTTPS cuando APP_ENV=production."
            )

        try:
            session_ttl_minutes = int(raw_ttl)
        except ValueError as exc:
            raise AuthConfigurationError(
                "SESSION_TTL_MINUTES debe ser un número entero."
            ) from exc
        if not 5 <= session_ttl_minutes <= 1440:
            raise AuthConfigurationError(
                "SESSION_TTL_MINUTES debe estar entre 5 y 1440."
            )

        normalized_origin = f"{parsed_origin.scheme}://{parsed_origin.netloc}"
        return cls(
            environment=environment,
            origin=normalized_origin,
            session_ttl_minutes=session_ttl_minutes,
        )


@dataclass(frozen=True)
class AuthenticatedSession:
    user_id: int
    username: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True)
class CreatedSession(AuthenticatedSession):
    session_token: str


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _connect(config: InternalDatabaseConfig):
    return psycopg.connect(
        host=config.host,
        port=config.port,
        dbname=config.database,
        user=config.user,
        password=config.password,
        connect_timeout=5,
    )


def authenticate_and_create_session(
    database_config: InternalDatabaseConfig,
    auth_config: AuthConfig,
    username: str,
    password: str,
) -> CreatedSession:
    try:
        with _connect(database_config) as connection:
            with connection.cursor() as cursor:
                cursor.execute(SELECT_USER_SQL, (username,))
                user_row = cursor.fetchone()

                password_hash = user_row[2] if user_row else _dummy_password_hash
                try:
                    password_matches = password_hasher.verify(password_hash, password)
                except VerifyMismatchError:
                    password_matches = False
                except (InvalidHashError, VerificationError):
                    raise AuthenticationStorageError(
                        "No fue posible verificar las credenciales."
                    ) from None

                if not user_row or not user_row[3] or not password_matches:
                    raise InvalidCredentialsError("Credenciales incorrectas.")

                session_token = secrets.token_urlsafe(32)
                csrf_token = secrets.token_urlsafe(32)
                expires_at = datetime.now(UTC) + timedelta(
                    minutes=auth_config.session_ttl_minutes
                )
                cursor.execute(
                    INSERT_SESSION_SQL,
                    (
                        user_row[0],
                        hash_session_token(session_token),
                        csrf_token,
                        expires_at,
                    ),
                )
    except InvalidCredentialsError:
        raise
    except AuthenticationStorageError:
        raise
    except PsycopgError:
        raise AuthenticationStorageError(
            "No fue posible acceder al almacenamiento de sesiones."
        ) from None

    return CreatedSession(
        user_id=user_row[0],
        username=user_row[1],
        csrf_token=csrf_token,
        expires_at=expires_at,
        session_token=session_token,
    )


def get_session(
    database_config: InternalDatabaseConfig,
    session_token: str,
) -> AuthenticatedSession | None:
    try:
        with _connect(database_config) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    SELECT_SESSION_SQL,
                    (hash_session_token(session_token),),
                )
                session_row = cursor.fetchone()
    except PsycopgError:
        raise AuthenticationStorageError(
            "No fue posible acceder al almacenamiento de sesiones."
        ) from None

    if session_row is None:
        return None
    return AuthenticatedSession(
        user_id=session_row[0],
        username=session_row[1],
        csrf_token=session_row[2],
        expires_at=session_row[3],
    )


def delete_session(
    database_config: InternalDatabaseConfig,
    session_token: str,
) -> None:
    try:
        with _connect(database_config) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    DELETE_SESSION_SQL,
                    (hash_session_token(session_token),),
                )
    except PsycopgError:
        raise AuthenticationStorageError(
            "No fue posible acceder al almacenamiento de sesiones."
        ) from None
