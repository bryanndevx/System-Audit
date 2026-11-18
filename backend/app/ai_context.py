"""Resumen de evidencia por lista permitida; nunca incluye filas ni texto del usuario."""

from __future__ import annotations

from typing import TYPE_CHECKING
from app.audit_catalog import CATALOG, EXTERNAL_REQUIREMENTS, definition_matches
from app import audit_queries, audit_extended_queries
from app import audit_technical_queries
from app.checklist_versions import TECHNICAL_CATALOG, matches, TECHNICAL_VERSION, TECHNICAL_CRITERIA

SAFE_QUERY_IDS = frozenset(name.removesuffix("_SQL").lower() for module in (audit_queries, audit_extended_queries, audit_technical_queries)
                           for name in vars(module) if name.endswith("_SQL"))

if TYPE_CHECKING:
    from app.audit_engine import ActivityResult

CRITERIA_VERSION = "gemini-criterios-v4"
CONTEXT_VERSION = "postgres-tecnico-contexto-v1"

TOPICS = {
    "2.1": "Inventario de tablas por esquema",
    "2.2": "Clasificación técnica de tablas",
    "2.3": "Volumetría actual y límites del crecimiento histórico",
    "2.4": "Indicios de uso y dependencias de tablas",
    "2.5": "Relaciones técnicas entre tablas y módulos",
    "2.6": "Indicios de tablas de auditoría",
    "2.7": "Inventario de vistas",
    "2.8": "Inventario de rutinas y triggers",
    "3.1": "Diccionario de campos",
    "3.2": "Tipos de campos",
    "3.3": "Obligatoriedad de campos",
    "3.4": "Dominios y valores permitidos",
    "3.5": "Campos generados",
    "3.6": "Indicios de reglas de campos",
    "3.7": "Indicios de datos sensibles",
    "3.8": "Nomenclatura de campos",
    "3.9": "Indicios de campos deprecados",
    "4.1": "Inventario de índices",
    "4.2": "Llaves primarias y foráneas",
    "4.3": "Indicios de índices redundantes",
    "4.4": "Indicios de índices faltantes",
    "4.5": "Observabilidad de consultas",
    "4.6": "Indicadores de mantenimiento de índices",
    "4.7": "Índices compuestos y cubrientes",
    "4.8": "Particionamiento",
    "5.1": "Relaciones y base técnica del modelo de datos",
    "5.2": "Indicios estructurales de normalización",
    "5.3": "Indicios de relaciones sin llave foránea",
    "5.4": "Cardinalidad técnica",
    "5.5": "Relaciones entre esquemas",
    "5.6": "Tablas puente",
    "5.7": "Convenciones de llaves primarias",
    "5.8": "Consistencia de tipos entre llaves foráneas",
}

