"""Carga local limitada a Gemini; no interpreta código ni guarda credenciales auditadas."""

import os
from pathlib import Path

GEMINI_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
GEMINI_VARIABLES = frozenset({"GEMINI_ENABLED", "GEMINI_MODEL", "GEMINI_API_KEY"})


class LocalConfigurationError(ValueError):
    pass


def load_local_gemini_environment() -> None:
    if os.getenv("APP_ENV", "").strip().lower() == "production":
        return
    try:
        if not GEMINI_ENV_PATH.is_file():
            return
        if GEMINI_ENV_PATH.stat().st_size > 16 * 1024:
            raise LocalConfigurationError("backend/.env supera el tamaño permitido de 16 KiB.")
        content = GEMINI_ENV_PATH.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError):
        raise LocalConfigurationError("No se pudo leer backend/.env como texto UTF-8.") from None

    values = {}
    for line_number, line in enumerate(content.splitlines(), start=1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, separator, value = line.partition("=")
        name = name.strip()
        if name not in GEMINI_VARIABLES:
            continue
        value = value.strip()
        if not separator or (value[:1] in {"'", '"'} and (len(value) < 2 or value[-1] != value[0])):
            raise LocalConfigurationError(f"Formato inválido en backend/.env, línea {line_number}.")
        if value[:1] in {"'", '"'}:
            value = value[1:-1]
        values[name] = value
    # Validar el archivo completo antes de modificar el entorno. La terminal tiene prioridad.
    for name, value in values.items():
        os.environ.setdefault(name, value)
