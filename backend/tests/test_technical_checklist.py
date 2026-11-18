import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch

from openpyxl import load_workbook
from pydantic import ValidationError

from app.audit_coverage import finalize_activity_states
from app.audit_engine import ChecklistActivityReference
from app.audit_history import summarize_audit
from app.ai_context import build_activity_context
from app.ai_diagnostics import AiNarrative
from app.audits import AuditExecutionRequest
from app.checklists import parse_checklist,ChecklistValidationError
from app.checklist_versions import TECHNICAL_VERSION,TECHNICAL_CATALOG,LEGACY_VERSION,detect_version,fingerprint
from app.audit_catalog import CATALOG
from app.audit_technical_templates import statements_metrics,migration_history
from scripts.create_technical_checklist import create_workbook
from tests.test_audit_history import sample_result,sample_activity
from tests.test_audits import connection_request


class VersionTests(unittest.TestCase):
    def test_new_workbook_roundtrip_and_original_definitions_preserved(self):
        before=[dict(a) for a in CATALOG.values()]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'technical.xlsx'
            create_workbook(path)
            imported=parse_checklist(path.read_bytes(),path.name)
            self.assertEqual(imported.checklist_version,TECHNICAL_VERSION)
            self.assertEqual(imported.checklist_huella,fingerprint(TECHNICAL_VERSION))
            activities=[ChecklistActivityReference(**a.model_dump(),fase=p.nombre) for p in imported.fases for a in p.actividades]
            self.assertEqual([a.model_dump() for a in activities],[ChecklistActivityReference(**a).model_dump() for a in TECHNICAL_CATALOG.values()])
            self.assertEqual(len(imported.fases),8)
            book=load_workbook(path)
            self.assertTrue(all(cell.value is None for row in book['Checklist Maestro'].iter_rows(min_row=2,min_col=6,max_col=8) for cell in row))
            book['Checklist Maestro']['D2']='Otro entregable'
            book.save(path)
            book.close()
            with self.assertRaisesRegex(ChecklistValidationError,'versión'):
                parse_checklist(path.read_bytes(),path.name)
        self.assertEqual(list(CATALOG.values()),before)

    def test_order_and_mixed_versions_cannot_be_declared_as_technical(self):
        activities=[ChecklistActivityReference(**a) for a in TECHNICAL_CATALOG.values()]
        self.assertEqual(detect_version(activities),TECHNICAL_VERSION)
        with self.assertRaises(ValidationError):
            AuditExecutionRequest(conexion=connection_request(),actividades=activities[::-1],checklist_version=TECHNICAL_VERSION)
        with self.assertRaises(ValidationError):
            AuditExecutionRequest(conexion=connection_request(),actividades=activities[:2])
        self.assertEqual(detect_version([ChecklistActivityReference(**a) for a in CATALOG.values()]),LEGACY_VERSION)

    def test_every_technical_identifier_has_a_plan_or_reviewed_transform(self):
        from app.audit_technical import PLANS
        delegated={f'{phase}.{index}' for phase,count in ((2,8),(3,8),(4,8),(5,8)) for index in range(1,count+1)}
        self.assertEqual(set(TECHNICAL_CATALOG),set(PLANS)|delegated)


