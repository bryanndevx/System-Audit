"""Genera el nuevo Excel desde requisitos versionados, sin resultados ni datos empresariales."""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from app.checklist_versions import TECHNICAL_VERSION, TECHNICAL_CATALOG, fingerprint
from app.checklists import EXPECTED_HEADERS


def create_workbook(destination: Path):
    if destination.exists():
        raise FileExistsError('El archivo ya existe. No se sobrescriben checklists silenciosamente.')
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Checklist Maestro'
    sheet.append(EXPECTED_HEADERS)
    for item in TECHNICAL_CATALOG.values():
        sheet.append([item['fase'],item['numero'],item['actividad'],item['entregable_esperado'],item['prioridad'],None,None,None])
    sheet.freeze_panes = 'C2'
    sheet.auto_filter.ref = sheet.dimensions
    for cell in sheet[1]:
        cell.font=Font(bold=True,color='FFFFFF')
        cell.fill=PatternFill('solid',fgColor='263D64')
    for row in sheet.iter_rows(min_row=2):
        sheet.row_dimensions[row[0].row].height=55
        for cell in row:
            cell.alignment=Alignment(wrap_text=True,vertical='top')
    for key,width in {'A':45,'B':10,'C':90,'D':55,'E':15,'F':18,'G':20,'H':40}.items():
        sheet.column_dimensions[key].width=width
    metadata=workbook.create_sheet('Version')
    metadata.append(['version',TECHNICAL_VERSION])
    metadata.append(['sha256',fingerprint(TECHNICAL_VERSION)])
    metadata.append(['alcance','Requisitos técnicos PostgreSQL; no contiene resultados.'])
    metadata.append(['criterio','Completada = evidencia suficiente y diagnóstico/recomendación IA válidos.'])
    destination.parent.mkdir(parents=True,exist_ok=True)
    workbook.save(destination)
    workbook.close()


if __name__ == '__main__':
    target=Path(__file__).resolve().parents[2]/'frontend/referencias/checklist_postgresql_tecnico_v1.xlsx'
    create_workbook(target)
    print(f'Checklist nuevo: {target}')
