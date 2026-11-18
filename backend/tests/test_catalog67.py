import json
import unittest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException
from psycopg import errors

from app import audit_extended_queries as q, audit_queries as base
from app.ai_context import build_activity_context
from app.ai_diagnostics import GeneratedNarrative, GeminiError, add_ai_narratives
from app.audit_catalog import CATALOG, COMPLETE_DELIVERABLES, EXTERNAL_ONLY
from app.audit_engine import ChecklistActivityReference, MAX_QUERY_ROWS, _fetch_rows, execute_audit_activities
from app.audit_extended import PLANS
from app.audit_history import SavedAudit, summarize_audit
from app.audit_pdf import render_audit_pdf
from app.audits import export_pdf, execute_audit_stream
from tests.test_audit_history import runtime, session
from tests.test_audits import FakeConnection, successful_responses, connection_request, policy
from app.audits import AuditExecutionRequest
from app.checklists import parse_checklist, ChecklistValidationError
from tests.test_checklists import build_workbook
from app.audit_data_checks import orphan_statement


def responses():
    result = successful_responses()
    for module in (q, base):
        for name, statement in vars(module).items():
            if name.endswith('_SQL'):
                result.setdefault(statement, [])
    return result


def reference(identifier):
    return ChecklistActivityReference(**CATALOG[identifier])


