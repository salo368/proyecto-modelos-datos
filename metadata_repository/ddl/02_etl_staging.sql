-- ============================================================
-- Metadata repository - staging schema of the source-metadata ETL
--
-- etl/etl_source_metadata.py persists each stage here before the
-- final load into data_source / db_table / db_column:
--
--   stg_extract    raw data dictionary read from both sources
--   stg_dq         same rows plus a quality verdict (OK / RECHAZADO)
--   stg_transform  accepted rows with normalised types and descriptions
--   stg_loadready  final shape, ready for the target load
--
-- Grain: one row per column of a source table. Table-level fields
-- (row_count_approx, table_description) travel denormalised on each row.
-- Every run appends rows under its own run_id; nothing is truncated.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS staging;

CREATE TABLE IF NOT EXISTS staging.stg_extract (
    run_id            INTEGER NOT NULL,
    source_name       VARCHAR(100) NOT NULL,
    db_engine         VARCHAR(50)  NOT NULL,
    schema_name       VARCHAR(100) NOT NULL,
    table_name        VARCHAR(100) NOT NULL,
    row_count_approx  INTEGER,
    column_name       VARCHAR(100),
    ordinal_position  INTEGER,
    data_type         VARCHAR(200),
    is_nullable       BOOLEAN,
    is_primary_key    BOOLEAN,
    is_foreign_key    BOOLEAN,
    fk_ref_table      VARCHAR(100),
    fk_ref_column     VARCHAR(100),
    extracted_at      TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS staging.stg_dq (
    LIKE staging.stg_extract INCLUDING ALL,
    dq_status  VARCHAR(20) NOT NULL,   -- 'OK' | 'RECHAZADO'
    dq_notes   TEXT
);

CREATE TABLE IF NOT EXISTS staging.stg_transform (
    LIKE staging.stg_extract INCLUDING ALL,
    native_data_type   VARCHAR(200),   -- original type, before normalisation
    table_description  TEXT
);

CREATE TABLE IF NOT EXISTS staging.stg_loadready (
    LIKE staging.stg_transform INCLUDING ALL
);
