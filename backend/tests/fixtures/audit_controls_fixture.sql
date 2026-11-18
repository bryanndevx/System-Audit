-- Solo datos ficticios. Instalar exclusivamente en una instancia aislada de pruebas.
BEGIN;
CREATE SCHEMA audit_controls_fixture;
CREATE TABLE audit_controls_fixture.reference_item (id bigint PRIMARY KEY, code text UNIQUE NOT NULL);
CREATE TABLE audit_controls_fixture.transaction_item (id bigint PRIMARY KEY, reference_id bigint);
INSERT INTO audit_controls_fixture.reference_item VALUES (1,'synthetic-a'),(2,'synthetic-b');
INSERT INTO audit_controls_fixture.transaction_item VALUES (1,1),(2,999),(3,NULL);
ALTER TABLE audit_controls_fixture.transaction_item ADD CONSTRAINT reference_item_fk
    FOREIGN KEY (reference_id) REFERENCES audit_controls_fixture.reference_item(id) NOT VALID;
COMMIT;
