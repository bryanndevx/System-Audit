import asyncio
import ipaddress
import os
import re
import socket
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, SecretStr, ValidationError, field_validator
from psycopg import errors
from psycopg.pq import TransactionStatus

from app.auth import require_csrf
from app.sessions import AuthenticatedSession

CONNECT_TIMEOUT_SECONDS = 5
STATEMENT_TIMEOUT_MILLISECONDS = 3_000
TOTAL_OPERATION_TIMEOUT_SECONDS = 10
SESSION_OPTIONS = (
    "-c default_transaction_read_only=on "
    f"-c statement_timeout={STATEMENT_TIMEOUT_MILLISECONDS}"
)
HOST_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")

CONNECTION_METADATA_SQL = """
    SELECT current_user,
           current_database(),
           current_setting('transaction_read_only') = 'on',
           EXISTS (SELECT 1 FROM pg_catalog.pg_class LIMIT 1)
"""
ROLE_ATTRIBUTES_SQL = """
    SELECT rolsuper,
           rolcreaterole,
           rolcreatedb,
           rolreplication,
           rolbypassrls
      FROM pg_catalog.pg_roles
     WHERE rolname = current_user
"""
SET_TRANSACTION_READ_ONLY_SQL = "SET TRANSACTION READ ONLY"

router = APIRouter(prefix="/api/connections", tags=["connections"])


class ExternalConnectionConfigurationError(ValueError):
    pass


class DestinationNotAllowedError(ValueError):
    pass


class InsufficientDatabasePrivilegesError(PermissionError):
    pass


def _normalize_host(value: str) -> str:
    if value != value.strip():
        raise ValueError("El host no puede tener espacios al inicio o al final.")
    if any(character.isspace() for character in value):
        raise ValueError("El host no puede contener espacios.")
    if any(character in value for character in ("/", "\\", "@", ",", "=", "[", "]")):
        raise ValueError("El host debe ser un nombre DNS o una dirección IP.")

    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass

    normalized = value.rstrip(".").encode("idna").decode("ascii").lower()
    if not normalized or len(normalized) > 253:
        raise ValueError("El host no es válido.")
    if not all(HOST_LABEL_PATTERN.fullmatch(label) for label in normalized.split(".")):
        raise ValueError("El host no es válido.")
    return normalized


