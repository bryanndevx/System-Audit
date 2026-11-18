"""Catálogo técnico v1: planes explícitos, evidencia suficiente y evaluación independiente del hallazgo."""

import re
import time

from app import audit_queries as b, audit_extended_queries as x, audit_technical_queries as q
from app.audit_extended import COLUMN_LABELS

PLANS = {
    '1.1': (q.INSTANCE_IDENTITY_SQL,),
    '1.2': (x.DATABASE_ENVIRONMENTS_SQL,q.SCHEMA_OBJECTS_SQL,b.TABLE_INVENTORY_SQL,b.TABLE_FOREIGN_KEYS_SQL),
    '1.3': (q.SCHEMA_OBJECTS_SQL,x.ACCESS_CONTROLS_SQL),
    '1.4': (x.EXTENSIONS_SQL,q.FDW_INVENTORY_SQL,x.FOREIGN_SERVERS_SQL,x.PUBLICATIONS_SQL,x.SUBSCRIPTIONS_METADATA_SQL),
    '1.5': (q.INSTANCE_IDENTITY_SQL,b.ENGINE_CONFIGURATION_SQL,x.SECURITY_CONFIGURATION_SQL,x.WAL_CONFIGURATION_SQL,b.DATABASE_SIZE_SQL),
    '1.6': (q.SCHEMA_OBJECTS_SQL,),
    '1.7': (q.MIGRATION_COLUMNS_SQL,),
    '1.8': (q.OBJECT_NAMES_SQL,),
    '3.9': (q.COLUMN_REVIEW_SQL,),
    '4.5': (b.QUERY_OBSERVABILITY_SQL,q.STATEMENTS_CAPABILITY_SQL),
    '6.1': (q.SESSION_INDICATORS_SQL,q.DATABASE_IO_SQL,x.CACHE_STATISTICS_SQL,b.DATABASE_STATISTICS_CONTEXT_SQL),
    '6.2': (b.TABLE_VOLUMETRY_SQL,b.PARTITION_CONFIGURATION_SQL,b.DATABASE_STATISTICS_CONTEXT_SQL),
    '6.3': (q.MATERIALIZED_VIEWS_SQL,b.VIEW_DEPENDENCIES_SQL),
    '6.4': (q.ROUTINE_PROPERTIES_SQL,b.ROUTINE_DEPENDENCIES_SQL),
    '6.5': (b.COLUMN_DICTIONARY_SQL,b.TABLE_VOLUMETRY_SQL,b.PARTITION_CONFIGURATION_SQL),
    '6.6': (q.DATABASE_IO_SQL,),
    '6.7': (b.ENGINE_CONFIGURATION_SQL,x.SECURITY_CONFIGURATION_SQL),
    '6.8': (),  # Consolidación posterior de hallazgos de la misma ejecución.
    '7.1': (b.COLUMN_DICTIONARY_SQL,b.TABLE_CONSTRAINTS_SQL,b.DOMAIN_CONSTRAINTS_SQL),
    '7.2': (b.TABLE_FOREIGN_KEYS_SQL,x.REFERENTIAL_CONTROL_SQL),
    '7.3': (b.TABLE_CONSTRAINTS_SQL,b.COLUMN_DICTIONARY_SQL,x.REFERENTIAL_CONTROL_SQL),
    '7.4': (b.TABLE_INVENTORY_SQL,b.TABLE_COLUMNS_SQL,b.TABLE_FOREIGN_KEYS_SQL,b.TABLE_CONSTRAINTS_SQL),
    '7.5': (b.TABLE_CONSTRAINTS_SQL,b.COLUMN_DICTIONARY_SQL,b.TABLE_TRIGGER_INVENTORY_SQL,b.DOMAIN_CONSTRAINTS_SQL),
    '7.6': (x.SECURITY_CONFIGURATION_SQL,x.CACHE_STATISTICS_SQL),
    '7.7': (b.COLUMN_DICTIONARY_SQL,b.COLUMN_CHECK_CONSTRAINTS_SQL,b.DOMAIN_CONSTRAINTS_SQL,b.ENUM_VALUES_SQL),
    '7.8': (q.MIGRATION_COLUMNS_SQL,b.TABLE_ROUTINE_DEPENDENCIES_SQL,b.VIEW_DEPENDENCIES_SQL),
    '8.1': (x.ROLES_SQL,x.MEMBERSHIPS_SQL,x.PRIVILEGES_SQL,x.COLUMN_PRIVILEGES_SQL,x.DEFAULT_PRIVILEGES_SQL),
    '8.2': (q.SSL_SETTINGS_SQL,x.SESSION_TLS_SQL),
    '8.3': (x.WAL_CONFIGURATION_SQL,x.ARCHIVER_SQL,x.BACKUP_PROGRESS_SQL),
    '8.4': (x.REPLICATION_SQL,x.REPLICATION_VISIBILITY_SQL,x.REPLICATION_SLOTS_SQL,x.WAL_RECEIVER_SQL,x.RECOVERY_SQL),
    '8.5': (x.EXTENSIONS_SQL,x.AUDIT_LOG_SETTINGS_SQL,b.TABLE_TRIGGER_INVENTORY_SQL,b.EVENT_TRIGGER_INVENTORY_SQL),
    '8.6': (x.SECURITY_CONFIGURATION_SQL,x.ACCESS_CONTROLS_SQL,q.POLICY_METADATA_SQL),
    '8.7': (q.INSTANCE_IDENTITY_SQL,x.DATABASE_ENVIRONMENTS_SQL,q.SCHEMA_OBJECTS_SQL),
    '8.8': (q.MIGRATION_COLUMNS_SQL,),
    '8.9': (x.PRIVILEGES_SQL,x.DEFAULT_PRIVILEGES_SQL,x.AUDIT_LOG_SETTINGS_SQL,b.EVENT_TRIGGER_INVENTORY_SQL),
    '8.10': (x.ACCESS_CONTROLS_SQL,q.POLICY_METADATA_SQL,x.MASKING_METADATA_SQL,x.EXTENSIONS_SQL),
}

