import secrets
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from argon2 import PasswordHasher
from psycopg import errors

from app.internal_db import InternalDatabaseConfig
from app.user_admin import (
    INSERT_USER_SQL,
    UserAlreadyExistsError,
    UserValidationError,
    create_internal_user,
    hash_password,
    validate_password,
    validate_username,
)


class UserValidationTests(unittest.TestCase):
    def test_accepts_allowed_username_characters(self):
        self.assertEqual(validate_username("Auditor_01.test-user"), "Auditor_01.test-user")

    def test_rejects_invalid_usernames(self):
        invalid_usernames = ("", " usuario", "usuario ", "usuario con espacio", "usuario@dominio")

        for username in invalid_usernames:
            with self.subTest(username=username):
                with self.assertRaises(UserValidationError):
                    validate_username(username)

    def test_rejects_username_longer_than_100_characters(self):
        with self.assertRaises(UserValidationError):
            validate_username("a" * 101)

    def test_rejects_short_password(self):
        short_value = secrets.token_urlsafe(3)
        self.assertLess(len(short_value), 12)

        with self.assertRaises(UserValidationError):
            validate_password(short_value)

    def test_hashes_password_with_argon2_defaults(self):
        password_value = secrets.token_urlsafe(18)

        password_hash = hash_password(password_value)

        self.assertNotEqual(password_hash, password_value)
        self.assertTrue(PasswordHasher().verify(password_hash, password_value))


class CreateInternalUserTests(unittest.TestCase):
    @patch("app.user_admin.hash_password")
    @patch("app.user_admin.psycopg.connect")
    def test_uses_parameterized_insert(self, connect: MagicMock, hash_password_mock: MagicMock):
        password_value = secrets.token_urlsafe(18)
        password_hash = str(object())
        database_password = str(object())
        hash_password_mock.return_value = password_hash
        connection = connect.return_value.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        config = InternalDatabaseConfig(
            host="localhost",
            port=5432,
            database="sistema_auditoria",
            user="application_user",
            password=database_password,
        )

        create_internal_user(config, "auditor.test", password_value)

        cursor.execute.assert_called_once_with(
            INSERT_USER_SQL,
            ("auditor.test", password_hash),
        )
        connect.assert_called_once_with(
            host="localhost",
            port=5432,
            dbname="sistema_auditoria",
            user="application_user",
            password=database_password,
            connect_timeout=5,
        )

    @patch("app.user_admin.hash_password")
    @patch("app.user_admin.psycopg.connect")
    def test_reports_duplicate_username(self, connect: MagicMock, hash_password_mock: MagicMock):
        hash_password_mock.return_value = str(object())
        cursor = connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
        cursor.execute.side_effect = errors.UniqueViolation()
        config = InternalDatabaseConfig(
            host="localhost",
            port=5432,
            database="sistema_auditoria",
            user="application_user",
            password=str(object()),
        )

        with self.assertRaises(UserAlreadyExistsError):
            create_internal_user(config, "auditor.test", secrets.token_urlsafe(18))


class UsersMigrationTests(unittest.TestCase):
    def test_defines_only_the_approved_columns_without_destructive_statements(self):
        migration_path = (
            Path(__file__).resolve().parents[1]
            / "sql"
            / "migrations"
            / "001_create_users.sql"
        )
        sql = migration_path.read_text(encoding="utf-8")
        approved_definitions = (
            "id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY",
            "username VARCHAR(100) NOT NULL UNIQUE",
            "password_hash TEXT NOT NULL",
            "is_active BOOLEAN NOT NULL DEFAULT TRUE",
            "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
        )

        for definition in approved_definitions:
            with self.subTest(definition=definition):
                self.assertIn(definition, sql)

        uppercase_sql = sql.upper()
        for forbidden_statement in ("DROP TABLE", "ALTER TABLE", "DELETE FROM", "TRUNCATE"):
            with self.subTest(statement=forbidden_statement):
                self.assertNotIn(forbidden_statement, uppercase_sql)


if __name__ == "__main__":
    unittest.main()
