BEGIN;

CREATE SCHEMA audit_metadata_fixture;

CREATE TABLE audit_metadata_fixture.audit_event_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_at TIMESTAMPTZ NOT NULL,
    actor_id BIGINT,
    action TEXT NOT NULL,
    old_values JSONB,
    new_values JSONB,
    UNIQUE (event_at, actor_id, action)
);

CREATE TABLE audit_metadata_fixture.trace_named_only (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY
);

CREATE TABLE audit_metadata_fixture.reference_data (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    label TEXT NOT NULL
);

CREATE VIEW audit_metadata_fixture.audit_event_summary AS
SELECT action, COUNT(*) AS event_count
  FROM audit_metadata_fixture.audit_event_log
 GROUP BY action;

COMMENT ON VIEW audit_metadata_fixture.audit_event_summary IS
    'Resumen técnico ficticio de eventos para pruebas de integración.';

CREATE MATERIALIZED VIEW audit_metadata_fixture.audit_event_daily AS
SELECT event_at::date AS event_date, COUNT(*) AS event_count
  FROM audit_metadata_fixture.audit_event_log
 GROUP BY event_at::date
WITH NO DATA;

CREATE FUNCTION audit_metadata_fixture.normalize_action(value TEXT)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
RETURN lower(value);

CREATE PROCEDURE audit_metadata_fixture.fixture_noop()
LANGUAGE SQL
AS 'SELECT NULL';

CREATE FUNCTION audit_metadata_fixture.preserve_fixture_row()
RETURNS trigger
LANGUAGE plpgsql
AS 'BEGIN RETURN NEW; END';

CREATE TRIGGER audit_event_log_before_insert
BEFORE INSERT ON audit_metadata_fixture.audit_event_log
FOR EACH ROW
EXECUTE FUNCTION audit_metadata_fixture.preserve_fixture_row();

ALTER TABLE audit_metadata_fixture.audit_event_log
    DISABLE TRIGGER audit_event_log_before_insert;

COMMIT;