# Solo valores numéricos/booleanos de primer nivel de campos técnicos conocidos.
SCALAR_FIELDS = frozenset({
    "bytes", "total_tablas", "total_indeterminadas", "clasificaciones_empresariales_confirmadas",
    "track_counts", "ventana_representativa", "total_candidatas_baja",
    "correspondencias_confirmadas", "correspondencias_pendientes", "total_candidatas",
    "total_sustentadas", "total_probables", "total_funcion_confirmada", "total_vistas",
    "total_vistas_materializadas", "inventario_completo_verificable", "total_funciones",
    "total_procedimientos", "total_triggers_relacion", "total_event_triggers", "total_campos",
    "total_indices", "total_entidades", "total_relaciones_fk", "diagrama_visual_generado",
    "relaciones_sin_fk_incluidas", "pool_conexiones_aplicacion_evaluado",
    "dimensionamiento_servidor_disponible", "total_pk", "total_fk", "incluye_texto_sql",
    "demuestra_frecuencia_historica", "fragmentacion_exacta_disponible",
    "necesidades_reporteria_evaluadas", "carga_consultas_evaluada", "cuerpos_extraidos",
    "rutinas_ejecutadas", "planes_ejecucion_disponibles", "campos_obligatorios",
    "campos_opcionales", "campos_busqueda_aplicacion_evaluados", "patrones_consulta_evaluados",
    "estrategia_futura_confirmada", "registros_evaluados", "correspondencia_esquema_modulo_confirmada",
    "contenido_datos_inspeccionado", "convencion_documentada_disponible",
    "coherencia_normativa_confirmada", "total_fk_con_diferencias", "total_snake_case_minusculas",
    "convencion_aprobada_disponible",
})
LIST_FIELDS = frozenset({
    "esquemas", "tablas", "vistas", "rutinas", "triggers", "tablas_para_revision",
    "candidatas_baja", "candidatas", "llaves_primarias", "llaves_foraneas", "entidades",
    "relaciones_fk", "consultas_activas", "consultas_criticas_confirmadas", "indices",
    "duplicados_exactos", "posibles_redundancias_prefijo", "eliminaciones_recomendadas",
    "fk_sin_indice_prefijo", "candidatos_tecnicos", "propuestas_indices_confirmadas",
    "tablas_particionadas", "candidatas_particionamiento_confirmadas", "candidatas_revision",
    "relaciones_huerfanas_confirmadas", "valores_predeterminados", "tipos_enum", "dominios_usados",
    "restricciones_dominio", "restricciones_check", "referencias_fk_posibles_catalogos",
    "relaciones", "tablas_puente_probables", "campos_generados", "campos_identidad_contexto",
    "relaciones_fk_entre_esquemas", "esquemas_observados", "reglas_tecnicas_observables",
    "campos_candidatos", "campos", "parametros", "recomendaciones_confirmadas",
    "campos_sensibles_confirmados", "campos_deprecados_confirmados",
    "reglas_empresariales_confirmadas", "violaciones_normalizacion_confirmadas",
    "tablas_puente_faltantes_confirmadas", "inconsistencias_intermodulos_confirmadas",
})

GENERAL_CRITERIA = (
    "Describe solo el resumen aportado. Los valores ya están calculados en Python: "
    "puedes citar sus valores literalmente, pero no hagas cálculos ni porcentajes ni inventes cifras. La ausencia de evidencia "
    "no es incumplimiento ni conformidad. No evalúes exactitud, cumplimiento normativo "
    "ni significado empresarial. No propongas SQL, cambios automáticos o eliminación "
    "de objetos. Recomienda revisión manual cuando falte contexto. No se proporcionan "
    "identidades, filas de negocio, comentarios ni definiciones SQL. Solo se permiten parámetros técnicos revisados y agregados. "
    "Un conteo de lista indica elementos resumidos, no siempre objetos únicos."
)
ACTIVITY_CRITERIA = {
    "2.1": "Describir inventario y visibilidad del rol; distinguir falta de permisos de ausencia de objetos.",
    "2.2": "Separar clasificación técnica, indeterminación y clasificación empresarial no confirmada.",
    "2.3": "Explicar volumen actual; no inferir tendencia o crecimiento sin mediciones históricas equivalentes.",
    "2.4": "Los indicios de uso no prueban obsolescencia; no recomendar bajas sin ventana y validación funcional.",
    "2.5": "Las relaciones técnicas entre tablas no confirman su pertenencia a módulos empresariales.",
    "2.6": "Las candidatas por metadatos no confirman función de auditoría ni contenido de registros.",
    "2.7": "Describir inventario de vistas/materializadas y límites de visibilidad; no evaluar necesidad funcional.",
    "2.8": "Inventario de rutinas y triggers no prueba ejecución correcta ni evalúa sus cuerpos.",
    "3.1": "El diccionario se limita a metadatos visibles; no afirmar completitud respecto de objetos inaccesibles.",
    "3.2": "Los tipos declarados no demuestran corrección de los valores de negocio.",
    "3.3": "NOT NULL describe obligatoriedad técnica; no demuestra validez de registros ni regla empresarial.",
    "3.4": "Enumeraciones, dominios, CHECK y FK describen reglas declaradas; no certificar catálogos empresariales.",
    "3.5": "Distinguir campos generados e identidad; no evaluar fórmulas o cálculos externos no observados.",
    "3.6": "Los indicios técnicos no confirman reglas de negocio ni que estas se apliquen fuera de PostgreSQL.",
    "3.7": "Indicios de campos sensibles requieren revisión del responsable; no se inspeccionan valores personales.",
    "3.8": "Describir patrones y conteos, sin declarar incumplimiento si no existe convención aprobada.",
    "3.9": "Los indicios de deprecación no confirman desuso; revisar aplicaciones e integraciones antes de actuar.",
    "4.1": "Inventario y uso acumulado de índices no prueban utilidad, redundancia o falta de uso histórico.",
    "4.2": "PK y FK documentadas no incluyen relaciones implementadas únicamente en código de aplicación.",
    "4.3": "Duplicados estructurales o prefijos son candidatos; validar restricciones y carga antes de cualquier cambio.",
    "4.4": "Una FK sin índice de prefijo es candidata a revisión, no una orden de crear un índice.",
    "4.5": "Una instantánea no determina consultas históricamente frecuentes/pesadas; faltan carga y planes.",
    "4.6": "Indicadores de mantenimiento no miden fragmentación exacta; no recomendar reconstrucción automática.",
    "4.7": "Evaluar candidatos con patrones y planes reales; no confirmar índices compuestos/cubrientes sin ellos.",
    "4.8": "Describir particionado actual; no confirmar estrategia futura sin volumen, crecimiento y carga aprobados.",
    "5.1": "La base técnica ER no equivale a diagrama visual ni modelo empresarial completo.",
    "5.2": "Los indicios estructurales no prueban normalización o desnormalización sin dependencias funcionales.",
    "5.3": "Relaciones sugeridas sin FK son indicios; no se inspeccionaron registros para confirmar huérfanos.",
    "5.4": "Cardinalidad técnica y tablas puente probables no confirman cardinalidad empresarial.",
    "5.5": "Esquemas relacionados por FK no equivalen a módulos ni prueban inconsistencias intermodulares.",
    "5.6": "Tablas puente probables requieren revisión del modelo funcional; no inventar tablas faltantes.",
    "5.7": "Los patrones de PK no son incumplimientos si no se proporciona una convención documentada.",
    "5.8": "Diferencias de tipo exacto entre FK no demuestran incompatibilidad o fallo de integridad por sí solas.",
}

