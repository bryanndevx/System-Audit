"""PDF a partir del resultado guardado. Sin consultas externas ni llamadas a IA."""

import re
import json
import hashlib
from datetime import datetime
from html import escape
from io import BytesIO
from pathlib import Path

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.graphics.shapes import Drawing, Rect, Line, String
from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, TableStyle

from app.audit_history import SavedAudit, summarize_audit

for name, filename in (("AuditSans", "Vera.ttf"), ("AuditSansBold", "VeraBd.ttf")):
    pdfmetrics.registerFont(TTFont(name, str(Path(reportlab.__file__).parent / "fonts" / filename)))
pdfmetrics.registerFontFamily("AuditSans", normal="AuditSans", bold="AuditSansBold", italic="AuditSans", boldItalic="AuditSansBold")

WIDTH = A4[0] - 36 * mm
BLUE = colors.HexColor("#263d64")
GRADES = {"total": "Entregable técnico completo", "parcial": "Entregable parcial", "no_automatizada": "Requiere información externa", "error": "Error técnico", "sin_configuracion": "Sin configuración"}
DELIVERABLE_STATES = {"completo": "Entregable completo", "requiere_informacion_externa": "Requiere información externa — incompleta", "evidencia_incompleta": "Evidencia PostgreSQL incompleta", "error_tecnico": "Error técnico", "sin_configuracion": "Sin configuración"}
STYLES = getSampleStyleSheet()
for name in ("Normal", "BodyText", "Heading1", "Heading2", "Heading3", "Title"):
    STYLES[name].fontName = "AuditSansBold" if name.startswith("Heading") or name == "Title" else "AuditSans"
    STYLES[name].textColor = BLUE
    STYLES[name].splitLongWords = True
STYLES.add(ParagraphStyle("Cell", fontName="AuditSans", fontSize=7.2, leading=9.5, spaceAfter=0, splitLongWords=True))
STYLES.add(ParagraphStyle("Cover", parent=STYLES["Title"], alignment=TA_CENTER, leading=30, fontSize=23))


def text(value):
    if value is None:
        return "No disponible"
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, datetime):
        return value.isoformat()
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value))


def paragraph(value, style="BodyText"):
    return Paragraph(escape(text(value)).replace("\n", "<br/>"), STYLES[style])


def table(headers, rows):
    data = [[paragraph(h, "Cell") for h in headers]]
    for row in rows:
        data.append([paragraph(cell, "Cell") for cell in row])
    result = LongTable(data, colWidths=[WIDTH / len(headers)] * len(headers), repeatRows=1,
                       splitByRow=1, splitInRow=1, hAlign="LEFT")
    result.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e3edfc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, BLUE),
        ("LINEBELOW", (0, 1), (-1, -1), 0.2, colors.HexColor("#dce5f2")),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return result


