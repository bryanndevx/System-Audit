USER_SCHEMAS_SQL = """
    SELECT namespace.oid::bigint,
           namespace.nspname,
           pg_catalog.has_schema_privilege(namespace.oid, 'USAGE')
      FROM pg_catalog.pg_namespace AS namespace
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
     ORDER BY namespace.nspname
"""

TABLE_INVENTORY_SQL = """
    SELECT relation.oid::bigint,
           namespace.nspname,
           relation.relname,
           pg_catalog.format('%I.%I', namespace.nspname, relation.relname),
           relation.relkind,
           relation.relispartition,
           CASE
               WHEN parent_relation.oid IS NULL THEN NULL
               ELSE pg_catalog.format(
                   '%I.%I',
                   parent_namespace.nspname,
                   parent_relation.relname
               )
           END,
           pg_catalog.has_schema_privilege(namespace.oid, 'USAGE'),
           pg_catalog.has_table_privilege(relation.oid, 'SELECT')
      FROM pg_catalog.pg_class AS relation
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = relation.relnamespace
 LEFT JOIN pg_catalog.pg_inherits AS inheritance
        ON inheritance.inhrelid = relation.oid
 LEFT JOIN pg_catalog.pg_class AS parent_relation
        ON parent_relation.oid = inheritance.inhparent
 LEFT JOIN pg_catalog.pg_namespace AS parent_namespace
        ON parent_namespace.oid = parent_relation.relnamespace
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
       AND relation.relkind IN ('r', 'p', 'f')
     ORDER BY namespace.nspname,
              relation.relname,
              inheritance.inhseqno
"""

DATABASE_SIZE_SQL = """
    SELECT pg_catalog.pg_database_size(pg_catalog.current_database())
"""

DATABASE_STATISTICS_CONTEXT_SQL = """
    SELECT pg_catalog.current_setting('track_counts')::boolean,
           statistics.stats_reset
      FROM pg_catalog.pg_stat_database AS statistics
     WHERE statistics.datname = pg_catalog.current_database()
"""

TABLE_VOLUMETRY_SQL = """
    SELECT relation.oid::bigint,
           namespace.nspname,
           relation.relname,
           pg_catalog.format('%I.%I', namespace.nspname, relation.relname),
           relation.relkind,
           relation.relispartition,
           inheritance.inhparent::bigint,
           CASE WHEN relation.relkind = 'f'
                THEN NULL
                ELSE pg_catalog.pg_table_size(relation.oid)
           END,
           CASE WHEN relation.relkind = 'f'
                THEN NULL
                ELSE pg_catalog.pg_indexes_size(relation.oid)
           END,
           CASE WHEN relation.relkind = 'f'
                THEN NULL
                ELSE pg_catalog.pg_total_relation_size(relation.oid)
           END,
           CASE WHEN relation.reltuples < 0 OR relation.relkind = 'f'
                THEN NULL
                ELSE pg_catalog.round(relation.reltuples)::bigint
           END,
           relation.relpages::bigint,
           table_statistics.n_live_tup,
           table_statistics.n_dead_tup,
           table_statistics.n_mod_since_analyze,
           table_statistics.last_vacuum,
           table_statistics.last_autovacuum,
           table_statistics.last_analyze,
           table_statistics.last_autoanalyze,
           pg_catalog.has_schema_privilege(namespace.oid, 'USAGE'),
           pg_catalog.has_table_privilege(relation.oid, 'SELECT')
      FROM pg_catalog.pg_class AS relation
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = relation.relnamespace
 LEFT JOIN LATERAL (
           SELECT parent_link.inhparent
             FROM pg_catalog.pg_inherits AS parent_link
            WHERE parent_link.inhrelid = relation.oid
            ORDER BY parent_link.inhseqno
            LIMIT 1
           ) AS inheritance ON TRUE
 LEFT JOIN pg_catalog.pg_stat_all_tables AS table_statistics
        ON table_statistics.relid = relation.oid
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
       AND relation.relkind IN ('r', 'p', 'f')
     ORDER BY namespace.nspname, relation.relname
"""

