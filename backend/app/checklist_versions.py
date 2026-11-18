"""Versiones explícitas e inmutables de requisitos; los resultados no cambian el alcance."""

import hashlib
import json
from pathlib import Path

from app.audit_catalog import CATALOG as LEGACY_CATALOG

TECHNICAL_VERSION = 'postgresql-tecnico-v1'
LEGACY_VERSION = 'checklist-original-v1'
TECHNICAL_CRITERIA = 'evaluacion-observable-ia-v1'
FROZEN_TECHNICAL_FINGERPRINT = 'cca21629ae628a0f15f3573465ad663ff537c7862c8010ed3fb2f1fb94345e60'
TECHNICAL_CATALOG = {a['numero']: a for a in json.loads(Path(__file__).with_name('technical_checklist_v1.json').read_text(encoding='utf-8'))}


def matches(activity, definition):
    return (getattr(activity, 'actividad', getattr(activity, 'nombre_original', None)) == definition['actividad']
            and getattr(activity, 'fase', getattr(activity, 'fase_original', None)) == definition['fase']
            and activity.entregable_esperado == definition['entregable_esperado']
            and getattr(activity, 'prioridad', getattr(activity, 'prioridad_original', None)) == definition['prioridad'])


def detect_version(activities):
    for version, catalog in ((TECHNICAL_VERSION, TECHNICAL_CATALOG), (LEGACY_VERSION, LEGACY_CATALOG)):
        # Versionar la lista completa, sin aceptar selecciones, mezclas ni cambios de orden.
        if [a.numero for a in activities] == list(catalog) and all(matches(a, catalog[a.numero]) for a in activities):
            return version
    return 'personalizado'


def fingerprint(version):
    catalog = TECHNICAL_CATALOG if version == TECHNICAL_VERSION else LEGACY_CATALOG if version == LEGACY_VERSION else None
    if catalog is None:
        return None
    document = {'actividades': list(catalog.values()), 'criterios': TECHNICAL_CRITERIA if version == TECHNICAL_VERSION else 'criterio-historico'}
    digest=hashlib.sha256(json.dumps(document,ensure_ascii=False,sort_keys=True,separators=(',', ':')).encode()).hexdigest()
    if version == TECHNICAL_VERSION and digest != FROZEN_TECHNICAL_FINGERPRINT:
        raise ValueError('La definición técnica v1 fue alterada. Cree una versión nueva antes de modificar requisitos fijados.')
    return digest
