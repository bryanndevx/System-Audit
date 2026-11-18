"""Actividades adicionales: evidencias declaradas y límites por entregable."""

import time

from app import audit_extended_queries as q
from app import audit_queries as base
from app.audit_catalog import COMPLETE_DELIVERABLES, EXTERNAL_ONLY, EXTERNAL_REQUIREMENTS

# Nombres funcionales estables para las posiciones revisadas de consultas compartidas.
COLUMN_LABELS = {
    base.USER_SCHEMAS_SQL: 'oid esquema permiso_uso_esquema',
    base.TABLE_INVENTORY_SQL: 'oid esquema tabla nombre_completo tipo es_particion tabla_padre permiso_uso_esquema permiso_lectura',
    base.TABLE_COLUMNS_SQL: 'tabla_oid esquema tabla nombre_completo orden campo tipo obligatorio',
    base.PARTITION_CONFIGURATION_SQL: 'tabla_padre_oid esquema_padre tabla_padre nombre_completo_padre estrategia clave_particion particion_oid esquema_particion particion nombre_completo_particion limites_particion permiso_uso_esquema permiso_lectura',
    base.ENGINE_CONFIGURATION_SQL: 'parametro valor unidad tipo contexto origen reinicio_pendiente',
    base.TABLE_VOLUMETRY_SQL: 'oid esquema tabla nombre_completo tipo es_particion padre_oid datos_bytes indices_bytes total_bytes filas_estimadas paginas tuplas_vivas_estimadas tuplas_muertas_estimadas modificaciones_desde_analisis ultimo_vacuum ultimo_autovacuum ultimo_analisis ultimo_autoanalisis permiso_uso_esquema permiso_lectura',
    base.QUERY_OBSERVABILITY_SQL: 'track_activities track_counts calcular_identificador_consulta reinicio_estadisticas extension_pg_stat_statements_instalada esquema_extension permiso_uso_esquema permiso_lectura',
    base.INDEX_INVENTORY_SQL: 'tabla_oid esquema tabla nombre_completo indice_oid indice metodo es_pk es_unico es_exclusion es_valido preparado vigente columnas_clave columnas_totales claves definicion_claves columnas_incluidas predicado expresiones bytes lecturas ultimo_escaneo',
    base.COLUMN_DICTIONARY_SQL: 'tabla_oid esquema tabla nombre_completo tipo_tabla orden campo tipo tipo_oid modificador_tipo obligatorio valor_predeterminado identidad generado esquema_tipo nombre_tipo clase_tipo dominio_tipo_base esquema_colacion colacion comentario es_local herencias permiso_uso_esquema permiso_lectura',
    base.TABLE_CONSTRAINTS_SQL: 'tabla_oid restriccion_oid restriccion tipo columnas',
    base.TABLE_FOREIGN_KEYS_SQL: 'restriccion_oid tabla_origen_oid tabla_destino_oid restriccion tabla_origen tabla_destino columnas_origen columnas_destino accion_actualizacion accion_eliminacion',
    base.TABLE_TRIGGER_INVENTORY_SQL: 'trigger_oid esquema tabla nombre_completo trigger eventos_codigo habilitado es_interno trigger_padre_oid trigger_padre esquema_funcion funcion argumentos extension',
    base.COLUMN_CHECK_CONSTRAINTS_SQL: 'tabla_oid restriccion_oid restriccion definicion columnas',
    base.DOMAIN_CONSTRAINTS_SQL: 'tipo_oid esquema dominio restriccion_oid restriccion definicion',
}