TABLE_COLUMNS_SQL = """
    SELECT relation.oid::bigint,
           namespace.nspname,
           relation.relname,
           pg_catalog.format('%I.%I', namespace.nspname, relation.relname),
           attribute.attnum,
           attribute.attname,
           pg_catalog.format_type(attribute.atttypid, attribute.atttypmod),
           attribute.attnotnull
      FROM pg_catalog.pg_class AS relation
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = relation.relnamespace
      JOIN pg_catalog.pg_attribute AS attribute
        ON attribute.attrelid = relation.oid
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
       AND relation.relkind IN ('r', 'p', 'f')
       AND attribute.attnum > 0
       AND NOT attribute.attisdropped
     ORDER BY namespace.nspname, relation.relname, attribute.attnum
"""

COLUMN_DICTIONARY_SQL = """
    SELECT relation.oid::bigint,
           namespace.nspname,
           relation.relname,
           pg_catalog.format('%I.%I', namespace.nspname, relation.relname),
           relation.relkind,
           attribute.attnum,
           attribute.attname,
           pg_catalog.format_type(attribute.atttypid, attribute.atttypmod),
           attribute.atttypid::bigint,
           attribute.atttypmod,
           attribute.attnotnull,
           pg_catalog.pg_get_expr(default_record.adbin, default_record.adrelid),
           attribute.attidentity,
           attribute.attgenerated,
           type_namespace.nspname,
           type_record.typname,
           type_record.typtype,
           CASE
               WHEN type_record.typtype = 'd'
               THEN pg_catalog.format_type(
                   type_record.typbasetype,
                   type_record.typtypmod
               )
               ELSE NULL
           END,
           collation_namespace.nspname,
           collation_record.collname,
           pg_catalog.col_description(relation.oid, attribute.attnum),
           attribute.attislocal,
           attribute.attinhcount,
           pg_catalog.has_schema_privilege(namespace.oid, 'USAGE'),
           pg_catalog.has_table_privilege(relation.oid, 'SELECT')
      FROM pg_catalog.pg_class AS relation
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = relation.relnamespace
      JOIN pg_catalog.pg_attribute AS attribute
        ON attribute.attrelid = relation.oid
      JOIN pg_catalog.pg_type AS type_record
        ON type_record.oid = attribute.atttypid
      JOIN pg_catalog.pg_namespace AS type_namespace
        ON type_namespace.oid = type_record.typnamespace
 LEFT JOIN pg_catalog.pg_attrdef AS default_record
        ON default_record.adrelid = relation.oid
       AND default_record.adnum = attribute.attnum
 LEFT JOIN pg_catalog.pg_collation AS collation_record
        ON collation_record.oid = attribute.attcollation
       AND attribute.attcollation <> 0
 LEFT JOIN pg_catalog.pg_namespace AS collation_namespace
        ON collation_namespace.oid = collation_record.collnamespace
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
       AND relation.relkind IN ('r', 'p', 'f')
       AND attribute.attnum > 0
       AND NOT attribute.attisdropped
     ORDER BY namespace.nspname, relation.relname, attribute.attnum
"""

COLUMN_CHECK_CONSTRAINTS_SQL = """
    SELECT constraint_record.conrelid::bigint,
           constraint_record.oid::bigint,
           constraint_record.conname,
           pg_catalog.pg_get_constraintdef(constraint_record.oid, true),
           COALESCE(
               pg_catalog.array_agg(attribute.attname ORDER BY key_column.ordinality)
                   FILTER (WHERE attribute.attname IS NOT NULL),
               ARRAY[]::name[]
           )
      FROM pg_catalog.pg_constraint AS constraint_record
      JOIN pg_catalog.pg_class AS relation
        ON relation.oid = constraint_record.conrelid
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = relation.relnamespace
 LEFT JOIN LATERAL pg_catalog.unnest(constraint_record.conkey)
           WITH ORDINALITY AS key_column(attnum, ordinality)
        ON TRUE
 LEFT JOIN pg_catalog.pg_attribute AS attribute
        ON attribute.attrelid = constraint_record.conrelid
       AND attribute.attnum = key_column.attnum
     WHERE constraint_record.contype = 'c'
       AND namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
       AND relation.relkind IN ('r', 'p', 'f')
     GROUP BY constraint_record.conrelid,
              constraint_record.oid,
              constraint_record.conname
     ORDER BY constraint_record.conrelid, constraint_record.conname
"""

