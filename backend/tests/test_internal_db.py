import unittest
from unittest.mock import MagicMock, patch

import psycopg

from app.internal_db import (
    CONNECTION_CHECK_SQL,
    InternalDatabaseConfig,
    InternalDatabaseConfigurationError,
    InternalDatabaseConnectionError,
    check_internal_database_connection,
)


class InternalDatabaseTests(unittest.TestCase):
    @patch("app.internal_db.psycopg.connect")
    def test_libpq_connection_errors_are_classified_without_sqlstate(self, connect):
        config = InternalDatabaseConfig("localhost", 5432, "internal_db", "internal_user", str(object()))
        for detail, expected in (
            ('password authentication failed for user "private-user"', "autenticación"),
            ('database "private-database" does not exist', "base interna no existe"),
            ('la base de datos "private-database" no existe', "base interna no existe"),
            ('la autentificación password falló para el usuario "private-user"', "autenticación"),
            ('no password supplied', "autenticación"),
            ('connection refused', "servicio PostgreSQL"),
        ):
            with self.subTest(detail=detail):
                connect.side_effect = psycopg.OperationalError(detail)
                with self.assertRaises(InternalDatabaseConnectionError) as raised:
                    check_internal_database_connection(config)
                self.assertIn(expected, str(raised.exception))
                self.assertNotIn("private-", str(raised.exception))

    def test_preserves_password_whitespace(self):
        environment = {
            "DB_HOST": " localhost ", "DB_PORT": "5432", "DB_NAME": "internal_db",
            "DB_USER": "internal_user", "DB_PASSWORD": " " + str(object()) + " ",
        }
        with patch.dict("os.environ", environment, clear=True):
            config = InternalDatabaseConfig.from_environment()
        self.assertEqual(config.password, environment["DB_PASSWORD"])
        self.assertEqual(config.host, "localhost")

    @patch("app.internal_db.psycopg.connect")
    def test_connection_errors_are_actionable_without_exposing_driver_details(self, connect):
        config = InternalDatabaseConfig("localhost", 5432, "internal_db", "internal_user", str(object()))
        for error, expected in (
            (psycopg.errors.InvalidPassword, "DB_PASSWORD"),
            (psycopg.errors.InvalidCatalogName, "DB_NAME"),
            (psycopg.OperationalError, "servicio PostgreSQL"),
        ):
            with self.subTest(error=error):
                connect.side_effect = error("private-driver-detail")
                with self.assertRaises(InternalDatabaseConnectionError) as raised:
                    check_internal_database_connection(config)
                self.assertIn(expected, str(raised.exception))
                self.assertNotIn("private-driver-detail", str(raised.exception))
                self.assertNotIn(config.password, str(raised.exception))

    def test_reads_configuration_from_environment_without_exposing_password(self):
        password_value = str(object())
        environment = {
            "DB_HOST": "localhost",
            "DB_PORT": "5432",
            "DB_NAME": "internal_db",
            "DB_USER": "internal_user",
            "DB_PASSWORD": password_value,
        }

        with patch.dict("os.environ", environment, clear=True):
            config = InternalDatabaseConfig.from_environment()

        self.assertEqual(config.port, 5432)
        self.assertNotIn(password_value, repr(config))

    def test_rejects_missing_environment_variables(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(InternalDatabaseConfigurationError):
                InternalDatabaseConfig.from_environment()

    @patch("app.internal_db.psycopg.connect")
    def test_uses_read_only_connection_and_expected_query(self, connect: MagicMock):
        password_value = str(object())
        connection = connect.return_value.__enter__.return_value
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = ("internal_user", "internal_db")
        config = InternalDatabaseConfig(
            host="localhost",
            port=5432,
            database="internal_db",
            user="internal_user",
            password=password_value,
        )

        check_internal_database_connection(config)

        cursor.execute.assert_called_once_with(CONNECTION_CHECK_SQL)
        connect.assert_called_once_with(
            host="localhost",
            port=5432,
            dbname="internal_db",
            user="internal_user",
            password=password_value,
            connect_timeout=5,
            autocommit=True,
            options="-c default_transaction_read_only=on",
        )


if __name__ == "__main__":
    unittest.main()