# Los hechos describen comprobaciones existentes; no añaden umbrales de negocio.
OBSERVATIONS = {
    "total_tablas": "Tablas incluidas en esta evidencia.",
    "total_indeterminadas": "Tablas cuya clasificación técnica quedó indeterminada.",
    "elementos_duplicados_exactos": "Grupos de índices con coincidencia estructural; requieren revisión de carga y restricciones.",
    "elementos_posibles_redundancias_prefijo": "Candidatos por prefijo; no son eliminaciones confirmadas.",
    "elementos_fk_sin_indice_prefijo": "FK sin índice válido con prefijo observado; no son índices recomendados confirmados.",
    "elementos_campos_candidatos": "Campos candidatos por indicios; la clasificación funcional no está confirmada.",
    "total_fk_con_diferencias": "FK con diferencias de tipo exacto; no implica incompatibilidad confirmada.",
    "campos_obligatorios": "Campos con obligatoriedad técnica declarada.",
    "campos_opcionales": "Campos que permiten nulos técnicamente.",
    "tablas_sin_permiso_lectura": "Tablas inventariadas sin permiso SELECT para el rol conectado.",
    "esquemas_sin_permiso_uso": "Esquemas inventariados sin permiso USAGE para el rol conectado.",
    "campos_fuera_patron_snake_case": "Campos fuera del patrón técnico observado; no demuestra incumplimiento normativo.",
}


def _technical_findings(data: dict, summary: dict) -> list[dict]:
    schemas = data.get("esquemas")
    if isinstance(schemas, list):
        schemas = [item for item in schemas if isinstance(item, dict)]
        schema_flags = [item.get("permiso_uso") for item in schemas if type(item.get("permiso_uso")) is bool]
        if schema_flags:
            summary["esquemas_sin_permiso_uso"] = schema_flags.count(False)
        table_flags = [
            table["permiso_lectura"] for schema in schemas
            for table in (schema.get("tablas") if isinstance(schema.get("tablas"), list) else [])
            if isinstance(table, dict) and type(table.get("permiso_lectura")) is bool
        ]
        if table_flags:
            summary["tablas_sin_permiso_lectura"] = table_flags.count(False)
    total = summary.get("total_campos")
    matching = summary.get("total_snake_case_minusculas")
    if type(total) is int and type(matching) is int and 0 <= matching <= total:
        summary["campos_fuera_patron_snake_case"] = total - matching
    return [
        {"codigo": name, "descripcion": description, "valor": summary[name]}
        for name, description in OBSERVATIONS.items() if name in summary
    ]
