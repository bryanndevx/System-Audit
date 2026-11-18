"""Persistencia PostgreSQL interna real y Gemini SIMULADO, opt-in en clúster ficticio."""
import os
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.ai_diagnostics import GeminiConfig, GeminiError
from app.audit_engine import AuditExecutionResult
from app.audit_history import acquire_ai_lock, get_saved_audit, save_audit
from app.auth import get_runtime_config, require_csrf
from app.audits import router
from app.internal_db import InternalDatabaseConfig
from fastapi import FastAPI
from tests.test_ai_recovery import AsgiClient
from tests.test_ai_diagnostics import narrative
from tests.test_audit_history import runtime, session


@unittest.skipUnless(os.getenv('RUN_AI_RECOVERY_INTEGRATION') == '1', 'Requiere clúster interno ficticio aislado.')
class RealHistoryRecoveryTests(unittest.TestCase):
    def test_retry_real_jsonb_with_simulated_503_recovery_no_audited_connection(self):
        self.check_recovery()

    def test_large_fictitious_evidence_compression_and_automatic_analysis(self):
        self.check_recovery(large=True)

    def check_recovery(self, large=False):
        self.assertEqual(os.environ['DB_HOST'], '127.0.0.1')
        config = InternalDatabaseConfig.from_environment()
        rt = runtime()
        rt = type(rt)(config, rt.auth)
        owner = int(os.environ['AI_RECOVERY_TEST_USERID'])
        value = AuditExecutionResult.model_validate_json(Path(os.environ['AI_RECOVERY_TEST_RESULT']).read_text(encoding='utf-8'))
        self.assertEqual(len(value.actividades), 67)
        if large:
            # Carga artificial de almacenamiento; no son nuevos hallazgos SQL.
            for activity in value.actividades:
                activity.evidencias[0].datos['prueba_almacenamiento_ficticia'] = 'x' * 300000
            from app.audit_history import storage_payload
            self.assertEqual(storage_payload(value)['formato_almacenamiento'], 'zlib-json-v1')
        saved = save_audit(config, owner, 'auditoria_prueba_recuperacion', value)
        audit_id = saved.almacenamiento.id
        before = [a.model_dump(include={'evidencias', 'consultas', 'duracion_ms', 'estado_ejecucion'}) for a in saved.actividades]
        # Dos conexiones internas compiten por el mismo bloqueo, incluso entre procesos.
        lock = acquire_ai_lock(config, owner, audit_id)
        try:
            self.assertIsNone(acquire_ai_lock(config, owner, audit_id))
        finally:
            lock.close()
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[require_csrf] = lambda: session(owner)
        app.dependency_overrides[get_runtime_config] = lambda: rt
        client = AsgiClient(app)
        calls = 0
        def simulated(config, contexts):
            nonlocal calls
            calls += 1
            self.assertNotIn('prueba_almacenamiento_ficticia', str(contexts))
            if calls == 1:
                raise GeminiError('SIMULADO HTTP 503', transient=True, status=503)
            if calls == 3:
                partial = get_saved_audit(rt.database, owner, audit_id).resultado
                self.assertEqual(sum(a.redaccion_ia.estado == 'generada' for a in partial.actividades), 12)
            return {c['id']: narrative(c['id']) for c in contexts}
        with patch('app.audits.open_verified_external_connection', side_effect=AssertionError('No consultar la BD auditada')) as sql, patch('app.audits.execute_audit_activities', side_effect=AssertionError('No repetir motor SQL')), patch('app.ai_diagnostics.GeminiConfig.from_environment', return_value=GeminiConfig('synthetic', 'gemini-test')), patch('app.ai_diagnostics.request_gemini', side_effect=simulated), patch('app.ai_diagnostics.asyncio.sleep', new_callable=AsyncMock):
            response = client.post(f'/api/audits/{audit_id}/retry-ai')
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['resumen']['completadas'], 67)
            self.assertEqual(calls, 7)  # Un fallo + seis lotes válidos.
            self.assertEqual(client.post(f'/api/audits/{audit_id}/retry-ai').status_code, 200)
            self.assertEqual(calls, 7)
            sql.assert_not_called()
        reloaded = get_saved_audit(config, owner, audit_id)
        self.assertEqual(reloaded.resultado.resumen.completadas, 67)
        self.assertEqual(before, [a.model_dump(include={'evidencias', 'consultas', 'duracion_ms', 'estado_ejecucion'}) for a in reloaded.resultado.actividades])
        self.assertIsNone(get_saved_audit(config, owner + 10000, audit_id))