# Cada entrada selecciona evidencias distintas. No recibe SQL del cliente ni de IA.
PLANS = {
    "1.1": (q.SERVER_FACTS_SQL, q.EXTENSIONS_SQL),
    "1.3": (q.SERVER_FACTS_SQL, base.USER_SCHEMAS_SQL, base.PARTITION_CONFIGURATION_SQL),
    "1.4": (q.FOREIGN_SERVERS_SQL, q.EXTENSIONS_SQL, q.PUBLICATIONS_SQL, q.SUBSCRIPTIONS_METADATA_SQL),
    "1.5": (q.SERVER_FACTS_SQL, base.ENGINE_CONFIGURATION_SQL),
    "1.6": (base.USER_SCHEMAS_SQL, base.TABLE_INVENTORY_SQL),
    "1.7": (q.MIGRATION_CANDIDATES_SQL, q.SERVER_FACTS_SQL),
    "1.8": (base.TABLE_INVENTORY_SQL, base.TABLE_COLUMNS_SQL),
    "6.5": (base.TABLE_VOLUMETRY_SQL, base.PARTITION_CONFIGURATION_SQL),
    "6.6": (q.CACHE_STATISTICS_SQL, base.QUERY_OBSERVABILITY_SQL),
    "6.8": (base.TABLE_VOLUMETRY_SQL, base.INDEX_INVENTORY_SQL, q.REFERENTIAL_CONTROL_SQL),
    "7.1": (base.COLUMN_DICTIONARY_SQL, base.TABLE_CONSTRAINTS_SQL, base.DOMAIN_CONSTRAINTS_SQL),
    "7.2": (base.TABLE_FOREIGN_KEYS_SQL, q.REFERENTIAL_CONTROL_SQL),
    "7.3": (base.TABLE_CONSTRAINTS_SQL, q.REFERENTIAL_CONTROL_SQL),
    "7.4": (base.TABLE_FOREIGN_KEYS_SQL, base.TABLE_CONSTRAINTS_SQL),
    "7.5": (base.TABLE_CONSTRAINTS_SQL, base.TABLE_TRIGGER_INVENTORY_SQL, base.COLUMN_DICTIONARY_SQL),
    "7.6": (q.SECURITY_CONFIGURATION_SQL, q.CACHE_STATISTICS_SQL),
    "7.7": (base.COLUMN_CHECK_CONSTRAINTS_SQL, base.DOMAIN_CONSTRAINTS_SQL, base.COLUMN_DICTIONARY_SQL),
    "7.8": (q.MIGRATION_CANDIDATES_SQL, q.REFERENTIAL_CONTROL_SQL, base.TABLE_CONSTRAINTS_SQL),
    "8.1": (q.ROLES_SQL, q.MEMBERSHIPS_SQL, q.PRIVILEGES_SQL, q.COLUMN_PRIVILEGES_SQL, q.DEFAULT_PRIVILEGES_SQL, q.ACCESS_CONTROLS_SQL),
    "8.2": (q.SECURITY_CONFIGURATION_SQL, q.SESSION_TLS_SQL, q.EXTENSIONS_SQL),
    "8.3": (q.WAL_CONFIGURATION_SQL, q.ARCHIVER_SQL, q.BACKUP_PROGRESS_SQL, q.REPLICATION_SLOTS_SQL),
    "8.4": (q.WAL_CONFIGURATION_SQL, q.RECOVERY_SQL, q.REPLICATION_SQL, q.REPLICATION_VISIBILITY_SQL, q.REPLICATION_SLOTS_SQL, q.WAL_RECEIVER_SQL),
    "8.5": (q.SECURITY_CONFIGURATION_SQL, q.EXTENSIONS_SQL, base.TABLE_TRIGGER_INVENTORY_SQL, q.AUDIT_LOG_SETTINGS_SQL),
    "8.6": (q.SECURITY_CONFIGURATION_SQL, q.ACCESS_CONTROLS_SQL, q.SESSION_TLS_SQL),
    "8.7": (q.DATABASE_ENVIRONMENTS_SQL, q.ROLES_SQL),
    "8.8": (q.MIGRATION_CANDIDATES_SQL,),
    "8.10": (q.MASKING_METADATA_SQL, q.EXTENSIONS_SQL, q.ACCESS_CONTROLS_SQL),
}