class ExternalConnectionRequest(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    database: str = Field(min_length=1, max_length=63)
    username: str = Field(min_length=1, max_length=63)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        return _normalize_host(value)

    @field_validator("database", "username")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("El valor no puede tener espacios al inicio o al final.")
        if "\x00" in value:
            raise ValueError("El valor contiene caracteres no permitidos.")
        return value


class ExternalConnectionResponse(BaseModel):
    verified: bool
    message: str


async def parse_external_connection_request(
    request: Request,
) -> ExternalConnectionRequest:
    try:
        payload = await request.json()
        return ExternalConnectionRequest.model_validate(payload)
    except (ValueError, TypeError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Revise los datos de conexión proporcionados.",
        ) from None


@dataclass(frozen=True)
class ExternalConnectionPolicy:
    environment: str
    allowed_hosts: frozenset[str]
    allowed_networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]
    allowed_ports: frozenset[int]
    ssl_mode: str
    ssl_root_cert: str | None

    @classmethod
    def from_environment(cls) -> "ExternalConnectionPolicy":
        environment = os.getenv("APP_ENV", "").strip().lower()
        if environment not in {"development", "production"}:
            raise ExternalConnectionConfigurationError(
                "APP_ENV debe configurarse como development o production."
            )

        raw_hosts = os.getenv("AUDITED_DB_ALLOWED_HOSTS", "")
        raw_networks = os.getenv("AUDITED_DB_ALLOWED_CIDRS", "")
        raw_ports = os.getenv("AUDITED_DB_ALLOWED_PORTS", "")
        ssl_mode = os.getenv("AUDITED_DB_SSL_MODE", "").strip().lower()
        ssl_root_cert = os.getenv("AUDITED_DB_SSL_ROOT_CERT", "").strip() or None

        try:
            allowed_hosts = frozenset(
                _normalize_host(host.strip())
                for host in raw_hosts.split(",")
                if host.strip()
            )
            allowed_networks = tuple(
                ipaddress.ip_network(network.strip(), strict=True)
                for network in raw_networks.split(",")
                if network.strip()
            )
            allowed_ports = frozenset(
                int(port.strip())
                for port in raw_ports.split(",")
                if port.strip()
            )
        except (ValueError, UnicodeError) as exc:
            raise ExternalConnectionConfigurationError(
                "La allowlist de bases auditadas no es válida."
            ) from exc

        if not allowed_hosts and not allowed_networks:
            raise ExternalConnectionConfigurationError(
                "Debe configurarse al menos un destino permitido."
            )
        if not allowed_ports or any(not 1 <= port <= 65535 for port in allowed_ports):
            raise ExternalConnectionConfigurationError(
                "AUDITED_DB_ALLOWED_PORTS debe contener puertos válidos."
            )
        if ssl_mode not in {"disable", "verify-full"}:
            raise ExternalConnectionConfigurationError(
                "AUDITED_DB_SSL_MODE debe ser disable o verify-full."
            )
        if environment == "production" and ssl_mode != "verify-full":
            raise ExternalConnectionConfigurationError(
                "Producción requiere TLS con verificación de identidad."
            )
        if ssl_mode == "verify-full" and not ssl_root_cert:
            raise ExternalConnectionConfigurationError(
                "TLS con verificación requiere una autoridad certificadora."
            )
        if ssl_root_cert and ssl_root_cert != "system" and not Path(ssl_root_cert).is_file():
            raise ExternalConnectionConfigurationError(
                "La autoridad certificadora configurada no está disponible."
            )

        return cls(
            environment=environment,
            allowed_hosts=allowed_hosts,
            allowed_networks=allowed_networks,
            allowed_ports=allowed_ports,
            ssl_mode=ssl_mode,
            ssl_root_cert=ssl_root_cert,
        )


def get_external_connection_policy() -> ExternalConnectionPolicy:
    try:
        return ExternalConnectionPolicy.from_environment()
    except ExternalConnectionConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="La comprobación de conexiones no está configurada correctamente.",
        ) from exc


