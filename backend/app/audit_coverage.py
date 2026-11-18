"""Estado del entregable separado del resultado técnico de las consultas."""

from app.audit_catalog import COMPLETE_DELIVERABLES, EXTERNAL_REQUIREMENTS

EVIDENCE_LABELS = {
    'server_facts': 'Motor, versión y parámetros básicos de PostgreSQL',
    'extensions': 'Inventario de extensiones',
    'foreign_servers': 'Integraciones mediante servidores externos',
    'publications': 'Publicaciones de replicación',
    'subscriptions_metadata': 'Metadatos de suscripciones',
    'replication_slots': 'Estado de slots y WAL requerido',
    'wal_receiver': 'Estado del receptor WAL',
    'audit_log_settings': 'Configuración de auditoría de cambios',
}


def describe_deliverable(activity):
    activity.informacion_obtenida = [
        EVIDENCE_LABELS.get(evidence.clave, evidence.clave.replace('_', ' '))
        + (' (sin filas obtenidas)' if evidence.disponibilidad == 'sin_datos' else '')
        for evidence in activity.evidencias if evidence.disponibilidad in {'disponible', 'sin_datos'}
        and evidence.naturaleza != 'no_disponible' and evidence.clave != 'ficha_stack_incompleta'
    ]
    external = EXTERNAL_REQUIREMENTS.get(activity.identificador)
    if activity.estado_ejecucion == 'error_tecnico':
        activity.estado_entregable = 'error_tecnico'
        activity.informacion_faltante = list(activity.advertencias)
    elif activity.grado_automatizacion == 'sin_configuracion':
        activity.estado_entregable = 'sin_configuracion'
        activity.informacion_faltante = list(activity.limitaciones)
    elif activity.grado_automatizacion == 'total':
        activity.estado_entregable = 'completo'
    elif external and activity.identificador not in COMPLETE_DELIVERABLES:
        activity.estado_entregable = 'requiere_informacion_externa'
        activity.informacion_faltante = [external, *activity.advertencias]
    else:
        activity.estado_entregable = 'evidencia_incompleta'
        activity.informacion_faltante = [*activity.advertencias, *activity.limitaciones]


def finalize_activity_states(result):
    """Solo la nueva versión mide ejecución completa con narrativa validada."""
    from app.checklist_versions import TECHNICAL_VERSION
    if result.checklist_version != TECHNICAL_VERSION:
        return
    for activity in result.actividades:
        # El aviso de IA de una pasada anterior no es un requisito externo.
        ai_notice = 'Falta diagnóstico y recomendación de IA válidos. La evidencia SQL se conserva; no es información externa de la base.'
        activity.informacion_faltante = [text for text in activity.informacion_faltante if text != ai_notice]
        errors=[q['estado'] for q in activity.consultas if q['estado']!='completada']
        reason=None
        if activity.motivo_incompleta in {'permisos','limite_recursos'}:
            reason=activity.motivo_incompleta
        elif 'permisos' in errors:
            reason='permisos'
        elif 'limite' in errors:
            reason='limite_recursos'
        elif errors or activity.estado_ejecucion=='error_tecnico':
            reason='error_tecnico'
        elif activity.estado_ejecucion=='sin_automatizacion_configurada':
            reason='sin_configuracion'
        elif activity.motivo_incompleta=='evidencia_insuficiente':
            reason='evidencia_insuficiente'
        elif activity.informacion_faltante:
            reason='informacion_externa'
        elif activity.estado_evidencia not in {'suficiente','sin_datos'} or not any(e.disponibilidad in {'disponible','sin_datos'} and e.naturaleza!='no_disponible' for e in activity.evidencias):
            reason='evidencia_insuficiente'
        elif (activity.redaccion_ia.estado!='generada' or not (activity.redaccion_ia.diagnostico or '').strip()
              or not (activity.redaccion_ia.recomendacion or '').strip() or not activity.redaccion_ia.referencias_evidencia
              or len(set(activity.redaccion_ia.referencias_evidencia))!=len(activity.redaccion_ia.referencias_evidencia)
              or not all(1<=reference<=len(activity.evidencias) for reference in activity.redaccion_ia.referencias_evidencia)):
            reason='ia_no_disponible'
        activity.estado_actividad='incompleta' if reason else 'completada'
        activity.motivo_incompleta=reason
        if reason=='ia_no_disponible':
            activity.informacion_faltante=[ai_notice]
        if reason in {'permisos','limite_recursos','error_tecnico','evidencia_insuficiente','sin_configuracion'}:
            activity.informacion_faltante=list(dict.fromkeys([*activity.informacion_faltante,*activity.advertencias])) or ['Falta evidencia técnica suficiente; revisar la traza de consultas.']