async def execute_extended_activity(connection, activity):
    from app.audit_engine import ActivityEvidence, ActivityResult, _activity_status, _fetch_rows, _technical_warning
    started = time.perf_counter()
    identifier = activity.numero
    result = ActivityResult(
        identificador=identifier, numero_original=identifier,
        nombre_original=activity.actividad, fase_original=activity.fase,
        estado_ejecucion="no_ejecutable", estado_evidencia="no_obtenida",
        evidencias=[], advertencias=[], limitaciones=[EXTERNAL_REQUIREMENTS.get(identifier, "")], duracion_ms=0,
    )
    if identifier in EXTERNAL_ONLY:
        return result
    outcomes = []
    for statement in PLANS[identifier]:
        outcome = await _fetch_rows(connection, statement)
        outcomes.append(outcome)
        query_id = next(name.removesuffix("_SQL").lower() for module in (q, base)
                        for name, sql in vars(module).items() if name.endswith("_SQL") and sql == statement)
        warning = _technical_warning(query_id, outcome)
        if warning:
            result.advertencias.append(warning)
        rows = []
        for row in outcome.rows or []:
            columns = tuple(COLUMN_LABELS[statement].split()) if statement in COLUMN_LABELS else outcome.columns
            columns = columns or tuple(f"columna_{i+1}" for i in range(len(row)))
            if len(columns) != len(row):
                raise ValueError("La consulta no coincide con su estructura de evidencia revisada.")
            # Algunas expresiones PostgreSQL tienen nombres repetidos; conservar todos los valores.
            if len(set(columns)) != len(columns):
                columns = tuple(f"{column}_{i+1}" for i, column in enumerate(columns))
            rows.append(dict(zip(columns, row)))
        result.evidencias.append(ActivityEvidence(
            clave=query_id, consulta_id=query_id,
            disponibilidad="no_disponible" if outcome.rows is None else "disponible" if rows else "sin_datos",
            naturaleza="no_disponible" if outcome.rows is None else "estimada" if statement == base.TABLE_VOLUMETRY_SQL else "exacta",
            datos={"filas": rows, "total_filas_obtenidas": len(rows), "truncada": outcome.error == "limite",
                   "alcance": "metadatos_y_estadisticas_sin_valores_de_negocio"},
        ))
    result.estado_ejecucion = _activity_status(outcomes)
    if identifier == "1.1":
        facts = result.evidencias[0].datos['filas']
        version = facts[0].get('version') if facts else None
        components = [
            {"componente": "Motor de base de datos", "valor": "PostgreSQL" if facts else None, "estado": "obtenido" if facts else "no_obtenido"},
            {"componente": "Versión del motor", "valor": version, "estado": "obtenido" if version else "no_obtenido"},
        ]
        components.extend({"componente": name, "valor": None, "estado": "requiere_informacion_externa"}
                          for name in ("Lenguaje backend", "Framework backend", "ORM", "Lenguaje frontend", "Framework frontend", "Infraestructura de despliegue"))
        result.evidencias.insert(0, ActivityEvidence(clave='ficha_stack_incompleta',consulta_id='server_facts',
            disponibilidad='disponible' if facts else 'no_disponible', naturaleza='calculada', datos={'componentes': components}))
    if identifier == "7.3":
        from app.audit_data_checks import collect_fk_data_counts
        result.evidencias.append(await collect_fk_data_counts(connection))
        result.limitaciones.append("Conteos exactos solo para FK declaradas comprobadas, máximo diez; se omiten RLS activo, tablas externas y tipos personalizados. Los fallos permanecen registrados por comprobación. No se buscan duplicados sin una regla de unicidad empresarial.")
    result.estado_evidencia = ("no_obtenida" if result.estado_ejecucion == "error_tecnico" else
                              "suficiente" if identifier in COMPLETE_DELIVERABLES and result.estado_ejecucion == "completada" else "insuficiente")
    result.limitaciones.append("Visibilidad según permisos de la conexión e instante de consulta; las estadísticas pueden haberse reiniciado.")
    if identifier == "8.4":
        result.limitaciones.append("Campos estadísticos NULL o filas ausentes no prueban ausencia de replicación; contrastar permisos pg_read_all_stats sin elevar automáticamente el usuario.")
    if identifier == "6.8":
        result.limitaciones.append("El entregable es una base de revisión técnica; no se calcula una matriz de impacto/esfuerzo sin estimaciones validadas.")
    result.duracion_ms = round((time.perf_counter() - started) * 1000)
    return result