SCOPE_NOTES = {
    '1.1': 'version() identifica la compilación; PostgreSQL no ofrece un campo universal de edición comercial. No se infiere proveedor o licencia.',
    '1.3': 'La organización observada no identifica empresas ni confirma un modelo multi-tenant de aplicación.',
    '1.7': 'Se inspeccionan los formatos de versionado reconocidos, sin leer scripts, autores ni logs de migración.',
    '2.2': 'La clasificación es técnica; categorías ambiguas son un resultado válido y no se convierten en propósito empresarial confirmado.',
    '2.3': 'Captura puntual con tamaños y estimaciones estadísticas: no equivale a COUNT exacto ni demuestra tasa de crecimiento.',
    '2.4': 'Los indicios de inactividad están condicionados al reinicio y ventana de estadísticas; no confirman desuso en la aplicación.',
    '3.7': 'Sensibilidad preliminar por metadatos; no se inspeccionan registros personales ni se confirma su contenido.',
    '3.8': 'Criterio sintáctico documentado: identificadores ASCII snake_case en minúsculas; no se presupone una norma empresarial.',
    '3.9': 'Ausencia de comentarios o pocas dependencias son candidatos de revisión, no prueba de deprecación.',
    '4.5': 'La ausencia de pg_stat_statements o su precarga deshabilitada es una observación válida. Solo se leen métricas accesibles, sin texto SQL.',
    '4.6': 'Tuplas muertas y autovacuum son indicadores; no se mide fragmentación exacta ni se ejecuta mantenimiento.',
    '5.1': 'Diagrama físico de relaciones declaradas; no se inventan relaciones ni cardinalidades de negocio.',
    '6.2': 'Una captura no mide crecimiento histórico; constituye una referencia temporal para seguimiento de capacidad.',
    '6.5': 'Los candidatos no autorizan purgar datos ni fijan plazos de retención.',
    '6.6': 'El hit ratio se calcula solo con denominador no nulo; caché de bloques no representa caché de aplicación.',
    '6.7': 'Los valores son efectivos en la sesión protegida del auditor; los parámetros con origen client no representan necesariamente el valor por defecto del servidor.',
    '6.8': 'Criticidad provisional de reglas técnicas documentadas, no valoración empresarial ni decisión automática de cambio.',
    '7.3': 'Se evalúa prevención declarativa; no se afirma ausencia de duplicados o huérfanos en registros.',
    '7.6': 'La configuración transaccional no demuestra comportamiento ACID de transacciones de la aplicación.',
    '8.2': 'SSL del servidor y cifrado de esta sesión no prueban cifrado de todas las conexiones ni del almacenamiento.',
    '8.3': 'WAL y archivado no prueban backups utilizables ni PITR operativo. No se descartan copias externas.',
    '8.4': 'Replicación y slots no prueban recuperación ensayada ni definen RPO/RTO. Los NULL están sujetos a visibilidad.',
    '8.8': 'La ausencia de historiales reconocidos no demuestra ausencia de migraciones externas o de un sistema propio.',
    '8.10': 'Capacidad/configuración visible no demuestra que registros personales estén anonimizados.',
}


