"""Gemini SIMULADO: no se conecta al proveedor ni se consume cuota real."""
import asyncio
import json
import secrets
import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from fastapi import FastAPI
from types import SimpleNamespace

from app.ai_context import build_activity_context
from app.ai_diagnostics import (AiNarrative, GeminiConfig, GeminiError, add_ai_narratives,
                                request_gemini, request_with_retries, retry_after_seconds)
from app.audit_coverage import finalize_activity_states
from app.audit_history import SavedAudit, summarize_audit
from app.audits import router
from app.auth import get_runtime_config, require_csrf
from app.checklist_versions import TECHNICAL_VERSION
from tests.test_ai_diagnostics import activity, result, narrative, envelope
from tests.test_audit_history import runtime, session


def pending_result(count=1):
    numbers = [f'2.{i}' for i in range(1, 9)] + [f'3.{i}' for i in range(1, 10)]
    value = result([activity(number) for number in numbers[:count]])
    value.checklist_version = TECHNICAL_VERSION
    finalize_activity_states(value)
    return value


class AsgiClient:
    """Cliente ASGI mínimo sin nuevas dependencias, solo para estas rutas JSON."""
    def __init__(self, app):
        self.app = app

    def post(self, path):
        async def run():
            messages = []
            async def receive():
                return {'type': 'http.request', 'body': b'', 'more_body': False}
            async def send(message):
                messages.append(message)
            await self.app({'type': 'http', 'http_version': '1.1', 'method': 'POST',
                            'scheme': 'http', 'path': path, 'raw_path': path.encode(),
                            'query_string': b'', 'headers': [], 'server': ('test', 80),
                            'client': ('127.0.0.1', 1234), 'root_path': ''}, receive, send)
            body = b''.join(m.get('body', b'') for m in messages)
            return SimpleNamespace(status_code=messages[0]['status'], text=body.decode(), json=lambda: json.loads(body))
        return asyncio.run(run())