GROUP_CRITERIA = {
    "2": "Un inventario no confirma función empresarial. Una instantánea no mide crecimiento; "
         "contadores sin ventana representativa no confirman obsolescencia. Esquema no equivale a módulo.",
    "3": "Los metadatos describen estructura, no validez de registros ni reglas empresariales. "
         "Los nombres no confirman datos sensibles o deprecación. No hay convención normativa aprobada.",
    "4": "Los candidatos no justifican crear o borrar índices. Se requieren carga y planes revisados. "
         "Las estadísticas no miden fragmentación exacta ni frecuencia histórica de consultas.",
    "5": "Las FK y los indicios estructurales no prueban cardinalidad empresarial o normalización. "
         "No se presupone una convención normativa aprobada. La recomendación requiere validación funcional.",
}


SAFE_TECHNICAL_VALUES = frozenset({
    "version", "version_numero", "codificacion", "zona_horaria", "en_recuperacion",
    "transaccion_solo_lectura", "tls_sesion_actual", "protocolo", "cifrado", "bits",
    "segmentos_archivados", "fallos_archivado", "reinicio_estadisticas", "ultimo_archivado", "ultimo_fallo",
    "replay_pausado", "ultima_transaccion_reproducida", "todas_estadisticas_visibles",
    "triggers_no_activos_en_origen", "validada", "triggers_internos", "diferible",
    "parametro", "valor", "unidad", "reinicio_pendiente", "bloques_leidos", "bloques_cache",
    "origen", "contexto", "extension_pg_stat_statements_instalada", "track_activities", "track_counts",
    "activo", "tipo", "disponibilidad_wal", "estado", "habilitada", "todas_las_tablas",
    "replica_inserciones", "replica_actualizaciones", "replica_eliminaciones", "replica_truncamientos",
})
SAFE_PARAMETERS = frozenset({
    "ssl", "ssl_min_protocol_version", "ssl_max_protocol_version", "password_encryption", "row_security",
    "logging_collector", "log_statement", "log_connections", "log_disconnections", "log_min_duration_statement",
    "log_checkpoints", "log_lock_waits", "fsync", "full_page_writes", "synchronous_commit",
    "default_transaction_isolation", "wal_level", "archive_mode", "archive_timeout", "wal_compression",
    "max_wal_size", "min_wal_size", "wal_keep_size", "max_replication_slots", "max_wal_senders",
    "hot_standby", "archive_command", "archive_library", "restore_command",
    "deadlock_timeout", "effective_cache_size", "effective_io_concurrency", "idle_in_transaction_session_timeout",
    "lock_timeout", "maintenance_work_mem", "max_connections", "random_page_cost", "shared_buffers",
    "statement_timeout", "temp_buffers", "wal_buffers", "work_mem",
    "pgaudit.log", "pgaudit.log_relation", "pgaudit.log_parameter", "pgaudit.log_statement_once", "log_duration",
})


def safe_technical_rows(data):
    """Solo configuraciones revisadas y contadores; excluye nombres, SQL, ACL y valores de negocio."""
    rows = data.get("filas", [])
    if not isinstance(rows, list):
        return []
    safe = []
    for row in rows[:100]:
        if not isinstance(row, dict):
            continue
        if "parametro" in row and row["parametro"] not in SAFE_PARAMETERS:
            continue
        item = {}
        for key, value in row.items():
            if key not in SAFE_TECHNICAL_VALUES:
                continue
            if type(value) in {int, float, bool} or value is None:
                item[key] = value
            elif isinstance(value, str) and len(value) <= 80 and all(c.isalnum() or c in " ._:+-/" for c in value):
                item[key] = value
            elif hasattr(value, "isoformat"):
                item[key] = value.isoformat()
        if item:
            safe.append(item)
    return safe


