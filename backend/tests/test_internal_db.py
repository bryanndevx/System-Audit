import unittest
from unittest.mock import MagicMock, patch

from app.internal_db import (
    CONNECTION_CHECK_SQL,
    InternalDatabaseConfig,
    InternalDatabaseConfigurationError,
    check_internal_database_connection,
)


class InternalDatabaseTests(unittest.TestCase):
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
