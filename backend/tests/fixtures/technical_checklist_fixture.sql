-- Preparación exclusiva de una instancia ficticia, antes de auditar con un lector.
BEGIN;
CREATE SCHEMA technical_version_fixture;
CREATE TABLE technical_version_fixture.alembic_version (version_num varchar(32) PRIMARY KEY);
INSERT INTO technical_version_fixture.alembic_version VALUES ('synthetic_revision_001');
CREATE TABLE technical_version_fixture.review_item (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 optional_reference bigint,
 created_at timestamptz NOT NULL DEFAULT now(),
 valid_until date,
 state text CHECK (state IN ('synthetic_open','synthetic_closed'))
);
CREATE TABLE technical_version_fixture.isolated_entity (code text PRIMARY KEY);
CREATE TABLE technical_version_fixture.rls_item (id bigint PRIMARY KEY);
ALTER TABLE technical_version_fixture.rls_item ENABLE ROW LEVEL SECURITY;
CREATE POLICY fixture_reader_policy ON technical_version_fixture.rls_item FOR SELECT USING (true);
COMMIT;
