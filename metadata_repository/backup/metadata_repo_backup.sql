-- ============================================================
-- Backup: Repositorio de metadatos
-- Generated: 2026-09-26 by tools/generate_backup.py
-- Engine: PostgreSQL 16
--
-- Restore on an empty database with:
--   psql "<connection-url>" -f metadata_repository/backup/metadata_repo_backup.sql
--
-- Contents:
--   data_source: 2 filas
--   db_table: 13 filas
--   db_column: 85 filas
--   business_entity: 8 filas
--   business_attribute: 47 filas
--   column_business_mapping: 78 filas
--   dw_object: 11 filas
--   dw_measure: 9 filas
--   dw_attribute: 81 filas
--   dw_lineage: 68 filas
--   etl_process: 3 filas
--   etl_execution: 11 filas
--   dq_rule: 27 filas
--   dq_result: 78 filas
--   usage_herramienta: 3 filas
--   usage_consulta: 8 filas
--   usage_consulta_objeto: 27 filas
--   usage_acceso_objeto: 9 filas
-- ============================================================

-- Drop previous objects
DROP TABLE IF EXISTS usage_acceso_objeto CASCADE;
DROP TABLE IF EXISTS usage_consulta_objeto CASCADE;
DROP TABLE IF EXISTS usage_consulta CASCADE;
DROP TABLE IF EXISTS usage_herramienta CASCADE;
DROP TABLE IF EXISTS dq_result CASCADE;
DROP TABLE IF EXISTS dq_rule CASCADE;
DROP TABLE IF EXISTS etl_execution CASCADE;
DROP TABLE IF EXISTS etl_process CASCADE;
DROP TABLE IF EXISTS dw_lineage CASCADE;
DROP TABLE IF EXISTS dw_attribute CASCADE;
DROP TABLE IF EXISTS dw_measure CASCADE;
DROP TABLE IF EXISTS dw_object CASCADE;
DROP TABLE IF EXISTS column_business_mapping CASCADE;
DROP TABLE IF EXISTS business_attribute CASCADE;
DROP TABLE IF EXISTS business_entity CASCADE;
DROP TABLE IF EXISTS db_column CASCADE;
DROP TABLE IF EXISTS db_table CASCADE;
DROP TABLE IF EXISTS data_source CASCADE;

-- ---- metadata_repository/ddl/01_core_schema.sql ----
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

-- ---- metadata_repository/ddl/03_dw_extension.sql ----
-- ============================================================
-- Metadata repository - data warehouse extension
--
-- Adds eight tables so the repository also describes the data
-- warehouse and the processes that load it:
--
--   1. Warehouse structure       dw_object, dw_measure, dw_attribute
--   2. Source -> DW lineage      dw_lineage
--   3. ETL operation             etl_process, etl_execution
--   4. Data quality              dq_rule, dq_result
--
-- dw_* tables are filled by etl/etl_dw_metadata.py, dq_rule by
-- seeds/dq_rules.sql, and etl_process / etl_execution / dq_result by
-- every run of the pipeline that loads the warehouse (pipeline/common.py).
-- ============================================================

-- ------------------------------------------------------------
-- 1. Warehouse structure
-- ------------------------------------------------------------

-- Every fact, dimension and data-mart view of the warehouse.
CREATE TABLE IF NOT EXISTS dw_object (
    dw_object_id    SERIAL PRIMARY KEY,
    object_name     VARCHAR(100) NOT NULL UNIQUE,   -- 'fact_ventas', 'dim_cliente'
    object_type     VARCHAR(20)  NOT NULL,          -- 'FACT' | 'DIMENSION' | 'VIEW'
    grain           TEXT,                           -- facts and views only
    description     TEXT NOT NULL,
    is_conformed    BOOLEAN NOT NULL DEFAULT FALSE, -- dimensions only
    scd_type        VARCHAR(10),                    -- slowly changing dimension type
    scd_justificacion TEXT,                         -- why that SCD type was chosen
    row_count       INTEGER,
    loaded_at       TIMESTAMP NOT NULL DEFAULT now(),
    CHECK (object_type IN ('FACT', 'DIMENSION', 'VIEW')),
    CHECK (scd_type IS NULL OR scd_type IN ('TIPO_1', 'TIPO_2', 'TIPO_3'))
);

-- Measures of each fact. additivity tells a BI tool whether the column
-- can be summed across every dimension, only some, or none.
CREATE TABLE IF NOT EXISTS dw_measure (
    dw_measure_id   SERIAL PRIMARY KEY,
    dw_object_id    INTEGER NOT NULL REFERENCES dw_object(dw_object_id) ON DELETE CASCADE,
    measure_name    VARCHAR(100) NOT NULL,
    data_type       VARCHAR(50)  NOT NULL,
    additivity      VARCHAR(20)  NOT NULL,
    formula         TEXT,
    description     TEXT,
    UNIQUE (dw_object_id, measure_name),
    CHECK (additivity IN ('ADITIVA', 'SEMI_ADITIVA', 'NO_ADITIVA'))
);

-- Non-measure columns of facts and dimensions, with their role.
CREATE TABLE IF NOT EXISTS dw_attribute (
    dw_attribute_id SERIAL PRIMARY KEY,
    dw_object_id    INTEGER NOT NULL REFERENCES dw_object(dw_object_id) ON DELETE CASCADE,
    attribute_name  VARCHAR(100) NOT NULL,
    data_type       VARCHAR(50)  NOT NULL,
    attribute_role  VARCHAR(30)  NOT NULL,
    description     TEXT,
    UNIQUE (dw_object_id, attribute_name),
    CHECK (attribute_role IN ('SURROGATE_KEY', 'BUSINESS_KEY', 'FOREIGN_KEY',
                              'DESCRIPTIVE', 'FLAG', 'DEGENERATE'))
);

-- ------------------------------------------------------------
-- 2. Source -> DW lineage
--
-- Links the source columns catalogued in db_column to the warehouse
-- field they feed, so lineage runs end to end:
--
--   business_attribute <- column_business_mapping <- db_column
--                                                        |
--                                                   dw_lineage
--                                                        |
--                                          dw_measure / dw_attribute
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dw_lineage (
    dw_lineage_id       SERIAL PRIMARY KEY,
    source_column_id    INTEGER REFERENCES db_column(column_id)         ON DELETE SET NULL,
    target_measure_id   INTEGER REFERENCES dw_measure(dw_measure_id)     ON DELETE CASCADE,
    target_attribute_id INTEGER REFERENCES dw_attribute(dw_attribute_id) ON DELETE CASCADE,
    transformation_rule TEXT NOT NULL,
    -- Each row targets exactly one measure or one attribute.
    CHECK (
        (target_measure_id IS NOT NULL AND target_attribute_id IS NULL) OR
        (target_measure_id IS NULL     AND target_attribute_id IS NOT NULL)
    )
);

-- ------------------------------------------------------------
-- 3. ETL operation
-- ------------------------------------------------------------

-- Catalogue of warehouse ETL processes and the tool that runs them.
CREATE TABLE IF NOT EXISTS etl_process (
    etl_process_id  SERIAL PRIMARY KEY,
    process_name    VARCHAR(100) NOT NULL UNIQUE,
    tool            VARCHAR(80)  NOT NULL,
    source_systems  VARCHAR(200) NOT NULL,
    target_system   VARCHAR(100) NOT NULL,
    description     TEXT
);

-- Execution log: one row per attempt of each process. The row is written
-- EN_CURSO when the attempt starts and closed when it ends, so
-- finished_at - started_at is its real duration and a process that dies
-- leaves a trace (the next run closes it as ERROR). A resumed run adds
-- a new attempt under the same run_id. run_id and run_origen are
-- staging_dw.etl_run ids in the staging database: the run, and the
-- staging run it read (dimensions and facts only).
CREATE TABLE IF NOT EXISTS etl_execution (
    etl_execution_id SERIAL PRIMARY KEY,
    etl_process_id   INTEGER NOT NULL REFERENCES etl_process(etl_process_id),
    run_id           INTEGER NOT NULL,
    run_origen       INTEGER,
    started_at       TIMESTAMP NOT NULL,
    finished_at      TIMESTAMP,
    status           VARCHAR(20) NOT NULL,
    rows_read        INTEGER,
    rows_written     INTEGER,
    rows_rejected    INTEGER,
    error_message    TEXT,
    CHECK (status IN ('EN_CURSO', 'OK', 'ERROR'))
);

-- Repository created by an earlier version of this script.
ALTER TABLE etl_execution ADD COLUMN IF NOT EXISTS run_origen INTEGER;

-- ------------------------------------------------------------
-- 4. Data quality
--
-- dq_rule is the catalogue of quality rules; dq_result stores how
-- each rule performed in a given ETL execution.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dq_rule (
    dq_rule_id       SERIAL PRIMARY KEY,
    rule_name        VARCHAR(120) NOT NULL UNIQUE,
    rule_type        VARCHAR(40)  NOT NULL,   -- technical category of the check
    criterio_dama    VARCHAR(20),             -- data quality dimension it measures
    clase_dq         VARCHAR(10),             -- technical or business quality
    -- Pipeline layer where the rule is evaluated:
    --   DATA_QUALITY    row by row in the staging ETL; can reject rows
    --   TRANSFORMATION  profiling finding solved by a modelling decision
    --   MONITOREO       about warehouse operation, outside the load
    capa             VARCHAR(20),
    source_column_id INTEGER REFERENCES db_column(column_id) ON DELETE SET NULL,
    expression       TEXT NOT NULL,
    severity         VARCHAR(20) NOT NULL,
    resolution       TEXT NOT NULL,           -- what the ETL does when the rule fails
    CHECK (rule_type IN ('COMPLETITUD', 'UNICIDAD', 'INTEGRIDAD', 'RANGO',
                         'FORMATO', 'COHERENCIA', 'CONFORMIDAD', 'FRESCURA')),
    CHECK (criterio_dama IS NULL OR criterio_dama IN
           ('EXACTITUD', 'EXHAUSTIVIDAD', 'CONSISTENCIA', 'OPORTUNIDAD',
            'RELEVANCIA', 'CONFIANZA')),
    CHECK (clase_dq IS NULL OR clase_dq IN ('TECNICA', 'NEGOCIO')),
    CHECK (capa IS NULL OR capa IN ('DATA_QUALITY', 'TRANSFORMATION', 'MONITOREO')),
    CHECK (severity  IN ('BLOQUEANTE', 'ADVERTENCIA', 'INFORMATIVA'))
);

