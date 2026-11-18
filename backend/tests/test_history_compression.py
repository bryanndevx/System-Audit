"""Evidencia exclusivamente ficticia para límites y compresión sin pérdida."""
import base64
import unittest
import zlib
from unittest.mock import patch

from app.audit_history import storage_payload, decode_storage_payload, AuditHistoryError
from tests.test_audit_history import sample_result


class CompressionTests(unittest.TestCase):
    def test_large_result_roundtrip_preserves_every_field(self):
        value = sample_result()
        value.actividades[0].evidencias[0].datos['comentario_ficticio'] = 'evidencia sintética ' * 2000
        with patch('app.audit_history.MAX_SAVED_RESULT_BYTES', 4000):
            payload = storage_payload(value)
            self.assertEqual(payload['formato_almacenamiento'], 'zlib-json-v1')
            self.assertEqual(decode_storage_payload(payload), value.model_dump(mode='json'))
        self.assertEqual(payload['resumen'], value.model_dump(mode='json')['resumen'])

    def test_small_and_historical_results_are_unchanged(self):
        value = sample_result()
        payload = storage_payload(value)
        self.assertNotIn('formato_almacenamiento', payload)
        self.assertEqual(decode_storage_payload(payload), value.model_dump(mode='json'))

    def test_decoded_size_is_bounded(self):
        payload = {'formato_almacenamiento': 'zlib-json-v1', 'resultado_comprimido': base64.b64encode(zlib.compress(b'x' * 10000)).decode()}
        with patch('app.audit_history.MAX_DECODED_RESULT_BYTES', 100), self.assertRaises(AuditHistoryError):
            decode_storage_payload(payload)

    def test_corruption_is_reported_without_partial_evidence(self):
        for encoded in ('not base64', base64.b64encode(b'invalid compressed stream').decode()):
            with self.assertRaises(AuditHistoryError):
                decode_storage_payload({'formato_almacenamiento': 'zlib-json-v1', 'resultado_comprimido': encoded})

    def test_excessive_original_size_is_rejected_before_database_access(self):
        with patch('app.audit_history.MAX_DECODED_RESULT_BYTES', 100), self.assertRaises(AuditHistoryError):
            storage_payload(sample_result())
