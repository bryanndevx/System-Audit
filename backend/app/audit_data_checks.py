"""Conteos agregados con plantilla revisada e identificadores de pg_catalog.

No retorna filas de negocio. Omite tipos personalizados, FDW y RLS activo.
No acepta SQL del cliente ni del modelo. Máximo diez FK y seis segundos por conteo.
"""

import asyncio
import time

import psycopg
from psycopg import sql

from app.audit_extended_queries import FK_DATA_CHECK_DEFINITIONS_SQL
from app.external_connections import SET_TRANSACTION_READ_ONLY_SQL

MAX_FK_DATA_CHECKS = 10
ORPHAN_COUNT_TEMPLATE = sql.SQL("""
 SELECT count(*) FILTER (WHERE {nonnull} AND NOT EXISTS (
     SELECT 1 FROM {target} AS p WHERE {matches})) AS registros_huerfanos,
        count(*) FILTER (WHERE {mixed}) AS nulos_parciales_match_full
 FROM {source} AS c
""")


def orphan_statement(definition):
    # Nombres proceden exclusivamente del catálogo; Identifier también escapa comillas.
    _, source_schema, source_table, target_schema, target_table, source_columns, target_columns, *_ = definition
    nonnull = sql.SQL(' AND ').join(sql.SQL('c.{} IS NOT NULL').format(sql.Identifier(col)) for col in source_columns)
    any_nonnull = sql.SQL(' OR ').join(sql.SQL('c.{} IS NOT NULL').format(sql.Identifier(col)) for col in source_columns)
    matches = sql.SQL(' AND ').join(sql.SQL('c.{} OPERATOR(pg_catalog.=) p.{}').format(sql.Identifier(a), sql.Identifier(b)) for a, b in zip(source_columns, target_columns))
    mixed = sql.SQL('({}) AND NOT ({})').format(any_nonnull, nonnull) if definition[-1] == 'f' else sql.SQL('FALSE')
    return ORPHAN_COUNT_TEMPLATE.format(nonnull=nonnull, target=sql.Identifier(target_schema, target_table),
                                       source=sql.Identifier(source_schema, source_table), matches=matches, mixed=mixed)


async def collect_fk_data_counts(connection):
    from app.audit_engine import ActivityEvidence, _fetch_rows, _query_trace
    definitions = await _fetch_rows(connection, FK_DATA_CHECK_DEFINITIONS_SQL)
    checks = []
    attempted = 0
    for definition in definitions.rows or []:
        name, source_schema, source_table, target_schema, target_table, source_cols, target_cols, builtin, permitted, rls, match = definition
        item = {"restriccion": name, "tabla_origen": f"{source_schema}.{source_table}", "tabla_destino": f"{target_schema}.{target_table}",
                "registros_huerfanos": None, "nulos_parciales_match_full": None, "estado": "no_evaluada"}
        reason = ('tipo_personalizado_no_admitido' if not builtin else 'permisos_insuficientes' if not permitted else
                  'visibilidad_rls_no_completa' if rls else 'limite_de_comprobaciones' if attempted >= MAX_FK_DATA_CHECKS else None)
        if reason:
            item['motivo'] = reason
            checks.append(item)
            continue
        attempted += 1
        started = time.perf_counter()
        try:
            async with asyncio.timeout(6):
                async with connection.cursor() as cursor:
                    await cursor.execute(SET_TRANSACTION_READ_ONLY_SQL)
                    await cursor.execute(orphan_statement(definition))
                    row = await cursor.fetchone()
                    item.update(registros_huerfanos=int(row[0]), nulos_parciales_match_full=int(row[1]), estado='completada')
        except (TimeoutError, psycopg.errors.QueryCanceled):
            item.update(estado='timeout')
        except psycopg.errors.InsufficientPrivilege:
            item.update(estado='permisos')
        except psycopg.Error:
            item.update(estado='ejecucion')
        finally:
            await connection.rollback()
        trace = _query_trace.get()
        if trace is not None:
            trace.append({"consulta_id": "fk_orphan_count_template", "estado": item['estado'], "filas": int(item['estado'] == 'completada'),
                          "reutilizada": False, "duracion_ms": round((time.perf_counter()-started)*1000)})
        checks.append(item)
    return ActivityEvidence(clave='conteos_agregados_fk', consulta_id='fk_orphan_count_template',
        disponibilidad='no_disponible' if definitions.rows is None else 'disponible' if checks else 'sin_datos',
        naturaleza='calculada', datos={'comprobaciones': checks, 'total_fk_obtenidas': len(definitions.rows or []),
            'comprobaciones_completadas': sum(c['estado']=='completada' for c in checks),
            'total_huerfanos_en_comprobaciones_completadas': sum(c['registros_huerfanos'] or 0 for c in checks),
            'alcance': 'solo_fk_declaradas_y_filas_visibles_no_demuestra_ausencia_de_duplicados_de_negocio'})