class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_bad_context_does_not_abort_other_activities_or_leave_default_messages(self):
        value = pending_result(2)
        original = value.actividades[0].evidencias[0].model_dump()
        from app.ai_context import build_activity_context as build
        def context(item):
            if item.identificador == '2.1':
                raise TypeError('synthetic private metadata')
            return build(item)
        with patch('app.ai_diagnostics.build_activity_context', side_effect=context), patch('app.ai_diagnostics.GeminiConfig.from_environment', return_value=GeminiConfig('synthetic', 'gemini-test')), patch('app.ai_diagnostics.request_gemini', return_value={'2.2': narrative('2.2')}):
            await add_ai_narratives(value)
        self.assertEqual(value.actividades[0].redaccion_ia.tipo_error, 'contexto_invalido')
        self.assertNotIn('private', value.actividades[0].redaccion_ia.mensaje)
        self.assertEqual(value.actividades[0].evidencias[0].model_dump(), original)
        self.assertEqual(value.actividades[1].redaccion_ia.estado, 'generada')

    def test_total_deadline_closes_transport_retained_by_http_response(self):
        with patch('app.ai_diagnostics.http.client.HTTPSConnection') as connect, patch('app.ai_diagnostics.threading.Timer') as timer:
            transport = connect.return_value.sock
            response = Mock(status=200)
            response.read.return_value = envelope()
            def getresponse():
                connect.return_value.sock = None
                timer.call_args.args[1]()
                return response
            connect.return_value.getresponse.side_effect = getresponse
            with self.assertRaises(GeminiError) as error:
                request_gemini(GeminiConfig('synthetic', 'gemini-test'), [build_activity_context(activity())])
            self.assertTrue(error.exception.transient)
            transport.shutdown.assert_called_once()
            timer.return_value.cancel.assert_called_once()

    async def test_503_then_success_real_client_with_simulated_http(self):
        with patch('app.ai_diagnostics.http.client.HTTPSConnection') as connect, patch('app.ai_diagnostics.asyncio.sleep', new_callable=AsyncMock) as sleep:
            failure = Mock(status=503)
            failure.read.return_value = json.dumps({'error': {'status': 'UNAVAILABLE', 'message': 'simulated'}}).encode()
            failure.getheader.return_value = '7'
            success = Mock(status=200)
            success.read.return_value = envelope()
            connect.return_value.getresponse.side_effect = [failure, success]
            config = GeminiConfig(secrets.token_urlsafe(20), 'gemini-test')
            generated = await request_with_retries(config, [build_activity_context(activity())])
        self.assertEqual(generated['2.1'], narrative())
        self.assertEqual(connect.return_value.request.call_count, 2)
        sleep.assert_awaited_once_with(7.0)
        self.assertEqual(connect.call_args.kwargs['timeout'], 20)

    async def test_429_backoff_and_jitter(self):
        with patch('app.ai_diagnostics.request_gemini', side_effect=[GeminiError('simulated', transient=True, status=429), {'2.1': narrative()}]) as request, patch('app.ai_diagnostics.asyncio.sleep', new_callable=AsyncMock) as sleep, patch('app.ai_diagnostics.random.uniform', return_value=0.5):
            await request_with_retries(GeminiConfig('synthetic', 'gemini-test'), [])
        self.assertEqual(request.call_count, 2)
        sleep.assert_awaited_once_with(2.5)

    async def test_exhaustion_is_bounded_and_preserves_sql(self):
        value = pending_result()
        evidence = value.actividades[0].evidencias[0].model_dump()
        with patch('app.ai_diagnostics.GeminiConfig.from_environment', return_value=GeminiConfig('synthetic', 'gemini-test')), patch('app.ai_diagnostics.request_gemini', side_effect=GeminiError('simulated 503', transient=True, status=503)) as request, patch('app.ai_diagnostics.asyncio.sleep', new_callable=AsyncMock) as sleep:
            await add_ai_narratives(value)
        finalize_activity_states(value)
        self.assertEqual(request.call_count, 3)
        self.assertEqual(sleep.await_count, 2)
        self.assertEqual(value.actividades[0].evidencias[0].model_dump(), evidence)
        self.assertEqual(value.actividades[0].motivo_incompleta, 'ia_no_disponible')
        self.assertEqual(value.actividades[0].redaccion_ia.tipo_error, 'transitorio')

    async def test_invalid_json_not_retried(self):
        with patch('app.ai_diagnostics.http.client.HTTPSConnection') as connect:
            connect.return_value.getresponse.return_value.status = 200
            connect.return_value.getresponse.return_value.read.return_value = b'not-json'
            with self.assertRaises(GeminiError):
                await request_with_retries(GeminiConfig('synthetic', 'gemini-test'), [])
        connect.return_value.request.assert_called_once()

    async def test_large_retry_after_does_not_retry_early(self):
        with patch('app.ai_diagnostics.request_gemini', side_effect=GeminiError('simulated', transient=True, status=429, retry_after=300)) as request, patch('app.ai_diagnostics.asyncio.sleep', new_callable=AsyncMock) as sleep:
            with self.assertRaises(GeminiError):
                await request_with_retries(GeminiConfig('synthetic', 'gemini-test'), [])
        request.assert_called_once()
        sleep.assert_not_awaited()

    def test_retry_after_http_date(self):
        date = datetime.now(UTC) + timedelta(seconds=30)
        self.assertTrue(28 <= retry_after_seconds(date.strftime('%a, %d %b %Y %H:%M:%S GMT')) <= 30)
        self.assertEqual(retry_after_seconds('invalid'), 0)

    async def test_concurrent_audits_serialize_provider_calls(self):
        active = 0
        maximum = 0
        async def simulated_thread(*args):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {}
        with patch('app.ai_diagnostics.asyncio.to_thread', side_effect=simulated_thread):
            config = GeminiConfig('synthetic', 'gemini-test')
            await asyncio.gather(request_with_retries(config, []), request_with_retries(config, []))
        self.assertEqual(maximum, 1)

    async def test_timeout_drains_inflight_thread_before_releasing_queue(self):
        original_timeout = asyncio.timeout
        finished = False
        async def simulated_thread(*args):
            nonlocal finished
            await asyncio.sleep(0.02)
            finished = True
            return {}
        with patch('app.ai_diagnostics.asyncio.to_thread', side_effect=simulated_thread), patch('app.ai_diagnostics.asyncio.timeout', side_effect=lambda _: original_timeout(0.001)), patch('app.ai_diagnostics.MAX_ATTEMPTS', 1):
            with self.assertRaisesRegex(GeminiError, 'tiempo máximo'):
                await request_with_retries(GeminiConfig('synthetic', 'gemini-test'), [])
        self.assertTrue(finished)

    async def test_logs_never_include_exception_body_or_key(self):
        private = secrets.token_urlsafe(24)
        with patch('app.ai_diagnostics.request_gemini', side_effect=GeminiError(private, transient=True, status=503)), patch('app.ai_diagnostics.MAX_ATTEMPTS', 1), self.assertLogs('app.ai_diagnostics', level='WARNING') as logs:
            with self.assertRaises(GeminiError):
                await request_with_retries(GeminiConfig(private, 'gemini-test'), [])
        self.assertNotIn(private, '\n'.join(logs.output))

    async def test_checkpoints_skip_successful_batches_and_recover_pending(self):
        value = pending_result(13)
        snapshots = []
        async def checkpoint(current):
            snapshots.append(current.model_copy(deep=True))
        def generate(config, contexts):
            return {c['id']: narrative(c['id']) for c in contexts}
        with patch('app.ai_diagnostics.GeminiConfig.from_environment', return_value=GeminiConfig('synthetic', 'gemini-test')), patch('app.ai_diagnostics.request_gemini', side_effect=[generate(None, [build_activity_context(a) for a in value.actividades[:12]]), GeminiError('simulated')]):
            await add_ai_narratives(value, checkpoint)
        self.assertEqual(len(snapshots), 1)
        with patch('app.ai_diagnostics.GeminiConfig.from_environment', return_value=GeminiConfig('synthetic', 'gemini-test')), patch('app.ai_diagnostics.request_gemini', side_effect=generate) as request:
            await add_ai_narratives(value)
            await add_ai_narratives(value)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(len(request.call_args.args[1]), 1)
        finalize_activity_states(value)
        self.assertTrue(all(a.estado_actividad == 'completada' for a in value.actividades))

    async def test_external_requirement_survives_valid_ai(self):
        value = pending_result()
        value.actividades[0].informacion_faltante = ['Exportación técnica externa autorizada.']
        with patch('app.ai_diagnostics.GeminiConfig.from_environment', return_value=GeminiConfig('synthetic', 'gemini-test')), patch('app.ai_diagnostics.request_gemini', return_value={'2.1': narrative()}):
            await add_ai_narratives(value)
        finalize_activity_states(value)
        self.assertEqual(value.actividades[0].motivo_incompleta, 'informacion_externa')

    async def test_retry_after_is_persisted_and_prevents_early_manual_retry(self):
        value = pending_result()
        with patch('app.ai_diagnostics.GeminiConfig.from_environment', return_value=GeminiConfig('synthetic', 'gemini-test')), patch('app.ai_diagnostics.request_gemini', side_effect=GeminiError('simulated', transient=True, status=429, retry_after=300)) as request:
            await add_ai_narratives(value)
            reloaded = type(value).model_validate_json(value.model_dump_json())
            await add_ai_narratives(reloaded)
            request.assert_called_once()
        self.assertGreater(reloaded.actividades[0].redaccion_ia.reintentar_desde, datetime.now(UTC))

    def test_repeated_finalization_preserves_insufficient_evidence_cause(self):
        value = result()
        value.checklist_version = TECHNICAL_VERSION
        value.actividades[0].estado_evidencia = 'insuficiente'
        for _ in range(3):
            finalize_activity_states(value)
            self.assertEqual(value.actividades[0].motivo_incompleta, 'evidencia_insuficiente')


