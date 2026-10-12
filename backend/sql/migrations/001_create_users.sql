DO $$
DECLARE
    users_table_oid OID;
    schema_is_compatible BOOLEAN;
BEGIN
    SELECT table_class.oid
      INTO users_table_oid
      FROM pg_catalog.pg_class AS table_class
      JOIN pg_catalog.pg_namespace AS table_schema
        ON table_schema.oid = table_class.relnamespace
     WHERE table_schema.nspname = 'public'
       AND table_class.relname = 'users'
       AND table_class.relkind = 'r';

    IF users_table_oid IS NULL THEN
        CREATE TABLE public.users (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            username VARCHAR(100) NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        RETURN;
    END IF;

    SELECT COALESCE(
        COUNT(*) = 5
        AND BOOL_AND(
            CASE column_definition.attnum
                WHEN 1 THEN
                    column_definition.attname = 'id'
                    AND column_definition.data_type = 'bigint'
                    AND column_definition.attnotnull
                    AND column_definition.attidentity = 'a'
                WHEN 2 THEN
                    column_definition.attname = 'username'
                    AND column_definition.data_type = 'character varying(100)'
                    AND column_definition.attnotnull
                    AND column_definition.attidentity = ''
                    AND column_definition.default_expression IS NULL
                WHEN 3 THEN
                    column_definition.attname = 'password_hash'
                    AND column_definition.data_type = 'text'
                    AND column_definition.attnotnull
                    AND column_definition.attidentity = ''
                    AND column_definition.default_expression IS NULL
                WHEN 4 THEN
                    column_definition.attname = 'is_active'
                    AND column_definition.data_type = 'boolean'
                    AND column_definition.attnotnull
                    AND column_definition.attidentity = ''
                    AND column_definition.default_expression IN ('true', 'true::boolean')
                WHEN 5 THEN
                    column_definition.attname = 'created_at'
                    AND column_definition.data_type = 'timestamp with time zone'
                    AND column_definition.attnotnull
                    AND column_definition.attidentity = ''
                    AND LOWER(column_definition.default_expression) IN ('now()', 'current_timestamp')
                ELSE FALSE
            END
        ),
        FALSE
    )
      INTO schema_is_compatible
      FROM (
          SELECT column_attribute.attnum,
                 column_attribute.attname,
                 pg_catalog.format_type(
                     column_attribute.atttypid,
                     column_attribute.atttypmod
                 ) AS data_type,
                 column_attribute.attnotnull,
                 column_attribute.attidentity,
                 pg_catalog.pg_get_expr(
                     column_default.adbin,
                     column_default.adrelid
                 ) AS default_expression
            FROM pg_catalog.pg_attribute AS column_attribute
            LEFT JOIN pg_catalog.pg_attrdef AS column_default
              ON column_default.adrelid = column_attribute.attrelid
             AND column_default.adnum = column_attribute.attnum
           WHERE column_attribute.attrelid = users_table_oid
             AND column_attribute.attnum > 0
             AND NOT column_attribute.attisdropped
           ORDER BY column_attribute.attnum
      ) AS column_definition;

    schema_is_compatible := schema_is_compatible
        AND EXISTS (
            SELECT 1
              FROM pg_catalog.pg_constraint
             WHERE conrelid = users_table_oid
               AND contype = 'p'
               AND conkey = ARRAY[1]::SMALLINT[]
        )
        AND EXISTS (
            SELECT 1
              FROM pg_catalog.pg_constraint
             WHERE conrelid = users_table_oid
               AND contype = 'u'
               AND conkey = ARRAY[2]::SMALLINT[]
        );

    IF NOT schema_is_compatible THEN
        RAISE EXCEPTION
            'La tabla public.users ya existe, pero su estructura no coincide con la migración 001.'
            USING ERRCODE = '42P16';
    END IF;
END
$$;