DOMAIN_CONSTRAINTS_SQL = """
    SELECT type_record.oid::bigint,
           namespace.nspname,
           type_record.typname,
           constraint_record.oid::bigint,
           constraint_record.conname,
           pg_catalog.pg_get_constraintdef(constraint_record.oid, true)
      FROM pg_catalog.pg_type AS type_record
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = type_record.typnamespace
      JOIN pg_catalog.pg_constraint AS constraint_record
        ON constraint_record.contypid = type_record.oid
     WHERE type_record.typtype = 'd'
       AND namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
     ORDER BY namespace.nspname, type_record.typname, constraint_record.conname
"""

ENUM_VALUES_SQL = """
    SELECT type_record.oid::bigint,
           namespace.nspname,
           type_record.typname,
           enum_record.enumlabel
      FROM pg_catalog.pg_type AS type_record
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = type_record.typnamespace
      JOIN pg_catalog.pg_enum AS enum_record
        ON enum_record.enumtypid = type_record.oid
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
     ORDER BY namespace.nspname,
              type_record.typname,
              enum_record.enumsortorder
"""

INDEX_INVENTORY_SQL = """
    SELECT table_relation.oid::bigint,
           namespace.nspname,
           table_relation.relname,
           pg_catalog.format('%I.%I', namespace.nspname, table_relation.relname),
           index_relation.oid::bigint,
           index_relation.relname,
           access_method.amname,
           index_record.indisprimary,
           index_record.indisunique,
           index_record.indisexclusion,
           index_record.indisvalid,
           index_record.indisready,
           index_record.indislive,
           index_record.indnkeyatts,
           index_record.indnatts,
           ARRAY(
               SELECT attribute.attname
                 FROM pg_catalog.unnest(index_record.indkey)
                      WITH ORDINALITY AS key_column(attnum, position)
            LEFT JOIN pg_catalog.pg_attribute AS attribute
                   ON attribute.attrelid = table_relation.oid
                  AND attribute.attnum = key_column.attnum
                WHERE key_column.position <= index_record.indnkeyatts
                ORDER BY key_column.position
           ),
           ARRAY(
               SELECT pg_catalog.pg_get_indexdef(
                          index_relation.oid,
                          key_position,
                          true
                      )
                 FROM pg_catalog.generate_series(
                          1,
                          index_record.indnkeyatts
                      ) AS key_position
           ),
           ARRAY(
               SELECT attribute.attname
                 FROM pg_catalog.unnest(index_record.indkey)
                      WITH ORDINALITY AS included_column(attnum, position)
            LEFT JOIN pg_catalog.pg_attribute AS attribute
                   ON attribute.attrelid = table_relation.oid
                  AND attribute.attnum = included_column.attnum
                WHERE included_column.position > index_record.indnkeyatts
                ORDER BY included_column.position
           ),
           pg_catalog.pg_get_expr(index_record.indpred, index_record.indrelid),
           pg_catalog.pg_get_expr(index_record.indexprs, index_record.indrelid),
           pg_catalog.pg_relation_size(index_relation.oid),
           index_statistics.idx_scan,
           index_statistics.last_idx_scan
      FROM pg_catalog.pg_index AS index_record
      JOIN pg_catalog.pg_class AS table_relation
        ON table_relation.oid = index_record.indrelid
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = table_relation.relnamespace
      JOIN pg_catalog.pg_class AS index_relation
        ON index_relation.oid = index_record.indexrelid
      JOIN pg_catalog.pg_am AS access_method
        ON access_method.oid = index_relation.relam
 LEFT JOIN pg_catalog.pg_stat_all_indexes AS index_statistics
        ON index_statistics.indexrelid = index_relation.oid
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
       AND table_relation.relkind IN ('r', 'p', 'f')
     ORDER BY namespace.nspname, table_relation.relname, index_relation.relname
"""

