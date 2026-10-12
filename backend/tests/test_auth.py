import asyncio
import secrets
import unittest
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException, Response
from openpyxl import Workbook
from starlette.datastructures import Headers, UploadFile
from starlette.requests import Request

from app.auth import (
    GENERIC_CREDENTIALS_MESSAGE,
    LOGIN_ATTEMPT_LIMIT,
    AuthRuntimeConfig,
    LoginAttemptLimiter,
    LoginRequest,
    current_user,
    get_current_session,
    login,
    require_csrf,
)
from app.checklists import import_checklist
from app.internal_db import InternalDatabaseConfig
from app.sessions import (
    INSERT_SESSION_SQL,
    AuthConfig,
    AuthConfigurationError,
    AuthenticatedSession,
    CreatedSession,
    InvalidCredentialsError,
    authenticate_and_create_session,
    hash_session_token,
)


def make_request(
    origin: str = "http://localhost:5173",
    csrf_token: str | None = None,
    scheme: str | None = None,
) -> Request:
    headers = [(b"origin", origin.encode("ascii"))]
    if csrf_token:
        headers.append((b"x-csrf-token", csrf_token.encode("ascii")))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/auth/login",
            "headers": headers,
            "client": ("127.0.0.1", 50000),
            "server": ("localhost", 5173),
            "scheme": scheme or origin.split(":", maxsplit=1)[0],
        }
    )


def runtime_config(environment: str = "development") -> AuthRuntimeConfig:
    return AuthRuntimeConfig(
        database=InternalDatabaseConfig(
            host="localhost",
            port=5432,
            database="sistema_auditoria",
            user="application_user",
            password=str(object()),
        ),
        auth=AuthConfig(
            environment=environment,
            origin=(
                "https://auditoria.example"
                if environment == "production"
                else "http://localhost:5173"
            ),
            session_ttl_minutes=480,
        ),
    )


def build_workbook() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Checklist Maestro"
    worksheet.append(
        (
            "Fase",
            "#",
            "Paso / Actividad",
            "Entregable Esperado",
            "Prioridad",
            "Estado",
            "Responsable",
            "Notas / Evidencia",
        )
    )
    worksheet.append(("Fase 1", 1, "Actividad 1", None, "Alta", None, None, None))
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class AuthConfigTests(unittest.TestCase):
    def test_requires_explicit_configuration(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(AuthConfigurationError):
                AuthConfig.from_environment()

    def test_rejects_http_origin_in_production(self):
        environment = {
            "APP_ENV": "production",
            "APP_ORIGIN": "http://auditoria.example",
            "SESSION_TTL_MINUTES": "480",
        }
        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaisesRegex(AuthConfigurationError, "HTTPS"):
                AuthConfig.from_environment()

    def test_accepts_explicit_https_production_configuration(self):
        environment = {
            "APP_ENV": "production",
            "APP_ORIGIN": "https://auditoria.example",
            "SESSION_TTL_MINUTES": "480",
        }
        with patch.dict("os.environ", environment, clear=True):
            config = AuthConfig.from_environment()

        self.assertTrue(config.secure_cookie)
        self.assertEqual(config.origin, "https://auditoria.example")


class SessionStorageTests(unittest.TestCase):
    @patch("app.sessions._connect")
    @patch("app.sessions.password_hasher")
    def test_stores_only_hash_of_opaque_session_token(
        self,
        password_hasher: MagicMock,
        connect: MagicMock,
    ):
        password_hasher.verify.return_value = True
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (7, "auditor_admin", str(object()), True)

        session = authenticate_and_create_session(
            runtime_config().database,
            runtime_config().auth,
            "auditor_admin",
            secrets.token_urlsafe(18),
        )

        insert_call = cursor.execute.call_args_list[1]
        self.assertEqual(insert_call.args[0], INSERT_SESSION_SQL)
        inserted_values = insert_call.args[1]
        self.assertEqual(inserted_values[1], hash_session_token(session.session_token))
        self.assertNotEqual(inserted_values[1], session.session_token)
        password_hasher.verify.assert_called_once()


class LoginEndpointTests(unittest.TestCase):
    @patch("app.auth.authenticate_and_create_session")
    def test_rejects_plain_http_requests_in_production(
        self,
        authenticate: MagicMock,
    ):
        with self.assertRaises(HTTPException) as context:
            login(
                LoginRequest(
                    username="test_user",
                    password=secrets.token_urlsafe(18),
                ),
                make_request(
                    origin="https://auditoria.example",
                    scheme="http",
                ),
                Response(),
                runtime_config(environment="production"),
            )

        self.assertEqual(context.exception.status_code, 400)
        authenticate.assert_not_called()

    @patch("app.auth.authenticate_and_create_session")
    def test_returns_generic_error_for_invalid_credentials(
        self,
        authenticate: MagicMock,
    ):
        authenticate.side_effect = InvalidCredentialsError()
        credentials = LoginRequest(
            username="desconocido",
            password=secrets.token_urlsafe(18),
        )

        with self.assertRaises(HTTPException) as context:
            login(
                credentials,
                make_request(),
                Response(),
                runtime_config(),
            )

        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.detail, GENERIC_CREDENTIALS_MESSAGE)

    @patch("app.auth.authenticate_and_create_session")
    def test_sets_secure_httponly_cookie_in_production(
        self,
        authenticate: MagicMock,
    ):
        authenticate.return_value = CreatedSession(
            user_id=7,
            username="auditor_admin",
            csrf_token=secrets.token_urlsafe(32),
            expires_at=datetime.now(UTC) + timedelta(hours=8),
            session_token=secrets.token_urlsafe(32),
        )
        response = Response()

        result = login(
            LoginRequest(username="auditor_admin", password=secrets.token_urlsafe(18)),
            make_request(origin="https://auditoria.example"),
            response,
            runtime_config(environment="production"),
        )

        cookie = response.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=lax", cookie)
        self.assertEqual(result.user.username, "auditor_admin")
        self.assertEqual(result.csrf_token, authenticate.return_value.csrf_token)

    def test_limits_repeated_failures_in_memory(self):
        limiter = LoginAttemptLimiter()
        key = ("127.0.0.1", "auditor_admin")

        for attempt in range(LOGIN_ATTEMPT_LIMIT):
            limiter.record_failure(key, now=float(attempt))

        self.assertTrue(limiter.is_blocked(key, now=float(LOGIN_ATTEMPT_LIMIT)))


