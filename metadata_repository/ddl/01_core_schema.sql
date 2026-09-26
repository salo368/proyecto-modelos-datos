-- ============================================================
-- Metadata repository - core schema
--
-- Technical metadata of the two sources (data_source, db_table,
-- db_column), business metadata (business_entity, business_attribute)
-- and the semantic lineage that links them (column_business_mapping).
--
-- Technical tables are filled by etl/etl_source_metadata.py; business
-- tables and the lineage mapping by seeds/business_metadata.sql.
-- ============================================================

-- ------------------------------------------------------------
-- Technical metadata
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS data_source (
    source_id     SERIAL PRIMARY KEY,
    source_name   VARCHAR(100) NOT NULL UNIQUE,   -- 'classicmodels', 'customerservice'
    db_engine     VARCHAR(50)  NOT NULL,           -- 'MySQL', 'PostgreSQL'
    description   TEXT
);

CREATE TABLE IF NOT EXISTS db_table (
    table_id          SERIAL PRIMARY KEY,
    source_id         INTEGER NOT NULL REFERENCES data_source(source_id),
    schema_name       VARCHAR(100) NOT NULL,
    table_name        VARCHAR(100) NOT NULL,
    table_description TEXT,
    row_count_approx  INTEGER,
    loaded_at         TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (source_id, schema_name, table_name)
);

CREATE TABLE IF NOT EXISTS db_column (
    column_id         SERIAL PRIMARY KEY,
    table_id          INTEGER NOT NULL REFERENCES db_table(table_id) ON DELETE CASCADE,
    column_name       VARCHAR(100) NOT NULL,
    ordinal_position  INTEGER,
    data_type         VARCHAR(100) NOT NULL,   -- type normalised across engines
    native_data_type  VARCHAR(150),            -- type as reported by the source engine
    is_nullable       BOOLEAN NOT NULL DEFAULT TRUE,
    is_primary_key    BOOLEAN NOT NULL DEFAULT FALSE,
    is_foreign_key    BOOLEAN NOT NULL DEFAULT FALSE,
    fk_ref_column_id  INTEGER REFERENCES db_column(column_id),
    loaded_at         TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (table_id, column_name)
);

-- ------------------------------------------------------------
-- Business metadata (entered manually)
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS business_entity (
    entity_id           SERIAL PRIMARY KEY,
    entity_name          VARCHAR(150) NOT NULL UNIQUE,
    entity_description   TEXT NOT NULL,
    data_domain          VARCHAR(150) NOT NULL
);

CREATE TABLE IF NOT EXISTS business_attribute (
    attribute_id         SERIAL PRIMARY KEY,
    entity_id            INTEGER NOT NULL REFERENCES business_entity(entity_id) ON DELETE CASCADE,
    attribute_name       VARCHAR(150) NOT NULL,
    attribute_definition TEXT NOT NULL,
    UNIQUE (entity_id, attribute_name)
);

-- ------------------------------------------------------------
-- Semantic lineage: technical column <-> business attribute
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS column_business_mapping (
    mapping_id    SERIAL PRIMARY KEY,
    column_id     INTEGER NOT NULL REFERENCES db_column(column_id) ON DELETE CASCADE,
    attribute_id  INTEGER NOT NULL REFERENCES business_attribute(attribute_id) ON DELETE CASCADE,
    UNIQUE (column_id, attribute_id)
);

-- ------------------------------------------------------------
-- Indexes for the joins used by queries/required_questions.sql
-- ------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_db_table_source ON db_table(source_id);
CREATE INDEX IF NOT EXISTS idx_db_column_table ON db_column(table_id);
CREATE INDEX IF NOT EXISTS idx_business_attribute_entity ON business_attribute(entity_id);
CREATE INDEX IF NOT EXISTS idx_mapping_column ON column_business_mapping(column_id);
CREATE INDEX IF NOT EXISTS idx_mapping_attribute ON column_business_mapping(attribute_id);