QUERY_OBSERVABILITY_SQL = """
    SELECT pg_catalog.current_setting('track_activities')::boolean,
           pg_catalog.current_setting('track_counts')::boolean,
           pg_catalog.current_setting('compute_query_id', true),
           database_statistics.stats_reset,
           extension_record.oid IS NOT NULL,
           extension_namespace.nspname,
           CASE
               WHEN extension_namespace.oid IS NULL THEN FALSE
               ELSE pg_catalog.has_schema_privilege(
                   extension_namespace.oid,
                   'USAGE'
               )
           END,
           CASE
               WHEN statements_view.oid IS NULL THEN FALSE
               ELSE pg_catalog.has_table_privilege(
                   statements_view.oid,
                   'SELECT'
               )
           END
      FROM (SELECT 1) AS seed
 LEFT JOIN pg_catalog.pg_stat_database AS database_statistics
        ON database_statistics.datname = pg_catalog.current_database()
 LEFT JOIN pg_catalog.pg_extension AS extension_record
        ON extension_record.extname = 'pg_stat_statements'
 LEFT JOIN pg_catalog.pg_namespace AS extension_namespace
        ON extension_namespace.oid = extension_record.extnamespace
 LEFT JOIN pg_catalog.pg_class AS statements_view
        ON statements_view.relnamespace = extension_namespace.oid
       AND statements_view.relname = 'pg_stat_statements'
       AND statements_view.relkind IN ('v', 'm')
"""

ACTIVE_QUERY_SNAPSHOT_SQL = """
    SELECT activity.query_id::text,
           activity.state,
           activity.wait_event_type,
           activity.wait_event,
           pg_catalog.count(*)::bigint,
           pg_catalog.round(
               pg_catalog.max(
                   EXTRACT(
                       epoch FROM (
                           pg_catalog.clock_timestamp() - activity.query_start
                       )
                   ) * 1000
               )
           )::bigint
      FROM pg_catalog.pg_stat_activity AS activity
     WHERE activity.datname = pg_catalog.current_database()
       AND activity.pid <> pg_catalog.pg_backend_pid()
       AND activity.query_start IS NOT NULL
       AND activity.query_id IS NOT NULL
     GROUP BY activity.query_id,
              activity.state,
              activity.wait_event_type,
              activity.wait_event
     ORDER BY 6 DESC NULLS LAST, 5 DESC, activity.query_id
"""

PARTITION_CONFIGURATION_SQL = """
    SELECT parent_relation.oid::bigint,
           parent_namespace.nspname,
           parent_relation.relname,
           pg_catalog.format(
               '%I.%I',
               parent_namespace.nspname,
               parent_relation.relname
           ),
           partitioned_table.partstrat,
           pg_catalog.pg_get_partkeydef(parent_relation.oid),
           child_relation.oid::bigint,
           child_namespace.nspname,
           child_relation.relname,
           pg_catalog.format(
               '%I.%I',
               child_namespace.nspname,
               child_relation.relname
           ),
           pg_catalog.pg_get_expr(
               child_relation.relpartbound,
               child_relation.oid,
               true
           ),
           pg_catalog.has_schema_privilege(parent_namespace.oid, 'USAGE'),
           pg_catalog.has_table_privilege(parent_relation.oid, 'SELECT')
      FROM pg_catalog.pg_partitioned_table AS partitioned_table
      JOIN pg_catalog.pg_class AS parent_relation
        ON parent_relation.oid = partitioned_table.partrelid
      JOIN pg_catalog.pg_namespace AS parent_namespace
        ON parent_namespace.oid = parent_relation.relnamespace
 LEFT JOIN pg_catalog.pg_inherits AS inheritance
        ON inheritance.inhparent = parent_relation.oid
 LEFT JOIN pg_catalog.pg_class AS child_relation
        ON child_relation.oid = inheritance.inhrelid
 LEFT JOIN pg_catalog.pg_namespace AS child_namespace
        ON child_namespace.oid = child_relation.relnamespace
     WHERE parent_namespace.nspname <> 'information_schema'
       AND parent_namespace.nspname !~ '^pg_'
     ORDER BY parent_namespace.nspname,
              parent_relation.relname,
              inheritance.inhseqno
"""

