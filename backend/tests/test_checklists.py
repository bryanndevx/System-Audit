import asyncio
import unittest
from io import BytesIO
from unittest.mock import patch

from fastapi import HTTPException
from openpyxl import Workbook
from starlette.datastructures import Headers, UploadFile

from app.checklists import (
    ChecklistValidationError,
    EXPECTED_HEADERS,
    import_checklist,
    parse_checklist,
)


def build_workbook(
    rows: list[tuple[object, ...]],
    sheet_name: str = "Checklist Maestro",
    headers: tuple[str, ...] = EXPECTED_HEADERS,
) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    worksheet.append(headers)
    for row in rows:
        worksheet.append(row)

    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


class ParseChecklistTests(unittest.TestCase):
    def test_groups_activities_and_inherits_phase(self):
        content = build_workbook(
            [
                ("Fase 1", 1, "Actividad A", "Entrega A", "Alta", "Anterior", None, "Evidencia anterior"),
                (None, 2, "Actividad B", "Entrega B", "Media", None, None, None),
                ("Fase 2", 3, "Actividad C", None, "Baja", None, None, None),
            ]
        )

        result = parse_checklist(content, "checklist.xlsx")

        self.assertEqual(result.nombre_archivo, "checklist.xlsx")
        self.assertEqual(result.cantidad_fases, 2)
        self.assertEqual(result.cantidad_actividades, 3)
        self.assertEqual([phase.nombre for phase in result.fases], ["Fase 1", "Fase 2"])
        self.assertEqual(
            [activity.actividad for activity in result.fases[0].actividades],
            ["Actividad A", "Actividad B"],
        )
        self.assertNotIn("estado", result.fases[0].actividades[0].model_dump())
        self.assertNotIn("notas", result.fases[0].actividades[0].model_dump())

    def test_preserves_non_consecutive_phase_blocks(self):
        content = build_workbook(
            [
                ("Fase A", 1, "Actividad A1", None, None, None, None, None),
                ("Fase B", 2, "Actividad B1", None, None, None, None, None),
                ("Fase A", 3, "Actividad A2", None, None, None, None, None),
            ]
        )

        result = parse_checklist(content, "orden.xlsx")

        self.assertEqual([phase.nombre for phase in result.fases], ["Fase A", "Fase B", "Fase A"])
        self.assertEqual(
            [phase.actividades[0].actividad for phase in result.fases],
            ["Actividad A1", "Actividad B1", "Actividad A2"],
        )

    def test_rejects_missing_required_sheet(self):
        content = build_workbook([], sheet_name="Otra hoja")

        with self.assertRaisesRegex(ChecklistValidationError, "Checklist Maestro"):
            parse_checklist(content, "checklist.xlsx")

    def test_rejects_activity_without_phase(self):
        content = build_workbook([(None, 1, "Actividad sin fase", None, None, None, None, None)])

        with self.assertRaisesRegex(ChecklistValidationError, "no tiene una fase asociada"):
            parse_checklist(content, "checklist.xlsx")

    def test_rejects_duplicate_activity_identifiers(self):
        content = build_workbook(
            [
                ("Fase 1", "2.1", "Inventario", None, None, None, None, None),
                (None, "2.1", "Otra actividad", None, None, None, None, None),
            ]
        )

        with self.assertRaisesRegex(ChecklistValidationError, "está duplicado"):
            parse_checklist(content, "checklist.xlsx")

    def test_rejects_invalid_workbook(self):
        with self.assertRaisesRegex(ChecklistValidationError, "no es un libro Excel"):
            parse_checklist(b"contenido invalido", "checklist.xlsx")

    def test_rejects_invalid_headers(self):
        invalid_headers = EXPECTED_HEADERS[:-1] + ("Observaciones",)
        content = build_workbook([], headers=invalid_headers)

        with self.assertRaisesRegex(ChecklistValidationError, "encabezados esperada"):
            parse_checklist(content, "checklist.xlsx")

    def test_endpoint_returns_structured_counts(self):
        content = build_workbook(
            [("Fase única", 1, "Actividad", "Entregable", "Alta", None, None, None)]
        )
        upload = UploadFile(
            file=BytesIO(content),
            filename="checklist.xlsx",
            headers=Headers(
                {
                    "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                }
            ),
        )

        result = asyncio.run(import_checklist(upload))

        self.assertEqual(result.cantidad_fases, 1)
        self.assertEqual(result.cantidad_actividades, 1)

    def test_endpoint_rejects_wrong_extension(self):
        upload = UploadFile(
            file=BytesIO(b"contenido"),
            filename="checklist.xls",
            headers=Headers({"content-type": "application/octet-stream"}),
        )

        with self.assertRaises(HTTPException) as context:
            asyncio.run(import_checklist(upload))

        self.assertEqual(context.exception.status_code, 400)

    def test_endpoint_rejects_oversized_file(self):
        upload = UploadFile(
            file=BytesIO(b"12"),
            filename="checklist.xlsx",
            headers=Headers({"content-type": "application/octet-stream"}),
        )

        with patch.dict("os.environ", {"CHECKLIST_MAX_BYTES": "1"}):
            with self.assertRaises(HTTPException) as context:
                asyncio.run(import_checklist(upload))

        self.assertEqual(context.exception.status_code, 413)


if __name__ == "__main__":
    unittest.main()
