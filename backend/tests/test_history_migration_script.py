import secrets
import unittest
from unittest.mock import patch

import psycopg

from app.internal_db import InternalDatabaseConfig, InternalDatabaseConnectionError
from scripts import apply_history_migration


class MigrationErrorTests(unittest.TestCase):
    def test_database_errors_are_specific_without_exposing_original_details(self):
        for error, expected in (
            (psycopg.errors.UndefinedTable, "migración 001"),
            (psycopg.errors.InsufficientPrivilege, "permisos"),
            (psycopg.errors.ReadOnlySqlTransaction, "solo lectura"),
            (psycopg.errors.LockNotAvailable, "bloqueo"),
            (psycopg.errors.QueryCanceled, "tiempo máximo"),
            (psycopg.errors.UndefinedColumn, "incompatibles"),
            (psycopg.errors.InvalidForeignKey, "llave primaria"),
            (psycopg.OperationalError, "conexión"),
        ):
            with self.subTest(error=error):
                message = apply_history_migration.migration_error_message(error("private-driver-detail"))
                self.assertIn(expected, message)
                self.assertNotIn("private-driver-detail", message)


class MigrationScriptTests(unittest.TestCase):
    @patch("scripts.apply_history_migration.psycopg.connect")
    @patch("scripts.apply_history_migration.prepare_runtime_configuration", side_effect=InternalDatabaseConnectionError("PostgreSQL rechazó la autenticación. Revise DB_USER y DB_PASSWORD."))
    @patch("builtins.print")
    def test_preflight_failure_preserves_safe_reason_and_never_executes_migration(self, output, prepare, connect):
        self.assertEqual(apply_history_migration.main(), 2)
        self.assertIn("autenticación", str(output.call_args_list))
        self.assertNotIn("Aplicando", str(output.call_args_list))
        connect.assert_not_called()

    @patch("scripts.apply_history_migration.prepare_runtime_configuration")
    @patch("scripts.apply_history_migration.InternalDatabaseConfig.from_environment")
    @patch("scripts.apply_history_migration.psycopg.connect")
    @patch("builtins.print")
    def test_success_executes_versioned_script_without_printing_password(self, output, connect, config, prepare):
        password = secrets.token_urlsafe(25)
        config.return_value = InternalDatabaseConfig("localhost", 5432, "internal", "test_operator", password)
        self.assertEqual(apply_history_migration.main(), 0)
        connection = connect.return_value.__enter__.return_value
        sql = connection.execute.call_args.args[0]
        self.assertIn("CREATE TABLE IF NOT EXISTS public.audit_runs", sql)
        self.assertEqual(connection.execute.call_count, 1)
        self.assertNotIn(password, str(output.call_args_list))

    @patch("scripts.apply_history_migration.prepare_runtime_configuration")
    @patch("scripts.apply_history_migration.InternalDatabaseConfig.from_environment")
    @patch("scripts.apply_history_migration.psycopg.connect")
    @patch("builtins.print")
    def test_commit_failure_is_not_reported_as_success(self, output, connect, config, prepare):
        config.return_value = InternalDatabaseConfig("localhost", 5432, "internal", "test_operator", secrets.token_urlsafe(25))
        connect.return_value.__exit__.side_effect = psycopg.OperationalError("private-detail")
        self.assertEqual(apply_history_migration.main(), 2)
        self.assertNotIn("Historial preparado", str(output.call_args_list))
        self.assertNotIn("private-detail", str(output.call_args_list))
