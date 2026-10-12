import os
from dataclasses import dataclass

import psycopg

CONNECTION_CHECK_SQL = "SELECT current_user, current_database()"


class InternalDatabaseConfigurationError(ValueError):
    pass


class InternalDatabaseConnectionError(RuntimeError):
    pass


@dataclass(frozen=True, repr=False)
class InternalDatabaseConfig:
    host: str
    port: int
    database: str
    user: str
    password: str

    @classmethod
    def from_environment(cls) -> "InternalDatabaseConfig":
        variable_names = (
            "DB_HOST",
            "DB_PORT",
            "DB_NAME",
            "DB_USER",
            "DB_PASSWORD",
        )
        values = {name: os.getenv(name, "").strip() for name in variable_names}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise InternalDatabaseConfigurationError(
                "Faltan variables de entorno requeridas: " + ", ".join(missing) + "."
            )

        try:
            port = int(values["DB_PORT"])
        except ValueError as exc:
            raise InternalDatabaseConfigurationError(
                "DB_PORT debe ser un número entero válido."
            ) from exc

        if not 1 <= port <= 65535:
            raise InternalDatabaseConfigurationError(
                "DB_PORT debe estar entre 1 y 65535."
            )

        return cls(
            host=values["DB_HOST"],
            port=port,
            database=values["DB_NAME"],
            user=values["DB_USER"],
            password=values["DB_PASSWORD"],
        )


def check_internal_database_connection(config: InternalDatabaseConfig) -> None:
    try:
        with psycopg.connect(
            host=config.host,
            port=config.port,
            dbname=config.database,
            user=config.user,
            password=config.password,
            connect_timeout=5,
            autocommit=True,
            options="-c default_transaction_read_only=on",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(CONNECTION_CHECK_SQL)
                result = cursor.fetchone()
    except psycopg.Error:
        raise InternalDatabaseConnectionError(
            "No fue posible verificar la conexión con la base de datos interna."
        ) from None

    if result is None or len(result) != 2 or not all(result):
        raise InternalDatabaseConnectionError(
            "La base de datos interna no devolvió una respuesta válida."
        )