class RecoveryHttpIntegrationTests(unittest.TestCase):
    """Integra ruta FastAPI, estados y guardado simulado; proveedor siempre SIMULADO."""
    def test_owner_retry_persists_recovery_without_sql_and_repeated_post_is_noop(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_csrf] = lambda: session()
        app.dependency_overrides[get_runtime_config] = runtime
        audit_id = uuid4()
        stored = pending_result()
        evidence = stored.actividades[0].evidencias[0].model_dump()
        def read(config, owner, requested_id):
            return SavedAudit(id=audit_id, base_datos='synthetic', fecha=datetime.now(UTC), resultado=stored.model_copy(deep=True)) if requested_id == audit_id else None
        def update(config, owner, requested_id, current):
            nonlocal stored
            current.resumen = summarize_audit(current)
            stored = current.model_copy(deep=True)
        client = AsgiClient(app)
        with patch('app.audits.get_saved_audit', side_effect=read), patch('app.audits.update_audit_analysis', side_effect=update), patch('app.audits.acquire_ai_lock', return_value=Mock()) as lock, patch('app.audits.open_verified_external_connection', side_effect=AssertionError('SQL must never rerun')) as sql, patch('app.audits.execute_audit_activities', side_effect=AssertionError('SQL must never rerun')), patch('app.ai_diagnostics.GeminiConfig.from_environment', return_value=GeminiConfig('synthetic', 'gemini-test')), patch('app.ai_diagnostics.request_gemini', return_value={'2.1': narrative()}) as provider:
            url = f'/api/audits/{audit_id}/retry-ai'
            response = client.post(url)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['actividades'][0]['estado_actividad'], 'completada')
            self.assertEqual(response.json()['resumen']['completadas'], 1)
            self.assertEqual(client.post(url).status_code, 200)
            self.assertEqual(client.post(f'/api/audits/{uuid4()}/retry-ai').status_code, 404)
            provider.assert_called_once()
            sql.assert_not_called()
            lock.return_value.close.assert_called()
        self.assertEqual(stored.actividades[0].evidencias[0].model_dump(), evidence)

    def test_missing_csrf_or_session_rejected(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_runtime_config] = runtime
        client = AsgiClient(app)
        with patch('app.ai_diagnostics.request_gemini') as request:
            self.assertIn(client.post(f'/api/audits/{uuid4()}/retry-ai').status_code, (401, 403))
            request.assert_not_called()

    def test_duplicate_retry_in_progress_is_409_without_provider_call(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_csrf] = lambda: session()
        app.dependency_overrides[get_runtime_config] = runtime
        audit_id = uuid4()
        record = SavedAudit(id=audit_id, base_datos='synthetic', fecha=datetime.now(UTC), resultado=pending_result())
        with patch('app.audits.get_saved_audit', return_value=record), patch('app.audits.acquire_ai_lock', return_value=None), patch('app.ai_diagnostics.request_gemini') as provider:
            self.assertEqual(AsgiClient(app).post(f'/api/audits/{audit_id}/retry-ai').status_code, 409)
            provider.assert_not_called()

    def test_unexpected_analysis_failure_is_saved_with_safe_cause(self):
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_csrf] = lambda: session()
        app.dependency_overrides[get_runtime_config] = runtime
        audit_id = uuid4()
        value = pending_result()
        record = SavedAudit(id=audit_id, base_datos='synthetic', fecha=datetime.now(UTC), resultado=value)
        with (patch('app.audits.get_saved_audit', return_value=record), patch('app.audits.acquire_ai_lock', return_value=Mock()), patch('app.audits.add_ai_narratives', side_effect=TypeError('synthetic-private')),
              patch('app.audits.update_audit_analysis') as save):
            response = AsgiClient(app).post(f'/api/audits/{audit_id}/retry-ai')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['actividades'][0]['redaccion_ia']['tipo_error'], 'error_interno')
        self.assertNotIn('synthetic-private', response.text)
        save.assert_called_once()