def extended_findings(query_id, data):
    """Hallazgos agregados calculados antes de IA; nunca devuelve identidades de objetos."""
    if query_id == 'migration_history':
        records=data.get('registros',[])
        if not isinstance(records,list):
            return {}
        return {'registros_historial_obtenidos':len(records), 'truncada':data.get('truncada') is True,
                'registros_con_fallo_explicito':sum(r.get('success') is False or r.get('exectype')=='FAILED' for r in records),
                'migraciones_revertidas_prisma':sum(r.get('rolled_back_at') is not None for r in records),
                'migraciones_prisma_sin_finalizacion':sum('finished_at' in r and r['finished_at'] is None and r.get('rolled_back_at') is None for r in records),
                'historial_sin_estado_explicito':not any('success' in r or 'exectype' in r or 'finished_at' in r for r in records)}
    if query_id == 'statements_metrics':
        rows=data.get('consultas',[])
        return {'consultas_con_metricas':len(rows), 'llamadas_observadas':sum(r.get('calls',0) for r in rows),
                'tiempo_ejecucion_ms_observado':sum(r.get('total_exec_time',0) for r in rows)}
    if query_id == 'consolidacion_tecnica_v1':
        findings=data.get('hallazgos',[])
        result={'hallazgos_tecnicos_provisionales':len(findings)}
        for code in ('fk_no_validada','triggers_fk_no_activos','indice_no_valido','indice_no_preparado','proteccion_durabilidad_deshabilitada','ssl_servidor_deshabilitado','sesion_sin_tls','archivado_wal_deshabilitado','rol_administrativo_para_revision','vista_materializada_no_poblada'):
            result[code]=sum(r.get('codigo')==code for r in findings)
        for key in ('total_objetos','medicion_disponible','hit_ratio_porcentaje','bloques_cache','bloques_leidos','tablas_versionadoras_detectadas'):
            if type(data.get(key)) in {int,float,bool}:
                result[key]=data[key]
        return result
    if query_id == "fk_orphan_count_template":
        return {key: data[key] for key in ("total_fk_obtenidas", "comprobaciones_completadas", "total_huerfanos_en_comprobaciones_completadas") if type(data.get(key)) is int}
    if query_id not in SAFE_QUERY_IDS:
        return {}
    rows = data.get("filas", [])
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return {}
    result = {"filas_tecnicas_obtenidas": len(rows), "truncada": data.get("truncada") is True}
    fields = {
        "roles": ("superusuario", "crea_roles", "crea_bd", "omite_rls", "permite_login"),
        "memberships": ("administra",),
        "access_controls": ("rls", "fuerza_rls"),
    }
    for field in fields.get(query_id, ()):
        result[f"total_{field}"] = sum(row.get(field) is True for row in rows)
    if query_id == "referential_control":
        result["fk_no_validadas"] = sum(row.get("validada") is False for row in rows)
        result["fk_con_triggers_no_activos_en_origen"] = sum(type(row.get("triggers_no_activos_en_origen")) is int and row["triggers_no_activos_en_origen"] > 0 for row in rows)
    if query_id in {"privileges", "column_privileges", "default_privileges"}:
        result["permisos_declarados_public"] = sum(row.get("beneficiario") == "PUBLIC" for row in rows)
    if query_id == "extensions":
        for name in ("pg_stat_statements", "pgaudit", "anon"):
            result[f"extension_{name}_registrada"] = any(row.get("extension") == name for row in rows)
    if query_id == "column_dictionary":
        result["campos_obligatorios"] = sum(row.get("obligatorio") is True for row in rows)
        result["campos_opcionales"] = sum(row.get("obligatorio") is False for row in rows)
        result["campos_con_default"] = sum(row.get("valor_predeterminado") is not None for row in rows)
        result["campos_generados"] = sum(row.get("generado") in ("s", "v") for row in rows)
        result["campos_identidad"] = sum(row.get("identidad") in ("a", "d") for row in rows)
    if query_id == "table_constraints":
        for code, name in (("p", "pk"), ("f", "fk"), ("u", "unique"), ("c", "check"), ("x", "exclusion"), ("n", "not_null")):
            result[f"restricciones_{name}"] = sum(row.get("tipo") == code for row in rows)
    if query_id == "index_inventory":
        result["indices_no_validos"] = sum(row.get("es_valido") is False for row in rows)
        result["indices_no_preparados"] = sum(row.get("preparado") is False for row in rows)
        result["indices_unicos"] = sum(row.get("es_unico") is True for row in rows)
    if query_id == "table_volumetry":
        result["datos_bytes_obtenidos"] = sum(row['datos_bytes'] for row in rows if type(row.get('datos_bytes')) is int)
        result["indices_bytes_obtenidos"] = sum(row['indices_bytes'] for row in rows if type(row.get('indices_bytes')) is int)
        result["volumetria_con_estadistica_ausente"] = sum(row.get('filas_estimadas') is None for row in rows)
    return result