CREATE TABLE IF NOT EXISTS dq_result (
    dq_result_id     SERIAL PRIMARY KEY,
    dq_rule_id       INTEGER NOT NULL REFERENCES dq_rule(dq_rule_id)             ON DELETE CASCADE,
    etl_execution_id INTEGER NOT NULL REFERENCES etl_execution(etl_execution_id) ON DELETE CASCADE,
    evaluated_at     TIMESTAMP NOT NULL DEFAULT now(),
    rows_evaluated   INTEGER,
    rows_failed      INTEGER,
    passed           BOOLEAN NOT NULL
);

-- ------------------------------------------------------------
-- Indexes
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_dw_measure_object     ON dw_measure(dw_object_id);
CREATE INDEX IF NOT EXISTS idx_dw_attribute_object   ON dw_attribute(dw_object_id);
CREATE INDEX IF NOT EXISTS idx_dw_lineage_source     ON dw_lineage(source_column_id);
CREATE INDEX IF NOT EXISTS idx_dw_lineage_measure    ON dw_lineage(target_measure_id);
CREATE INDEX IF NOT EXISTS idx_dw_lineage_attribute  ON dw_lineage(target_attribute_id);
CREATE INDEX IF NOT EXISTS idx_etl_exec_process      ON etl_execution(etl_process_id);
CREATE INDEX IF NOT EXISTS idx_dq_result_rule        ON dq_result(dq_rule_id);
CREATE INDEX IF NOT EXISTS idx_dq_result_execution   ON dq_result(etl_execution_id);

-- ---- metadata_repository/ddl/04_usage_extension.sql ----
-- ============================================================
-- Metadata repository - usage metadata extension
--
-- Describes how the data warehouse is used:
--
--   usage_herramienta      tools that access the warehouse
--   usage_consulta         known queries, expected frequency, joins
--   usage_consulta_objeto  which warehouse objects each query reads
--   usage_acceso_objeto    measured access, taken from the engine's
--                          own counters (pg_stat_user_tables)
--
-- Filled by etl/etl_usage_metadata.py.
-- ============================================================

CREATE TABLE IF NOT EXISTS usage_herramienta (
    usage_herramienta_id SERIAL PRIMARY KEY,
    nombre           VARCHAR(80)  NOT NULL UNIQUE,
    tipo             VARCHAR(40)  NOT NULL,
    proposito        TEXT         NOT NULL,
    acceso           VARCHAR(20)  NOT NULL,
    CHECK (tipo   IN ('BI', 'ETL', 'CLIENTE_SQL', 'APLICACION')),
    CHECK (acceso IN ('LECTURA', 'ESCRITURA', 'AMBOS'))
);

CREATE TABLE IF NOT EXISTS usage_consulta (
    usage_consulta_id SERIAL PRIMARY KEY,
    nombre            VARCHAR(120) NOT NULL UNIQUE,
    usage_herramienta_id INTEGER NOT NULL
        REFERENCES usage_herramienta(usage_herramienta_id) ON DELETE CASCADE,
    proposito         TEXT,
    frecuencia        VARCHAR(20) NOT NULL,   -- expected run frequency
    nro_joins         INTEGER,                -- number of joins in the query
    CHECK (frecuencia IN ('CONTINUA', 'DIARIA', 'SEMANAL', 'MENSUAL', 'BAJO_DEMANDA'))
);

CREATE TABLE IF NOT EXISTS usage_consulta_objeto (
    usage_consulta_id INTEGER NOT NULL
        REFERENCES usage_consulta(usage_consulta_id) ON DELETE CASCADE,
    dw_object_id      INTEGER NOT NULL
        REFERENCES dw_object(dw_object_id) ON DELETE CASCADE,
    PRIMARY KEY (usage_consulta_id, dw_object_id)
);

-- Snapshot of pg_stat_user_tables for each warehouse table. A high
-- lecturas_secuenciales against lecturas_por_indice means queries scan
-- the whole table.
CREATE TABLE IF NOT EXISTS usage_acceso_objeto (
    usage_acceso_id       SERIAL PRIMARY KEY,
    dw_object_id          INTEGER NOT NULL
        REFERENCES dw_object(dw_object_id) ON DELETE CASCADE,
    medido_en             TIMESTAMP NOT NULL DEFAULT now(),
    lecturas_secuenciales BIGINT,   -- seq_scan
    filas_leidas_secuencial BIGINT, -- seq_tup_read
    lecturas_por_indice   BIGINT,   -- idx_scan
    filas_insertadas      BIGINT,   -- n_tup_ins
    filas_actualizadas    BIGINT,   -- n_tup_upd
    filas_borradas        BIGINT    -- n_tup_del
);

CREATE INDEX IF NOT EXISTS idx_usage_acceso_objeto ON usage_acceso_objeto(dw_object_id);
CREATE INDEX IF NOT EXISTS idx_usage_consulta_herr ON usage_consulta(usage_herramienta_id);

-- Usage profile per warehouse object: declared queries vs measured reads.
CREATE OR REPLACE VIEW vw_perfil_uso AS
SELECT o.object_name,
       o.object_type,
       COUNT(DISTINCT co.usage_consulta_id) AS consultas_declaradas,
       COALESCE(MAX(a.lecturas_secuenciales), 0) AS lecturas_secuenciales,
       COALESCE(MAX(a.lecturas_por_indice),   0) AS lecturas_por_indice,
       MAX(a.medido_en) AS ultima_medicion
FROM dw_object o
LEFT JOIN usage_consulta_objeto co ON co.dw_object_id = o.dw_object_id
LEFT JOIN usage_acceso_objeto   a  ON a.dw_object_id  = o.dw_object_id
GROUP BY o.object_name, o.object_type
ORDER BY lecturas_secuenciales DESC, o.object_name;

-- ============================================================
-- Data
-- ============================================================

-- data_source: 2 filas
INSERT INTO data_source (source_id, source_name, db_engine, description) VALUES
    (1, 'classicmodels', 'MySQL', 'Base de datos transaccional de ventas (MySQL): clientes, empleados, oficinas, ordenes de compra, pagos junto con el catalogo de productos.'),
    (2, 'customerservice', 'PostgreSQL', 'Base de datos del centro de servicio al cliente (PostgreSQL): clientes, empleados, catalogo de productos, llamadas de servicio junto con el registro de productos de interes de cada cliente.');

-- db_table: 13 filas
INSERT INTO db_table (table_id, source_id, schema_name, table_name, table_description, row_count_approx, loaded_at) VALUES
    (1, 1, 'classicmodels', 'customers', 'Clientes de la compania que realizan ordenes de compra.', 122, '2026-09-26 23:55:24.390129'),
    (2, 1, 'classicmodels', 'employees', 'Empleados de la compania, incluye representantes de ventas y su jerarquia.', 23, '2026-09-26 23:55:24.390129'),
    (3, 1, 'classicmodels', 'offices', 'Oficinas o sedes fisicas de la compania.', 7, '2026-09-26 23:55:24.390129'),
    (4, 1, 'classicmodels', 'orderdetails', 'Detalle (lineas) de cada orden de compra: producto, cantidad y precio.', 2996, '2026-09-26 23:55:24.390129'),
    (5, 1, 'classicmodels', 'orders', 'Encabezado de las ordenes de compra realizadas por los clientes.', 326, '2026-09-26 23:55:24.390129'),
    (6, 1, 'classicmodels', 'payments', 'Pagos realizados por los clientes asociados a sus ordenes de compra.', 273, '2026-09-26 23:55:24.390129'),
    (7, 1, 'classicmodels', 'productlines', 'Lineas o categorias de productos.', 7, '2026-09-26 23:55:24.390129'),
    (8, 1, 'classicmodels', 'products', 'Catalogo de productos que la compania vende.', 110, '2026-09-26 23:55:24.390129'),
    (9, 2, 'public', 'cs_customers', 'Clientes registrados en el sistema de call center.', 122, '2026-09-26 23:55:24.390129'),
    (10, 2, 'public', 'cs_customer_calls', 'Registro de llamadas de servicio al cliente.', 108, '2026-09-26 23:55:24.390129'),
    (11, 2, 'public', 'cs_employees', 'Empleados que atienden llamadas en el call center.', 30, '2026-09-26 23:55:24.390129'),
    (12, 2, 'public', 'cs_products', 'Catalogo de productos referenciado en las llamadas de servicio.', 110, '2026-09-26 23:55:24.390129'),
    (13, 2, 'public', 'cs_customer_products', 'Relacion entre clientes y productos consultados en servicio.', 101, '2026-09-26 23:55:24.390129');

