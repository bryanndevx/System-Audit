"""Una llamada de diagnóstico con datos ficticios, sin PostgreSQL ni auditorías."""

import os
import sys
from getpass import getpass

from app.ai_diagnostics import GeminiConfig, GeminiError, request_gemini
from run_backend import has_interactive_terminal
from app.local_config import LocalConfigurationError, load_local_gemini_environment


def main() -> int:
    try:
        load_local_gemini_environment()
        if not os.getenv("GEMINI_API_KEY", "").strip():
            if not has_interactive_terminal():
                print("Ejecute en una terminal interactiva para ingresar la clave de forma oculta.", file=sys.stderr)
                return 2
            os.environ["GEMINI_API_KEY"] = getpass("Clave API de Gemini (entrada oculta): ")
        # La ejecución explícita del diagnóstico habilita solo este proceso.
        os.environ["GEMINI_ENABLED"] = "1"
        config = GeminiConfig.from_environment()
        print(f"Modelo: {config.model}. Prueba con datos ficticios; una solicitud a Gemini.")
        request_gemini(config, [{
            "id": "2.1", "tema": "Prueba ficticia de inventario de tablas",
            "estado_sql": "completada", "estado_evidencia": "suficiente",
            "criterios": "Datos ficticios de diagnóstico. No afirmar resultados de una auditoría real.",
            "evidencias": [{
                "referencia": 1, "disponibilidad": "disponible", "naturaleza": "calculada",
                "agregados": {"total_tablas": 0},
            }],
        }])
    except (EOFError, KeyboardInterrupt):
        print("Diagnóstico cancelado.", file=sys.stderr)
        return 130
    except LocalConfigurationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except GeminiError as exc:
        print(str(exc), file=sys.stderr)
        if exc.diagnostic_detail:
            print(f"Detalle técnico (datos ocultos): {exc.diagnostic_detail}", file=sys.stderr)
        return 1
    print("Gemini respondió y la salida estructurada es válida. No se ejecutó ninguna auditoría.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