class AuthenticationDependencyTests(unittest.TestCase):
    def test_me_returns_user_and_csrf_token_for_session_restore(self):
        session = AuthenticatedSession(
            user_id=7,
            username="test_user",
            csrf_token=secrets.token_urlsafe(32),
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        result = current_user(Response(), session)

        self.assertEqual(result.user.id, session.user_id)
        self.assertEqual(result.user.username, session.username)
        self.assertEqual(result.csrf_token, session.csrf_token)

    def test_rejects_request_without_session_cookie(self):
        with self.assertRaises(HTTPException) as context:
            get_current_session(make_request(), runtime_config(), None)

        self.assertEqual(context.exception.status_code, 401)

    def test_rejects_invalid_csrf_token(self):
        session = AuthenticatedSession(
            user_id=7,
            username="auditor_admin",
            csrf_token="expected-token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )

        with self.assertRaises(HTTPException) as context:
            require_csrf(
                make_request(csrf_token="other-token"),
                runtime_config(),
                session,
            )

        self.assertEqual(context.exception.status_code, 403)

    def test_valid_session_and_csrf_allow_excel_import(self):
        csrf_token = secrets.token_urlsafe(32)
        session = AuthenticatedSession(
            user_id=7,
            username="auditor_admin",
            csrf_token=csrf_token,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        verified_session = require_csrf(
            make_request(csrf_token=csrf_token),
            runtime_config(),
            session,
        )
        upload = UploadFile(
            file=BytesIO(build_workbook()),
            filename="checklist.xlsx",
            headers=Headers(
                {
                    "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                }
            ),
        )

        result = asyncio.run(import_checklist(upload, verified_session))

        self.assertEqual(result.cantidad_fases, 1)
        self.assertEqual(result.cantidad_actividades, 1)


class SessionsMigrationTests(unittest.TestCase):
    def test_is_versioned_non_destructive_and_defines_server_sessions(self):
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "sql"
            / "migrations"
            / "002_create_user_sessions.sql"
        )
        sql = migration_path.read_text(encoding="utf-8")

        for definition in (
            "user_id BIGINT NOT NULL REFERENCES public.users(id) ON DELETE CASCADE",
            "token_hash CHAR(64) NOT NULL UNIQUE",
            "csrf_token TEXT NOT NULL",
            "expires_at TIMESTAMPTZ NOT NULL",
        ):
            with self.subTest(definition=definition):
                self.assertIn(definition, sql)

        uppercase_sql = sql.upper()
        for forbidden_statement in ("DROP TABLE", "ALTER TABLE", "TRUNCATE"):
            with self.subTest(statement=forbidden_statement):
                self.assertNotIn(forbidden_statement, uppercase_sql)


if __name__ == "__main__":
    unittest.main()
