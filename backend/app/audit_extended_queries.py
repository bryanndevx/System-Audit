"""SELECT revisados para arquitectura, integridad y controles. Sin valores de negocio."""

SERVER_FACTS_SQL = """
 SELECT current_database() AS base_datos, current_setting('server_version') AS version,
        current_setting('server_version_num')::int AS version_numero,
        current_setting('server_encoding') AS codificacion,
        current_setting('TimeZone') AS zona_horaria,
        pg_is_in_recovery() AS en_recuperacion,
        current_setting('transaction_read_only')::boolean AS transaccion_solo_lectura
"""
PUBLICATIONS_SQL = """
 SELECT pubname AS publicacion,puballtables AS todas_las_tablas,
        pubinsert AS replica_inserciones,pubupdate AS replica_actualizaciones,
        pubdelete AS replica_eliminaciones,pubtruncate AS replica_truncamientos
 FROM pg_catalog.pg_publication ORDER BY pubname
"""
SUBSCRIPTIONS_METADATA_SQL = """
 SELECT subname AS suscripcion,subenabled AS habilitada,subpublications AS publicaciones
 FROM pg_catalog.pg_subscription
 WHERE subdbid=(SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database())
 ORDER BY subname
"""
REPLICATION_SLOTS_SQL = """
 SELECT slot_name AS slot,slot_type AS tipo,active AS activo,
        restart_lsn::text AS wal_requerido_desde,confirmed_flush_lsn::text AS wal_confirmado,
        wal_status AS disponibilidad_wal
 FROM pg_catalog.pg_replication_slots
 WHERE database IS NULL OR database=current_database() ORDER BY slot_name
"""
WAL_RECEIVER_SQL = """
 SELECT status AS estado,last_msg_send_time AS ultimo_mensaje_enviado,
        last_msg_receipt_time AS ultimo_mensaje_recibido,latest_end_time AS ultima_posicion_reportada_fecha
 FROM pg_catalog.pg_stat_wal_receiver ORDER BY pid
"""
AUDIT_LOG_SETTINGS_SQL = """
 SELECT name AS parametro,setting AS valor,context AS contexto,source AS origen
 FROM pg_catalog.pg_settings WHERE name IN
 ('pgaudit.log','pgaudit.log_relation','pgaudit.log_parameter','pgaudit.log_statement_once',
  'log_statement','log_duration','log_min_duration_statement','logging_collector') ORDER BY name
"""

