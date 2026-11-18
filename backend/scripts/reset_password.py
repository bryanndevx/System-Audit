"""Restablecimiento local de usuarios de la aplicación, con acceso a la BD interna."""

import os
import sys
from getpass import getpass

from app.internal_db import (
    InternalDatabaseConfig,
    InternalDatabaseConfigurationError,
    InternalDatabaseConnectionError,
    check_internal_database_connection,
)
from app.user_admin import (
    PasswordResetError,
    UserValidationError,
    reset_internal_password,
    validate_password,
    validate_username,
)
from run_backend import LOCAL_DEVELOPMENT_DEFAULTS, has_interactive_terminal


def main() -> int:
    try:
        if not has_interactive_terminal():
            print("Ejecute este comando en una terminal interactiva.", file=sys.stderr)
            return 2
        if os.getenv("APP_ENV", "").strip().lower() in {"", "development"}:
            for name in ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER"):
                os.environ.setdefault(name, LOCAL_DEVELOPMENT_DEFAULTS[name])
        if not os.getenv("DB_PASSWORD"):
            os.environ["DB_PASSWORD"] = getpass("Contraseña de PostgreSQL interno: ")
        config = InternalDatabaseConfig.from_environment()
        check_internal_database_connection(config)
        username = validate_username(input("Usuario de la aplicación: "))
        password = getpass("Nueva contraseña de la aplicación (mínimo 12 caracteres): ")
        validate_password(password)
        if password != getpass("Confirmar nueva contraseña: "):
            print("Las contraseñas no coinciden. No se realizaron cambios.", file=sys.stderr)
            return 2
        reset_internal_password(config, username, password)
    except (EOFError, KeyboardInterrupt):
        print("Operación cancelada.", file=sys.stderr)
        return 130
    except (
        InternalDatabaseConfigurationError, InternalDatabaseConnectionError,
        UserValidationError, PasswordResetError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print("Contraseña restablecida. Las sesiones anteriores se cerraron; inicie sesión nuevamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
