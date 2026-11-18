"""Plantillas SELECT fijas con identificadores provenientes de catálogos revisados."""

import asyncio
import time
from collections import defaultdict

import psycopg
from psycopg import sql

from app.external_connections import SET_TRANSACTION_READ_ONLY_SQL

MIGRATION_FIELDS = {
    'alembic_version': ('version_num',), 'django_migrations': ('app','name','applied'),
    'flyway_schema_history': ('installed_rank','version','type','installed_on','success'),
    'databasechangelog': ('id','dateexecuted','orderexecuted','exectype'),
    '_prisma_migrations': ('migration_name','started_at','finished_at','rolled_back_at'),
    'schema_migrations': ('version',), 'knex_migrations': ('name','migration_time'), 'SequelizeMeta': ('name',),
}
MIGRATION_TEMPLATE = sql.SQL('SELECT {columns} FROM {table} ORDER BY {columns}')
STATEMENT_FIELDS = ('queryid','calls','total_exec_time','mean_exec_time','rows','shared_blks_hit','shared_blks_read','temp_blks_written')
STATEMENTS_TEMPLATE = sql.SQL('SELECT {columns} FROM {view} WHERE dbid=(SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database()) ORDER BY total_exec_time DESC,queryid')


async def _run_template(connection, query_id, statement):
    from app.audit_engine import QueryOutcome, MAX_QUERY_ROWS, _query_cache, _query_trace
    if query_id not in {'migration_history', 'statements_metrics'}:
        raise ValueError('Plantilla no revisada.')
    cache, trace = _query_cache.get(), _query_trace.get()
    key = (query_id, statement.as_string())
    cached = cache is not None and key in cache
    started=time.perf_counter()
    if cached:
        outcome=cache[key]
    else:
        rows=None
        columns=()
        error=None
        try:
            async with asyncio.timeout(6):
                async with connection.cursor() as cursor:
                    await cursor.execute(SET_TRANSACTION_READ_ONLY_SQL)
                    await cursor.execute(statement)
                    columns=tuple(c.name for c in cursor.description)
                    rows=list(await cursor.fetchmany(MAX_QUERY_ROWS+1))
                    if len(rows)>MAX_QUERY_ROWS:
                        rows=rows[:MAX_QUERY_ROWS]
                        error='limite'
        except (TimeoutError,psycopg.errors.QueryCanceled):
            error='timeout'
        except psycopg.errors.InsufficientPrivilege:
            error='permisos'
        except psycopg.Error:
            error='ejecucion'
        finally:
            await connection.rollback()
        outcome=QueryOutcome(rows,error,columns)
        if cache is not None:
            cache[key]=outcome
    if trace is not None:
        trace.append({'consulta_id':query_id,'estado':outcome.error or 'completada','filas':len(outcome.rows or []),
                      'reutilizada':cached,'duracion_ms':round((time.perf_counter()-started)*1000)})
    return outcome


async def migration_history(connection, metadata_rows):
    from app.audit_engine import ActivityEvidence
    tables=defaultdict(dict)
    for row in metadata_rows:
        tables[(row['esquema'],row['tabla'])][row['columna']]=row
    evidence=[]
    missing=[]
    if len(tables)>20:
        missing.append('Se detectaron más de veinte tablas de migración; se limita la lectura y el entregable queda incompleto.')
    for (schema,table),columns in list(tables.items())[:20]:
        expected=MIGRATION_FIELDS[table]
        selected=[c for c in expected if c in columns]
        if any(not r['permiso_lectura'] or r['rls_activo'] for r in columns.values()):
            missing.append(f'Permisos o visibilidad RLS insuficientes para el historial {schema}.{table}.')
            continue
        if len(selected)!=len(expected):
            missing.append(f'Historial {schema}.{table}: faltan columnas estándar; requiere una referencia o exportación técnica autorizada.')
            continue
        statement=MIGRATION_TEMPLATE.format(columns=sql.SQL(',').join(map(sql.Identifier,selected)),table=sql.Identifier(schema,table))
        outcome=await _run_template(connection,'migration_history',statement)
        if outcome.error:
            missing.append(f'Historial {schema}.{table}: no se obtuvo completo ({outcome.error}).')
        evidence.append(ActivityEvidence(clave='historial_migraciones',consulta_id='migration_history',
            disponibilidad='no_disponible' if outcome.rows is None else 'disponible' if outcome.rows else 'sin_datos',
            naturaleza='exacta' if outcome.rows is not None else 'no_disponible',
            datos={'esquema':schema,'tabla':table,'versionador':table,'registros':[dict(zip(outcome.columns,row)) for row in outcome.rows or []],
                   'truncada':outcome.error=='limite','alcance':'revisiones_actuales_no_historial_completo' if table=='alembic_version' else 'solo_metadatos_de_versionado_no_cuerpos_SQL_ni_logs'}))
    return evidence,missing


async def statements_metrics(connection, capability):
    from app.audit_engine import ActivityEvidence
    if not capability.get('vista_instalada'):
        return [],[]  # Ausencia observada: no es necesario instalar el control para evaluarlo.
    if not capability.get('permiso_lectura'):
        return [],['Permisos insuficientes para las estadísticas de pg_stat_statements.']
    if capability.get('precargada') is None:
        return [],['Permisos insuficientes para confirmar la configuración de precarga de pg_stat_statements.']
    if capability.get('precargada') is not True:
        return [ActivityEvidence(clave='disponibilidad_estadisticas',consulta_id='statements_capability',disponibilidad='disponible',naturaleza='exacta',
            datos={'operatividad_confirmada':False,'motivo':'Precarga no confirmada; no se ejecuta la vista dependiente de memoria compartida.'})],[]
    columns=capability.get('columnas',[])
    if not all(c in columns for c in (*STATEMENT_FIELDS,'dbid')):
        return [],['Versión de pg_stat_statements sin las columnas revisadas; se requiere una exportación técnica compatible.']
    statement=STATEMENTS_TEMPLATE.format(columns=sql.SQL(',').join(map(sql.Identifier,STATEMENT_FIELDS)),view=sql.Identifier(capability['esquema'],capability['vista']))
    outcome=await _run_template(connection,'statements_metrics',statement)
    item=ActivityEvidence(clave='metricas_consultas',consulta_id='statements_metrics',
        disponibilidad='no_disponible' if outcome.rows is None else 'disponible' if outcome.rows else 'sin_datos',
        naturaleza='exacta' if outcome.rows is not None else 'no_disponible',
        datos={'consultas':[dict(zip(outcome.columns,row)) for row in outcome.rows or []],
               'truncada':outcome.error=='limite','incluye_texto_sql':False})
    return [item],([f'No se obtuvieron completas las estadísticas de consultas ({outcome.error}).'] if outcome.error else [])