def evidence_flow(value, label="Datos"):
    """Matrices compactas para filas simples; detalle recursivo para estructuras anidadas."""
    flow = []
    if isinstance(value, dict):
        physical = value.get('diagrama_er_fisico')
        if isinstance(physical,list) and physical:
            flow.append(paragraph('Diagrama ER físico — entidades y llaves primarias declaradas','Heading3'))
            for offset in range(0,len(physical),2):
                nodes=physical[offset:offset+2]
                labels=[]
                for node in nodes:
                    key='; '.join(', '.join(columns) for columns in node.get('claves_primarias',[])) or 'Sin PK declarada'
                    label=f"{node['nombre_completo']} | PK: {key}"
                    labels.append([label[i:i+43] for i in range(0,len(label),43)])
                height=max(len(lines) for lines in labels)*11+20
                drawing=Drawing(WIDTH,height+8)
                for index,lines in enumerate(labels):
                    x=index*(WIDTH-220)
                    drawing.add(Rect(x,4,220,height,rx=4,ry=4,fillColor=colors.HexColor('#edf3ff'),strokeColor=colors.HexColor('#d6dfec')))
                    for i,line in enumerate(lines):
                        drawing.add(String(x+7,height-10-i*11,line,fontName='AuditSans',fontSize=8,fillColor=BLUE))
                flow.extend([drawing,Spacer(1,6)])
        relations = value.get('relaciones_fk')
        if isinstance(relations, list) and relations:
            flow.append(paragraph('Relaciones FK observadas — sin inferir cardinalidad empresarial', 'Heading3'))
            for relation in (relations if value.get('diagrama_er_fisico') is not None else relations[:20]):
                if not isinstance(relation, dict) or not all(key in relation for key in ('tabla_origen', 'tabla_destino', 'columnas_origen', 'columnas_destino')):
                    continue
                def node_lines(side):
                    label = f"{relation['tabla_'+side]} ({', '.join(relation['columnas_'+side])})"
                    return [label[i:i+43] for i in range(0, len(label), 43)]
                source, target = node_lines('origen'), node_lines('destino')
                height = max(len(source),len(target))*11+20
                drawing = Drawing(WIDTH,height+8)
                for x, lines in ((0,source),(WIDTH-220,target)):
                    drawing.add(Rect(x,4,220,height,rx=4,ry=4,fillColor=colors.HexColor('#edf3ff'),strokeColor=colors.HexColor('#d6dfec')))
                    for i,line in enumerate(lines):
                        drawing.add(String(x+7,height-10-i*11,line,fontName='AuditSans',fontSize=8,fillColor=BLUE))
                y=height/2+4
                drawing.add(Line(220,y,WIDTH-220,y,strokeColor=BLUE))
                drawing.add(Line(WIDTH-225,y+4,WIDTH-220,y,strokeColor=BLUE))
                drawing.add(Line(WIDTH-225,y-4,WIDTH-220,y,strokeColor=BLUE))
                flow.extend([paragraph(relation.get('restriccion','FK'),'Cell'),drawing,Spacer(1,6)])
            if len(relations)>20 and value.get('diagrama_er_fisico') is None:
                flow.append(paragraph('Diagrama limitado a veinte relaciones; la matriz conserva el inventario completo obtenido.'))
        scalars = [(k.replace("_", " "), v) for k, v in value.items() if not isinstance(v, (dict, list))]
        if scalars:
            flow.extend([table(["Parámetro", "Valor"], scalars), Spacer(1, 6)])
        for key, child in value.items():
            if isinstance(child, (dict, list)):
                flow.append(paragraph(key.replace("_", " "), "Heading3"))
                flow.extend(evidence_flow(child, key))
        if not value:
            flow.append(paragraph("Sin parámetros registrados."))
    elif isinstance(value, list):
        if not value:
            return [paragraph("Sin filas obtenidas. No implica incumplimiento ni ausencia de controles externos.")]
        if all(isinstance(row, dict) for row in value):
            def inline(item):
                return not isinstance(item, (dict, list)) or not item or (isinstance(item, list) and all(not isinstance(v, (dict, list)) for v in item) and len(str(item)) < 200)
            keys = list(dict.fromkeys(key for row in value for key, child in row.items() if inline(child)))
            identity = next((k for k in ("nombre_completo", "tabla", "campo", "restriccion", "parametro", "rol") if k in keys), None)
            if identity:
                keys.remove(identity)
            # Dividir matrices anchas en grupos de cinco columnas, conservando ordinal de fila.
            width = 4 if identity else 5
            for offset in range(0, max(1, len(keys)), width):
                group = ([identity] if identity else []) + keys[offset:offset + width]
                def cell(row, key):
                    child = row.get(key)
                    if not inline(child):
                        return "Ver detalle de esta fila"
                    if isinstance(child, list):
                        return " / ".join(text(v) for v in child) if child else "Lista vacía"
                    if isinstance(child, dict):
                        return "Sin parámetros"
                    return child
                flow.extend([table(["Fila", *[k.replace("_", " ") for k in group]],
                                   [[i + 1, *[cell(row, k) for k in group]] for i, row in enumerate(value)]), Spacer(1, 6)])
            for index, row in enumerate(value):
                nested = [(key, child) for key, child in row.items() if not inline(child)]
                if nested:
                    context = row.get(identity, "") if identity else ""
                    flow.append(paragraph(f"{label.replace('_', ' ')} · fila {index + 1} · {context}", "Heading3"))
                    for key, child in nested:
                        flow.append(paragraph(key.replace('_', ' '), "Heading3"))
                        flow.extend(evidence_flow(child, key))
        elif all(not isinstance(v, (dict, list)) for v in value):
            flow.append(table(["Fila", "Valor"], [[i + 1, v] for i, v in enumerate(value)]))
        else:
            for index, child in enumerate(value):
                flow.append(paragraph(f"{label.replace('_', ' ')} · fila {index + 1}", "Heading3"))
                flow.extend(evidence_flow(child, label))
    else:
        flow.append(table(["Parámetro", "Valor"], [[label, value]]))
    return flow


