import os
import re
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
from pydantic import BaseModel

from app.auth import require_csrf
from app.sessions import AuthenticatedSession

SHEET_NAME = "Checklist Maestro"
EXPECTED_HEADERS = (
    "Fase",
    "#",
    "Paso / Actividad",
    "Entregable Esperado",
    "Prioridad",
    "Estado",
    "Responsable",
    "Notas / Evidencia",
)
DEFAULT_MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_CHECKLIST_ACTIVITIES = 100
MAX_ACTIVITY_IDENTIFIER_LENGTH = 50
MAX_ACTIVITY_NAME_LENGTH = 500
MAX_PHASE_NAME_LENGTH = 250
MAX_DELIVERABLE_LENGTH = 1000
MAX_PRIORITY_LENGTH = 50
MAX_EXPANDED_FILE_BYTES = 30 * 1024 * 1024
MAX_WORKSHEET_ROWS = 5000
ALLOWED_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
}
PHASE_NUMBER_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)*)\s*(?:[.)-]\s*|\s+)")

router = APIRouter(prefix="/api/checklists", tags=["checklists"])


class ActividadImportada(BaseModel):
    numero: str
    actividad: str
    entregable_esperado: str | None
    prioridad: str | None
    numero_hoja: str | None = None


class FaseImportada(BaseModel):
    nombre: str
    actividades: list[ActividadImportada]


class ChecklistImportado(BaseModel):
    nombre_archivo: str
    cantidad_fases: int
    cantidad_actividades: int
    fases: list[FaseImportada]
    checklist_version: str = 'personalizado'
    checklist_huella: str | None = None


class ChecklistValidationError(ValueError):
    pass


def _max_file_bytes() -> int:
    raw_value = os.getenv("CHECKLIST_MAX_BYTES")
    if raw_value is None:
        return DEFAULT_MAX_FILE_BYTES

    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_MAX_FILE_BYTES

    return value if value > 0 else DEFAULT_MAX_FILE_BYTES


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _normalized(value: object) -> str:
    return " ".join(_text(value).split()).casefold()


def _activity_identifier(phase_name: str, activity_number: str) -> str:
    if "." in activity_number:
        return activity_number

    phase_number = PHASE_NUMBER_PATTERN.match(phase_name)
    if phase_number is None:
        return activity_number
    return f"{phase_number.group(1)}.{activity_number}"


def _find_data_rows(rows: Iterator[tuple[object, ...]]) -> tuple[int, Iterator[tuple[object, ...]]]:
    expected = tuple(header.casefold() for header in EXPECTED_HEADERS)

    for row_number, row in enumerate(rows, start=1):
        if row_number > MAX_WORKSHEET_ROWS:
            raise ChecklistValidationError("La hoja supera el máximo de 5000 filas procesables.")
        actual = tuple(_normalized(value) for value in row[: len(EXPECTED_HEADERS)])
        if actual == expected:
            return row_number, rows

    raise ChecklistValidationError(
        "No se encontró la fila de encabezados esperada en las columnas A:H. "
        "Verifique que incluya: " + ", ".join(EXPECTED_HEADERS) + "."
    )


