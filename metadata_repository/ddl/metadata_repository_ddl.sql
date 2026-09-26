-- ============================================================
-- Repositorio de Metadatos - Modelo fisico (PostgreSQL)
-- Proyecto: Modelos y Persistencia de Datos - Entrega 1
--
-- Arquitectura: hibrida a nivel conceptual (classicmodels y
-- customerservice siguen siendo el sistema de registro de su propio
-- metadato tecnico) / centralizada a nivel fisico (una sola BD
-- consultable con SQL plano para responder las 6 preguntas del
-- enunciado, incluido el linaje semantico).
--
-- Motor: PostgreSQL (servicio nuevo en Railway).
-- ============================================================

-- ------------------------------------------------------------
-- METADATO TECNICO
-- ------------------------------------------------------------

CREATE TABLE data_source (
    source_id     SERIAL PRIMARY KEY,
    source_name   VARCHAR(100) NOT NULL UNIQUE,   -- 'classicmodels', 'customerservice'
    db_engine     VARCHAR(50)  NOT NULL,           -- 'MySQL', 'PostgreSQL'
    description   TEXT
);

CREATE TABLE db_table (
    table_id          SERIAL PRIMARY KEY,
    source_id         INTEGER NOT NULL REFERENCES data_source(source_id),
    schema_name       VARCHAR(100) NOT NULL,
    table_name        VARCHAR(100) NOT NULL,
    table_description TEXT,
    row_count_approx  INTEGER,
    loaded_at         TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (source_id, schema_name, table_name)
);

CREATE TABLE db_column (
    column_id         SERIAL PRIMARY KEY,
    table_id          INTEGER NOT NULL REFERENCES db_table(table_id) ON DELETE CASCADE,
    column_name       VARCHAR(100) NOT NULL,
    ordinal_position  INTEGER,
    data_type         VARCHAR(100) NOT NULL,   -- tipo normalizado (categoria cruzada entre motores)
    native_data_type  VARCHAR(150),            -- tipo tal como lo reporta el motor de origen (ej. TINYINT(4), character varying(50))
    is_nullable       BOOLEAN NOT NULL DEFAULT TRUE,
    is_primary_key    BOOLEAN NOT NULL DEFAULT FALSE,
    is_foreign_key    BOOLEAN NOT NULL DEFAULT FALSE,
    fk_ref_column_id  INTEGER REFERENCES db_column(column_id),
    loaded_at         TIMESTAMP NOT NULL DEFAULT now(),
    UNIQUE (table_id, column_name)
);

-- ------------------------------------------------------------
-- METADATO DE NEGOCIO (ingreso manual)
-- ------------------------------------------------------------

CREATE TABLE business_entity (
    entity_id           SERIAL PRIMARY KEY,
    entity_name          VARCHAR(150) NOT NULL UNIQUE,
    entity_description   TEXT NOT NULL,
    data_domain          VARCHAR(150) NOT NULL
);

CREATE TABLE business_attribute (
    attribute_id         SERIAL PRIMARY KEY,
    entity_id            INTEGER NOT NULL REFERENCES business_entity(entity_id) ON DELETE CASCADE,
    attribute_name       VARCHAR(150) NOT NULL,
    attribute_definition TEXT NOT NULL,
    UNIQUE (entity_id, attribute_name)
);

-- ------------------------------------------------------------
-- LINAJE SEMANTICO (puente tecnico <-> negocio)
-- ------------------------------------------------------------

CREATE TABLE column_business_mapping (
    mapping_id    SERIAL PRIMARY KEY,
    column_id     INTEGER NOT NULL REFERENCES db_column(column_id) ON DELETE CASCADE,
    attribute_id  INTEGER NOT NULL REFERENCES business_attribute(attribute_id) ON DELETE CASCADE,
    UNIQUE (column_id, attribute_id)
);

-- ------------------------------------------------------------
-- Indices de apoyo para las consultas del enunciado
-- ------------------------------------------------------------

CREATE INDEX idx_db_table_source ON db_table(source_id);
CREATE INDEX idx_db_column_table ON db_column(table_id);
CREATE INDEX idx_business_attribute_entity ON business_attribute(entity_id);
CREATE INDEX idx_mapping_column ON column_business_mapping(column_id);
CREATE INDEX idx_mapping_attribute ON column_business_mapping(attribute_id);