class CatalogTests(unittest.IsolatedAsyncioTestCase):
    def test_import_enforces_deliverable_and_expansion_limits(self):
        with self.assertRaisesRegex(ChecklistValidationError, 'entregable'):
            parse_checklist(build_workbook([('1. Fase', 1, 'Actividad', 'x'*1001, 'Alta')]), 'limites.xlsx')
        from io import BytesIO
        from zipfile import ZipFile, ZIP_DEFLATED
        output = BytesIO()
        with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
            archive.writestr('large.xml', 'a' * (31 * 1024 * 1024))
        with self.assertRaisesRegex(ChecklistValidationError, 'expansión'):
            parse_checklist(output.getvalue(), 'expansion.xlsx')

    def test_data_count_template_quotes_identifiers_and_uses_no_business_values(self):
        definition = ('fk', 'schema"quote', 'table;literal', 'target', 'reference', ['column"name'], ['id'], True, True, False, 's')
        statement = orphan_statement(definition).as_string()
        self.assertIn('"schema""quote"."table;literal"', statement)
        self.assertIn('"column""name"', statement)
        self.assertIn('OPERATOR(pg_catalog.=)', statement)
        self.assertTrue(statement.strip().startswith('SELECT count(*)'))

    async def test_all_activities_preserve_metadata_and_report_deliverable_coverage(self):
        events = []
        async def progress(event):
            events.append(event)
        connection = FakeConnection(responses())
        result = await execute_audit_activities(connection, [reference(i) for i in CATALOG], progress)
        self.assertEqual(len(result.actividades), 67)
        self.assertEqual(len(events), 67)
        self.assertEqual(events[-1]['procesadas'], 67)
        for item in result.actividades:
            self.assertEqual(item.entregable_esperado, CATALOG[item.identificador]['entregable_esperado'])
            self.assertEqual(item.numero_hoja, CATALOG[item.identificador]['numero_hoja'])
            if item.identificador in EXTERNAL_ONLY:
                self.assertEqual(item.estado_ejecucion, 'no_ejecutable')
                self.assertEqual(item.consultas, [])
            elif item.identificador not in COMPLETE_DELIVERABLES:
                self.assertEqual(item.grado_automatizacion, 'parcial')
                self.assertTrue(item.limitaciones)
        self.assertEqual(connection.executed.count(base.TABLE_INVENTORY_SQL), 1)
        self.assertGreater(sum(q['reutilizada'] for a in result.actividades for q in a.consultas), 0)
        summary = summarize_audit(result)
        self.assertEqual(summary.total, summary.automatizadas + summary.parciales + summary.no_ejecutables + summary.errores_sql + summary.sin_configuracion)

    async def test_different_deliverable_cannot_be_counted_complete(self):
        item = reference('2.1')
        item.entregable_esperado = 'Un entregable ajeno al inventario'
        result = await execute_audit_activities(FakeConnection(responses()), [item])
        self.assertEqual(result.actividades[0].grado_automatizacion, 'parcial')
        self.assertEqual(summarize_audit(result).automatizadas, 0)

    async def test_missing_permissions_are_technical_errors_or_partial_not_external(self):
        data = responses()
        for statement in PLANS['8.3']:
            data[statement] = errors.InsufficientPrivilege()
        result = await execute_audit_activities(FakeConnection(data), [reference('8.3')])
        self.assertEqual(result.actividades[0].grado_automatizacion, 'error')
        data[q.ARCHIVER_SQL] = []
        result = await execute_audit_activities(FakeConnection(data), [reference('8.3')])
        self.assertEqual(result.actividades[0].estado_ejecucion, 'parcial')
        self.assertEqual(result.actividades[0].grado_automatizacion, 'parcial')

    async def test_runtime_rejects_arbitrary_sql_and_bounds_result_rows(self):
        connection = FakeConnection({q.EXTENSIONS_SQL: [('extension',)] * (MAX_QUERY_ROWS + 20)})
        outcome = await _fetch_rows(connection, q.EXTENSIONS_SQL)
        self.assertEqual(outcome.error, 'limite')
        self.assertEqual(len(outcome.rows), MAX_QUERY_ROWS)
        with self.assertRaises(ValueError):
            await _fetch_rows(connection, 'SELECT una_consulta_no_revisada')

    async def test_postgresql_statement_timeout_is_reported_as_timeout(self):
        outcome = await _fetch_rows(FakeConnection({q.EXTENSIONS_SQL: errors.QueryCanceled()}), q.EXTENSIONS_SQL)
        self.assertEqual(outcome.error, 'timeout')
        self.assertIsNone(outcome.rows)

    async def test_backup_context_has_original_deliverable_and_never_claims_recovery(self):
        result = await execute_audit_activities(FakeConnection(responses()), [reference('8.3'), reference('8.4')])
        for activity in result.actividades:
            context = build_activity_context(activity)
            self.assertEqual(context['entregable_esperado'], activity.entregable_esperado)
            self.assertIn('No inventar RPO/RTO', context['criterios'])
            self.assertEqual(context['cobertura'], 'parcial')
            self.assertTrue(context['informacion_externa_necesaria'])

    @patch('app.ai_diagnostics.request_gemini')
    @patch('app.ai_diagnostics.GeminiConfig.from_environment')
    async def test_ai_batches_and_preserves_previous_success_after_provider_failure(self, config, request):
        config.return_value.model = 'test-model'
        result = await execute_audit_activities(FakeConnection(responses()), [reference(i) for i in CATALOG])
        def generate(config, contexts):
            if request.call_count == 2:
                raise GeminiError('Servicio no disponible.')
            return {c['id']: GeneratedNarrative(id=c['id'], diagnostico='Evidencia parcial.', recomendacion='Verificar lo pendiente.', referencias_evidencia=[1]) for c in contexts}
        request.side_effect = generate
        await add_ai_narratives(result)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(sum(a.redaccion_ia.estado == 'generada' for a in result.actividades), 12)
        self.assertTrue(any(a.redaccion_ia.estado == 'error' for a in result.actividades))
        self.assertEqual(sum(a.redaccion_ia.estado == 'error' for a in result.actividades), 12)
        self.assertEqual(sum(a.redaccion_ia.estado == 'no_solicitada' for a in result.actividades), 41)

    @patch('app.ai_diagnostics.request_gemini')
    @patch('app.ai_diagnostics.GeminiConfig.from_environment')
    async def test_first_batch_503_does_not_attribute_provider_errors_to_unsent_activities(self, config, request):
        config.return_value.model = 'test-model'
        request.side_effect = GeminiError('Gemini (HTTP 503, UNAVAILABLE): disponibilidad del servicio.')
        result = await execute_audit_activities(FakeConnection(responses()), [reference(i) for i in CATALOG])
        before = [a.model_dump(exclude={'redaccion_ia'}) for a in result.actividades]
        await add_ai_narratives(result)
        request.assert_called_once()
        self.assertEqual(sum(a.redaccion_ia.estado == 'error' for a in result.actividades), 12)
        self.assertEqual(sum(a.redaccion_ia.estado == 'no_solicitada' for a in result.actividades), 53)
        self.assertEqual(sum(a.redaccion_ia.estado == 'no_aplica' for a in result.actividades), 2)
        self.assertEqual(summarize_audit(result).errores_ia, 12)
        self.assertEqual([a.model_dump(exclude={'redaccion_ia'}) for a in result.actividades], before)

    @patch('app.audits.get_saved_audit')
    async def test_pdf_is_paginated_and_owner_scoped_without_reexecuting(self, saved):
        result = await execute_audit_activities(FakeConnection(responses()), [reference('2.1'), reference('8.3')])
        result.actividades[0].evidencias[0].datos = {'matriz': [{'nombre': f'tabla_{i}', 'detalle': '<no ejecutar> & evidencia ' * 120} for i in range(75)]}
        record = SavedAudit(id=uuid4(), base_datos='fixture_pdf', fecha=datetime.now(UTC), resultado=result)
        saved.return_value = record
        with patch('app.audits.execute_audit_activities', new_callable=AsyncMock) as execute:
            response = export_pdf(record.id, session(), runtime())
        self.assertTrue(response.body.startswith(b'%PDF-'))
        self.assertGreater(response.body.count(b'/Type /Page\n'), 2)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(saved.call_args.args[1:], (session().user_id, record.id))
        execute.assert_not_awaited()
        saved.return_value = None
        with self.assertRaises(HTTPException) as error:
            export_pdf(record.id, session(), runtime())
        self.assertEqual(error.exception.status_code, 404)

    @patch('app.audits._perform_audit')
    async def test_stream_sends_progress_and_final_stored_result(self, perform):
        result = await execute_audit_activities(FakeConnection(responses()), [reference('2.1')])
        async def run(request, policy, session, runtime, progress):
            await progress({'tipo': 'actividad', 'procesadas': 1})
            return result
        perform.side_effect = run
        response = await execute_audit_stream(session(), policy(), AuditExecutionRequest(conexion=connection_request(), actividades=[reference('2.1')]), runtime())
        events = [json.loads(chunk) async for chunk in response.body_iterator]
        self.assertEqual([e['tipo'] for e in events], ['actividad', 'resultado'])


if __name__ == '__main__':
    unittest.main()
