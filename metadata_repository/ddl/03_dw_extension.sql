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

-- Execution log: one row per run of each process.
CREATE TABLE IF NOT EXISTS etl_execution (
    etl_execution_id SERIAL PRIMARY KEY,
    etl_process_id   INTEGER NOT NULL REFERENCES etl_process(etl_process_id),
    run_id           INTEGER NOT NULL,
    started_at       TIMESTAMP NOT NULL,
    finished_at      TIMESTAMP,
    status           VARCHAR(20) NOT NULL,
    rows_read        INTEGER,
    rows_written     INTEGER,
    rows_rejected    INTEGER,
    error_message    TEXT,
    CHECK (status IN ('EN_CURSO', 'OK', 'ERROR'))
);

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