ENGINE_CONFIGURATION_SQL = """
    SELECT setting.name,
           setting.setting,
           setting.unit,
           setting.vartype,
           setting.context,
           setting.source,
           setting.pending_restart
      FROM pg_catalog.pg_settings AS setting
     WHERE setting.name IN (
               'deadlock_timeout',
               'effective_cache_size',
               'effective_io_concurrency',
               'idle_in_transaction_session_timeout',
               'lock_timeout',
               'maintenance_work_mem',
               'max_connections',
               'random_page_cost',
               'shared_buffers',
               'statement_timeout',
               'temp_buffers',
               'wal_buffers',
               'work_mem'
           )
     ORDER BY setting.name
"""

KEY_CONSTRAINT_PROPERTIES_SQL = """
    SELECT constraint_record.oid::bigint,
           constraint_record.conrelid::bigint,
           constraint_record.conname,
           constraint_record.contype,
           constraint_record.convalidated,
           constraint_record.condeferrable,
           constraint_record.condeferred
      FROM pg_catalog.pg_constraint AS constraint_record
      JOIN pg_catalog.pg_class AS relation
        ON relation.oid = constraint_record.conrelid
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = relation.relnamespace
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
       AND relation.relkind IN ('r', 'p', 'f')
       AND constraint_record.contype IN ('p', 'f')
     ORDER BY constraint_record.conrelid, constraint_record.conname
"""

TABLE_CONSTRAINTS_SQL = """
    SELECT constraint_record.conrelid::bigint,
           constraint_record.oid::bigint,
           constraint_record.conname,
           constraint_record.contype,
           COALESCE(
               pg_catalog.array_agg(attribute.attname ORDER BY key_column.ordinality)
                   FILTER (WHERE attribute.attname IS NOT NULL),
               ARRAY[]::name[]
           )
      FROM pg_catalog.pg_constraint AS constraint_record
      JOIN pg_catalog.pg_class AS relation
        ON relation.oid = constraint_record.conrelid
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = relation.relnamespace
 LEFT JOIN LATERAL pg_catalog.unnest(constraint_record.conkey)
           WITH ORDINALITY AS key_column(attnum, ordinality)
        ON TRUE
 LEFT JOIN pg_catalog.pg_attribute AS attribute
        ON attribute.attrelid = constraint_record.conrelid
       AND attribute.attnum = key_column.attnum
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
       AND relation.relkind IN ('r', 'p', 'f')
     GROUP BY constraint_record.conrelid,
              constraint_record.oid,
              constraint_record.conname,
              constraint_record.contype
     ORDER BY constraint_record.conrelid, constraint_record.conname
"""

TABLE_FOREIGN_KEYS_SQL = """
    SELECT constraint_record.oid::bigint,
           constraint_record.conrelid::bigint,
           constraint_record.confrelid::bigint,
           constraint_record.conname,
           pg_catalog.format('%I.%I', source_namespace.nspname, source_relation.relname),
           pg_catalog.format('%I.%I', target_namespace.nspname, target_relation.relname),
           pg_catalog.array_agg(source_attribute.attname ORDER BY key_position.position),
           pg_catalog.array_agg(target_attribute.attname ORDER BY key_position.position),
           constraint_record.confupdtype,
           constraint_record.confdeltype
      FROM pg_catalog.pg_constraint AS constraint_record
      JOIN pg_catalog.pg_class AS source_relation
        ON source_relation.oid = constraint_record.conrelid
      JOIN pg_catalog.pg_namespace AS source_namespace
        ON source_namespace.oid = source_relation.relnamespace
      JOIN pg_catalog.pg_class AS target_relation
        ON target_relation.oid = constraint_record.confrelid
      JOIN pg_catalog.pg_namespace AS target_namespace
        ON target_namespace.oid = target_relation.relnamespace
      JOIN LATERAL pg_catalog.generate_subscripts(constraint_record.conkey, 1)
           AS key_position(position)
        ON TRUE
      JOIN pg_catalog.pg_attribute AS source_attribute
        ON source_attribute.attrelid = constraint_record.conrelid
       AND source_attribute.attnum = constraint_record.conkey[key_position.position]
      JOIN pg_catalog.pg_attribute AS target_attribute
        ON target_attribute.attrelid = constraint_record.confrelid
       AND target_attribute.attnum = constraint_record.confkey[key_position.position]
     WHERE constraint_record.contype = 'f'
       AND source_namespace.nspname <> 'information_schema'
       AND source_namespace.nspname !~ '^pg_'
     GROUP BY constraint_record.oid,
              constraint_record.conrelid,
              constraint_record.confrelid,
              constraint_record.conname,
              source_namespace.nspname,
              source_relation.relname,
              target_namespace.nspname,
              target_relation.relname,
              constraint_record.confupdtype,
              constraint_record.confdeltype
     ORDER BY constraint_record.conrelid, constraint_record.conname
"""

