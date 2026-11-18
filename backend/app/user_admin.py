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
RESET_PASSWORD_SQL = """
    UPDATE public.users SET password_hash = %s
     WHERE username = %s AND is_active = TRUE
     RETURNING id
"""
REVOKE_USER_SESSIONS_SQL = "DELETE FROM public.user_sessions WHERE user_id = %s"

password_hasher = PasswordHasher()


class UserValidationError(ValueError):
    pass


class UserAlreadyExistsError(RuntimeError):
    pass


class UsersTableMissingError(RuntimeError):
    pass


class UserCreationError(RuntimeError):
    pass


class PasswordResetError(RuntimeError):
    pass


def reset_internal_password(
    config: InternalDatabaseConfig, username: str, password: str,
) -> None:
    validated_username = validate_username(username)
    password_hash = hash_password(password)
    try:
        with psycopg.connect(
            host=config.host, port=config.port, dbname=config.database,
            user=config.user, password=config.password, connect_timeout=5,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(RESET_PASSWORD_SQL, (password_hash, validated_username))
                user = cursor.fetchone()
                if user is None:
                    raise PasswordResetError("No existe un usuario activo con ese nombre.")
                cursor.execute(REVOKE_USER_SESSIONS_SQL, (user[0],))
    except PsycopgError:
        raise PasswordResetError(
            "No se pudo restablecer la contraseña. Revise la conexión, los permisos "
            "y las migraciones 001 y 002 de la base interna."
        ) from None


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
