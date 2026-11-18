"""Regresión real con referencia manual independiente y credenciales solo de prueba."""
import asyncio
import os
import unittest

from app.audit_catalog import CATALOG
from app.audit_engine import ChecklistActivityReference, execute_audit_activities
from app.audit_history import summarize_audit
from app.event_loop import create_psycopg_compatible_event_loop
from app.external_connections import ExternalConnectionRequest, ExternalConnectionPolicy, open_verified_external_connection


@unittest.skipUnless(os.getenv('RUN_AUDIT_INTEGRATION') == '1', 'Requiere instancia ficticia y autorización explícita.')
class FullChecklistIntegrationTests(unittest.TestCase):
    def test_checklist_against_independent_control_fixture(self):
        asyncio.run(self.check(), loop_factory=create_psycopg_compatible_event_loop)

    async def check(self):
        host = os.environ['AUDIT_TEST_HOST']
        port = int(os.environ['AUDIT_TEST_PORT'])
        request = ExternalConnectionRequest(host=host, port=port, database=os.environ['AUDIT_TEST_DATABASE'],
            username=os.environ['AUDIT_TEST_USER'], password=os.environ['AUDIT_TEST_PASSWORD'])
        policy = ExternalConnectionPolicy('development', frozenset({host}), (), frozenset({port}), 'disable', None)
        async with open_verified_external_connection(request, policy, application_name='catalog67_regression') as connection:
            result = await execute_audit_activities(connection, [ChecklistActivityReference(**definition) for definition in CATALOG.values()])
        activities = {a.identificador: a for a in result.actividades}
        server = next(e for e in activities['1.1'].evidencias if e.clave=='server_facts').datos['filas'][0]
        self.assertTrue(server['transaccion_solo_lectura'])
        stack = next(e for e in activities['1.1'].evidencias if e.clave=='ficha_stack_incompleta').datos['componentes']
        self.assertEqual(activities['1.1'].evidencias[0].clave, 'ficha_stack_incompleta')
        self.assertEqual(stack[0]['valor'], 'PostgreSQL')
        self.assertTrue(stack[1]['valor'])
        self.assertTrue(all(c['valor'] is None for c in stack[2:]))
        self.assertEqual(activities['1.1'].estado_entregable, 'requiere_informacion_externa')
        self.assertEqual(list(activities), list(CATALOG))
        self.assertEqual(len(activities), 67)
        self.assertFalse(any(a.estado_ejecucion == 'error_tecnico' for a in activities.values()))
        self.assertFalse([q for a in activities.values() for q in a.consultas if q['estado'] != 'completada'])
        self.assertEqual(sum(a.estado_ejecucion == 'no_ejecutable' for a in activities.values()), 2)
        # Referencia manual: la fixture contiene una FK NOT VALID y exactamente un huérfano (reference_id=999).
        controls = next(e for e in activities['7.2'].evidencias if e.clave=='referential_control').datos['filas']
        observed = next(row for row in controls if row['esquema']=='audit_controls_fixture' and row['restriccion']=='reference_item_fk')
        self.assertFalse(observed['validada'])
        counts = next(e for e in activities['7.3'].evidencias if e.clave=='conteos_agregados_fk').datos['comprobaciones']
        count = next(row for row in counts if row['restriccion']=='reference_item_fk')
        self.assertEqual(count['registros_huerfanos'], 1)
        self.assertEqual(count['nulos_parciales_match_full'], 0)
        roles = next(e for e in activities['8.1'].evidencias if e.clave=='roles').datos['filas']
        reader = next(role for role in roles if role['rol']==request.username)
        self.assertFalse(reader['superusuario'])
        self.assertFalse(reader['crea_roles'])
        tls = next(e for e in activities['8.2'].evidencias if e.clave=='session_tls').datos['filas']
        self.assertFalse(tls[0]['tls_sesion_actual'])  # Fixture local sin TLS; no se atribuye cifrado en tránsito.
        self.assertEqual(activities['8.3'].grado_automatizacion, 'parcial')
        self.assertEqual(activities['8.4'].grado_automatizacion, 'parcial')
        summary = summarize_audit(result)
        self.assertEqual(summary.requieren_informacion_externa, 57)
        self.assertEqual(summary.automatizadas, 10)
        self.assertEqual(summary.porcentaje_automatizacion, 14.93)
