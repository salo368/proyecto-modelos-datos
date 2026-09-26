-- ============================================================
-- Staging del ETL de metadatos tecnicos (Giordano - Data Integration
-- Blueprint and Modeling).
--
-- 4 capas fisicas y persistidas: Extract -> Data Quality -> Transform
-- -> Load Ready Publish. El Target Load final va sobre las tablas del
-- repositorio creadas en metadata_repository_ddl.sql.
--
-- Correr DESPUES de metadata_repository_ddl.sql, en la misma BD.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS staging;

-- Grano: una fila = una columna de una tabla de una fuente. La info a
-- nivel de tabla (row_count_approx, table_description) viaja
-- desnormalizada en la misma fila; se separa recien en Load Ready
-- Publish.

CREATE TABLE staging.stg_extract (
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

CREATE TABLE staging.stg_dq (
    LIKE staging.stg_extract INCLUDING ALL,
    dq_status  VARCHAR(20) NOT NULL,   -- 'OK' o 'RECHAZADO'
    dq_notes   TEXT
);

CREATE TABLE staging.stg_transform (
    LIKE staging.stg_extract INCLUDING ALL,
    native_data_type   VARCHAR(200),   -- tipo original antes de normalize_data_type()
    table_description  TEXT
);

CREATE TABLE staging.stg_loadready (
    LIKE staging.stg_transform INCLUDING ALL
);
