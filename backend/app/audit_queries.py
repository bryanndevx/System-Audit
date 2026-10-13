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