def parse_checklist(content: bytes, file_name: str) -> ChecklistImportado:
    try:
        with ZipFile(BytesIO(content)) as archive:
            if len(archive.infolist()) > 2000 or sum(item.file_size for item in archive.infolist()) > MAX_EXPANDED_FILE_BYTES:
                raise ChecklistValidationError("El Excel supera el límite de expansión segura de 30 MiB o 2000 archivos internos.")
    except BadZipFile:
        raise ChecklistValidationError("El archivo no es un libro Excel .xlsx válido o está dañado.") from None
    try:
        workbook = load_workbook(
            filename=BytesIO(content),
            read_only=True,
            data_only=True,
            keep_links=False,
        )
    except (InvalidFileException, BadZipFile, OSError, ValueError) as exc:
        raise ChecklistValidationError(
            "El archivo no es un libro Excel .xlsx válido o está dañado."
        ) from exc

    try:
        if SHEET_NAME not in workbook.sheetnames:
            raise ChecklistValidationError(
                f"El archivo debe contener una hoja llamada '{SHEET_NAME}'."
            )

        worksheet = workbook[SHEET_NAME]
        if worksheet.max_row and worksheet.max_row > MAX_WORKSHEET_ROWS:
            raise ChecklistValidationError("La hoja supera el máximo de 5000 filas procesables; elimine el formato de filas vacías sobrantes.")
        rows = worksheet.iter_rows(values_only=True, max_col=len(EXPECTED_HEADERS))
        header_row, data_rows = _find_data_rows(rows)

        phases: list[FaseImportada] = []
        current_phase: FaseImportada | None = None
        current_phase_key = ""
        activity_number_rows: dict[str, int] = {}

        for row_number, row in enumerate(data_rows, start=header_row + 1):
            if row_number > MAX_WORKSHEET_ROWS:
                raise ChecklistValidationError("La hoja supera el máximo de 5000 filas procesables.")
            values = tuple(row[: len(EXPECTED_HEADERS)])
            padded_values = values + (None,) * (len(EXPECTED_HEADERS) - len(values))
            phase_value, number, activity, deliverable, priority, _, _, _ = padded_values

            if not any(_text(value) for value in padded_values):
                continue

            phase_name = _text(phase_value)
            if phase_name:
                phase_key = _normalized(phase_name)
                if current_phase is None or phase_key != current_phase_key:
                    current_phase = FaseImportada(nombre=phase_name, actividades=[])
                    phases.append(current_phase)
                    current_phase_key = phase_key

            activity_name = _text(activity)
            activity_number = _text(number)

            if not activity_name:
                if activity_number or _text(deliverable) or _text(priority):
                    raise ChecklistValidationError(
                        f"La fila {row_number} contiene datos de actividad, pero no tiene 'Paso / Actividad'."
                    )
                continue

            if current_phase is None:
                raise ChecklistValidationError(
                    f"La actividad de la fila {row_number} no tiene una fase asociada."
                )
            if not activity_number:
                raise ChecklistValidationError(
                    f"La actividad de la fila {row_number} no tiene valor en la columna '#'."
                )
            activity_identifier = _activity_identifier(
                current_phase.nombre,
                activity_number,
            )
            for value, max_length, label in (
                (activity_identifier, MAX_ACTIVITY_IDENTIFIER_LENGTH, "identificador de actividad"),
                (activity_name, MAX_ACTIVITY_NAME_LENGTH, "nombre de actividad"),
                (current_phase.nombre, MAX_PHASE_NAME_LENGTH, "nombre de fase"),
                (_text(deliverable), MAX_DELIVERABLE_LENGTH, "entregable esperado"),
                (_text(priority), MAX_PRIORITY_LENGTH, "prioridad"),
            ):
                if len(value) > max_length:
                    raise ChecklistValidationError(
                        f"El {label} de la fila {row_number} supera el máximo "
                        f"de {max_length} caracteres permitido para ejecutar la auditoría."
                    )
            if activity_identifier in activity_number_rows:
                first_row = activity_number_rows[activity_identifier]
                raise ChecklistValidationError(
                    f"El identificador de actividad '{activity_identifier}' está duplicado "
                    f"en las filas {first_row} y {row_number}."
                )
            if len(activity_number_rows) >= MAX_CHECKLIST_ACTIVITIES:
                raise ChecklistValidationError(
                    f"El checklist supera el máximo de {MAX_CHECKLIST_ACTIVITIES} "
                    "actividades por auditoría. No se importó el archivo; "
                    "divídalo en archivos de menor tamaño sin cambiar los identificadores."
                )
            activity_number_rows[activity_identifier] = row_number

            current_phase.actividades.append(
                ActividadImportada(
                    numero=activity_identifier,
                    numero_hoja=activity_number,
                    actividad=activity_name,
                    entregable_esperado=_text(deliverable) or None,
                    prioridad=_text(priority) or None,
                )
            )

        phases_with_activities = [phase for phase in phases if phase.actividades]
        activity_count = sum(len(phase.actividades) for phase in phases_with_activities)
        if activity_count == 0:
            raise ChecklistValidationError(
                "La hoja 'Checklist Maestro' no contiene actividades válidas."
            )

        from types import SimpleNamespace
        from app.checklist_versions import detect_version, fingerprint
        version = detect_version([SimpleNamespace(**a.model_dump(), fase=p.nombre) for p in phases_with_activities for a in p.actividades])
        if 'Version' in workbook.sheetnames:
            metadata = dict(workbook['Version'].iter_rows(min_row=1,max_row=2,max_col=2,values_only=True))
            if metadata.get('version') != version or metadata.get('sha256') != fingerprint(version):
                raise ChecklistValidationError('Los requisitos no coinciden con la versión y huella declaradas. No altere un checklist versionado durante una medición.')
        return ChecklistImportado(
            nombre_archivo=Path(file_name).name,
            cantidad_fases=len(phases_with_activities),
            cantidad_actividades=activity_count,
            fases=phases_with_activities,
            checklist_version=version, checklist_huella=fingerprint(version),
        )
    finally:
        workbook.close()


@router.post(
    "/import",
    response_model=ChecklistImportado,
    status_code=status.HTTP_200_OK,
)
async def import_checklist(
    file: UploadFile = File(...),
    authenticated_session: AuthenticatedSession = Depends(require_csrf),
) -> ChecklistImportado:
    del authenticated_session
    file_name = Path(file.filename or "").name
    if not file_name or Path(file_name).suffix.casefold() != ".xlsx":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Seleccione un archivo con extensión .xlsx.",
        )

    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El tipo de archivo no corresponde a un libro Excel .xlsx.",
        )

    max_bytes = _max_file_bytes()
    content = await file.read(max_bytes + 1)
    await file.close()

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo está vacío.",
        )
    if len(content) > max_bytes:
        max_megabytes = max_bytes / (1024 * 1024)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"El archivo supera el tamaño máximo permitido de {max_megabytes:g} MiB.",
        )

    try:
        return parse_checklist(content, file_name)
    except ChecklistValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
