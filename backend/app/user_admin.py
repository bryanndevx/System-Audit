import psycopg
from argon2 import PasswordHasher
from psycopg import Error as PsycopgError
from psycopg import errors

from app.internal_db import InternalDatabaseConfig

MINIMUM_PASSWORD_LENGTH = 12
INSERT_USER_SQL = """
    INSERT INTO users (username, password_hash)
    VALUES (%s, %s)
"""

password_hasher = PasswordHasher()


class UserValidationError(ValueError):
    pass


class UserAlreadyExistsError(RuntimeError):
    pass


class UsersTableMissingError(RuntimeError):
    pass


class UserCreationError(RuntimeError):
    pass


def validate_username(username: str) -> str:
    if not username:
        raise UserValidationError("El nombre de usuario es obligatorio.")
    if username != username.strip():
        raise UserValidationError(
            "El nombre de usuario no puede tener espacios al inicio o al final."
        )
    if len(username) > 100:
        raise UserValidationError(
            "El nombre de usuario no puede superar 100 caracteres."
        )
    if not all(character.isalnum() or character in "_-." for character in username):
        raise UserValidationError(
            "El nombre de usuario solo puede contener letras, números, guion bajo, guion y punto."
        )
    return username


def validate_password(password: str) -> None:
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise UserValidationError(
            f"La contraseña debe tener al menos {MINIMUM_PASSWORD_LENGTH} caracteres."
        )


def hash_password(password: str) -> str:
    validate_password(password)
    return password_hasher.hash(password)


def create_internal_user(
    config: InternalDatabaseConfig,
    username: str,
    password: str,
) -> None:
    validated_username = validate_username(username)
    password_hash = hash_password(password)

    try:
        with psycopg.connect(
            host=config.host,
            port=config.port,
            dbname=config.database,
            user=config.user,
            password=config.password,
            connect_timeout=5,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    INSERT_USER_SQL,
                    (validated_username, password_hash),
                )
    except errors.UniqueViolation:
        raise UserAlreadyExistsError(
            "Ya existe un usuario con ese nombre."
        ) from None
    except errors.UndefinedTable:
        raise UsersTableMissingError(
            "La tabla users no existe. Aplique primero la migración 001."
        ) from None
    except PsycopgError:
        raise UserCreationError(
            "No fue posible crear el usuario en la base de datos interna."
        ) from None
