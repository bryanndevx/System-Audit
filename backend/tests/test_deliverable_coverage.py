import unittest

from app.audit_coverage import describe_deliverable
from app.audit_catalog import CATALOG, COMPLETE_DELIVERABLES, EXTERNAL_REQUIREMENTS
from app.audit_history import summarize_audit
from tests.test_audit_history import sample_activity, sample_result


class DeliverableCoverageTests(unittest.TestCase):
    def test_partial_stack_keeps_technical_evidence_but_requires_external_information(self):
        activity = sample_activity('1.1')
        activity.grado_automatizacion = 'parcial'
        describe_deliverable(activity)
        self.assertEqual(activity.estado_ejecucion, 'completada')
        self.assertEqual(activity.estado_entregable, 'requiere_informacion_externa')
        self.assertTrue(activity.informacion_obtenida)
        self.assertIn('backend', activity.informacion_faltante[0])

    def test_permission_failure_is_never_relabelled_as_external_information(self):
        activity = sample_activity('1.1', status='error_tecnico', evidence='no_obtenida')
        activity.grado_automatizacion = 'error'
        activity.advertencias = ['Faltan permisos para consultar metadatos.']
        describe_deliverable(activity)
        self.assertEqual(activity.estado_entregable, 'error_tecnico')
        self.assertEqual(activity.informacion_faltante, activity.advertencias)

    def test_truncated_technical_inventory_is_incomplete_not_external(self):
        activity = sample_activity('2.1', status='parcial', evidence='insuficiente')
        activity.grado_automatizacion = 'parcial'
        activity.advertencias = ['Inventario truncado.']
        describe_deliverable(activity)
        self.assertEqual(activity.estado_entregable, 'evidencia_incompleta')

    def test_each_catalog_deliverable_has_explicit_reason_or_technical_scope(self):
        self.assertEqual(set(CATALOG), COMPLETE_DELIVERABLES | set(EXTERNAL_REQUIREMENTS))
        result = sample_result()
        result.actividades = []
        for identifier in CATALOG:
            activity = sample_activity(identifier)
            activity.grado_automatizacion = 'total' if identifier in COMPLETE_DELIVERABLES else 'parcial'
            describe_deliverable(activity)
            self.assertEqual(activity.estado_entregable, 'completo' if identifier in COMPLETE_DELIVERABLES else 'requiere_informacion_externa')
            if activity.estado_entregable != 'completo':
                self.assertTrue(activity.informacion_faltante)
            result.actividades.append(activity)
        summary = summarize_audit(result)
        self.assertEqual(summary.requieren_informacion_externa, 57)
        self.assertEqual(summary.con_evidencia_postgresql, 67)

    def test_unknown_activity_does_not_claim_to_need_external_information(self):
        activity = sample_activity('99.1', status='sin_automatizacion_configurada')
        activity.grado_automatizacion = 'sin_configuracion'
        describe_deliverable(activity)
        self.assertEqual(activity.estado_entregable, 'sin_configuracion')