TABLE_RELATION_PROPERTIES_SQL = """
    SELECT relation.oid::bigint,
           relation.relpersistence
      FROM pg_catalog.pg_class AS relation
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = relation.relnamespace
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
       AND relation.relkind IN ('r', 'p', 'f')
     ORDER BY relation.oid
"""

TABLE_COMMENTS_SQL = """
    SELECT relation.oid::bigint,
           pg_catalog.obj_description(relation.oid, 'pg_class'),
           attribute.attnum,
           attribute.attname,
           pg_catalog.col_description(relation.oid, attribute.attnum)
      FROM pg_catalog.pg_class AS relation
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = relation.relnamespace
 LEFT JOIN pg_catalog.pg_attribute AS attribute
        ON attribute.attrelid = relation.oid
       AND attribute.attnum > 0
       AND NOT attribute.attisdropped
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
       AND relation.relkind IN ('r', 'p', 'f')
     ORDER BY relation.oid, attribute.attnum
"""

TABLE_USAGE_STATISTICS_SQL = """
    SELECT relation.oid::bigint,
           namespace.nspname,
           relation.relname,
           pg_catalog.format('%I.%I', namespace.nspname, relation.relname),
           relation.relkind,
           relation.relispartition,
           inheritance.inhparent::bigint,
           statistics.seq_scan,
           statistics.idx_scan,
           statistics.n_tup_ins,
           statistics.n_tup_upd,
           statistics.n_tup_del,
           statistics.n_live_tup,
           statistics.n_dead_tup,
           statistics.last_vacuum,
           statistics.last_autovacuum,
           statistics.last_analyze,
           statistics.last_autoanalyze
      FROM pg_catalog.pg_class AS relation
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = relation.relnamespace
 LEFT JOIN LATERAL (
           SELECT parent_link.inhparent
             FROM pg_catalog.pg_inherits AS parent_link
            WHERE parent_link.inhrelid = relation.oid
            ORDER BY parent_link.inhseqno
            LIMIT 1
           ) AS inheritance ON TRUE
 LEFT JOIN pg_catalog.pg_stat_all_tables AS statistics
        ON statistics.relid = relation.oid
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
       AND relation.relkind IN ('r', 'p', 'f')
     ORDER BY namespace.nspname, relation.relname
"""

TABLE_ROUTINE_DEPENDENCIES_SQL = """
    SELECT referenced_relation.oid::bigint,
           routine.oid::bigint,
           routine_namespace.nspname,
           routine.proname,
           pg_catalog.pg_get_function_identity_arguments(routine.oid),
           dependency.deptype
      FROM pg_catalog.pg_depend AS dependency
      JOIN pg_catalog.pg_proc AS routine
        ON dependency.classid = 'pg_catalog.pg_proc'::pg_catalog.regclass
       AND dependency.objid = routine.oid
      JOIN pg_catalog.pg_namespace AS routine_namespace
        ON routine_namespace.oid = routine.pronamespace
      JOIN pg_catalog.pg_class AS referenced_relation
        ON dependency.refclassid = 'pg_catalog.pg_class'::pg_catalog.regclass
       AND dependency.refobjid = referenced_relation.oid
      JOIN pg_catalog.pg_namespace AS referenced_namespace
        ON referenced_namespace.oid = referenced_relation.relnamespace
     WHERE referenced_namespace.nspname <> 'information_schema'
       AND referenced_namespace.nspname !~ '^pg_'
       AND referenced_relation.relkind IN ('r', 'p', 'f')
     ORDER BY referenced_relation.oid,
              routine_namespace.nspname,
              routine.proname,
              pg_catalog.pg_get_function_identity_arguments(routine.oid)
"""