EXTENSIONS_SQL = """
 SELECT e.extname AS extension, e.extversion AS version, n.nspname AS esquema
 FROM pg_catalog.pg_extension e JOIN pg_catalog.pg_namespace n ON n.oid=e.extnamespace
 ORDER BY e.extname
"""
FOREIGN_SERVERS_SQL = """
 SELECT f.srvname AS servidor, w.fdwname AS wrapper, f.srvtype AS tipo,
        f.srvversion AS version, count(t.ftrelid)::int AS tablas_externas
 FROM pg_catalog.pg_foreign_server f
 JOIN pg_catalog.pg_foreign_data_wrapper w ON w.oid=f.srvfdw
 LEFT JOIN pg_catalog.pg_foreign_table t ON t.ftserver=f.oid
 GROUP BY f.oid,w.fdwname ORDER BY f.srvname
"""
MIGRATION_CANDIDATES_SQL = """
 SELECT n.nspname AS esquema,c.relname AS tabla,
        'candidata_por_nombre_no_historial_verificado'::text AS alcance
 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 WHERE n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
   AND c.relkind IN ('r','p') AND lower(c.relname) IN
       ('alembic_version','django_migrations','flyway_schema_history','databasechangelog',
        '_prisma_migrations','schema_migrations','knex_migrations','sequelizemeta')
 ORDER BY n.nspname,c.relname
"""
REFERENTIAL_CONTROL_SQL = """
 SELECT n.nspname AS esquema,c.relname AS tabla,k.conname AS restriccion,
        k.convalidated AS validada,k.condeferrable AS diferible,
        k.condeferred AS inicialmente_diferida,
        count(t.oid)::int AS triggers_internos,
        count(t.oid) FILTER (WHERE t.tgenabled NOT IN ('O','A'))::int AS triggers_no_activos_en_origen,
        current_setting('session_replication_role') AS rol_replicacion_sesion
 FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
 JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 LEFT JOIN pg_catalog.pg_trigger t ON t.tgconstraint=k.oid AND t.tgisinternal
 WHERE k.contype='f' AND n.nspname <> 'information_schema' AND n.nspname !~ '^pg_'
 GROUP BY n.nspname,c.relname,k.oid ORDER BY n.nspname,c.relname,k.conname
"""
ROLES_SQL = """
 SELECT rolname AS rol,rolcanlogin AS permite_login,rolsuper AS superusuario,
        rolcreatedb AS crea_bd,rolcreaterole AS crea_roles,rolreplication AS replicacion,
        rolbypassrls AS omite_rls,rolinherit AS hereda,rolconnlimit AS limite_conexiones,
        rolvaliduntil AS caducidad
 FROM pg_catalog.pg_roles ORDER BY rolname
"""
MEMBERSHIPS_SQL = """
 SELECT parent.rolname AS rol,member.rolname AS miembro,m.admin_option AS administra
 FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles parent ON parent.oid=m.roleid
 JOIN pg_catalog.pg_roles member ON member.oid=m.member ORDER BY parent.rolname,member.rolname
"""
PRIVILEGES_SQL = """
 WITH objects AS (
   SELECT 'base'::text AS tipo,d.datname::text AS objeto,d.datdba AS propietario,
          coalesce(d.datacl,acldefault('d',d.datdba)) AS acl
   FROM pg_catalog.pg_database d WHERE d.datname=current_database()
   UNION ALL
   SELECT 'esquema',n.nspname,n.nspowner,coalesce(n.nspacl,acldefault('n',n.nspowner))
   FROM pg_catalog.pg_namespace n WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
   UNION ALL
   SELECT CASE WHEN c.relkind='S' THEN 'secuencia' ELSE 'relacion' END,
          format('%I.%I',n.nspname,c.relname),c.relowner,
          coalesce(c.relacl,acldefault(CASE WHEN c.relkind='S' THEN 's'::"char" ELSE 'r'::"char" END,c.relowner))
   FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
   WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' AND c.relkind IN ('r','p','f','v','m','S')
   UNION ALL
   SELECT 'rutina',format('%I.%I(%s)',n.nspname,p.proname,pg_get_function_identity_arguments(p.oid)),
          p.proowner,coalesce(p.proacl,acldefault('f',p.proowner))
   FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
   WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
 )
 SELECT o.tipo,o.objeto,pg_get_userbyid(o.propietario) AS propietario,
        CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS beneficiario,
        a.privilege_type AS privilegio,a.is_grantable AS delegable,
        pg_get_userbyid(a.grantor) AS otorgante
 FROM objects o CROSS JOIN LATERAL aclexplode(o.acl) a
 ORDER BY o.tipo,o.objeto,beneficiario,a.privilege_type
"""
COLUMN_PRIVILEGES_SQL = """
 SELECT n.nspname AS esquema,c.relname AS tabla,col.attname AS columna,
        CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS beneficiario,
        a.privilege_type AS privilegio,a.is_grantable AS delegable
 FROM pg_catalog.pg_attribute col JOIN pg_catalog.pg_class c ON c.oid=col.attrelid
 JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 CROSS JOIN LATERAL aclexplode(col.attacl) a
 WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
   AND col.attnum>0 AND NOT col.attisdropped ORDER BY n.nspname,c.relname,col.attnum
"""
DEFAULT_PRIVILEGES_SQL = """
 SELECT pg_get_userbyid(d.defaclrole) AS propietario,n.nspname AS esquema,
        d.defaclobjtype AS tipo_objeto,
        CASE WHEN a.grantee=0 THEN 'PUBLIC' ELSE pg_get_userbyid(a.grantee) END AS beneficiario,
        a.privilege_type AS privilegio,a.is_grantable AS delegable
 FROM pg_catalog.pg_default_acl d LEFT JOIN pg_catalog.pg_namespace n ON n.oid=d.defaclnamespace
 CROSS JOIN LATERAL aclexplode(d.defaclacl) a ORDER BY propietario,n.nspname,tipo_objeto,beneficiario
"""
ACCESS_CONTROLS_SQL = """
 SELECT n.nspname AS esquema,c.relname AS tabla,c.relrowsecurity AS rls,
        c.relforcerowsecurity AS fuerza_rls,count(p.oid)::int AS politicas
 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
 LEFT JOIN pg_catalog.pg_policy p ON p.polrelid=c.oid
 WHERE n.nspname !~ '^pg_' AND n.nspname <> 'information_schema' AND c.relkind IN ('r','p')
 GROUP BY n.nspname,c.relname,c.oid ORDER BY n.nspname,c.relname
"""
SECURITY_CONFIGURATION_SQL = """
 SELECT name AS parametro,setting AS valor,unit AS unidad,pending_restart AS reinicio_pendiente
 FROM pg_catalog.pg_settings WHERE name IN
 ('ssl','ssl_min_protocol_version','ssl_max_protocol_version','password_encryption',
  'row_security','logging_collector','log_statement','log_connections','log_disconnections',
  'log_min_duration_statement','log_checkpoints','log_lock_waits',
  'fsync','full_page_writes','synchronous_commit','default_transaction_isolation')
 ORDER BY name
"""
SESSION_TLS_SQL = """
 SELECT ssl AS tls_sesion_actual,version AS protocolo,cipher AS cifrado,bits AS bits
 FROM pg_catalog.pg_stat_ssl WHERE pid=pg_backend_pid()
"""
WAL_CONFIGURATION_SQL = """
 SELECT name AS parametro,setting AS valor,unit AS unidad,pending_restart AS reinicio_pendiente
 FROM pg_catalog.pg_settings WHERE name IN
 ('wal_level','archive_mode','archive_timeout','wal_compression','max_wal_size','min_wal_size',
  'wal_keep_size','max_replication_slots','max_wal_senders','hot_standby')
 UNION ALL
 SELECT name,CASE WHEN setting='' THEN 'no_configurado' ELSE 'configurado_contenido_oculto' END,
        NULL,pending_restart FROM pg_catalog.pg_settings
 WHERE name IN ('archive_command','archive_library','restore_command')
 ORDER BY parametro
"""
ARCHIVER_SQL = """
 SELECT archived_count AS segmentos_archivados,failed_count AS fallos_archivado,
        last_archived_time AS ultimo_archivado,last_failed_time AS ultimo_fallo,
        stats_reset AS reinicio_estadisticas
 FROM pg_catalog.pg_stat_archiver
"""
RECOVERY_SQL = """
 SELECT pg_is_in_recovery() AS en_recuperacion,
        pg_last_xact_replay_timestamp() AS ultima_transaccion_reproducida,
        CASE WHEN pg_is_in_recovery() THEN pg_is_wal_replay_paused() ELSE NULL END AS replay_pausado
"""
REPLICATION_SQL = """
 SELECT state AS estado,sync_state AS sincronizacion,write_lag::text AS retraso_escritura,
        flush_lag::text AS retraso_persistencia,replay_lag::text AS retraso_reproduccion
 FROM pg_catalog.pg_stat_replication ORDER BY state,sync_state
"""
REPLICATION_VISIBILITY_SQL = """
 SELECT pg_has_role(current_user,'pg_read_all_stats','USAGE') AS todas_estadisticas_visibles,
        has_table_privilege(current_user,'pg_catalog.pg_stat_replication','SELECT') AS consulta_permitida
"""
BACKUP_PROGRESS_SQL = """
 SELECT phase AS fase,backup_total AS bytes_estimados,backup_streamed AS bytes_transmitidos,
        tablespaces_total AS tablespaces_totales,tablespaces_streamed AS tablespaces_transmitidos
 FROM pg_catalog.pg_stat_progress_basebackup ORDER BY phase
"""
DATABASE_ENVIRONMENTS_SQL = """
 SELECT datname AS base_datos,datallowconn AS permite_conexion,datistemplate AS es_plantilla
 FROM pg_catalog.pg_database ORDER BY datname
"""
CACHE_STATISTICS_SQL = """
 SELECT blks_read AS bloques_leidos,blks_hit AS bloques_cache,xact_commit AS commits,
        xact_rollback AS rollbacks,deadlocks,stats_reset AS reinicio_estadisticas
 FROM pg_catalog.pg_stat_database WHERE datname=current_database()
"""
MASKING_METADATA_SQL = """
 SELECT provider AS proveedor,count(*)::int AS etiquetas
 FROM pg_catalog.pg_seclabel GROUP BY provider ORDER BY provider
"""
FK_DATA_CHECK_DEFINITIONS_SQL = """
 SELECT k.conname AS restriccion,ns.nspname AS esquema_origen,c.relname AS tabla_origen,
        nt.nspname AS esquema_destino,p.relname AS tabla_destino,
        array_agg(ca.attname ORDER BY cols.ord) AS columnas_origen,
        array_agg(pa.attname ORDER BY cols.ord) AS columnas_destino,
        bool_and(ca.atttypid IN (16,20,21,23,25,700,701,1042,1043,1082,1114,1184,1700,2950)
                 AND pa.atttypid IN (16,20,21,23,25,700,701,1042,1043,1082,1114,1184,1700,2950)) AS tipos_integrados_admitidos,
        has_table_privilege(c.oid,'SELECT') AND has_table_privilege(p.oid,'SELECT') AS permiso_lectura,
        row_security_active(c.oid) OR row_security_active(p.oid) AS rls_activo,
        k.confmatchtype AS tipo_match
 FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
 JOIN pg_catalog.pg_namespace ns ON ns.oid=c.relnamespace
 JOIN pg_catalog.pg_class p ON p.oid=k.confrelid JOIN pg_catalog.pg_namespace nt ON nt.oid=p.relnamespace
 CROSS JOIN LATERAL unnest(k.conkey,k.confkey) WITH ORDINALITY cols(source_num,target_num,ord)
 JOIN pg_catalog.pg_attribute ca ON ca.attrelid=c.oid AND ca.attnum=cols.source_num
 JOIN pg_catalog.pg_attribute pa ON pa.attrelid=p.oid AND pa.attnum=cols.target_num
 WHERE k.contype='f' AND k.conparentid=0 AND c.relkind IN ('r','p') AND p.relkind IN ('r','p')
   AND ns.nspname !~ '^pg_' AND ns.nspname <> 'information_schema'
 GROUP BY k.oid,ns.nspname,c.relname,nt.nspname,p.relname,c.oid,p.oid
 ORDER BY ns.nspname,c.relname,k.conname
"""
