import asyncio
import secrets
import socket
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import psycopg
from fastapi import HTTPException
from pydantic import ValidationError
from psycopg import errors

from app.external_connections import (
    CONNECTION_METADATA_SQL,
    ROLE_ATTRIBUTES_SQL,
    SESSION_OPTIONS,
    SET_TRANSACTION_READ_ONLY_SQL,
    DestinationNotAllowedError,
    ExternalConnectionConfigurationError,
    ExternalConnectionPolicy,
    ExternalConnectionRequest,
    InsufficientDatabasePrivilegesError,
    parse_external_connection_request,
    resolve_allowed_address,
    test_external_connection,
    verify_external_connection,
)
from app.sessions import AuthenticatedSession


def connection_request() -> ExternalConnectionRequest:
    return ExternalConnectionRequest(
        host="localhost",
        port=5432,
        database="audit_test",
        username="audit_reader",
        password=secrets.token_urlsafe(18),
    )


def development_policy() -> ExternalConnectionPolicy:
    return ExternalConnectionPolicy(
        environment="development",
        allowed_hosts=frozenset({"localhost"}),
        allowed_networks=(),
        allowed_ports=frozenset({5432}),
        ssl_mode="disable",
        ssl_root_cert=None,
    )


def authenticated_session() -> AuthenticatedSession:
    return AuthenticatedSession(
        user_id=1,
        username="test_user",
        csrf_token=secrets.token_urlsafe(32),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class FakeCursor:
    def __init__(self, responses=None, execute_error=None, delay=0.0):
        self.responses = list(responses or [])
        self.execute_error = execute_error
        self.delay = delay
        self.executed: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False

    async def execute(self, statement: str):
        self.executed.append(statement)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.execute_error:
            raise self.execute_error

    async def fetchone(self):
        return self.responses.pop(0)


class FakeConnection:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor
        self.closed = False
        self.rollback_count = 0
        self.close_count = 0

    def cursor(self):
        return self._cursor

    async def rollback(self):
        self.rollback_count += 1

    async def close(self):
        self.close_count += 1
        self.closed = True


class ExternalConnectionValidationTests(unittest.TestCase):
    def test_redacts_password_from_model_representation(self):
        request = connection_request()

        self.assertNotIn(request.password.get_secret_value(), repr(request))

    def test_rejects_invalid_fields(self):
        invalid_values = (
            {"host": " https://db.example "},
            {"host": "db.example,other.example"},
            {"port": 0},
            {"port": 65536},
            {"database": " database"},
            {"username": "user "},
            {"password": ""},
        )

        base = connection_request().model_dump()
        base["password"] = secrets.token_urlsafe(18)
        for replacement in invalid_values:
            with self.subTest(replacement=replacement):
                with self.assertRaises(ValidationError):
                    ExternalConnectionRequest(**(base | replacement))


class ExternalConnectionRequestParsingTests(unittest.IsolatedAsyncioTestCase):
    async def test_validation_error_does_not_echo_password(self):
        password_value = secrets.token_urlsafe(900)
        request = AsyncMock()
        request.json.return_value = {
            "host": "localhost",
            "port": 5432,
            "database": "audit_test",
            "username": "audit_reader",
            "password": password_value,
        }

        with self.assertRaises(HTTPException) as context:
            await parse_external_connection_request(request)

        self.assertEqual(context.exception.status_code, 422)
        self.assertNotIn(password_value, context.exception.detail)


class ExternalConnectionPolicyTests(unittest.TestCase):
    def test_allows_explicit_local_development_configuration(self):
        environment = {
            "APP_ENV": "development",
            "AUDITED_DB_ALLOWED_HOSTS": "localhost,127.0.0.1",
            "AUDITED_DB_ALLOWED_PORTS": "5432",
            "AUDITED_DB_SSL_MODE": "disable",
        }

        with patch.dict("os.environ", environment, clear=True):
            policy = ExternalConnectionPolicy.from_environment()

        self.assertEqual(policy.ssl_mode, "disable")
        self.assertIn("localhost", policy.allowed_hosts)

    def test_production_requires_verify_full(self):
        environment = {
            "APP_ENV": "production",
            "AUDITED_DB_ALLOWED_HOSTS": "db.example",
            "AUDITED_DB_ALLOWED_PORTS": "5432",
            "AUDITED_DB_SSL_MODE": "disable",
        }

        with patch.dict("os.environ", environment, clear=True):
            with self.assertRaisesRegex(
                ExternalConnectionConfigurationError,
                "Producción requiere TLS",
            ):
                ExternalConnectionPolicy.from_environment()

    def test_production_accepts_allowlist_and_identity_verification(self):
        environment = {
            "APP_ENV": "production",
            "AUDITED_DB_ALLOWED_HOSTS": "db.example",
            "AUDITED_DB_ALLOWED_PORTS": "5432",
            "AUDITED_DB_SSL_MODE": "verify-full",
            "AUDITED_DB_SSL_ROOT_CERT": "system",
        }

        with patch.dict("os.environ", environment, clear=True):
            policy = ExternalConnectionPolicy.from_environment()

        self.assertEqual(policy.ssl_mode, "verify-full")
        self.assertEqual(policy.ssl_root_cert, "system")


class DestinationValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_host_outside_allowlist(self):
        with self.assertRaises(DestinationNotAllowedError):
            await resolve_allowed_address(
                "not-allowed.example",
                5432,
                development_policy(),
            )

    async def test_rejects_loopback_resolution_in_production(self):
        policy = ExternalConnectionPolicy(
            environment="production",
            allowed_hosts=frozenset({"db.example"}),
            allowed_networks=(),
            allowed_ports=frozenset({5432}),
            ssl_mode="verify-full",
            ssl_root_cert="system",
        )
        address_info = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", 5432),
            )
        ]
        loop = asyncio.get_running_loop()
        with patch.object(loop, "getaddrinfo", AsyncMock(return_value=address_info)):
            with self.assertRaises(DestinationNotAllowedError):
                await resolve_allowed_address("db.example", 5432, policy)


class VerifyExternalConnectionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.cursor = FakeCursor(
            responses=[
                ("audit_reader", "audit_test", True, True),
                (False, False, False, False, False),
            ]
        )
        self.connection = FakeConnection(self.cursor)

    @patch(
        "app.external_connections.resolve_allowed_address",
        AsyncMock(return_value="127.0.0.1"),
    )
    async def test_valid_connection_uses_read_only_options_and_predefined_sql(self):
        connect = AsyncMock(return_value=self.connection)
        request = connection_request()

        with patch("app.external_connections.psycopg.AsyncConnection.connect", connect):
            await verify_external_connection(request, development_policy())

        parameters = connect.await_args.kwargs
        self.assertEqual(parameters["host"], "localhost")
        self.assertEqual(parameters["hostaddr"], "127.0.0.1")
        self.assertEqual(parameters["options"], SESSION_OPTIONS)
        self.assertEqual(parameters["sslmode"], "disable")
        self.assertEqual(
            self.cursor.executed,
            [
                SET_TRANSACTION_READ_ONLY_SQL,
                CONNECTION_METADATA_SQL,
                ROLE_ATTRIBUTES_SQL,
            ],
        )
        self.assertEqual(self.connection.rollback_count, 1)
        self.assertEqual(self.connection.close_count, 1)

    @patch(
        "app.external_connections.resolve_allowed_address",
        AsyncMock(return_value="127.0.0.1"),
    )
    async def test_rejects_dangerous_role_attributes_without_checking_write_grants(self):
        self.cursor.responses[-1] = (True, False, False, False, False)
        connect = AsyncMock(return_value=self.connection)

        with patch("app.external_connections.psycopg.AsyncConnection.connect", connect):
            with self.assertRaises(InsufficientDatabasePrivilegesError):
                await verify_external_connection(
                    connection_request(),
                    development_policy(),
                )

        self.assertTrue(self.connection.closed)
        self.assertEqual(self.connection.rollback_count, 1)

    @patch(
        "app.external_connections.resolve_allowed_address",
        AsyncMock(return_value="127.0.0.1"),
    )
    async def test_closes_connection_when_read_check_fails(self):
        self.cursor.execute_error = errors.InsufficientPrivilege()
        connect = AsyncMock(return_value=self.connection)

        with patch("app.external_connections.psycopg.AsyncConnection.connect", connect):
            with self.assertRaises(errors.InsufficientPrivilege):
                await verify_external_connection(
                    connection_request(),
                    development_policy(),
                )

        self.assertTrue(self.connection.closed)
        self.assertEqual(self.connection.rollback_count, 1)


class ConnectionEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_limited_success_message(self):
        with patch(
            "app.external_connections.verify_external_connection",
            AsyncMock(),
        ):
            response = await test_external_connection(
                authenticated_session=authenticated_session(),
                policy=development_policy(),
                connection_request=connection_request(),
            )

        self.assertTrue(response.verified)
        self.assertIn("acceso básico a metadatos", response.message)
        self.assertIn("no garantiza", response.message.lower())

    async def test_maps_invalid_password_without_exposing_internal_details(self):
        internal_message = str(object())
        with patch(
            "app.external_connections.verify_external_connection",
            AsyncMock(side_effect=errors.InvalidPassword(internal_message)),
        ):
            with self.assertRaises(HTTPException) as context:
                await test_external_connection(
                    authenticated_session=authenticated_session(),
                    policy=development_policy(),
                    connection_request=connection_request(),
                )

        self.assertEqual(context.exception.status_code, 400)
        self.assertNotIn(internal_message, context.exception.detail)

    async def test_maps_unreachable_server_without_internal_details(self):
        internal_message = str(object())
        with patch(
            "app.external_connections.verify_external_connection",
            AsyncMock(side_effect=psycopg.OperationalError(internal_message)),
        ):
            with self.assertRaises(HTTPException) as context:
                await test_external_connection(
                    authenticated_session=authenticated_session(),
                    policy=development_policy(),
                    connection_request=connection_request(),
                )

        self.assertEqual(context.exception.status_code, 502)
        self.assertNotIn(internal_message, context.exception.detail)

    async def test_maps_insufficient_read_access(self):
        with patch(
            "app.external_connections.verify_external_connection",
            AsyncMock(side_effect=errors.InsufficientPrivilege()),
        ):
            with self.assertRaises(HTTPException) as context:
                await test_external_connection(
                    authenticated_session=authenticated_session(),
                    policy=development_policy(),
                    connection_request=connection_request(),
                )

        self.assertEqual(context.exception.status_code, 403)

    @patch(
        "app.external_connections.resolve_allowed_address",
        AsyncMock(return_value="127.0.0.1"),
    )
    async def test_total_timeout_still_closes_open_connection(self):
        slow_cursor = FakeCursor(delay=0.05)
        connection = FakeConnection(slow_cursor)
        connect = AsyncMock(return_value=connection)

        with (
            patch("app.external_connections.psycopg.AsyncConnection.connect", connect),
            patch("app.external_connections.TOTAL_OPERATION_TIMEOUT_SECONDS", 0.01),
        ):
            with self.assertRaises(HTTPException) as context:
                await test_external_connection(
                    authenticated_session=authenticated_session(),
                    policy=development_policy(),
                    connection_request=connection_request(),
                )

        self.assertEqual(context.exception.status_code, 504)
        self.assertTrue(connection.closed)
        self.assertEqual(connection.rollback_count, 1)


if __name__ == "__main__":
    unittest.main()
