import asyncio
import os
import secrets
import unittest
from unittest.mock import patch

from app.ai_context import build_activity_context
from app.ai_diagnostics import GeminiConfig, GeminiError, GeneratedNarrative, add_ai_narratives
from app.audit_coverage import finalize_activity_states
from app.audit_engine import ChecklistActivityReference, execute_audit_activities
from app.audit_history import summarize_audit
from app.checklist_versions import TECHNICAL_CATALOG, TECHNICAL_VERSION, fingerprint
from app.event_loop import create_psycopg_compatible_event_loop
from app.external_connections import ExternalConnectionRequest,ExternalConnectionPolicy,open_verified_external_connection


@unittest.skipUnless(os.getenv('RUN_AUDIT_INTEGRATION')=='1','Requiere instancia ficticia preparada y autorización explícita.')
class TechnicalChecklistIntegrationTests(unittest.TestCase):
    @unittest.skipUnless(os.getenv('AUDIT_METADATA_ONLY_USER'),'Requiere rol adicional sin lectura del historial.')
    def test_missing_history_permissions_are_preserved_as_technical_cause(self):
        asyncio.run(self.check_permissions(),loop_factory=create_psycopg_compatible_event_loop)

    async def check_permissions(self):
        host=os.environ['AUDIT_TEST_HOST'];port=int(os.environ['AUDIT_TEST_PORT'])
        request=ExternalConnectionRequest(host=host,port=port,database=os.environ['AUDIT_TEST_DATABASE'],username=os.environ['AUDIT_METADATA_ONLY_USER'],password=os.environ['AUDIT_TEST_PASSWORD'])
        policy=ExternalConnectionPolicy('development',frozenset({host}),(),frozenset({port}),'disable',None)
        async with open_verified_external_connection(request,policy,application_name='technical_metadata_only_test') as connection:
            result=await execute_audit_activities(connection,[ChecklistActivityReference(**a) for a in TECHNICAL_CATALOG.values()])
        finalize_activity_states(result)
        for number in ('1.7','7.8','8.8'):
            activity=next(a for a in result.actividades if a.identificador==number)
            self.assertEqual(activity.estado_actividad,'incompleta')
            self.assertEqual(activity.motivo_incompleta,'permisos')

    def test_new_scope_against_real_postgresql_with_simulated_ai(self):
        asyncio.run(self.check(),loop_factory=create_psycopg_compatible_event_loop)

    async def check(self):
        host=os.environ['AUDIT_TEST_HOST'];port=int(os.environ['AUDIT_TEST_PORT'])
        request=ExternalConnectionRequest(host=host,port=port,database=os.environ['AUDIT_TEST_DATABASE'],username=os.environ['AUDIT_TEST_USER'],password=os.environ['AUDIT_TEST_PASSWORD'])
        policy=ExternalConnectionPolicy('development',frozenset({host}),(),frozenset({port}),'disable',None)
        async with open_verified_external_connection(request,policy,application_name='technical_v1_integration') as connection:
            result=await execute_audit_activities(connection,[ChecklistActivityReference(**a) for a in TECHNICAL_CATALOG.values()])
        self.assertEqual(result.checklist_version,TECHNICAL_VERSION)
        self.assertEqual(result.checklist_huella,fingerprint(TECHNICAL_VERSION))
        self.assertEqual(len(result.actividades),67)
        errors=[(a.identificador,q) for a in result.actividades for q in a.consultas if q['estado']!='completada']
        self.assertEqual(errors,[])
        self.assertFalse(any(q['consulta_id']=='fk_orphan_count_template' for a in result.actividades for q in a.consultas))
        self.assertFalse([a.identificador for a in result.actividades if a.estado_evidencia not in {'suficiente','sin_datos'}])
        items={a.identificador:a for a in result.actividades}
        # Referencias independientes preparadas por la fixture, no por el algoritmo del motor.
        migrations=next(e for e in items['1.7'].evidencias if e.clave=='historial_migraciones' and e.datos['esquema']=='technical_version_fixture')
        self.assertEqual(migrations.datos['registros'],[{'version_num':'synthetic_revision_001'}])
        ssl=next(e for e in items['8.2'].evidencias if e.clave=='session_tls')
        self.assertFalse(ssl.datos['filas'][0]['tls_sesion_actual'])
        ssl_settings=next(e for e in items['8.2'].evidencias if e.clave=='ssl_settings').datos['filas']
        self.assertEqual(next(r['valor'] for r in ssl_settings if r['parametro']=='ssl'),'off')
        self.assertTrue(all(r['parametro'].startswith('ssl') for r in ssl_settings))
        graph=next(e.datos for e in items['5.1'].evidencias if isinstance(e.datos,dict) and 'diagrama_er_fisico' in e.datos)
        isolated=next(node for node in graph['diagrama_er_fisico'] if node['nombre_completo']=='technical_version_fixture.isolated_entity')
        self.assertEqual(isolated['claves_primarias'],[['code']])
        review=next(e.datos for e in items['3.9'].evidencias if e.clave=='columnas_para_revision')
        self.assertTrue(any(row['tabla']=='review_item' and row['campo']=='valid_until' and not row['tiene_comentario'] for row in review['columnas']))
        finalize_activity_states(result)
        self.assertEqual(summarize_audit(result).automatizadas,0)
        self.assertTrue(all(a.motivo_incompleta=='ia_no_disponible' for a in result.actividades))
        # Volver al resultado SQL para cada escenario de IA. La narrativa es explícitamente ficticia.
        for activity in result.actividades:
            activity.informacion_faltante=[]
            activity.motivo_incompleta=None
        failed=result.model_copy(deep=True)
        contexts=[build_activity_context(a) for a in result.actividades]
        self.assertTrue(all(c and c['checklist_version']==TECHNICAL_VERSION for c in contexts))
        def generate(config,contexts):
            return {c['id']:GeneratedNarrative(id=c['id'],diagnostico='Diagnóstico simulado con evidencia de la instancia ficticia; no corresponde a SmartDent.',
                recomendacion='Recomendación simulada de revisión técnica; no ejecutar cambios desde la auditoría.',referencias_evidencia=[1]) for c in contexts}
        config=GeminiConfig(secrets.token_urlsafe(24),'gemini-test-model')
        with patch('app.ai_diagnostics.GeminiConfig.from_environment',return_value=config),patch('app.ai_diagnostics.request_gemini',side_effect=generate) as provider:
            await add_ai_narratives(result)
            self.assertEqual(provider.call_count,6)
        finalize_activity_states(result)
        self.assertTrue(all(a.estado_actividad=='completada' for a in result.actividades))
        result.resumen=summarize_audit(result)
        self.assertEqual(summarize_audit(result).porcentaje_automatizacion,100)
        self.assertEqual(items['8.2'].estado_actividad,'completada')
        with patch('app.ai_diagnostics.GeminiConfig.from_environment',return_value=config),patch('app.ai_diagnostics.request_gemini',side_effect=GeminiError('HTTP 503 de prueba.')) as provider:
            await add_ai_narratives(failed)
            provider.assert_called_once()
        finalize_activity_states(failed)
        self.assertEqual(summarize_audit(failed).automatizadas,0)
        self.assertEqual([a.evidencias for a in failed.actividades],[a.evidencias for a in result.actividades])
        # Exportar sin otra conexión ni otra llamada IA.
        from app.audit_pdf import render_audit_pdf
        from app.audit_history import SavedAudit
        from datetime import datetime,UTC
        from uuid import uuid4
        document=render_audit_pdf(SavedAudit(id=uuid4(),base_datos='fixture_tecnica',fecha=datetime.now(UTC),resultado=result))
        self.assertTrue(document.startswith(b'%PDF-'))
        destination=os.getenv('TECHNICAL_TEST_OUTPUT')
        if destination:
            from pathlib import Path
            target=Path(destination)
            target.write_text(result.model_dump_json(indent=2),encoding='utf-8')
            target.with_suffix('.pdf').write_bytes(document)
