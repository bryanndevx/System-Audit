"""Prepara solo el historial de la base interna; no ejecuta auditorías."""

import re
import sys
from pathlib import Path

import psycopg

from app.internal_db import (
    InternalDatabaseConfig, InternalDatabaseConfigurationError, InternalDatabaseConnectionError,
)
from app.external_connections import ExternalConnectionConfigurationError
from app.local_config import LocalConfigurationError
from app.sessions import AuthConfigurationError
from run_backend import prepare_runtime_configuration


def migration_error_message(error: psycopg.Error) -> str:
    # No imprimir el error original: puede contener parámetros o detalles privados.
    messages = {
        "42P01": "Falta una tabla requerida. Aplique primero la migración 001 en la base interna y compruebe public.users.",
        "42501": "El usuario interno no tiene permisos para crear el historial o referenciar public.users. Ejecute la migración con el administrador de la base interna.",
        "25006": "La sesión interna está en modo de solo lectura. Revise el usuario y la configuración de la base interna; no cambie la base auditada.",
        "55P03": "La migración no pudo obtener un bloqueo a tiempo. Cierre transacciones pendientes de la base interna y vuelva a intentar.",
        "57014": "La migración se canceló o superó el tiempo máximo. Revise la disponibilidad y los bloqueos de la base interna.",
        "42703": "Una tabla existente tiene columnas incompatibles con la migración 003. Se requiere revisar su estructura; no se borraron registros.",
        "42830": "public.users no tiene una llave primaria o única compatible. Revise su estructura con la migración 001; no se modificó esa tabla.",
        "28P01": "PostgreSQL rechazó la autenticación. Revise DB_USER y DB_PASSWORD.",
        "3D000": "La base interna no existe. Revise DB_NAME.",
    }
    code = error.sqlstate
    label = f" (PostgreSQL {code})" if isinstance(code, str) and re.fullmatch(r"[0-9A-Z]{5}", code) else ""
    message = messages.get(code, "No se pudo aplicar o confirmar la migración. Revise la conexión, el esquema y los permisos de la base interna.")
    return f"No se pudo preparar el historial{label}: {message}"


def main() -> int:
    try:
        prepare_runtime_configuration()
        print("Conexión a la base interna verificada. Aplicando migración 003…", flush=True)
        config = InternalDatabaseConfig.from_environment()
        migration = Path(__file__).resolve().parents[1] / "sql/migrations/003_create_audit_runs.sql"
        with psycopg.connect(
            host=config.host, port=config.port, dbname=config.database,
            user=config.user, password=config.password, connect_timeout=5,
            options="-c statement_timeout=10000 -c lock_timeout=3000",
        ) as connection:
            connection.execute(migration.read_text(encoding="utf-8"))
    except (EOFError, KeyboardInterrupt):
        print("Operación cancelada.", file=sys.stderr)
        return 130
    except (
        InternalDatabaseConfigurationError, InternalDatabaseConnectionError,
        AuthConfigurationError, ExternalConnectionConfigurationError, LocalConfigurationError,
    ) as exc:
        print(f"No se pudo preparar el historial: {exc}", file=sys.stderr)
        return 2
    except psycopg.Error as exc:
        print(migration_error_message(exc), file=sys.stderr)
        return 2
    except OSError:
        print("No se pudo leer el archivo de la migración 003. Verifique que exista backend/sql/migrations/003_create_audit_runs.sql.", file=sys.stderr)
        return 2
    print("Historial preparado en la base interna. No se modificó la base auditada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
