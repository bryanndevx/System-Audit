import getpass
import sys

from app.internal_db import (
    InternalDatabaseConfig,
    InternalDatabaseConfigurationError,
)
from app.user_admin import (
    UserAlreadyExistsError,
    UserCreationError,
    UsersTableMissingError,
    UserValidationError,
    create_internal_user,
    validate_password,
    validate_username,
)


def main() -> int:
    try:
        config = InternalDatabaseConfig.from_environment()
        username = validate_username(input("Nombre de usuario: "))
        password = getpass.getpass("Contraseña: ")
        validate_password(password)
        password_confirmation = getpass.getpass("Confirmar contraseña: ")
        if password != password_confirmation:
            print("Las contraseñas no coinciden.", file=sys.stderr)
            return 2

        create_internal_user(config, username, password)
    except (EOFError, KeyboardInterrupt):
        print("Operación cancelada.", file=sys.stderr)
        return 130
    except InternalDatabaseConfigurationError as exc:
        print(f"Configuración incompleta: {exc}", file=sys.stderr)
        return 2
    except UserValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except (UserAlreadyExistsError, UsersTableMissingError, UserCreationError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print("Usuario creado correctamente.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