class CompletionTests(unittest.TestCase):
    def make_result(self,control):
        result=sample_result()
        result.checklist_version=TECHNICAL_VERSION
        activity=sample_activity('8.2')
        definition=TECHNICAL_CATALOG['8.2']
        activity.nombre_original=definition['actividad']
        activity.entregable_esperado=definition['entregable_esperado']
        activity.prioridad_original=definition['prioridad']
        activity.fase_original=definition['fase']
        activity.evidencias[0].consulta_id='session_tls'
        activity.evidencias[0].datos={'filas':[{'tls_sesion_actual':control}], 'total_filas_obtenidas':1}
        activity.redaccion_ia=AiNarrative(estado='generada',diagnostico='Condición observada en la prueba.',recomendacion='Mantener o revisar el control según la evidencia.',referencias_evidencia=[1])
        result.actividades=[activity]
        return result

    def test_enabled_and_disabled_controls_complete_with_evidence_and_narrative(self):
        for control in (True,False):
            result=self.make_result(control)
            finalize_activity_states(result)
            self.assertEqual(result.actividades[0].estado_actividad,'completada')
            self.assertEqual(summarize_audit(result).porcentaje_automatizacion,100)
            context=build_activity_context(result.actividades[0])
            self.assertEqual(context['checklist_version'],TECHNICAL_VERSION)
            self.assertIsNone(context['informacion_externa_necesaria'])
            self.assertIn('resultado válido',context['criterios'])

    def test_missing_ai_is_incomplete_and_not_counted_as_automation(self):
        result=self.make_result(False)
        result.actividades[0].redaccion_ia=AiNarrative(estado='error',mensaje='Servicio no disponible.')
        finalize_activity_states(result)
        self.assertEqual(result.actividades[0].motivo_incompleta,'ia_no_disponible')
        self.assertEqual(summarize_audit(result).automatizadas,0)
        self.assertTrue(result.actividades[0].evidencias)

    def test_empty_evidence_never_completes_even_with_a_narrative(self):
        result=self.make_result(False)
        result.actividades[0].evidencias=[]
        finalize_activity_states(result)
        self.assertEqual(result.actividades[0].motivo_incompleta,'evidencia_insuficiente')
        self.assertEqual(summarize_audit(result).automatizadas,0)

    def test_invalid_evidence_reference_or_blank_narrative_never_completes(self):
        for references,diagnosis in (([9],'Texto'),([1,1],'Texto'),([1],'   ')):
            result=self.make_result(False)
            result.actividades[0].redaccion_ia.referencias_evidencia=references
            result.actividades[0].redaccion_ia.diagnostico=diagnosis
            finalize_activity_states(result)
            self.assertEqual(result.actividades[0].motivo_incompleta,'ia_no_disponible')

    def test_permission_timeout_and_limit_keep_their_real_cause(self):
        for query_error,reason in (('permisos','permisos'),('timeout','error_tecnico'),('limite','limite_recursos')):
            result=self.make_result(False)
            result.actividades[0].consultas=[{'estado':query_error}]
            finalize_activity_states(result)
            self.assertEqual(result.actividades[0].estado_actividad,'incompleta')
            self.assertEqual(result.actividades[0].motivo_incompleta,reason)
            self.assertEqual(summarize_audit(result).automatizadas,0)

    def test_external_export_requirement_is_distinct_from_technical_failure(self):
        result=self.make_result(False)
        result.actividades[0].informacion_faltante=['Formato de historial propio: se requiere exportación técnica documentada.']
        finalize_activity_states(result)
        self.assertEqual(result.actividades[0].motivo_incompleta,'informacion_externa')


class TemplateTests(unittest.IsolatedAsyncioTestCase):
    @patch('app.audit_engine._fetch_rows',new_callable=AsyncMock)
    async def test_cache_ratio_has_no_invented_value_when_no_blocks_exist(self,fetch):
        from app.audit_engine import QueryOutcome
        from app.audit_technical import execute_technical_activity
        for hits,reads,expected in ((0,0,None),(8,2,80.0)):
            fetch.return_value=QueryOutcome([(hits,reads,None)],columns=('bloques_cache','bloques_leidos','reinicio_estadisticas'))
            result=await execute_technical_activity(None,ChecklistActivityReference(**TECHNICAL_CATALOG['6.6']))
            data=next(e.datos for e in result.evidencias if e.clave=='indicadores_cache')
            self.assertEqual(data['hit_ratio_porcentaje'],expected)
            self.assertEqual(data['medicion_disponible'],expected is not None)
            self.assertEqual(result.estado_evidencia,'suficiente')

    async def test_absent_extension_and_disabled_preload_are_observations_not_failures(self):
        evidence,missing=await statements_metrics(None,{'vista_instalada':False})
        self.assertEqual(missing,[])
        evidence,missing=await statements_metrics(None,{'vista_instalada':True,'permiso_lectura':True,'precargada':False})
        self.assertEqual(missing,[])
        self.assertFalse(evidence[0].datos['operatividad_confirmada'])

    async def test_permission_does_not_get_misreported_as_absent_extension(self):
        evidence,missing=await statements_metrics(None,{'vista_instalada':True,'permiso_lectura':False})
        self.assertTrue(missing[0].startswith('Permisos'))

    @patch('app.audit_technical_templates._run_template',new_callable=AsyncMock)
    async def test_history_template_never_reads_scripts_logs_or_authors(self,run):
        from app.audit_engine import QueryOutcome
        run.return_value=QueryOutcome([('fictitious_revision',)],columns=('version_num',))
        evidence,missing=await migration_history(None,[{'esquema':'schema"quoted','tabla':'alembic_version','columna':'version_num','permiso_lectura':True,'rls_activo':False}])
        statement=run.call_args.args[-1].as_string()
        self.assertIn('"schema""quoted"."alembic_version"',statement)
        self.assertNotIn('logs',statement)
        self.assertEqual(missing,[])
        self.assertEqual(evidence[0].datos['registros'],[{'version_num':'fictitious_revision'}])