VIEW_INVENTORY_SQL = """
    SELECT relation.oid::bigint,
           namespace.nspname,
           relation.relname,
           pg_catalog.format('%I.%I', namespace.nspname, relation.relname),
           relation.relkind,
           relation.relispopulated,
           pg_catalog.pg_get_viewdef(relation.oid, true),
           pg_catalog.obj_description(relation.oid, 'pg_class'),
           pg_catalog.has_schema_privilege(namespace.oid, 'USAGE'),
           pg_catalog.has_table_privilege(relation.oid, 'SELECT')
      FROM pg_catalog.pg_class AS relation
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = relation.relnamespace
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
       AND relation.relkind IN ('v', 'm')
     ORDER BY namespace.nspname, relation.relname
"""

VIEW_DEPENDENCIES_SQL = """
    SELECT view_relation.oid::bigint,
           referenced_relation.oid::bigint,
           referenced_namespace.nspname,
           referenced_relation.relname,
           pg_catalog.format(
               '%I.%I',
               referenced_namespace.nspname,
               referenced_relation.relname
           ),
           referenced_relation.relkind,
           referenced_namespace.nspname = 'information_schema'
               OR referenced_namespace.nspname ~ '^pg_'
      FROM pg_catalog.pg_class AS view_relation
      JOIN pg_catalog.pg_namespace AS view_namespace
        ON view_namespace.oid = view_relation.relnamespace
      JOIN pg_catalog.pg_rewrite AS rewrite_rule
        ON rewrite_rule.ev_class = view_relation.oid
      JOIN pg_catalog.pg_depend AS dependency
        ON dependency.classid = 'pg_catalog.pg_rewrite'::pg_catalog.regclass
       AND dependency.objid = rewrite_rule.oid
       AND dependency.refclassid = 'pg_catalog.pg_class'::pg_catalog.regclass
      JOIN pg_catalog.pg_class AS referenced_relation
        ON referenced_relation.oid = dependency.refobjid
      JOIN pg_catalog.pg_namespace AS referenced_namespace
        ON referenced_namespace.oid = referenced_relation.relnamespace
     WHERE view_namespace.nspname <> 'information_schema'
       AND view_namespace.nspname !~ '^pg_'
       AND view_relation.relkind IN ('v', 'm')
       AND referenced_relation.oid <> view_relation.oid
     ORDER BY view_relation.oid,
              referenced_namespace.nspname,
              referenced_relation.relname
"""

ROUTINE_INVENTORY_SQL = """
    SELECT routine.oid::bigint,
           namespace.nspname,
           routine.proname,
           pg_catalog.format('%I.%I', namespace.nspname, routine.proname),
           routine.prokind,
           language.lanname,
           pg_catalog.pg_get_function_identity_arguments(routine.oid),
           pg_catalog.pg_get_function_result(routine.oid),
           routine.prosecdef,
           routine.provolatile,
           routine.proparallel,
           pg_catalog.has_function_privilege(routine.oid, 'EXECUTE'),
           extension.extname
      FROM pg_catalog.pg_proc AS routine
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = routine.pronamespace
      JOIN pg_catalog.pg_language AS language
        ON language.oid = routine.prolang
 LEFT JOIN pg_catalog.pg_depend AS extension_dependency
        ON extension_dependency.classid = 'pg_catalog.pg_proc'::pg_catalog.regclass
       AND extension_dependency.objid = routine.oid
       AND extension_dependency.refclassid = 'pg_catalog.pg_extension'::pg_catalog.regclass
       AND extension_dependency.deptype = 'e'
 LEFT JOIN pg_catalog.pg_extension AS extension
        ON extension.oid = extension_dependency.refobjid
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
       AND routine.prokind IN ('f', 'p', 'w')
     ORDER BY namespace.nspname,
              routine.proname,
              pg_catalog.pg_get_function_identity_arguments(routine.oid)
"""