def build_activity_context(activity: ActivityResult) -> dict | None:
    identifier = activity.identificador
    if identifier not in CATALOG or activity.estado_ejecucion not in {"completada", "parcial"}:
        return None
    if not activity.evidencias:
        return None
    evidence = []
    for index, item in enumerate(activity.evidencias):
        summary = {}
        findings = []
        coverage = None
        if isinstance(item.datos, dict):
            for name in sorted(SCALAR_FIELDS):
                value = item.datos.get(name)
                if type(value) in {int, bool} and 0 <= value <= 10**30:
                    summary[name] = value
            for name in sorted(LIST_FIELDS):
                value = item.datos.get(name)
                if isinstance(value, list):
                    summary[f"elementos_{name}"] = len(value)
            findings = _technical_findings(item.datos, summary)
            summary.update(extended_findings(item.consulta_id, item.datos))
            value = item.datos.get("cobertura_entregable")
            if isinstance(value, str) and value in {"parcial", "completa", "completa_metadatos_disponibles"}:
                coverage = value
        evidence.append({
            "referencia": index + 1,
            "disponibilidad": item.disponibilidad,
            "naturaleza": item.naturaleza,
            "agregados": summary,
            "hallazgos": findings,
            "cobertura_entregable": coverage,
            "resultados_tecnicos": safe_technical_rows(item.datos) if isinstance(item.datos, dict) and item.consulta_id in SAFE_QUERY_IDS else [],
        })
    context = {
        "id": identifier, "tema": TOPICS.get(identifier, CATALOG[identifier]["actividad"]),
        "estado_sql": activity.estado_ejecucion, "estado_evidencia": activity.estado_evidencia,
        "criterios": GROUP_CRITERIA.get(identifier.split(".")[0], GENERAL_CRITERIA) + " " + ACTIVITY_CRITERIA.get(identifier, EXTERNAL_REQUIREMENTS.get(identifier, "Describir únicamente controles y metadatos declarados, sin afirmar cumplimiento.")),
        "cobertura": activity.grado_automatizacion,
        "estado_entregable": activity.estado_entregable,
        "informacion_externa_necesaria": EXTERNAL_REQUIREMENTS.get(identifier),
        "consultas_no_completadas": [q["consulta_id"] for q in activity.consultas if q["estado"] != "completada" and q["consulta_id"] in SAFE_QUERY_IDS],
        "evidencias": evidence,
    }
    if definition_matches(activity):
        context.update({"numero_original": activity.numero_original, "nombre_original": CATALOG[identifier]["actividad"],
                        "entregable_esperado": CATALOG[identifier]["entregable_esperado"]})
    if identifier in TECHNICAL_CATALOG and matches(activity, TECHNICAL_CATALOG[identifier]):
        from app.audit_technical import SCOPE_NOTES
        context.update({'tema':TECHNICAL_CATALOG[identifier]['actividad'], 'nombre_original':TECHNICAL_CATALOG[identifier]['actividad'],
            'numero_original':identifier,'entregable_esperado':TECHNICAL_CATALOG[identifier]['entregable_esperado'],
            'checklist_version':TECHNICAL_VERSION,'criterio_evaluacion':TECHNICAL_CRITERIA,
            'criterios':GENERAL_CRITERIA+' Evalúa el alcance técnico OBSERVABLE descrito en el entregable. Un mecanismo deshabilitado, ausente o una configuración deficiente es un resultado válido, no impide completar la evaluación. No exijas fuentes fuera de este alcance. '+SCOPE_NOTES.get(identifier,''),
            'informacion_externa_necesaria':None})
    if identifier in {"8.3", "8.4"}:
        context["criterios"] += " WAL no prueba copias utilizables. Archivado no prueba PITR operativo. No inferir ausencia de backups externos. No inventar RPO/RTO. Recomendar evaluar alternativas y pruebas autorizadas, sin afirmar que pgBackRest o AES-256 están implementados ni imponerlos como única solución."
    return context