-- db_column: 85 filas
INSERT INTO db_column (column_id, table_id, column_name, ordinal_position, data_type, native_data_type, is_nullable, is_primary_key, is_foreign_key, fk_ref_column_id, loaded_at) VALUES
    (1, 1, 'customerNumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (2, 1, 'customerName', 2, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (3, 1, 'contactLastName', 3, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (4, 1, 'contactFirstName', 4, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (5, 1, 'phone', 5, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (6, 1, 'addressLine1', 6, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (7, 1, 'addressLine2', 7, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (8, 1, 'city', 8, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (9, 1, 'state', 9, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (10, 1, 'postalCode', 10, 'VARCHAR(15)', 'VARCHAR(15)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (11, 1, 'country', 11, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (13, 1, 'creditLimit', 13, 'DECIMAL', 'DECIMAL(10, 2)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (14, 2, 'employeeNumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (15, 2, 'lastName', 2, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (16, 2, 'firstName', 3, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (17, 2, 'extension', 4, 'VARCHAR(10)', 'VARCHAR(10)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (18, 2, 'email', 5, 'VARCHAR(100)', 'VARCHAR(100)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (21, 2, 'jobTitle', 8, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (22, 3, 'officeCode', 1, 'VARCHAR(10)', 'VARCHAR(10)', FALSE, TRUE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (23, 3, 'city', 2, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (24, 3, 'phone', 3, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (25, 3, 'addressLine1', 4, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (26, 3, 'addressLine2', 5, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (27, 3, 'state', 6, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (28, 3, 'country', 7, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (29, 3, 'postalCode', 8, 'VARCHAR(15)', 'VARCHAR(15)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (30, 3, 'territory', 9, 'VARCHAR(10)', 'VARCHAR(10)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (33, 4, 'quantityOrdered', 3, 'INTEGER', 'INTEGER', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (34, 4, 'priceEach', 4, 'DECIMAL', 'DECIMAL(10, 2)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (35, 4, 'orderLineNumber', 5, 'INTEGER', 'SMALLINT', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (36, 5, 'orderNumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (37, 5, 'orderDate', 2, 'DATE', 'DATE', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (38, 5, 'requiredDate', 3, 'DATE', 'DATE', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (39, 5, 'shippedDate', 4, 'DATE', 'DATE', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (40, 5, 'status', 5, 'VARCHAR(15)', 'VARCHAR(15)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (41, 5, 'comments', 6, 'TEXT', 'TEXT', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (44, 6, 'checkNumber', 2, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, TRUE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (45, 6, 'paymentDate', 3, 'DATE', 'DATE', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (46, 6, 'amount', 4, 'DECIMAL', 'DECIMAL(10, 2)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (47, 7, 'productLine', 1, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, TRUE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (48, 7, 'textDescription', 2, 'VARCHAR(4000)', 'VARCHAR(4000)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (49, 7, 'htmlDescription', 3, 'TEXT', 'MEDIUMTEXT', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (50, 7, 'image', 4, 'BINARY', 'MEDIUMBLOB', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (51, 8, 'productCode', 1, 'VARCHAR(15)', 'VARCHAR(15)', FALSE, TRUE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (52, 8, 'productName', 2, 'VARCHAR(70)', 'VARCHAR(70)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (54, 8, 'productScale', 4, 'VARCHAR(10)', 'VARCHAR(10)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (55, 8, 'productVendor', 5, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (56, 8, 'productDescription', 6, 'TEXT', 'TEXT', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (57, 8, 'quantityInStock', 7, 'INTEGER', 'SMALLINT', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (58, 8, 'buyPrice', 8, 'DECIMAL', 'DECIMAL(10, 2)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (59, 8, 'MSRP', 9, 'DECIMAL', 'DECIMAL(10, 2)', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (60, 9, 'customernumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (61, 9, 'contactlastname', 2, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (62, 9, 'contactfirstname', 3, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (63, 9, 'phone', 4, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (64, 9, 'addressline1', 5, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (65, 9, 'addressline2', 6, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (66, 9, 'city', 7, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (67, 9, 'state', 8, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (68, 9, 'postalcode', 9, 'VARCHAR(15)', 'VARCHAR(15)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (69, 9, 'country', 10, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (73, 10, 'text', 4, 'VARCHAR(200)', 'VARCHAR(200)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (74, 10, 'date', 5, 'TIMESTAMP', 'TIMESTAMP', FALSE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (75, 11, 'employeenumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (76, 11, 'lastname', 2, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (77, 11, 'firstname', 3, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (78, 11, 'email', 4, 'VARCHAR(100)', 'VARCHAR(100)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (79, 12, 'productcode', 1, 'VARCHAR(15)', 'VARCHAR(15)', FALSE, TRUE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (80, 12, 'productname', 2, 'VARCHAR(70)', 'VARCHAR(70)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (81, 12, 'productscale', 3, 'VARCHAR(10)', 'VARCHAR(10)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (82, 12, 'productvendor', 4, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (83, 12, 'productdescription', 5, 'TEXT', 'TEXT', TRUE, FALSE, FALSE, NULL, '2026-09-26 23:55:24.390129'),
    (19, 2, 'officeCode', 6, 'VARCHAR(10)', 'VARCHAR(10)', FALSE, FALSE, TRUE, 22, '2026-09-26 23:55:24.390129'),
    (12, 1, 'salesRepEmployeeNumber', 12, 'INTEGER', 'INTEGER', TRUE, FALSE, TRUE, 14, '2026-09-26 23:55:24.390129'),
    (20, 2, 'reportsTo', 7, 'INTEGER', 'INTEGER', TRUE, FALSE, TRUE, 14, '2026-09-26 23:55:24.390129'),
    (31, 4, 'orderNumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, TRUE, 36, '2026-09-26 23:55:24.390129'),
    (32, 4, 'productCode', 2, 'VARCHAR(15)', 'VARCHAR(15)', FALSE, TRUE, TRUE, 51, '2026-09-26 23:55:24.390129'),
    (42, 5, 'customerNumber', 7, 'INTEGER', 'INTEGER', FALSE, FALSE, TRUE, 1, '2026-09-26 23:55:24.390129'),
    (43, 6, 'customerNumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, TRUE, 1, '2026-09-26 23:55:24.390129'),
    (53, 8, 'productLine', 3, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, TRUE, 47, '2026-09-26 23:55:24.390129'),
    (70, 10, 'employeenumber', 1, 'INTEGER', 'INTEGER', FALSE, FALSE, TRUE, 75, '2026-09-26 23:55:24.390129'),
    (71, 10, 'customernumber', 2, 'INTEGER', 'INTEGER', FALSE, FALSE, TRUE, 60, '2026-09-26 23:55:24.390129'),
    (72, 10, 'productcode', 3, 'VARCHAR(15)', 'VARCHAR(15)', FALSE, FALSE, TRUE, 79, '2026-09-26 23:55:24.390129'),
    (84, 13, 'customernumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, TRUE, 60, '2026-09-26 23:55:24.390129'),
    (85, 13, 'productcode', 2, 'VARCHAR(15)', 'VARCHAR(15)', FALSE, TRUE, TRUE, 79, '2026-09-26 23:55:24.390129');

-- business_entity: 8 filas
INSERT INTO business_entity (entity_id, entity_name, entity_description, data_domain) VALUES
    (1, 'Cliente', 'Persona o empresa que compra productos de la compania o realiza contacto con el centro de servicio.', 'Datos de Cliente'),
    (2, 'Empleado', 'Persona que trabaja en la compania, como representante de ventas o agente de servicio al cliente.', 'Datos de Recurso Humano'),
    (3, 'Producto', 'Articulo del catalogo que la compania vende o que es objeto de consulta en servicio al cliente.', 'Datos de Producto'),
    (4, 'Linea de Producto', 'Categoria o familia a la que pertenece un producto.', 'Datos de Producto'),
    (5, 'Oficina', 'Sede fisica de la compania donde trabajan los empleados.', 'Datos Organizacionales'),
    (6, 'Orden de Compra', 'Pedido realizado por un cliente, compuesto por un encabezado y sus lineas de detalle.', 'Datos Transaccionales de Ventas'),
    (7, 'Pago', 'Registro de un pago realizado por un cliente asociado a sus ordenes de compra.', 'Datos Financieros'),
    (8, 'Llamada de Servicio', 'Registro de una llamada realizada por un cliente al centro de servicio al cliente.', 'Datos de Servicio al Cliente');

-- business_attribute: 47 filas
INSERT INTO business_attribute (attribute_id, entity_id, attribute_name, attribute_definition) VALUES
    (1, 1, 'Limite de Credito', 'Monto maximo de credito autorizado para el cliente.'),
    (2, 1, 'Pais de Cliente', 'Pais de domicilio del cliente.'),
    (3, 1, 'Codigo Postal de Cliente', 'Codigo postal del domicilio del cliente.'),
    (4, 1, 'Estado o Region de Cliente', 'Estado, departamento o region del domicilio del cliente.'),
    (5, 1, 'Ciudad de Cliente', 'Ciudad de residencia o domicilio del cliente.'),
    (6, 1, 'Direccion Linea 2', 'Segunda linea (complemento) de la direccion fisica del cliente.'),
    (7, 1, 'Direccion Linea 1', 'Primera linea de la direccion fisica del cliente.'),
    (8, 1, 'Telefono de Cliente', 'Numero telefonico de contacto del cliente.'),
    (9, 1, 'Nombre de Contacto', 'Nombre de la persona de contacto del cliente.'),
    (10, 1, 'Apellido de Contacto', 'Apellido de la persona de contacto del cliente.'),
    (11, 1, 'Nombre de Cliente', 'Nombre o razon social del cliente.'),
    (12, 1, 'Numero de Cliente', 'Identificador unico del cliente.'),
    (13, 2, 'Numero de Empleado Supervisor', 'Identificador del empleado al que este empleado reporta (jefe directo).'),
    (14, 2, 'Cargo', 'Cargo o puesto que ocupa el empleado en la compania.'),
    (15, 2, 'Extension Telefonica', 'Extension telefonica interna del empleado.'),
    (16, 2, 'Correo Electronico', 'Correo electronico de contacto del empleado.'),
    (17, 2, 'Nombre de Empleado', 'Nombre del empleado.'),
    (18, 2, 'Apellido de Empleado', 'Apellido del empleado.'),
    (19, 2, 'Numero de Empleado', 'Identificador unico del empleado.'),
    (20, 3, 'Precio Sugerido de Venta', 'Precio de venta al publico sugerido (MSRP).'),
    (21, 3, 'Precio de Compra', 'Precio al que la compania adquiere el producto.'),
    (22, 3, 'Cantidad en Inventario', 'Unidades disponibles del producto en inventario.'),
    (23, 3, 'Descripcion de Producto', 'Descripcion textual de las caracteristicas del producto.'),
    (24, 3, 'Fabricante o Proveedor', 'Fabricante o proveedor que suministra el producto.'),
    (25, 3, 'Escala de Producto', 'Escala de fabricacion del producto (ej. 1:10, 1:24).'),
    (26, 3, 'Nombre de Producto', 'Nombre comercial del producto.'),
    (27, 3, 'Codigo de Producto', 'Identificador unico del producto en el catalogo.'),
    (28, 4, 'Descripcion de Linea', 'Descripcion textual de la linea de producto.'),
    (29, 4, 'Codigo de Linea', 'Nombre/codigo de la linea o categoria de producto.'),
    (30, 5, 'Territorio', 'Territorio comercial al que pertenece la oficina.'),
    (31, 5, 'Pais de Oficina', 'Pais donde se ubica la oficina.'),
    (32, 5, 'Direccion de Oficina', 'Direccion fisica de la oficina.'),
    (33, 5, 'Telefono de Oficina', 'Numero telefonico principal de la oficina.'),
    (34, 5, 'Ciudad de Oficina', 'Ciudad donde se ubica la oficina.'),
    (35, 5, 'Codigo de Oficina', 'Identificador unico de la oficina o sede.'),
    (36, 6, 'Precio Unitario', 'Precio unitario acordado para el producto en esa orden.'),
    (37, 6, 'Cantidad Ordenada', 'Cantidad de unidades pedidas de un producto en la orden.'),
    (38, 6, 'Estado de Orden', 'Estado actual de la orden (ej. Shipped, Cancelled).'),
    (39, 6, 'Fecha de Envio', 'Fecha real de envio de la orden.'),
    (40, 6, 'Fecha Requerida', 'Fecha en la que el cliente requiere la entrega.'),
    (41, 6, 'Fecha de Orden', 'Fecha en que se realizo la orden.'),
    (42, 6, 'Numero de Orden', 'Identificador unico de la orden de compra.'),
    (43, 7, 'Monto de Pago', 'Valor monetario del pago realizado.'),
    (44, 7, 'Fecha de Pago', 'Fecha en que se registro el pago.'),
    (45, 7, 'Numero de Cheque', 'Identificador del cheque o comprobante de pago.'),
    (46, 8, 'Fecha de Llamada', 'Fecha y hora en que se realizo la llamada de servicio.'),
    (47, 8, 'Comentario de Llamada', 'Texto u observacion registrada durante la llamada de servicio.');

-- column_business_mapping: 78 filas
INSERT INTO column_business_mapping (mapping_id, column_id, attribute_id) VALUES
    (1, 12, 19),
    (2, 13, 1),
    (3, 11, 2),
    (4, 10, 3),
    (5, 9, 4),
    (6, 8, 5),
    (7, 7, 6),
    (8, 6, 7),
    (9, 5, 8),
    (10, 4, 9),
    (11, 3, 10),
    (12, 2, 11),
    (13, 1, 12),
    (14, 19, 35),
    (15, 20, 13),
    (16, 21, 14),
    (17, 17, 15),
    (18, 18, 16),
    (19, 16, 17),
    (20, 15, 18),
    (21, 14, 19),
    (22, 30, 30),
    (23, 28, 31),
    (24, 25, 32),
    (25, 24, 33),
    (26, 23, 34),
    (27, 22, 35),
    (28, 34, 36),
    (29, 33, 37),
    (30, 32, 27),
    (31, 31, 42),
    (32, 42, 12),
    (33, 40, 38),
    (34, 39, 39),
    (35, 38, 40),
    (36, 37, 41),
    (37, 36, 42),
    (38, 46, 43),
    (39, 45, 44),
    (40, 44, 45),
    (41, 43, 12),
    (42, 48, 28),
    (43, 47, 29),
    (44, 53, 29),
    (45, 59, 20),
    (46, 58, 21),
    (47, 57, 22),
    (48, 56, 23),
    (49, 55, 24),
    (50, 54, 25),
    (51, 52, 26),
    (52, 51, 27),
    (53, 69, 2),
    (54, 68, 3),
    (55, 67, 4),
    (56, 66, 5),
    (57, 65, 6),
    (58, 64, 7),
    (59, 63, 8),
    (60, 62, 9),
    (61, 61, 10),
    (62, 60, 12),
    (63, 74, 46),
    (64, 73, 47),
    (65, 72, 27),
    (66, 71, 12),
    (67, 70, 19),
    (68, 78, 16),
    (69, 77, 17),
    (70, 76, 18),
    (71, 75, 19),
    (72, 83, 23),
    (73, 82, 24),
    (74, 81, 25),
    (75, 80, 26),
    (76, 79, 27),
    (77, 85, 27),
    (78, 84, 12);

-- dw_object: 11 filas
INSERT INTO dw_object (dw_object_id, object_name, object_type, grain, description, is_conformed, scd_type, scd_justificacion, row_count, loaded_at) VALUES
    (1, 'dim_cliente', 'DIMENSION', NULL, 'Dimension de cliente. Conformada entre classicmodels y customerservice, que solapan al 100% por customerNumber. Las banderas presente_en_ventas y presente_en_servicio indican en que fuente aparece cada cliente.', TRUE, 'TIPO_1', 'El origen es un snapshot estatico sin captura de cambios, de modo que no hay versiones que preservar. Con un feed incremental seria la primera candidata a TIPO 2: el limite de credito y la direccion cambian y afectan el analisis historico.', 122, '2026-09-26 23:55:35.796622'),
    (2, 'dim_empleado', 'DIMENSION', NULL, 'Dimension de empleado. NO conformada: las dos fuentes tienen solape 0% en la llave. Usa llave de negocio compuesta (numero_empleado, sistema_origen) para que ambas poblaciones convivan sin colisionar. Tiene dos miembros especiales: -1 Desconocido y -2 Sin asignar.', FALSE, 'TIPO_1', 'El origen no registra cambios de cargo ni de oficina, asi que no hay transiciones que versionar.', 55, '2026-09-26 23:55:35.796622'),
    (3, 'dim_estado_orden', 'DIMENSION', NULL, 'Dimension de estado de la orden. es_efectiva distingue las ventas cerradas de las canceladas, en disputa o en espera.', FALSE, 'TIPO_1', 'Dimension derivada de un dominio cerrado de seis valores; no cambia entre cargas.', 6, '2026-09-26 23:55:35.796622'),
    (4, 'dim_lote_carga', 'DIMENSION', NULL, 'Dimension de auditoria. La capa 7 registra cada carga en la misma transaccion que los datos, y cada fila de las dimensiones y los hechos apunta con lote_carga_key a la carga que la escribio por ultima vez. Dice desde que corrida de staging se cargo cada rama; el proceso de hechos la consulta para no cargar hechos sobre dimensiones de otra corrida.', FALSE, 'TIPO_1', 'Una fila por carga. Solo cambia si una corrida retomada vuelve a cargar: entonces se sobrescriben su fecha y su conteo de filas.', 2, '2026-09-26 23:55:35.796622'),
    (5, 'dim_oficina', 'DIMENSION', NULL, 'Dimension de oficina. Exclusiva de classicmodels: la sede desde la que trabaja el representante de ventas. Tiene dos miembros especiales: -1 Desconocida y -2 Sin asignar.', FALSE, 'TIPO_1', 'Catalogo de siete sedes, estable y sin historial en el origen.', 9, '2026-09-26 23:55:35.796622'),
    (6, 'dim_producto', 'DIMENSION', NULL, 'Dimension de producto. Conformada entre las dos fuentes, que solapan al 100% por productCode. Incluye la linea de producto desnormalizada.', TRUE, 'TIPO_1', 'Mismo motivo que dim_cliente. Con datos vivos convendria TIPO 2 para que el margen de una venta antigua use el precio de compra vigente entonces, no el de hoy.', 110, '2026-09-26 23:55:35.796622'),
    (7, 'dim_tiempo', 'DIMENSION', NULL, 'Dimension de tiempo generada dia a dia, por anios completos, sobre el periodo que cubren las ventas y las llamadas (2003 a 2005 con los datos actuales). Conformada: la comparten los dos hechos.', TRUE, 'TIPO_1', 'Dimension generada y deterministica: una fecha nunca cambia de atributos, asi que el concepto de historial no aplica.', 1096, '2026-09-26 23:55:35.796622'),
    (8, 'fact_llamadas_servicio', 'FACT', 'Una llamada al centro de servicio al cliente.', 'Hecho secundario. Registra cada llamada de customerservice, relacionada con el cliente que llamo, el producto consultado y el agente que atendio.', FALSE, NULL, NULL, 108, '2026-09-26 23:55:35.796622'),
    (9, 'fact_ventas', 'FACT', 'Una linea de una orden de compra.', 'Hecho principal del almacen. Registra cada linea de detalle de las ordenes de classicmodels, con sus medidas de cantidad, monto, costo y margen.', FALSE, NULL, NULL, 2996, '2026-09-26 23:55:35.796622'),
    (10, 'vw_interaccion_cliente_producto', 'VIEW', 'Cliente x producto x mes.', 'Data mart (schema dm) que cruza los dos hechos al grano cliente-producto-mes. Responde que productos generan mas llamadas por unidad vendida, pregunta que ninguna fuente contesta por si sola.', FALSE, NULL, NULL, 2964, '2026-09-26 23:55:35.796622'),
    (11, 'vw_ventas_mensuales_linea', 'VIEW', 'Mes x linea de producto.', 'Data mart (schema dm) de desempeno comercial: ordenes, unidades, monto y margen por mes y linea de producto, solo ventas efectivas.', FALSE, NULL, NULL, 180, '2026-09-26 23:55:35.796622');

-- dw_measure: 9 filas
INSERT INTO dw_measure (dw_measure_id, dw_object_id, measure_name, data_type, additivity, formula, description) VALUES
    (1, 8, 'cantidad_llamadas', 'SMALLINT', 'ADITIVA', '1', 'Contador de llamadas. Permite sumar llamadas en cualquier dimension.'),
    (2, 8, 'longitud_texto', 'INTEGER', 'ADITIVA', 'length(cs_customer_calls.text)', 'Longitud de la nota del agente, como proxy de complejidad del caso.'),
    (3, 9, 'cantidad_ordenada', 'INTEGER', 'ADITIVA', 'orderdetails.quantityOrdered', 'Unidades del producto pedidas en la linea.'),
    (4, 9, 'precio_unitario', 'NUMERIC(12, 2)', 'NO_ADITIVA', 'orderdetails.priceEach', 'Precio pactado por unidad. No se suma: se promedia ponderado.'),
    (5, 9, 'monto_linea', 'NUMERIC(14, 2)', 'ADITIVA', 'quantityOrdered * priceEach', 'Valor facturado de la linea. Es la medida central del almacen.'),
    (6, 9, 'costo_linea', 'NUMERIC(14, 2)', 'ADITIVA', 'quantityOrdered * products.buyPrice', 'Costo de adquisicion de las unidades vendidas.'),
    (7, 9, 'margen_linea', 'NUMERIC(14, 2)', 'ADITIVA', 'monto_linea - costo_linea', 'Utilidad bruta de la linea.'),
    (8, 9, 'precio_msrp', 'NUMERIC(12, 2)', 'NO_ADITIVA', 'products.MSRP', 'Precio sugerido de venta. Sirve para medir descuento aplicado.'),
    (9, 9, 'dias_hasta_envio', 'SMALLINT', 'SEMI_ADITIVA', 'orders.shippedDate - orders.orderDate', 'Dias entre el pedido y el despacho. Se promedia, no se suma. NULL en las ordenes que no se despacharon.');

-- dw_attribute: 81 filas
INSERT INTO dw_attribute (dw_attribute_id, dw_object_id, attribute_name, data_type, attribute_role, description) VALUES
    (1, 1, 'cliente_key', 'INTEGER', 'SURROGATE_KEY', NULL),
    (2, 1, 'numero_cliente', 'INTEGER', 'BUSINESS_KEY', NULL),
    (3, 1, 'nombre_cliente', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (4, 1, 'contacto_nombre', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (5, 1, 'contacto_apellido', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (6, 1, 'telefono', 'VARCHAR(50)', 'DESCRIPTIVE', NULL),
    (7, 1, 'direccion_completa', 'VARCHAR(220)', 'DESCRIPTIVE', NULL),
    (8, 1, 'ciudad', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (9, 1, 'estado_region', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (10, 1, 'codigo_postal', 'VARCHAR(20)', 'DESCRIPTIVE', NULL),
    (11, 1, 'pais', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (12, 1, 'limite_credito', 'NUMERIC(12, 2)', 'DESCRIPTIVE', NULL),
    (13, 1, 'presente_en_ventas', 'BOOLEAN', 'FLAG', NULL),
    (14, 1, 'presente_en_servicio', 'BOOLEAN', 'FLAG', NULL),
    (15, 1, 'lote_carga_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (16, 2, 'empleado_key', 'INTEGER', 'SURROGATE_KEY', NULL),
    (17, 2, 'numero_empleado', 'INTEGER', 'BUSINESS_KEY', NULL),
    (18, 2, 'sistema_origen', 'VARCHAR(20)', 'DESCRIPTIVE', NULL),
    (19, 2, 'nombre', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (20, 2, 'apellido', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (21, 2, 'email', 'VARCHAR(140)', 'DESCRIPTIVE', NULL),
    (22, 2, 'cargo', 'VARCHAR(80)', 'DESCRIPTIVE', NULL),
    (23, 2, 'numero_oficina', 'VARCHAR(20)', 'DESCRIPTIVE', NULL),
    (24, 2, 'lote_carga_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (25, 3, 'estado_key', 'INTEGER', 'SURROGATE_KEY', NULL),
    (26, 3, 'estado', 'VARCHAR(30)', 'BUSINESS_KEY', NULL),
    (27, 3, 'es_efectiva', 'BOOLEAN', 'FLAG', NULL),
    (28, 3, 'lote_carga_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (29, 4, 'lote_carga_key', 'INTEGER', 'SURROGATE_KEY', NULL),
    (30, 4, 'proceso', 'VARCHAR(20)', 'DESCRIPTIVE', NULL),
    (31, 4, 'run_staging', 'INTEGER', 'DESCRIPTIVE', NULL),
    (32, 4, 'cargado_en', 'TIMESTAMP', 'DESCRIPTIVE', NULL),
    (33, 4, 'filas', 'INTEGER', 'DESCRIPTIVE', NULL),
    (34, 5, 'oficina_key', 'INTEGER', 'SURROGATE_KEY', NULL),
    (35, 5, 'codigo_oficina', 'VARCHAR(20)', 'BUSINESS_KEY', NULL),
    (36, 5, 'ciudad', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (37, 5, 'pais', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (38, 5, 'region', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (39, 5, 'territorio', 'VARCHAR(20)', 'DESCRIPTIVE', NULL),
    (40, 5, 'lote_carga_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (41, 6, 'producto_key', 'INTEGER', 'SURROGATE_KEY', NULL),
    (42, 6, 'codigo_producto', 'VARCHAR(20)', 'BUSINESS_KEY', NULL),
    (43, 6, 'nombre_producto', 'VARCHAR(140)', 'DESCRIPTIVE', NULL),
    (44, 6, 'linea_producto', 'VARCHAR(60)', 'DESCRIPTIVE', NULL),
    (45, 6, 'descripcion_linea', 'TEXT', 'DESCRIPTIVE', NULL),
    (46, 6, 'escala', 'VARCHAR(20)', 'DESCRIPTIVE', NULL),
    (47, 6, 'proveedor', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (48, 6, 'precio_compra', 'NUMERIC(12, 2)', 'DESCRIPTIVE', NULL),
    (49, 6, 'precio_msrp', 'NUMERIC(12, 2)', 'DESCRIPTIVE', NULL),
    (50, 6, 'presente_en_ventas', 'BOOLEAN', 'FLAG', NULL),
    (51, 6, 'presente_en_servicio', 'BOOLEAN', 'FLAG', NULL),
    (52, 6, 'lote_carga_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (53, 7, 'tiempo_key', 'INTEGER', 'SURROGATE_KEY', NULL),
    (54, 7, 'fecha', 'DATE', 'BUSINESS_KEY', NULL),
    (55, 7, 'anio', 'SMALLINT', 'DESCRIPTIVE', NULL),
    (56, 7, 'trimestre', 'SMALLINT', 'DESCRIPTIVE', NULL),
    (57, 7, 'mes', 'SMALLINT', 'DESCRIPTIVE', NULL),
    (58, 7, 'nombre_mes', 'VARCHAR(12)', 'DESCRIPTIVE', NULL),
    (59, 7, 'dia', 'SMALLINT', 'DESCRIPTIVE', NULL),
    (60, 7, 'dia_semana', 'SMALLINT', 'DESCRIPTIVE', NULL),
    (61, 7, 'nombre_dia', 'VARCHAR(12)', 'DESCRIPTIVE', NULL),
    (62, 7, 'es_fin_semana', 'BOOLEAN', 'FLAG', NULL),
    (63, 7, 'anio_mes', 'CHAR(7)', 'DESCRIPTIVE', NULL),
    (64, 7, 'lote_carga_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (65, 8, 'llamada_key', 'BIGINT', 'SURROGATE_KEY', NULL),
    (66, 8, 'tiempo_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (67, 8, 'cliente_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (68, 8, 'producto_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (69, 8, 'empleado_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (70, 8, 'texto_llamada', 'TEXT', 'DEGENERATE', NULL),
    (71, 8, 'lote_carga_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (72, 9, 'venta_key', 'BIGINT', 'SURROGATE_KEY', NULL),
    (73, 9, 'tiempo_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (74, 9, 'cliente_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (75, 9, 'producto_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (76, 9, 'empleado_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (77, 9, 'oficina_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (78, 9, 'estado_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (79, 9, 'numero_orden', 'INTEGER', 'DEGENERATE', NULL),
    (80, 9, 'numero_linea', 'SMALLINT', 'DEGENERATE', NULL),
    (81, 9, 'lote_carga_key', 'INTEGER', 'FOREIGN_KEY', NULL);

-- dw_lineage: 68 filas
INSERT INTO dw_lineage (dw_lineage_id, source_column_id, target_measure_id, target_attribute_id, transformation_rule) VALUES
    (1, 1, NULL, 2, 'llave de negocio, copia directa'),
    (2, 2, NULL, 3, 'copia directa'),
    (3, 4, NULL, 4, 'copia directa'),
    (4, 3, NULL, 5, 'copia directa'),
    (5, 5, NULL, 6, 'copia directa'),
    (6, 6, NULL, 7, 'concatenacion: addressLine1 + addressLine2 (esta ultima nula en 81,97%)'),
    (7, 7, NULL, 7, 'concatenacion: segunda linea de la direccion'),
    (8, 8, NULL, 8, 'copia directa'),
    (9, 9, NULL, 9, 'copia directa'),
    (10, 10, NULL, 10, 'copia directa'),
    (11, 11, NULL, 11, 'copia directa'),
    (12, 13, NULL, 12, 'copia directa'),
    (13, 1, NULL, 13, 'bandera: existe en classicmodels'),
    (14, 60, NULL, 14, 'bandera: existe en customerservice'),
    (15, 14, NULL, 17, 'llave de negocio compuesta con sistema_origen'),
    (16, 75, NULL, 17, 'union: agentes de customerservice'),
    (17, 16, NULL, 19, 'union de employees y cs_employees'),
    (18, 77, NULL, 19, 'union: agentes de customerservice'),
    (19, 15, NULL, 20, 'union de employees y cs_employees'),
    (20, 76, NULL, 20, 'union: agentes de customerservice'),
    (21, 18, NULL, 21, 'union de employees y cs_employees'),
    (22, 78, NULL, 21, 'union: agentes de customerservice'),
    (23, 21, NULL, 22, 'de classicmodels; constante para los agentes de servicio'),
    (24, 19, NULL, 23, 'solo classicmodels; NULL para agentes de servicio'),
    (25, 40, NULL, 26, 'valores distintos de orders.status'),
    (26, 40, NULL, 27, 'derivada: FALSE si status es Cancelled, Disputed u On Hold'),
    (27, 22, NULL, 35, 'llave de negocio, copia directa'),
    (28, 23, NULL, 36, 'copia directa'),
    (29, 28, NULL, 37, 'copia directa'),
    (30, 27, NULL, 38, 'copia directa'),
    (31, 30, NULL, 39, 'copia directa'),
    (32, 51, NULL, 42, 'llave de negocio, copia directa'),
    (33, 52, NULL, 43, 'copia directa'),
    (34, 53, NULL, 44, 'copia directa'),
    (35, 48, NULL, 45, 'desnormalizacion desde productlines'),
    (36, 54, NULL, 46, 'copia directa'),
    (37, 55, NULL, 47, 'copia directa'),
    (38, 58, NULL, 48, 'copia directa'),
    (39, 59, NULL, 49, 'copia directa'),
    (40, 51, NULL, 50, 'bandera: existe en classicmodels'),
    (41, 79, NULL, 51, 'bandera: existe en customerservice'),
    (42, 74, NULL, 66, 'lookup: date -> tiempo_key'),
    (43, 71, NULL, 67, 'lookup: customernumber -> cliente_key'),
    (44, 72, NULL, 68, 'lookup: productcode -> producto_key'),
    (45, 70, NULL, 69, 'lookup: (employeenumber, ''customerservice'') -> empleado_key'),
    (46, 73, NULL, 70, 'dimension degenerada'),
    (47, 71, 1, NULL, 'constante 1 por fila'),
    (48, 73, 2, NULL, 'calculo: length(text)'),
    (49, 37, NULL, 73, 'lookup: orderDate -> tiempo_key'),
    (50, 42, NULL, 74, 'lookup: customerNumber -> cliente_key'),
    (51, 32, NULL, 75, 'lookup: productCode -> producto_key'),
    (52, 12, NULL, 76, 'lookup del vendedor del cliente; -2 Sin asignar si no tiene vendedor, -1 Desconocido si su vendedor no llego al almacen'),
    (53, 19, NULL, 77, 'lookup de la oficina del vendedor; -2 Sin asignar si el cliente no tiene vendedor, -1 Desconocido si el vendedor no llego al almacen'),
    (54, 40, NULL, 78, 'lookup: status -> estado_key'),
    (55, 36, NULL, 79, 'dimension degenerada'),
    (56, 35, NULL, 80, 'dimension degenerada'),
    (57, 33, 3, NULL, 'copia directa'),
    (58, 34, 4, NULL, 'copia directa'),
    (59, 34, 5, NULL, 'calculo: quantityOrdered * priceEach'),
    (60, 33, 5, NULL, 'calculo: quantityOrdered * priceEach'),
    (61, 58, 6, NULL, 'calculo: quantityOrdered * buyPrice'),
    (62, 33, 6, NULL, 'calculo: quantityOrdered * buyPrice'),
    (63, 58, 7, NULL, 'calculo: monto_linea - costo_linea'),
    (64, 33, 7, NULL, 'calculo: monto_linea - costo_linea'),
    (65, 34, 7, NULL, 'calculo: monto_linea - costo_linea'),
    (66, 59, 8, NULL, 'copia directa'),
    (67, 39, 9, NULL, 'calculo: shippedDate - orderDate; NULL si no se despacho'),
    (68, 37, 9, NULL, 'calculo: shippedDate - orderDate');

-- etl_process: 3 filas
INSERT INTO etl_process (etl_process_id, process_name, tool, source_systems, target_system, description) VALUES
    (1, 'etl_dw_staging', 'Python 3.11 + SQLAlchemy 2.1 + pandas 3.0', 'classicmodels (MySQL), customerservice (PostgreSQL)', 'staging (PostgreSQL)', 'Capas 1 a 4: extrae las 13 tablas de las dos fuentes una sola vez, las perfila, evalua calidad tecnica y de negocio, y separa fisicamente limpios de rechazados.'),
    (2, 'etl_dw_dimensions', 'Python 3.11 + SQLAlchemy 2.1 + pandas 3.0', 'staging_dw.stg_clean de la ultima corrida de staging exitosa (etl_execution.run_origen); las fuentes no se releen', 'dw (PostgreSQL)', 'Capas 5 a 7 para el modelo de dimensiones: conforma por area tematica desde Clean Staging y carga las seis dimensiones.'),
    (3, 'etl_dw_facts', 'Python 3.11 + SQLAlchemy 2.1 + pandas 3.0', 'staging_dw.stg_clean de la ultima corrida de staging exitosa (etl_execution.run_origen); las fuentes no se releen', 'dw (PostgreSQL)', 'Capas 5 a 7 para el modelo de hechos: conforma ventas y servicio desde Clean Staging, resuelve llaves subrogadas y carga los dos hechos.');

-- etl_execution: 11 filas
INSERT INTO etl_execution (etl_execution_id, etl_process_id, run_id, run_origen, started_at, finished_at, status, rows_read, rows_written, rows_rejected, error_message) VALUES
    (1, 1, 1, NULL, '2026-09-26 23:55:27.835568', '2026-09-26 23:55:30.726210', 'OK', 4335, 4335, 0, NULL),
    (2, 2, 2, 1, '2026-09-26 23:55:31.367386', '2026-09-26 23:55:32.584238', 'OK', 1394, 1394, 0, NULL),
    (3, 3, 3, 1, '2026-09-26 23:55:33.189778', '2026-09-26 23:55:35.420279', 'OK', 3104, 3104, 0, NULL),
    (4, 1, 4, NULL, '2026-09-26 23:55:40.163538', '2026-09-26 23:55:42.977858', 'OK', 4335, 4335, 0, NULL),
    (5, 2, 5, 4, '2026-09-26 23:55:44.358645', '2026-09-26 23:55:45.794294', 'OK', 1394, 1394, 0, NULL),
    (6, 3, 6, 4, '2026-09-26 23:55:46.487467', '2026-09-26 23:55:48.873146', 'OK', 3104, 3104, 0, NULL),
    (7, 1, 7, NULL, '2026-09-26 23:55:50.818893', '2026-09-26 23:55:52.650384', 'ERROR', NULL, NULL, NULL, 'RuntimeError: Fault injected after layer 3 (PIPELINE_FAULT=error@3)'),
    (8, 1, 7, NULL, '2026-09-26 23:55:53.303644', '2026-09-26 23:55:54.519660', 'OK', 4335, 4335, 0, NULL),
    (9, 2, 8, 7, '2026-09-26 23:55:55.353863', '2026-09-26 23:55:56.936319', 'ERROR', NULL, NULL, NULL, 'Abandonada: el proceso termino sin cerrar la corrida'),
    (10, 2, 8, 7, '2026-09-26 23:55:56.945206', '2026-09-26 23:55:57.411345', 'OK', 1394, 1394, 0, NULL),
    (11, 3, 9, 7, '2026-09-26 23:55:58.145134', '2026-09-26 23:56:00.484648', 'OK', 3104, 3104, 0, NULL);

-- dq_rule: 27 filas
INSERT INTO dq_rule (dq_rule_id, rule_name, rule_type, criterio_dama, clase_dq, capa, source_column_id, expression, severity, resolution) VALUES
    (1, 'consistencia_entre_fuentes_cliente', 'CONFORMIDAD', 'CONSISTENCIA', 'NEGOCIO', 'DATA_QUALITY', 1, 'cs_customers coincide con customers en telefono, ciudad, pais y codigo postal', 'ADVERTENCIA', 'Si difieren, classicmodels es la fuente autoritativa de dim_cliente; la diferencia queda trazada.'),
    (2, 'cliente_conformidad_fuentes', 'CONFORMIDAD', 'CONSISTENCIA', 'NEGOCIO', 'TRANSFORMATION', 1, 'Todo customerNumber de classicmodels existe en cs_customers', 'BLOQUEANTE', 'Permite que dim_cliente sea conformada y que los dos hechos la compartan.'),
    (3, 'cliente_direccion_linea2_nula', 'COMPLETITUD', 'EXHAUSTIVIDAD', 'TECNICA', 'TRANSFORMATION', 7, 'pct_nulos(addressLine2) < 50', 'INFORMATIVA', 'Se consolida con addressLine1 en el atributo direccion_completa.'),
    (4, 'empleado_conformidad_fuentes', 'CONFORMIDAD', 'CONSISTENCIA', 'NEGOCIO', 'TRANSFORMATION', 14, 'Numeros de empleado compartidos entre las dos fuentes', 'INFORMATIVA', 'Las dos poblaciones no se solapan: dim_empleado usa llave de negocio compuesta (numero_empleado, sistema_origen) en vez de fusionarlas.'),
    (5, 'formato_email', 'FORMATO', 'EXACTITUD', 'TECNICA', 'DATA_QUALITY', 18, 'email contiene @ y un dominio con punto', 'ADVERTENCIA', 'El registro pasa; la anomalia queda en el reporte de transacciones malas.'),
    (6, 'valores_positivos', 'RANGO', 'EXACTITUD', 'NEGOCIO', 'DATA_QUALITY', 33, 'cantidades, precios, costos y pagos > 0; limite de credito >= 0', 'BLOQUEANTE', 'El registro va a la pila de rechazados.'),
    (7, 'orden_con_lineas_rechazadas', 'COMPLETITUD', 'EXHAUSTIVIDAD', 'NEGOCIO', 'DATA_QUALITY', 36, 'Toda orden que pasa conserva todas sus lineas (se evalua despues de padre_rechazado)', 'ADVERTENCIA', 'La orden se carga con las lineas que pasaron; la advertencia avisa que su total y su numero de lineas en el almacen quedan por debajo de la fuente.'),
    (8, 'fecha_no_futura', 'RANGO', 'EXACTITUD', 'NEGOCIO', 'DATA_QUALITY', 37, 'orderDate, paymentDate y la fecha de la llamada <= fecha de la carga', 'BLOQUEANTE', 'El registro va a la pila de rechazados: un evento no puede ocurrir despues de la carga. dim_tiempo se genera sobre el periodo que cubren las ventas y las llamadas, asi que una fecha errada lo extenderia.'),
    (9, 'secuencia_de_fechas', 'COHERENCIA', 'EXACTITUD', 'NEGOCIO', 'DATA_QUALITY', 39, 'shippedDate >= orderDate y requiredDate >= orderDate', 'BLOQUEANTE', 'El registro va a la pila de rechazados.'),
    (10, 'orden_fecha_envio_nula', 'COMPLETITUD', 'EXHAUSTIVIDAD', 'TECNICA', 'TRANSFORMATION', 39, 'shippedDate no nula', 'INFORMATIVA', 'Las ordenes aun no despachadas quedan con dias_hasta_envio NULL; dim_estado_orden explica el motivo.'),
    (11, 'envio_consistente_con_estado', 'COHERENCIA', 'EXACTITUD', 'NEGOCIO', 'DATA_QUALITY', 40, 'status = ''Shipped'' implica shippedDate no nula', 'BLOQUEANTE', 'El registro va a la pila de rechazados.'),
    (12, 'estado_orden_no_efectivo', 'INTEGRIDAD', 'EXACTITUD', 'NEGOCIO', 'TRANSFORMATION', 40, 'status en (Cancelled, Disputed, On Hold) no es venta cerrada', 'INFORMATIVA', 'Se cargan todas las ordenes; dim_estado_orden.es_efectiva permite excluirlas de los reportes sin borrarlas del almacen.'),
    (13, 'orden_comentarios_nulos', 'COMPLETITUD', 'RELEVANCIA', 'NEGOCIO', 'TRANSFORMATION', 41, 'pct_nulos(comments) < 50', 'INFORMATIVA', 'Texto libre sin valor analitico: no se lleva a fact_ventas.'),
    (14, 'productline_columnas_vacias', 'COMPLETITUD', 'EXHAUSTIVIDAD', 'TECNICA', 'TRANSFORMATION', 49, 'COUNT(htmlDescription) = 0 AND COUNT(image) = 0', 'INFORMATIVA', 'Las dos columnas se extraen (traer todo) pero no pasan a dim_producto.'),
    (15, 'consistencia_entre_fuentes_producto', 'CONFORMIDAD', 'CONSISTENCIA', 'NEGOCIO', 'DATA_QUALITY', 51, 'cs_products coincide con products en nombre, escala y proveedor', 'ADVERTENCIA', 'Si difieren, classicmodels es la fuente autoritativa de dim_producto; la diferencia queda trazada.'),
    (16, 'producto_conformidad_fuentes', 'CONFORMIDAD', 'CONSISTENCIA', 'NEGOCIO', 'TRANSFORMATION', 51, 'Todo productCode de classicmodels existe en cs_products', 'BLOQUEANTE', 'Permite que dim_producto sea conformada y que los dos hechos la compartan.'),
    (17, 'precio_sugerido_coherente', 'COHERENCIA', 'EXACTITUD', 'NEGOCIO', 'DATA_QUALITY', 59, 'MSRP >= buyPrice', 'ADVERTENCIA', 'El registro pasa; se traza para revision del area comercial.'),
    (18, 'cliente_con_vendedor', 'COMPLETITUD', 'EXHAUSTIVIDAD', 'NEGOCIO', 'DATA_QUALITY', 12, 'salesRepEmployeeNumber no nulo', 'ADVERTENCIA', 'La fuente admite el nulo (tecnicamente valido), pero el negocio espera que todo cliente tenga vendedor. El registro pasa y sus ventas apuntan al miembro especial -2 Sin asignar de dim_empleado y dim_oficina.'),
    (19, 'referencia_opcional_no_resuelta', 'INTEGRIDAD', 'CONSISTENCIA', 'NEGOCIO', 'DATA_QUALITY', 12, 'Las referencias opcionales (vendedor del cliente, jefe del empleado) apuntan a un registro existente y no rechazado', 'ADVERTENCIA', 'El registro pasa: el rechazo no se propaga por una referencia opcional. Sus ventas apuntan al miembro especial -1 Desconocido de dim_empleado y dim_oficina; reportsTo no se modela.'),
    (20, 'venta_vendedor_no_resuelto', 'COMPLETITUD', 'EXHAUSTIVIDAD', 'NEGOCIO', 'TRANSFORMATION', 12, 'Toda linea de venta resuelve el vendedor y la oficina del cliente', 'INFORMATIVA', 'La linea no queda con llave nula: apunta al miembro especial -2 Sin asignar si el cliente no tiene vendedor, o -1 Desconocido si su vendedor no llego al almacen.'),
    (21, 'campos_obligatorios', 'COMPLETITUD', 'EXHAUSTIVIDAD', 'TECNICA', 'DATA_QUALITY', NULL, 'Toda columna con is_nullable = FALSE en db_column tiene valor', 'BLOQUEANTE', 'El registro va a la pila de rechazados. Las columnas obligatorias se leen del repositorio de metadatos, no estan escritas en el ETL.'),
    (22, 'tipo_de_dato_valido', 'FORMATO', 'EXACTITUD', 'TECNICA', 'DATA_QUALITY', NULL, 'Las columnas de fecha se interpretan como fecha y las numericas como numero', 'BLOQUEANTE', 'El registro va a la pila de rechazados: un valor que no se puede interpretar no se puede transformar.'),
    (23, 'registro_duplicado', 'UNICIDAD', 'EXACTITUD', 'TECNICA', 'DATA_QUALITY', NULL, 'Ningun registro es copia exacta de otro con la misma llave de su tabla (la llave primaria; en cs_customer_calls, cliente, producto, agente y fecha)', 'BLOQUEANTE', 'La primera copia sigue y las demas van a la pila de rechazados: contarlas inflaria los hechos.'),
    (24, 'llave_duplicada', 'UNICIDAD', 'CONSISTENCIA', 'TECNICA', 'DATA_QUALITY', NULL, 'Ninguna llave aparece en dos registros con contenido distinto', 'BLOQUEANTE', 'Todas las versiones van a la pila de rechazados, porque nada dice cual es la correcta, y sus hijos las siguen (padre_rechazado).'),
    (25, 'integridad_referencial', 'INTEGRIDAD', 'CONSISTENCIA', 'NEGOCIO', 'DATA_QUALITY', NULL, 'Toda referencia obligatoria apunta a un registro existente, dentro de cada fuente y entre fuentes (llamadas contra el maestro de clientes y productos de classicmodels)', 'BLOQUEANTE', 'El registro va a la pila de rechazados: cargarlo produciria un hecho huerfano en el almacen.'),
    (26, 'padre_rechazado', 'INTEGRIDAD', 'CONSISTENCIA', 'NEGOCIO', 'DATA_QUALITY', NULL, 'Toda referencia obligatoria apunta a un registro que no fue rechazado (se evalua despues de las demas reglas)', 'BLOQUEANTE', 'El registro sigue a su padre a la pila de rechazados, en cascada (cliente -> ordenes -> lineas): si pasara, apuntaria a un miembro que no llega al almacen y detendria la carga de hechos.'),
    (27, 'almacen_frescura_de_carga', 'FRESCURA', 'OPORTUNIDAD', 'TECNICA', 'MONITOREO', NULL, 'now() - ultima carga exitosa en etl_execution < 24 horas', 'ADVERTENCIA', 'Si la ultima carga exitosa supera las 24 horas, los reportes estan mostrando datos vencidos y hay que relanzar el pipeline.');

-- dq_result: 78 filas
INSERT INTO dq_result (dq_result_id, dq_rule_id, etl_execution_id, evaluated_at, rows_evaluated, rows_failed, passed) VALUES
    (1, 21, 1, '2026-09-26 23:55:30.726210', 4335, 0, TRUE),
    (2, 18, 1, '2026-09-26 23:55:30.726210', 122, 22, FALSE),
    (3, 1, 1, '2026-09-26 23:55:30.726210', 122, 0, TRUE),
    (4, 15, 1, '2026-09-26 23:55:30.726210', 110, 0, TRUE),
    (5, 11, 1, '2026-09-26 23:55:30.726210', 326, 0, TRUE),
    (6, 8, 1, '2026-09-26 23:55:30.726210', 707, 0, TRUE),
    (7, 5, 1, '2026-09-26 23:55:30.726210', 53, 0, TRUE),
    (8, 25, 1, '2026-09-26 23:55:30.726210', 3937, 0, TRUE),
    (9, 24, 1, '2026-09-26 23:55:30.726210', 4335, 0, TRUE),
    (10, 7, 1, '2026-09-26 23:55:30.726210', 326, 0, TRUE),
    (11, 26, 1, '2026-09-26 23:55:30.726210', 3937, 0, TRUE),
    (12, 17, 1, '2026-09-26 23:55:30.726210', 110, 0, TRUE),
    (13, 19, 1, '2026-09-26 23:55:30.726210', 145, 0, TRUE),
    (14, 23, 1, '2026-09-26 23:55:30.726210', 4335, 0, TRUE),
    (15, 9, 1, '2026-09-26 23:55:30.726210', 326, 0, TRUE),
    (16, 22, 1, '2026-09-26 23:55:30.726210', 3935, 0, TRUE),
    (17, 6, 1, '2026-09-26 23:55:30.726210', 3501, 0, TRUE),
    (18, 2, 2, '2026-09-26 23:55:32.584238', 122, 0, TRUE),
    (19, 3, 2, '2026-09-26 23:55:32.584238', 122, 100, FALSE),
    (20, 4, 2, '2026-09-26 23:55:32.584238', 53, 0, TRUE),
    (21, 12, 2, '2026-09-26 23:55:32.584238', 6, 3, FALSE),
    (22, 14, 2, '2026-09-26 23:55:32.584238', 2, 2, FALSE),
    (23, 16, 2, '2026-09-26 23:55:32.584238', 110, 0, TRUE),
    (24, 13, 3, '2026-09-26 23:55:35.420279', 326, 246, FALSE),
    (25, 10, 3, '2026-09-26 23:55:35.420279', 2996, 141, FALSE),
    (26, 20, 3, '2026-09-26 23:55:35.420279', 2996, 0, TRUE),
    (27, 21, 4, '2026-09-26 23:55:42.977858', 4335, 0, TRUE),
    (28, 18, 4, '2026-09-26 23:55:42.977858', 122, 22, FALSE),
    (29, 1, 4, '2026-09-26 23:55:42.977858', 122, 0, TRUE),
    (30, 15, 4, '2026-09-26 23:55:42.977858', 110, 0, TRUE),
    (31, 11, 4, '2026-09-26 23:55:42.977858', 326, 0, TRUE),
    (32, 8, 4, '2026-09-26 23:55:42.977858', 707, 0, TRUE),
    (33, 5, 4, '2026-09-26 23:55:42.977858', 53, 0, TRUE),
    (34, 25, 4, '2026-09-26 23:55:42.977858', 3937, 0, TRUE),
    (35, 24, 4, '2026-09-26 23:55:42.977858', 4335, 0, TRUE),
    (36, 7, 4, '2026-09-26 23:55:42.977858', 326, 0, TRUE),
    (37, 26, 4, '2026-09-26 23:55:42.977858', 3937, 0, TRUE),
    (38, 17, 4, '2026-09-26 23:55:42.977858', 110, 0, TRUE),
    (39, 19, 4, '2026-09-26 23:55:42.977858', 145, 0, TRUE),
    (40, 23, 4, '2026-09-26 23:55:42.977858', 4335, 0, TRUE),
    (41, 9, 4, '2026-09-26 23:55:42.977858', 326, 0, TRUE),
    (42, 22, 4, '2026-09-26 23:55:42.977858', 3935, 0, TRUE),
    (43, 6, 4, '2026-09-26 23:55:42.977858', 3501, 0, TRUE),
    (44, 2, 5, '2026-09-26 23:55:45.794294', 122, 0, TRUE),
    (45, 3, 5, '2026-09-26 23:55:45.794294', 122, 100, FALSE),
    (46, 4, 5, '2026-09-26 23:55:45.794294', 53, 0, TRUE),
    (47, 12, 5, '2026-09-26 23:55:45.794294', 6, 3, FALSE),
    (48, 14, 5, '2026-09-26 23:55:45.794294', 2, 2, FALSE),
    (49, 16, 5, '2026-09-26 23:55:45.794294', 110, 0, TRUE),
    (50, 13, 6, '2026-09-26 23:55:48.873146', 326, 246, FALSE),
    (51, 10, 6, '2026-09-26 23:55:48.873146', 2996, 141, FALSE),
    (52, 20, 6, '2026-09-26 23:55:48.873146', 2996, 0, TRUE),
    (53, 21, 8, '2026-09-26 23:55:54.519660', 4335, 0, TRUE),
    (54, 18, 8, '2026-09-26 23:55:54.519660', 122, 22, FALSE),
    (55, 1, 8, '2026-09-26 23:55:54.519660', 122, 0, TRUE),
    (56, 15, 8, '2026-09-26 23:55:54.519660', 110, 0, TRUE),
    (57, 11, 8, '2026-09-26 23:55:54.519660', 326, 0, TRUE),
    (58, 8, 8, '2026-09-26 23:55:54.519660', 707, 0, TRUE),
    (59, 5, 8, '2026-09-26 23:55:54.519660', 53, 0, TRUE),
    (60, 25, 8, '2026-09-26 23:55:54.519660', 3937, 0, TRUE),
    (61, 24, 8, '2026-09-26 23:55:54.519660', 4335, 0, TRUE),
    (62, 7, 8, '2026-09-26 23:55:54.519660', 326, 0, TRUE),
    (63, 26, 8, '2026-09-26 23:55:54.519660', 3937, 0, TRUE),
    (64, 17, 8, '2026-09-26 23:55:54.519660', 110, 0, TRUE),
    (65, 19, 8, '2026-09-26 23:55:54.519660', 145, 0, TRUE),
    (66, 23, 8, '2026-09-26 23:55:54.519660', 4335, 0, TRUE),
    (67, 9, 8, '2026-09-26 23:55:54.519660', 326, 0, TRUE),
    (68, 22, 8, '2026-09-26 23:55:54.519660', 3935, 0, TRUE),
    (69, 6, 8, '2026-09-26 23:55:54.519660', 3501, 0, TRUE),
    (70, 2, 10, '2026-09-26 23:55:57.411345', 122, 0, TRUE),
    (71, 3, 10, '2026-09-26 23:55:57.411345', 122, 100, FALSE),
    (72, 4, 10, '2026-09-26 23:55:57.411345', 53, 0, TRUE),
    (73, 12, 10, '2026-09-26 23:55:57.411345', 6, 3, FALSE),
    (74, 14, 10, '2026-09-26 23:55:57.411345', 2, 2, FALSE),
    (75, 16, 10, '2026-09-26 23:55:57.411345', 110, 0, TRUE),
    (76, 13, 11, '2026-09-26 23:56:00.484648', 326, 246, FALSE),
    (77, 10, 11, '2026-09-26 23:56:00.484648', 2996, 141, FALSE),
    (78, 20, 11, '2026-09-26 23:56:00.484648', 2996, 0, TRUE);

-- usage_herramienta: 3 filas
INSERT INTO usage_herramienta (usage_herramienta_id, nombre, tipo, proposito, acceso) VALUES
    (1, 'Metabase', 'BI', 'Construye y sirve los seis reportes del dashboard. Es el unico consumidor de cara al usuario final.', 'LECTURA'),
    (2, 'ETL Python (staging, dimensiones y hechos)', 'ETL', 'Carga el almacen desde las capas de staging. Unico proceso con permiso de escritura sobre las tablas del modelo dimensional.', 'ESCRITURA'),
    (3, 'Scripts de validacion y backup', 'CLIENTE_SQL', 'Comparan totales contra las fuentes y generan los respaldos. Acceso de solo lectura, bajo demanda.', 'LECTURA');

-- usage_consulta: 8 filas
INSERT INTO usage_consulta (usage_consulta_id, nombre, usage_herramienta_id, proposito, frecuencia, nro_joins) VALUES
    (1, 'Ventas y margen por mes', 1, 'Evolucion mensual del monto vendido y el margen, solo ordenes efectivas.', 'DIARIA', 3),
    (2, 'Intensidad de servicio por producto', 1, 'Llamadas al centro de servicio por unidad vendida. Es el reporte que cruza las dos fuentes.', 'DIARIA', 1),
    (3, 'Margen por linea de producto', 1, 'Monto y margen agrupados por familia de producto.', 'DIARIA', 2),
    (4, 'Clientes: compras frente a llamadas', 1, 'Dispersion de cada cliente entre lo que compra y lo que consulta.', 'SEMANAL', 1),
    (5, 'Ventas por oficina', 1, 'Monto vendido segun la sede del representante asignado.', 'SEMANAL', 2),
    (6, 'Carga del centro de servicio por agente', 1, 'Llamadas atendidas por agente. Verifica que la llave compuesta de dim_empleado separa bien las dos poblaciones.', 'SEMANAL', 2),
    (7, 'Validacion contra fuentes', 3, 'Conciliacion del almacen con las fuentes: nueve verificaciones de que cada registro de las fuentes esta cargado o fue rechazado.', 'BAJO_DEMANDA', 8),
    (8, 'Carga de dimensiones y hechos', 2, 'Escritura de las ocho tablas del modelo dimensional y del registro de cada carga en la dimension de auditoria, desde staging.', 'BAJO_DEMANDA', 0);

-- usage_consulta_objeto: 27 filas
INSERT INTO usage_consulta_objeto (usage_consulta_id, dw_object_id) VALUES
    (1, 9),
    (1, 7),
    (1, 3),
    (2, 10),
    (3, 9),
    (3, 6),
    (4, 10),
    (5, 9),
    (5, 5),
    (6, 8),
    (6, 2),
    (7, 9),
    (7, 8),
    (7, 1),
    (7, 6),
    (7, 5),
    (7, 2),
    (7, 4),
    (8, 7),
    (8, 1),
    (8, 6),
    (8, 2),
    (8, 5),
    (8, 3),
    (8, 9),
    (8, 8),
    (8, 4);

-- usage_acceso_objeto: 9 filas
INSERT INTO usage_acceso_objeto (usage_acceso_id, dw_object_id, medido_en, lecturas_secuenciales, filas_leidas_secuencial, lecturas_por_indice, filas_insertadas, filas_actualizadas, filas_borradas) VALUES
    (1, 2, '2026-09-26 23:55:36.280174', 5, 165, 3159, 55, 0, 0),
    (2, 9, '2026-09-26 23:55:36.280174', 21, 8988, 0, 2996, 0, 0),
    (3, 1, '2026-09-26 23:55:36.280174', 6, 488, 3226, 122, 0, 0),
    (4, 6, '2026-09-26 23:55:36.280174', 7, 550, 3214, 110, 0, 0),
    (5, 5, '2026-09-26 23:55:36.280174', 4, 18, 3005, 9, 0, 0),
    (6, 8, '2026-09-26 23:55:36.280174', 14, 216, 0, 108, 0, 0),
    (7, 4, '2026-09-26 23:55:36.280174', 3, 3, 3106, 2, 0, 0),
    (8, 3, '2026-09-26 23:55:36.280174', 6, 24, 3002, 6, 0, 0),
    (9, 7, '2026-09-26 23:55:36.280174', 8, 6576, 4200, 1096, 0, 0);

-- Sync SERIAL sequences with the restored data
SELECT setval(pg_get_serial_sequence('data_source', 'source_id'), 2, true);
SELECT setval(pg_get_serial_sequence('db_table', 'table_id'), 13, true);
SELECT setval(pg_get_serial_sequence('db_column', 'column_id'), 85, true);
SELECT setval(pg_get_serial_sequence('business_entity', 'entity_id'), 8, true);
SELECT setval(pg_get_serial_sequence('business_attribute', 'attribute_id'), 47, true);
SELECT setval(pg_get_serial_sequence('column_business_mapping', 'mapping_id'), 78, true);
SELECT setval(pg_get_serial_sequence('dw_object', 'dw_object_id'), 11, true);
SELECT setval(pg_get_serial_sequence('dw_measure', 'dw_measure_id'), 9, true);
SELECT setval(pg_get_serial_sequence('dw_attribute', 'dw_attribute_id'), 81, true);
SELECT setval(pg_get_serial_sequence('dw_lineage', 'dw_lineage_id'), 68, true);
SELECT setval(pg_get_serial_sequence('etl_process', 'etl_process_id'), 3, true);
SELECT setval(pg_get_serial_sequence('etl_execution', 'etl_execution_id'), 11, true);
SELECT setval(pg_get_serial_sequence('dq_rule', 'dq_rule_id'), 27, true);
SELECT setval(pg_get_serial_sequence('dq_result', 'dq_result_id'), 78, true);
SELECT setval(pg_get_serial_sequence('usage_herramienta', 'usage_herramienta_id'), 3, true);
SELECT setval(pg_get_serial_sequence('usage_consulta', 'usage_consulta_id'), 8, true);
SELECT setval(pg_get_serial_sequence('usage_acceso_objeto', 'usage_acceso_id'), 9, true);