async def collect(connection, result, statements):
    from app.audit_engine import ActivityEvidence, _fetch_rows, _technical_warning
    for statement in statements:
        outcome=await _fetch_rows(connection,statement)
        query_id=next(name.removesuffix('_SQL').lower() for module in (b,x,q) for name,value in vars(module).items() if name.endswith('_SQL') and value==statement)
        columns=tuple(COLUMN_LABELS[statement].split()) if statement in COLUMN_LABELS else outcome.columns
        rows=[dict(zip(columns or [f'columna_{i+1}' for i in range(len(row))],row)) for row in outcome.rows or []]
        result.evidencias.append(ActivityEvidence(clave=query_id,consulta_id=query_id,
            disponibilidad='no_disponible' if outcome.rows is None else 'disponible' if rows else 'sin_datos',
            naturaleza='no_disponible' if outcome.rows is None else 'estimada' if statement==b.TABLE_VOLUMETRY_SQL else 'exacta',
            datos={'filas':rows,'total_filas_obtenidas':len(rows),'truncada':outcome.error=='limite'}))
        warning=_technical_warning(query_id,outcome)
        if warning:
            result.advertencias.append(warning)
    return result


def data_rows(result,key):
    return next((e.datos.get('filas',[]) for e in result.evidencias if e.clave==key and isinstance(e.datos,dict)),[])


def add_evidence(result,key,data):
    from app.audit_engine import ActivityEvidence
    result.evidencias.append(ActivityEvidence(clave=key,consulta_id='consolidacion_tecnica_v1',
        disponibilidad='disponible',naturaleza='calculada',datos=data))


