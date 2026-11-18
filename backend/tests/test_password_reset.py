import secrets
import unittest
from unittest.mock import call, patch

import psycopg

from app.internal_db import InternalDatabaseConfig
from app.user_admin import (
    PasswordResetError,
    RESET_PASSWORD_SQL,
    REVOKE_USER_SESSIONS_SQL,
    reset_internal_password,
)
from scripts import reset_password


class PasswordResetTests(unittest.TestCase):
    @patch("app.user_admin.psycopg.connect")
    def test_updates_hash_and_revokes_sessions_in_one_transaction(self, connect):
        config = InternalDatabaseConfig("localhost", 5432, "internal", "operator", str(object()))
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (7,)
        password = secrets.token_urlsafe(20)
        reset_internal_password(config, "auditor", password)
        calls = cursor.execute.call_args_list
        self.assertEqual(calls[0].args[0], RESET_PASSWORD_SQL)
        password_hash, username = calls[0].args[1]
        from argon2 import PasswordHasher
        self.assertTrue(PasswordHasher().verify(password_hash, password))
        self.assertEqual(username, "auditor")
        self.assertEqual(calls[1], call(REVOKE_USER_SESSIONS_SQL, (7,)))
        self.assertEqual(len(calls), 2)

    @patch("app.user_admin.psycopg.connect")
    def test_unknown_user_does_not_revoke_sessions(self, connect):
        config = InternalDatabaseConfig("localhost", 5432, "internal", "operator", str(object()))
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = None
        with self.assertRaisesRegex(PasswordResetError, "usuario activo"):
            reset_internal_password(config, "missing", secrets.token_urlsafe(20))
        self.assertEqual(cursor.execute.call_count, 1)

    @patch("app.user_admin.psycopg.connect")
    def test_session_revocation_failure_rolls_back_password_update(self, connect):
        config = InternalDatabaseConfig("localhost", 5432, "internal", "operator", str(object()))
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (7,)
        cursor.execute.side_effect = [None, psycopg.OperationalError("private-detail")]
        with self.assertRaises(PasswordResetError) as raised:
            reset_internal_password(config, "auditor", secrets.token_urlsafe(20))
        self.assertNotIn("private-detail", str(raised.exception))
        self.assertIs(connect.return_value.__exit__.call_args.args[0], psycopg.OperationalError)

    @patch("scripts.reset_password.has_interactive_terminal", return_value=True)
    @patch("scripts.reset_password.check_internal_database_connection")
    @patch("scripts.reset_password.InternalDatabaseConfig.from_environment")
    @patch("scripts.reset_password.input", return_value="auditor")
    @patch("scripts.reset_password.getpass")
    @patch("scripts.reset_password.reset_internal_password")
    def test_confirmation_mismatch_does_not_update_password(self, reset, prompt, username, config, check, terminal):
        prompt.side_effect = [secrets.token_urlsafe(20), secrets.token_urlsafe(20)]
        with patch.dict("os.environ", {"DB_PASSWORD": str(object())}):
            self.assertEqual(reset_password.main(), 2)
        reset.assert_not_called()