def _is_forbidden_production_address(
    address: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> bool:
    return (
        address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_unspecified
    )


async def resolve_allowed_address(
    host: str,
    port: int,
    policy: ExternalConnectionPolicy,
) -> str:
    if port not in policy.allowed_ports:
        raise DestinationNotAllowedError("El destino no está permitido.")

    try:
        literal_address = ipaddress.ip_address(host)
    except ValueError:
        literal_address = None

    host_is_allowed = host in policy.allowed_hosts
    if literal_address is not None:
        host_is_allowed = host_is_allowed or any(
            literal_address in network for network in policy.allowed_networks
        )
    if not host_is_allowed:
        raise DestinationNotAllowedError("El destino no está permitido.")

    try:
        address_info = await asyncio.get_running_loop().getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror:
        raise DestinationNotAllowedError("El destino no se pudo resolver.") from None

    addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
    for item in address_info:
        raw_address = item[4][0].split("%", maxsplit=1)[0]
        address = ipaddress.ip_address(raw_address)
        if address not in addresses:
            addresses.append(address)

    if not addresses:
        raise DestinationNotAllowedError("El destino no se pudo resolver.")
    if policy.environment == "production" and any(
        _is_forbidden_production_address(address) for address in addresses
    ):
        raise DestinationNotAllowedError("El destino no está permitido.")

    if literal_address is not None and literal_address not in addresses:
        raise DestinationNotAllowedError("El destino no está permitido.")
    return str(addresses[0])


@asynccontextmanager
async def open_verified_external_connection(
    connection_request: ExternalConnectionRequest,
    policy: ExternalConnectionPolicy,
    *,
    application_name: str,
) -> AsyncIterator[psycopg.AsyncConnection]:
    resolved_address = await resolve_allowed_address(
        connection_request.host,
        connection_request.port,
        policy,
    )
    connection: psycopg.AsyncConnection | None = None
    connect_parameters: dict[str, object] = {
        "host": connection_request.host,
        "hostaddr": resolved_address,
        "port": connection_request.port,
        "dbname": connection_request.database,
        "user": connection_request.username,
        "password": connection_request.password.get_secret_value(),
        "connect_timeout": CONNECT_TIMEOUT_SECONDS,
        "options": SESSION_OPTIONS,
        "application_name": application_name,
        "sslmode": policy.ssl_mode,
        "autocommit": False,
    }
    if policy.ssl_root_cert:
        connect_parameters["sslrootcert"] = policy.ssl_root_cert

    validation_complete = False
    consumer_failed = False
    try:
        connection = await psycopg.AsyncConnection.connect(**connect_parameters)
        async with connection.cursor() as cursor:
            await cursor.execute(SET_TRANSACTION_READ_ONLY_SQL)
            await cursor.execute(CONNECTION_METADATA_SQL)
            metadata = await cursor.fetchone()
            if (
                metadata is None
                or len(metadata) != 4
                or not metadata[0]
                or not metadata[1]
                or metadata[2] is not True
                or metadata[3] is not True
            ):
                raise InsufficientDatabasePrivilegesError(
                    "No fue posible confirmar el acceso básico de lectura."
                )

            await cursor.execute(ROLE_ATTRIBUTES_SQL)
            role_attributes = await cursor.fetchone()
            if role_attributes is None or len(role_attributes) != 5:
                raise InsufficientDatabasePrivilegesError(
                    "No fue posible verificar los atributos del usuario."
                )
            if any(role_attributes):
                raise InsufficientDatabasePrivilegesError(
                    "El usuario posee atributos elevados no permitidos."
                )
        await connection.rollback()
        validation_complete = True
        try:
            yield connection
        except BaseException:
            consumer_failed = True
            raise
    finally:
        if connection is not None and not connection.closed:
            transaction_status = getattr(
                getattr(connection, "info", None),
                "transaction_status",
                None,
            )
            if (
                not validation_complete
                or consumer_failed
                or transaction_status not in {None, TransactionStatus.IDLE}
            ):
                try:
                    await connection.rollback()
                except psycopg.Error:
                    pass
            await connection.close()


async def verify_external_connection(
    connection_request: ExternalConnectionRequest,
    policy: ExternalConnectionPolicy,
) -> None:
    async with open_verified_external_connection(
        connection_request,
        policy,
        application_name="sistema_auditoria_connection_test",
    ):
        pass


@router.post("/test", response_model=ExternalConnectionResponse)
async def test_external_connection(
    authenticated_session: Annotated[AuthenticatedSession, Depends(require_csrf)],
    policy: Annotated[ExternalConnectionPolicy, Depends(get_external_connection_policy)],
    connection_request: Annotated[
        ExternalConnectionRequest,
        Depends(parse_external_connection_request),
    ],
) -> ExternalConnectionResponse:
    del authenticated_session
    try:
        async with asyncio.timeout(TOTAL_OPERATION_TIMEOUT_SECONDS):
            await verify_external_connection(connection_request, policy)
    except TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="La comprobación superó el tiempo máximo permitido.",
        ) from None
    except DestinationNotAllowedError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El destino de conexión no está permitido.",
        ) from exc
    except errors.InvalidPassword as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fue posible autenticar con las credenciales proporcionadas.",
        ) from exc
    except errors.InsufficientPrivilege as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no dispone del acceso básico de lectura requerido.",
        ) from exc
    except InsufficientDatabasePrivilegesError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario no cumple los requisitos mínimos para comprobar la conexión.",
        ) from exc
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No fue posible establecer una conexión PostgreSQL segura.",
        ) from exc

    return ExternalConnectionResponse(
        verified=True,
        message=(
            "Conexión verificada: conectividad y acceso básico a metadatos confirmados. "
            "Esto no garantiza que todas las actividades puedan ejecutarse."
        ),
    )