ROUTINE_DEPENDENCIES_SQL = """
    SELECT routine.oid::bigint,
           dependency.deptype,
           dependency.refclassid::pg_catalog.regclass::text,
           pg_catalog.pg_describe_object(
               dependency.refclassid,
               dependency.refobjid,
               dependency.refobjsubid
           )
      FROM pg_catalog.pg_proc AS routine
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = routine.pronamespace
      JOIN pg_catalog.pg_depend AS dependency
        ON dependency.classid = 'pg_catalog.pg_proc'::pg_catalog.regclass
       AND dependency.objid = routine.oid
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
       AND routine.prokind IN ('f', 'p', 'w')
       AND dependency.deptype <> 'e'
     ORDER BY routine.oid,
              dependency.refclassid,
              dependency.refobjid,
              dependency.refobjsubid
"""

TABLE_TRIGGER_INVENTORY_SQL = """
    SELECT trigger_record.oid::bigint,
           namespace.nspname,
           relation.relname,
           pg_catalog.format('%I.%I', namespace.nspname, relation.relname),
           trigger_record.tgname,
           trigger_record.tgtype::integer,
           trigger_record.tgenabled,
           trigger_record.tgisinternal,
           trigger_record.tgparentid::bigint,
           parent_trigger.tgname,
           function_namespace.nspname,
           function_record.proname,
           pg_catalog.pg_get_function_identity_arguments(function_record.oid),
           extension.extname
      FROM pg_catalog.pg_trigger AS trigger_record
      JOIN pg_catalog.pg_class AS relation
        ON relation.oid = trigger_record.tgrelid
      JOIN pg_catalog.pg_namespace AS namespace
        ON namespace.oid = relation.relnamespace
      JOIN pg_catalog.pg_proc AS function_record
        ON function_record.oid = trigger_record.tgfoid
      JOIN pg_catalog.pg_namespace AS function_namespace
        ON function_namespace.oid = function_record.pronamespace
 LEFT JOIN pg_catalog.pg_trigger AS parent_trigger
        ON parent_trigger.oid = trigger_record.tgparentid
 LEFT JOIN pg_catalog.pg_depend AS extension_dependency
        ON extension_dependency.classid = 'pg_catalog.pg_trigger'::pg_catalog.regclass
       AND extension_dependency.objid = trigger_record.oid
       AND extension_dependency.refclassid = 'pg_catalog.pg_extension'::pg_catalog.regclass
       AND extension_dependency.deptype = 'e'
 LEFT JOIN pg_catalog.pg_extension AS extension
        ON extension.oid = extension_dependency.refobjid
     WHERE namespace.nspname <> 'information_schema'
       AND namespace.nspname !~ '^pg_'
     ORDER BY namespace.nspname, relation.relname, trigger_record.tgname
"""

EVENT_TRIGGER_INVENTORY_SQL = """
    SELECT event_trigger.oid::bigint,
           event_trigger.evtname,
           event_trigger.evtevent,
           event_trigger.evtenabled,
           event_trigger.evttags,
           function_namespace.nspname,
           function_record.proname,
           pg_catalog.pg_get_function_identity_arguments(function_record.oid),
           extension.extname
      FROM pg_catalog.pg_event_trigger AS event_trigger
      JOIN pg_catalog.pg_proc AS function_record
        ON function_record.oid = event_trigger.evtfoid
      JOIN pg_catalog.pg_namespace AS function_namespace
        ON function_namespace.oid = function_record.pronamespace
 LEFT JOIN pg_catalog.pg_depend AS extension_dependency
        ON extension_dependency.classid = 'pg_catalog.pg_event_trigger'::pg_catalog.regclass
       AND extension_dependency.objid = event_trigger.oid
       AND extension_dependency.refclassid = 'pg_catalog.pg_extension'::pg_catalog.regclass
       AND extension_dependency.deptype = 'e'
 LEFT JOIN pg_catalog.pg_extension AS extension
        ON extension.oid = extension_dependency.refobjid
     ORDER BY event_trigger.evtname
"""
