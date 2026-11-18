"""Evidencias adicionales del alcance técnico v1. Solo SELECT revisados."""

INSTANCE_IDENTITY_SQL = """
 SELECT version() AS identificacion_compilacion,current_database() AS base_datos,
        current_setting('server_version') AS version,current_setting('server_version_num')::int AS version_numero,
        current_setting('server_encoding') AS codificacion,current_setting('TimeZone') AS zona_horaria,
        pg_is_in_recovery() AS en_recuperacion,current_setting('transaction_read_only')::boolean AS solo_lectura,
        clock_timestamp() AS captura
"""
SSL_SETTINGS_SQL = """
 SELECT name AS parametro,setting AS valor,source AS origen,pending_restart AS reinicio_pendiente
 FROM pg_catalog.pg_settings WHERE name IN ('ssl','ssl_min_protocol_version','ssl_max_protocol_version')
 ORDER BY name
"""
SCHEMA_OBJECTS_SQL = """
 SELECT n.nspname AS esquema,pg_get_userbyid(n.nspowner) AS propietario,
        has_schema_privilege(n.oid,'USAGE') AS permiso_uso,
        (SELECT count(*) FROM pg_catalog.pg_class c WHERE c.relnamespace=n.oid AND c.relkind IN ('r','p','f')) AS tablas,
        (SELECT count(*) FROM pg_catalog.pg_class c WHERE c.relnamespace=n.oid AND c.relkind='v') AS vistas,
        (SELECT count(*) FROM pg_catalog.pg_class c WHERE c.relnamespace=n.oid AND c.relkind='m') AS vistas_materializadas,
        (SELECT count(*) FROM pg_catalog.pg_class c WHERE c.relnamespace=n.oid AND c.relkind IN ('i','I')) AS indices,
        (SELECT count(*) FROM pg_catalog.pg_proc p WHERE p.pronamespace=n.oid) AS rutinas
 FROM pg_catalog.pg_namespace n WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' ORDER BY n.nspname
"""
FDW_INVENTORY_SQL = """
 SELECT w.fdwname AS wrapper,pg_get_userbyid(w.fdwowner) AS propietario,
        count(f.oid) AS servidores
 FROM pg_catalog.pg_foreign_data_wrapper w LEFT JOIN pg_catalog.pg_foreign_server f ON f.srvfdw=w.oid
 GROUP BY w.oid ORDER BY w.fdwname
"""
COLUMN_REVIEW_SQL = """
 SELECT n.nspname AS esquema,c.relname AS tabla,a.attname AS campo,a.attnum AS orden,
        pg_catalog.format_type(a.atttypid,a.atttypmod) AS tipo,
        nullif(pg_catalog.col_description(c.oid,a.attnum),'') IS NOT NULL AS tiene_comentario,
        (SELECT count(*) FROM pg_catalog.pg_depend d WHERE d.refclassid='pg_catalog.pg_class'::regclass
            AND d.refobjid=c.oid AND d.refobjsubid=a.attnum) AS dependencias_declaradas
 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
 WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' AND c.relkind IN ('r','p','f')
   AND a.attnum>0 AND NOT a.attisdropped ORDER BY n.nspname,c.relname,a.attnum
"""
OBJECT_NAMES_SQL = """
 SELECT n.nspname AS esquema,c.relname AS objeto,c.relkind::text AS tipo
 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema'
 UNION ALL
 SELECT n.nspname,p.proname,'rutina' FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
 WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' ORDER BY esquema,objeto,tipo
"""
SESSION_INDICATORS_SQL = """
 SELECT state AS estado,wait_event_type AS espera,count(*) AS sesiones
 FROM pg_catalog.pg_stat_activity WHERE datname=current_database()
 GROUP BY state,wait_event_type ORDER BY state,wait_event_type
"""
DATABASE_IO_SQL = """
 SELECT blks_read AS bloques_leidos,blks_hit AS bloques_cache,blk_read_time AS lectura_ms,
        blk_write_time AS escritura_ms,temp_files AS archivos_temporales,temp_bytes AS bytes_temporales,
        deadlocks,stats_reset AS reinicio_estadisticas,current_setting('track_io_timing')::boolean AS mide_tiempos_io
 FROM pg_catalog.pg_stat_database WHERE datname=current_database()
"""
MATERIALIZED_VIEWS_SQL = """
 SELECT n.nspname AS esquema,c.relname AS vista,c.relispopulated AS poblada,
        has_table_privilege(c.oid,'SELECT') AS permiso_lectura,pg_relation_size(c.oid) AS bytes,
        (SELECT count(*) FROM pg_catalog.pg_index i WHERE i.indrelid=c.oid) AS indices
 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE c.relkind='m' AND n.nspname !~ '^pg_' AND n.nspname<>'information_schema' ORDER BY n.nspname,c.relname
"""
ROUTINE_PROPERTIES_SQL = """
 SELECT n.nspname AS esquema,p.proname AS rutina,p.prokind::text AS tipo,l.lanname AS lenguaje,
        p.prosecdef AS security_definer,p.provolatile::text AS volatilidad,p.proparallel::text AS paralelismo,
        p.procost AS coste_estimado,p.prorows AS filas_estimadas,p.proisstrict AS estricta
 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
 JOIN pg_catalog.pg_language l ON l.oid=p.prolang
 WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' AND p.prokind IN ('f','p','w')
 ORDER BY n.nspname,p.proname,p.oid
"""
MIGRATION_COLUMNS_SQL = """
 SELECT n.nspname AS esquema,c.relname AS tabla,a.attname AS columna,
        has_table_privilege(c.oid,'SELECT') AS permiso_lectura,row_security_active(c.oid) AS rls_activo
 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
 WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' AND c.relkind IN ('r','p')
 AND c.relname IN ('alembic_version','django_migrations','flyway_schema_history','databasechangelog',
                 '_prisma_migrations','schema_migrations','knex_migrations','SequelizeMeta')
 AND a.attnum>0 AND NOT a.attisdropped ORDER BY n.nspname,c.relname,a.attnum
"""
STATEMENTS_CAPABILITY_SQL = """
 SELECT n.nspname AS esquema,c.relname AS vista,
        c.oid IS NOT NULL AS vista_instalada,
        coalesce(has_table_privilege(c.oid,'SELECT'),false) AS permiso_lectura,
        coalesce((SELECT array_agg(a.attname::text ORDER BY a.attnum) FROM pg_catalog.pg_attribute a
                  WHERE a.attrelid=c.oid AND a.attnum>0 AND NOT a.attisdropped),ARRAY[]::text[]) AS columnas,
        CASE WHEN e.oid IS NULL THEN false ELSE
            (SELECT setting LIKE '%pg_stat_statements%' FROM pg_catalog.pg_settings WHERE name='shared_preload_libraries')
        END AS precargada
 FROM (SELECT 1) seed LEFT JOIN pg_catalog.pg_extension e ON e.extname='pg_stat_statements'
 LEFT JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace
 LEFT JOIN pg_catalog.pg_class c ON c.relnamespace=n.oid AND c.relname='pg_stat_statements' AND c.relkind='v'
"""
POLICY_METADATA_SQL = """
 SELECT n.nspname AS esquema,c.relname AS tabla,p.polname AS politica,p.polcmd::text AS comando,
        p.polpermissive AS permisiva,cardinality(p.polroles) AS cantidad_roles,
        p.polqual IS NOT NULL AS condicion_lectura,p.polwithcheck IS NOT NULL AS condicion_escritura
 FROM pg_catalog.pg_policy p JOIN pg_catalog.pg_class c ON c.oid=p.polrelid
 JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname !~ '^pg_' AND n.nspname<>'information_schema' ORDER BY n.nspname,c.relname,p.polname
"""
