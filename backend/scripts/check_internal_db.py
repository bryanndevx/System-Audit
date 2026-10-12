import sys

from app.internal_db import (
    InternalDatabaseConfig,
    InternalDatabaseConfigurationError,
    InternalDatabaseConnectionError,
    check_internal_database_connection,
)


def main() -> int:
    try:
        config = InternalDatabaseConfig.from_environment()
        check_internal_database_connection(config)
    except InternalDatabaseConfigurationError as exc:
        print(f"Configuración incompleta: {exc}", file=sys.stderr)
        return 2
    except InternalDatabaseConnectionError:
        print(
            "No fue posible verificar la conexión con la base de datos interna.",
            file=sys.stderr,
        )
        return 1

    print("Conexión con la base de datos interna verificada correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