async def execute_technical_activity(connection,activity):
    from app import audit_engine as engine
    started=time.perf_counter()
    identifier=activity.numero
    missing=[]
    if identifier.startswith('2.'):
        function={
            '2.1':engine._execute_table_inventory,'2.2':engine._execute_table_classification,'2.3':engine._execute_volumetry,
            '2.4':engine._execute_table_retirement_candidates,'2.5':engine._execute_table_module_matrix,
            '2.6':engine._execute_audit_table_candidates,'2.7':engine._execute_view_inventory,'2.8':engine._execute_programmable_inventory,
        }[identifier]
        result=await function(connection,activity)
    elif identifier.startswith('3.') and identifier!='3.9':
        result=await engine._execute_column_dictionary_activity(connection,activity)
    elif identifier in {'4.1','4.2','4.3','4.4'}:
        result=await engine._execute_index_activity(connection,activity)
    elif identifier in {'4.6','4.7','4.8'}:
        result=await engine._execute_advanced_performance_activity(connection,activity)
    elif identifier.startswith('5.'):
        result=await engine._execute_data_model_activity(connection,activity)
    else:
        result=engine.ActivityResult(identificador=identifier,numero_original=identifier,nombre_original=activity.actividad,
            fase_original=activity.fase,estado_ejecucion='completada',estado_evidencia='suficiente',evidencias=[],advertencias=[],limitaciones=[],duracion_ms=0)
        await collect(connection,result,PLANS[identifier])
    # Solo cambia la interpretación del alcance NUEVO; la transformación histórica se conserva.
    result.limitaciones=['Alcance: metadatos y estadísticas observables de PostgreSQL; cada consulta tiene límites y visibilidad propios.']
    if identifier in SCOPE_NOTES:
        result.limitaciones.append(SCOPE_NOTES[identifier])
    extras={
        '2.5':(b.VIEW_DEPENDENCIES_SQL,b.TABLE_ROUTINE_DEPENDENCIES_SQL),
        '3.1':(b.COLUMN_DICTIONARY_SQL,), '3.6':(b.TABLE_CONSTRAINTS_SQL,), '3.7':(b.COLUMN_DICTIONARY_SQL,),
        '4.2':(b.TABLE_CONSTRAINTS_SQL,),
        '5.1':(b.TABLE_CONSTRAINTS_SQL,b.COLUMN_DICTIONARY_SQL,),
        '5.5':(b.TABLE_COLUMNS_SQL,),
    }
    await collect(connection,result,extras.get(identifier,()))
    if identifier=='1.1':
        facts=data_rows(result,'instance_identity')
        if facts:
            add_evidence(result,'ficha_motor_postgresql',{'motor':'PostgreSQL',
                'version':facts[0]['version'],'identificacion_reportada':facts[0]['identificacion_compilacion'],
                'edicion_comercial':None,'edicion_comercial_confirmada':False,
                'nota_edicion':'PostgreSQL no expone un campo universal de edición comercial; no se infiere proveedor o licencia.'})
    if identifier=='1.2':
        mapping=await engine._execute_data_model_activity(connection,activity.model_copy(update={'numero':'5.1'}))
        result.evidencias.extend(mapping.evidencias)
        result.advertencias.extend(mapping.advertencias)
    if identifier in {'1.7','7.8','8.8'}:
        from app.audit_technical_templates import migration_history
        evidence,missing=await migration_history(connection,data_rows(result,'migration_columns'))
        result.evidencias.extend(evidence)
        add_evidence(result,'alcance_versionado',{'tablas_versionadoras_detectadas':len({(r['esquema'],r['tabla']) for r in data_rows(result,'migration_columns')}),
            'formatos_reconocidos':['alembic','django','flyway','liquibase','prisma','schema_migrations','knex','sequelize'],
            'historial_externo_evaluado':False})
    if identifier=='4.5':
        from app.audit_technical_templates import statements_metrics
        capability=data_rows(result,'statements_capability')
        if capability:
            evidence,missing=await statements_metrics(connection,capability[0])
            result.evidencias.extend(evidence)
    if identifier=='1.8':
        rows=data_rows(result,'object_names')
        add_evidence(result,'patrones_nombres_objetos',{'criterio':'ASCII snake_case: ^[a-z][a-z0-9_]*$',
            'objetos':[dict(row,cumple_patron=bool(re.fullmatch('[a-z][a-z0-9_]*',row['objeto']))) for row in rows],
            'total_objetos':len(rows)})
    if identifier=='3.9':
        add_evidence(result,'columnas_para_revision',{'criterio':'Sin comentario o con cero dependencias declaradas; no implica desuso.',
            'columnas':[row for row in data_rows(result,'column_review') if not row['tiene_comentario'] or row['dependencias_declaradas']==0]})
    if identifier=='3.7':
        candidates=[]
        for row in data_rows(result,'column_dictionary'):
            tokens=engine._identifier_tokens(f"{row['campo']} {row.get('comentario') or ''}")
            signals=[group for group,terms in engine.SENSITIVE_COLUMN_HINTS.items() if tokens & terms]
            if signals:
                candidates.append({'esquema':row['esquema'],'tabla':row['tabla'],'campo':row['campo'],'categorias_preliminares':signals})
        add_evidence(result,'sensibilidad_por_metadatos',{'candidatas':candidates,'contenido_datos_inspeccionado':False})
    if identifier=='4.7':
        for evidence in result.evidencias:
            if isinstance(evidence.datos,dict) and 'indices_compuestos_o_con_includes_existentes' in evidence.datos:
                # La consulta base ya contiene diseños simples, compuestos, INCLUDE, expresiones y predicados.
                await collect(connection,result,(b.INDEX_INVENTORY_SQL,))
                break
    if identifier=='5.1':
        physical=next((e.datos for e in result.evidencias if isinstance(e.datos,dict) and 'entidades' in e.datos),None)
        if physical is not None:
            constraints=data_rows(result,'table_constraints')
            physical['diagrama_er_fisico']=[dict(entity,claves_primarias=[c['columnas'] for c in constraints if c['tabla_oid']==entity['oid'] and c['tipo']=='p']) for entity in physical['entidades']]
            physical['diagrama_visual_generado']=True
    if identifier=='5.5':
        # Comparación determinista de tipos de FK: reutilizar el algoritmo revisado de 5.8.
        comparison=await engine._execute_data_model_activity(connection,activity.model_copy(update={'numero':'5.8'}))
        result.evidencias.extend(comparison.evidencias)
        result.advertencias.extend(comparison.advertencias)
    if identifier=='6.5':
        columns=data_rows(result,'column_dictionary')
        temporal={1082,1083,1114,1184,1186,1266}
        add_evidence(result,'candidatos_retencion',{'criterio':'Tipos temporales declarados; no se infieren plazos ni se propone borrar registros.',
            'columnas':[{'esquema':r['esquema'],'tabla':r['tabla'],'campo':r['campo'],'tipo':r['tipo']} for r in columns if r['tipo_oid'] in temporal]})
    if identifier=='6.6':
        rows=data_rows(result,'database_io')
        if rows:
            hit,read=rows[0]['bloques_cache'],rows[0]['bloques_leidos']
            add_evidence(result,'indicadores_cache',{'bloques_cache':hit,'bloques_leidos':read,
                'hit_ratio_porcentaje':round(hit/(hit+read)*100,2) if hit+read else None,
                'medicion_disponible':bool(hit+read),'reinicio_estadisticas':rows[0]['reinicio_estadisticas']})
    if identifier=='7.4':
        classification=await engine._execute_table_classification(connection,activity.model_copy(update={'numero':'2.2'}))
        result.evidencias.extend(classification.evidencias)
        result.advertencias.extend(classification.advertencias)
    result.informacion_faltante=missing
    if any(item.startswith('Permisos') for item in missing):
        result.motivo_incompleta='permisos'
    elif any('se limita la lectura' in item for item in missing):
        result.motivo_incompleta='limite_recursos'
    result.estado_evidencia='insuficiente' if missing else 'suficiente'
    # Errores, truncamientos y falta de permisos se resuelven con la traza completa en el motor.
    result.duracion_ms=round((time.perf_counter()-started)*1000)
    return result


