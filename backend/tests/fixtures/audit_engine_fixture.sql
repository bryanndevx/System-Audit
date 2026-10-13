BEGIN;

CREATE SCHEMA audit_fixture;

CREATE TABLE audit_fixture.catalog_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_code TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX catalog_items_created_at_idx
    ON audit_fixture.catalog_items (created_at);

CREATE TABLE audit_fixture.technical_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    occurred_on DATE NOT NULL,
    event_type TEXT NOT NULL,
    PRIMARY KEY (id, occurred_on)
) PARTITION BY RANGE (occurred_on);

CREATE TABLE audit_fixture.technical_events_2025
    PARTITION OF audit_fixture.technical_events
    FOR VALUES FROM ('2025-01-01') TO ('2026-01-01');

CREATE TABLE audit_fixture.technical_events_2026
    PARTITION OF audit_fixture.technical_events
    FOR VALUES FROM ('2026-01-01') TO ('2027-01-01');

INSERT INTO audit_fixture.catalog_items (item_code)
VALUES ('ITEM-001'), ('ITEM-002');

INSERT INTO audit_fixture.technical_events (occurred_on, event_type)
VALUES
    ('2025-06-01', 'synthetic-test'),
    ('2026-06-01', 'synthetic-test');

COMMIT;