def render_audit_pdf(record: SavedAudit) -> bytes:
    result = record.resultado
    summary = summarize_audit(result)
    from app.checklist_versions import TECHNICAL_VERSION
    legacy = result.checklist_version != TECHNICAL_VERSION
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=19 * mm, bottomMargin=18 * mm,
                            title="Informe técnico de auditoría PostgreSQL", author="Sistema de auditoría PostgreSQL")
    flow = [Spacer(1, 35 * mm), paragraph("INFORME TÉCNICO DE AUDITORÍA POSTGRESQL", "Cover"), Spacer(1, 15 * mm)]
    flow.extend([table(["Identificación", "Valor"], [
        ["Aplicación auditada", result.nombre_aplicacion or "No especificada"],
        ["Entorno auditado", result.entorno_auditado or "No especificado"],
        ["Base de datos", record.base_datos],
        ["Fecha y hora de ejecución (UTC)", result.fecha_ejecucion or "No registrada en este resultado histórico"],
        ["Registro del informe (UTC)", record.fecha], ["ID", record.id], ["Catálogo", result.catalogo_version],
        ["Checklist",result.checklist_version or 'Histórico sin versión registrada'],
        ["Huella de requisitos SHA-256",result.checklist_huella],
        ["Criterio",result.criterios_evaluacion_version or 'Criterio histórico'],
    ]), Spacer(1, 12 * mm), paragraph("Uso interno. El informe conserva evidencia técnica del momento auditado; no certifica cumplimiento empresarial ni normativo."), PageBreak(),
                 paragraph("Resumen ejecutivo", "Heading1"),
                 table(["Indicador", "Resultado"], [["Actividades evaluadas", summary.total], ["Completadas con criterio histórico" if legacy else "Entregables técnicos completos", summary.automatizadas],
                     ["Incompletas",summary.total-summary.automatizadas],
                     ["Con evidencia PostgreSQL (incluye consultas sin filas)", summary.con_evidencia_postgresql],
                     ["Sin configuración", summary.sin_configuracion], ["Automatización completa", f"{summary.porcentaje_automatizacion}%"], ["Errores de IA", summary.errores_ia],
                     ["Tiempo total de proceso (ms)", result.duracion_ejecucion_ms if result.duracion_ejecucion_ms is not None else result.duracion_total_ms+result.duracion_ia_ms]]),
                 paragraph("Automatización = actividades completadas / actividades evaluadas. En la versión técnica una actividad completada exige evidencia suficiente, diagnóstico y recomendación válidos; los controles deshabilitados son resultados de evaluación. La IA no calcula resultados ni demuestra exactitud.")])
    if legacy:
        flow.append(paragraph("Registro histórico: faltan metadatos de cobertura por entregable. Sus cifras heredadas describen el criterio de ejecución anterior y no acreditan entregables completos con el catálogo actual."))
    phase = None
    annexes = []
    annex_index = {}
    for activity in result.actividades:
        if activity.fase_original != phase:
            flow.append(PageBreak())
            phase = activity.fase_original
            flow.append(paragraph(phase, "Heading1"))
        flow.extend([paragraph(f"{activity.numero_original}. {activity.nombre_original}", "Heading2"),
                     paragraph(f"Entregable esperado: {activity.entregable_esperado or 'No registrado en esta auditoría histórica'}"),
                     paragraph(f"Estado: {'Completada' if activity.estado_actividad=='completada' or (legacy and activity.grado_automatizacion=='total' and activity.redaccion_ia.estado=='generada') else 'Incompleta'} · Prioridad: {activity.prioridad_original or 'No registrada'} · SQL: {activity.duracion_ms} ms"),
                     paragraph("Evidencias técnicas", "Heading3")])
        for index, evidence in enumerate(activity.evidencias, 1):
            label = f"{activity.numero_original} · E{index} · {evidence.clave.replace('_', ' ')}"
            flow.extend([paragraph(label, "Heading3"), paragraph(f"Consulta: {evidence.consulta_id} · Disponibilidad: {evidence.disponibilidad} · Naturaleza: {evidence.naturaleza}")])
            # Las evidencias extensas se conservan completas en anexos con encabezados repetidos.
            if len(str(evidence.datos)) > 10000:
                digest = hashlib.sha256(json.dumps(evidence.model_dump(mode='json')['datos'], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                if digest not in annex_index:
                    annexes.append((label, evidence.datos))
                    annex_index[digest] = len(annexes)
                flow.append(paragraph(f"Evidencia extensa: consultar anexo {annex_index[digest]}. Las actividades que usan el mismo resultado referencian el mismo anexo."))
            else:
                flow.extend(evidence_flow(evidence.datos))
        if not activity.evidencias:
            flow.append(paragraph("Sin evidencia PostgreSQL obtenida."))
        narrative = activity.redaccion_ia
        flow.extend([paragraph("Diagnóstico", "Heading3"), paragraph(narrative.diagnostico or narrative.mensaje or "Sin redacción de IA disponible."),
                     paragraph("Recomendación", "Heading3"), paragraph(narrative.recomendacion or "Revisar las verificaciones pendientes indicadas; no se genera una recomendación sin evidencia."),
                     paragraph(f"Redacción: {narrative.estado} · Modelo: {narrative.modelo or 'No utilizado'} · Referencias: {', '.join('E'+str(i) for i in narrative.referencias_evidencia) or 'No registradas'}"),
                     paragraph("Limitaciones y verificaciones pendientes", "Heading3")])
        for item in dict.fromkeys([*activity.informacion_faltante, *activity.advertencias, *activity.limitaciones]):
            flow.append(paragraph("• " + item))
        if activity.consultas:
            flow.extend([paragraph("Trazabilidad de consultas", "Heading3"), table(["Consulta", "Estado", "Filas obtenidas", "Reutilizada"],
                 [[q["consulta_id"], q["estado"], q["filas"], q["reutilizada"]] for q in activity.consultas])])
    flow.extend([PageBreak(), paragraph("Conclusiones generales", "Heading1"),
                 paragraph(f"Se evaluaron {summary.total} actividades: {summary.automatizadas} completadas {'según criterio histórico' if legacy else 'con evidencia y narrativa válidas'} y {summary.total-summary.automatizadas} incompletas. La causa real de una evaluación incompleta se conserva en el resultado. Estos indicadores se calcularon en Python sobre el resultado almacenado."),
                 paragraph("Completar las verificaciones externas por actividad antes de decidir cambios. La falta de información no demuestra conformidad ni incumplimiento. Las recomendaciones de IA requieren revisión del auditor. No se ha repetido la auditoría para exportar este documento.")])
    for index, (label, data) in enumerate(annexes, 1):
        flow.extend([PageBreak(), paragraph(f"Anexo {index} — {label}", "Heading1"), *evidence_flow(data)])

    def footer(canvas, document):
        canvas.setFont("AuditSans", 8)
        canvas.setFillColor(BLUE)
        canvas.drawString(18 * mm, 10 * mm, "Auditoría PostgreSQL · Uso interno")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Página {document.page}")

    doc.build(flow, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