def consolidate_findings(activities):
    target=next((a for a in activities if a.identificador=='6.8'),None)
    if target is None:
        return
    findings=[]
    seen=set()
    for activity in activities:
        for evidence in activity.evidencias:
            for row in evidence.datos.get('filas',[]) if isinstance(evidence.datos,dict) else []:
                code=None
                if evidence.clave=='referential_control' and row.get('validada') is False:
                    code='fk_no_validada'
                elif evidence.clave=='referential_control' and (row.get('triggers_no_activos_en_origen') or 0)>0:
                    code='triggers_fk_no_activos'
                elif evidence.clave=='index_inventory' and row.get('es_valido') is False:
                    code='indice_no_valido'
                elif evidence.clave=='index_inventory' and row.get('preparado') is False:
                    code='indice_no_preparado'
                elif evidence.clave=='session_tls' and row.get('tls_sesion_actual') is False:
                    code='sesion_sin_tls'
                elif evidence.clave=='security_configuration' and row.get('parametro') in {'fsync','full_page_writes'} and row.get('valor')=='off':
                    code='proteccion_durabilidad_deshabilitada'
                elif evidence.clave in {'security_configuration','ssl_settings'} and row.get('parametro')=='ssl' and row.get('valor')=='off':
                    code='ssl_servidor_deshabilitado'
                elif evidence.clave=='wal_configuration' and row.get('parametro')=='archive_mode' and row.get('valor')=='off':
                    code='archivado_wal_deshabilitado'
                elif evidence.clave=='roles' and row.get('superusuario') is True:
                    code='rol_administrativo_para_revision'
                elif evidence.clave=='materialized_views' and row.get('poblada') is False:
                    code='vista_materializada_no_poblada'
                if code:
                    identity=(code,str(row))
                    if identity not in seen:
                        seen.add(identity)
                        criticality = 'alta' if code in {'fk_no_validada','triggers_fk_no_activos','indice_no_valido','indice_no_preparado','proteccion_durabilidad_deshabilitada'} else 'baja' if code in {'rol_administrativo_para_revision','vista_materializada_no_poblada'} else 'media'
                        findings.append({'codigo':code,'criticidad_provisional':criticality,
                            'actividad_fuente':activity.identificador,'referencia_evidencia':activity.evidencias.index(evidence)+1,
                            'contexto':row,'validacion_empresarial_pendiente':True})
    add_evidence(target,'matriz_preliminar_hallazgos',{'hallazgos':findings,'total_hallazgos':len(findings),
        'criterios':'Alta provisional: FK no validada, triggers FK inactivos, índices inválidos/no preparados o fsync/full_page_writes off. Media: TLS de sesión/servidor o archivado deshabilitado. Baja: roles administrativos a revisar y vistas materializadas no pobladas. No implica incumplimiento empresarial; no se aplican cambios.'})
    add_evidence(target,'cobertura_revision',{'actividades_fuente':len(activities)-1,
        'actividades_con_fallo_o_evidencia_incompleta':[a.identificador for a in activities if a is not target and a.estado_evidencia not in {'suficiente','sin_datos'}]})
    if all(a is target or a.estado_evidencia not in {'suficiente','sin_datos'} for a in activities):
        target.estado_evidencia='insuficiente'
        target.informacion_faltante=['No se obtuvieron evidencias técnicas suficientes de otras actividades para priorizar hallazgos.']
