import asyncio
import secrets
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
from app.audit_engine import ChecklistActivityReference
from app.audits import AuditExecutionRequest


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
    def test_imported_checklist_at_limits_is_accepted_by_execution_model(self):
        content = build_workbook([
            ("F" * 250, str(index).zfill(50), "A" * 500, None, None, None, None, None)
            for index in range(1, 101)
        ])
        result = parse_checklist(content, "limite.xlsx")
        activities = [
            ChecklistActivityReference(
                numero=activity.numero, actividad=activity.actividad, fase=phase.nombre,
            )
            for phase in result.fases for activity in phase.actividades
        ]
        self.assertEqual(len(activities), 100)
        request = AuditExecutionRequest.model_validate({
            "conexion": {
                "host": "localhost", "port": 5432, "database": "test_db",
                "username": "test_reader", "password": secrets.token_urlsafe(20),
            },
            "actividades": activities,
        })
        self.assertEqual(len(request.actividades), 100)

    def test_rejects_checklist_over_execution_limit_without_truncating(self):
        content = build_workbook([
            ("Fase", index, "Actividad", None, None, None, None, None)
            for index in range(1, 102)
        ])
        upload = UploadFile(
            file=BytesIO(content), filename="grande.xlsx",
            headers=Headers({"content-type": "application/octet-stream"}),
        )
        with self.assertRaises(HTTPException) as raised:
            asyncio.run(import_checklist(upload))
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("100 actividades", raised.exception.detail)

    def test_rejects_text_beyond_execution_limits_with_row_number(self):
        for phase, number, name, expected in (
            ("Fase", "1" * 51, "Actividad", "identificador"),
            ("Fase", "1", "A" * 501, "nombre de actividad"),
            ("F" * 251, "1", "Actividad", "nombre de fase"),
        ):
            with self.subTest(field=expected):
                content = build_workbook([(phase, number, name, None, None, None, None, None)])
                with self.assertRaises(ChecklistValidationError) as raised:
                    parse_checklist(content, "largo.xlsx")
                self.assertIn(expected, str(raised.exception))
                self.assertIn("fila 2", str(raised.exception))

    def test_validates_inherited_phase_and_expanded_identifier_lengths(self):
        for rows, expected_row in (
            ([("F" * 251, None, None), (None, "1", "Actividad")], "fila 3"),
            ([("12. Fase", "1" * 49, "Actividad")], "fila 2"),
        ):
            with self.subTest(rows=rows):
                with self.assertRaisesRegex(ChecklistValidationError, expected_row):
                    parse_checklist(build_workbook(rows), "fases.xlsx")

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

    def test_builds_hierarchical_identifiers_when_numbering_restarts_by_phase(self):
        content = build_workbook(
            [
                ("1. Primera fase", 1, "Actividad A", None, None, None, None, None),
                (None, 2, "Actividad B", None, None, None, None, None),
                ("2. Segunda fase", 1, "Actividad C", None, None, None, None, None),
            ]
        )

        result = parse_checklist(content, "checklist.xlsx")

        self.assertEqual(
            [
                activity.numero
                for phase in result.fases
                for activity in phase.actividades
            ],
            ["1.1", "1.2", "2.1"],
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
