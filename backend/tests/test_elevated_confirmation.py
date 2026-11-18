import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.external_connections import (
    ElevatedPrivilegesConfirmationRequired, InsufficientDatabasePrivilegesError,
    ExternalConnectionRequest, SESSION_OPTIONS, SET_TRANSACTION_READ_ONLY_SQL,
    verify_external_connection, test_external_connection,
)
from tests.test_external_connections import (
    FakeCursor, FakeConnection, connection_request, development_policy, authenticated_session,
)


class ElevatedConfirmationTests(unittest.IsolatedAsyncioTestCase):
    def test_confirmation_defaults_to_false_and_rejects_string_values(self):
        request = connection_request()
        self.assertFalse(request.confirmar_privilegios_elevados)
        data = request.model_dump()
        for value in ('false', 'true', 1, None):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                ExternalConnectionRequest.model_validate({**data, 'confirmar_privilegios_elevados': value})

    @patch('app.external_connections.resolve_allowed_address', new_callable=AsyncMock, return_value='127.0.0.1')
    async def test_every_elevated_attribute_requires_confirmation_and_keeps_read_only(self, resolve):
        for index in range(5):
            for confirmed in (False, True):
                attributes = tuple(i == index for i in range(5))
                cursor = FakeCursor([('fixture_user', 'fixture_db', True, True), attributes])
                connection = FakeConnection(cursor)
                request = connection_request()
                request.confirmar_privilegios_elevados = confirmed
                connect = AsyncMock(return_value=connection)
                with self.subTest(index=index, confirmed=confirmed), patch('app.external_connections.psycopg.AsyncConnection.connect', connect):
                    if confirmed and index != 0:
                        await verify_external_connection(request, development_policy())
                    else:
                        with self.assertRaises(ElevatedPrivilegesConfirmationRequired):
                            await verify_external_connection(request, development_policy())
                self.assertTrue(connection.closed)
                self.assertEqual(cursor.executed[0], SET_TRANSACTION_READ_ONLY_SQL)
                self.assertEqual(connect.await_args.kwargs['options'], SESSION_OPTIONS)
                self.assertIn('default_transaction_read_only=on', SESSION_OPTIONS)
                self.assertFalse(connect.await_args.kwargs['autocommit'])

    @patch('app.external_connections.verify_external_connection', new_callable=AsyncMock)
    async def test_endpoint_returns_structured_confirmation_without_secrets(self, verify):
        verify.side_effect = ElevatedPrivilegesConfirmationRequired((True, False, False, False, False))
        with self.assertRaises(HTTPException) as error:
            await test_external_connection(authenticated_session(), development_policy(), connection_request())
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(error.exception.detail['code'], 'elevated_privileges_confirmation_required')
        self.assertEqual(error.exception.detail['privileges'], ['Superusuario'])

    @patch('app.external_connections.resolve_allowed_address', new_callable=AsyncMock, return_value='127.0.0.1')
    async def test_confirmation_never_bypasses_read_only_validation(self, resolve):
        request = connection_request()
        request.confirmar_privilegios_elevados = True
        cursor = FakeCursor([('fixture_user', 'fixture_db', False, True)])
        connection = FakeConnection(cursor)
        with patch('app.external_connections.psycopg.AsyncConnection.connect', AsyncMock(return_value=connection)):
            with self.assertRaises(InsufficientDatabasePrivilegesError):
                await verify_external_connection(request, development_policy())
        self.assertTrue(connection.closed)
