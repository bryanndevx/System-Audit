import os
import sys
from getpass import getpass

import uvicorn

from app.external_connections import (
    ExternalConnectionConfigurationError,
    ExternalConnectionPolicy,
)
from app.internal_db import (
    InternalDatabaseConfig,
    InternalDatabaseConfigurationError,
    InternalDatabaseConnectionError,
    check_internal_database_connection,
)
from app.sessions import AuthConfig, AuthConfigurationError
from app.local_config import LocalConfigurationError, load_local_gemini_environment

APP_IMPORT_PATH = "app.main:app"
EVENT_LOOP_FACTORY = "app.event_loop:create_psycopg_compatible_event_loop"

LOCAL_DEVELOPMENT_DEFAULTS = {
    "APP_ENV": "development",
    "APP_ORIGIN": "http://localhost:5173",
    "SESSION_TTL_MINUTES": "480",
    "DB_HOST": "127.0.0.1",
    "DB_PORT": "5432",
    "DB_NAME": "sistema_auditoria",
    "DB_USER": "postgres",
    "AUDITED_DB_ALLOWED_HOSTS": "127.0.0.1,localhost",
    "AUDITED_DB_ALLOWED_PORTS": "5432",
    "AUDITED_DB_SSL_MODE": "disable",
}


def has_interactive_terminal() -> bool:
    if not sys.stdin.isatty():
        return False
    if sys.platform == "win32":
        # En Windows, NUL también devuelve isatty=True, pero no admite entrada.
        import ctypes
        import msvcrt
        from ctypes import wintypes

        try:
            handle = wintypes.HANDLE(msvcrt.get_osfhandle(sys.stdin.fileno()))
            mode = wintypes.DWORD()
            return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)))
        except (OSError, ValueError):
            return False
    return True


def prepare_runtime_configuration() -> None:
    load_local_gemini_environment()
    environment = os.getenv("APP_ENV", "").strip().lower()
    if environment in {"", "development"}:
        os.environ["APP_ENV"] = "development"
        for name, value in LOCAL_DEVELOPMENT_DEFAULTS.items():
            os.environ.setdefault(name, value)
        if not os.getenv("DB_PASSWORD", "").strip():
            if not has_interactive_terminal():
                raise InternalDatabaseConfigurationError(
                    "DB_PASSWORD no está configurada. Ejecute run_backend.py en una "
                    "terminal interactiva para ingresarla de forma oculta, o configúrela "
                    "en el entorno del proceso. Consulte LEEME_PRIMERO.md."
                )
            password = getpass(
                "Contraseña del usuario PostgreSQL interno "
                f"'{os.environ['DB_USER']}': "
            )
            if not password:
                raise InternalDatabaseConfigurationError(
                    "DB_PASSWORD es obligatoria."
                )
            os.environ["DB_PASSWORD"] = password

    database_config = InternalDatabaseConfig.from_environment()
    AuthConfig.from_environment()
    ExternalConnectionPolicy.from_environment()
    check_internal_database_connection(database_config)


def main() -> None:
    try:
        prepare_runtime_configuration()
    except (
        InternalDatabaseConfigurationError,
        InternalDatabaseConnectionError,
        AuthConfigurationError,
        ExternalConnectionConfigurationError,
        LocalConfigurationError,
    ) as exc:
        print(f"No se pudo iniciar el backend: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    except (EOFError, KeyboardInterrupt):
        print("Inicio cancelado al ingresar la contraseña.", file=sys.stderr)
        raise SystemExit(130) from None

    uvicorn.run(
        APP_IMPORT_PATH,
        host="127.0.0.1",
        port=8000,
        loop=EVENT_LOOP_FACTORY,
    )


if __name__ == "__main__":
    main()
