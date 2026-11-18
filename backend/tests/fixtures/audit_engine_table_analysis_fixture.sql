BEGIN;

CREATE SCHEMA audit_table_analysis_fixture;

CREATE TABLE audit_table_analysis_fixture.customer_master (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_code TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL
);

COMMENT ON TABLE audit_table_analysis_fixture.customer_master IS
    'Entidad ficticia para validar relaciones técnicas; el comentario no confirma un módulo empresarial.';

CREATE TABLE audit_table_analysis_fixture.status_catalog (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status_code TEXT NOT NULL UNIQUE,
    label TEXT NOT NULL
);

CREATE TABLE audit_table_analysis_fixture.sales_transaction (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES audit_table_analysis_fixture.customer_master (id),
    status_id BIGINT NOT NULL
        REFERENCES audit_table_analysis_fixture.status_catalog (id),
    created_at TIMESTAMPTZ NOT NULL
);

CREATE UNLOGGED TABLE audit_table_analysis_fixture.work_staging (
    source_id BIGINT,
    loaded_at TIMESTAMPTZ
);

CREATE TABLE audit_table_analysis_fixture.ambiguous_entity (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label TEXT
);

CREATE TABLE audit_table_analysis_fixture.sales_history (
    id BIGINT NOT NULL,
    occurred_on DATE NOT NULL,
    PRIMARY KEY (id, occurred_on)
) PARTITION BY RANGE (occurred_on);

CREATE TABLE audit_table_analysis_fixture.sales_history_2026
    PARTITION OF audit_table_analysis_fixture.sales_history
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

CREATE VIEW audit_table_analysis_fixture.sales_summary AS
SELECT customer_id, status_id, created_at
  FROM audit_table_analysis_fixture.sales_transaction;

CREATE FUNCTION audit_table_analysis_fixture.preserve_sales_row()
RETURNS trigger
LANGUAGE plpgsql
AS 'BEGIN RETURN NEW; END';

CREATE TRIGGER sales_transaction_before_insert
BEFORE INSERT ON audit_table_analysis_fixture.sales_transaction
FOR EACH ROW
EXECUTE FUNCTION audit_table_analysis_fixture.preserve_sales_row();

COMMIT;
