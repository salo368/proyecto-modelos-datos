-- ============================================================
-- Data warehouse - staging layers of the ETL (schema staging_dw)
--
-- The warehouse ETL follows Giordano's data integration reference
-- architecture. Every layer is a physical table:
--
--   #  Layer               Table(s)                                  Written by
--   -----------------------------------------------------------------------------
--   1  Extract/Publish     (extraction models in etl_dw_staging.py)  -
--   2  Initial Staging     stg_initial_classicmodels,                etl_dw_staging.py
--                          stg_initial_customerservice, stg_perfil
--   3  Data Quality        stg_error_log                             etl_dw_staging.py
--   4  Clean Staging       stg_clean, stg_rejected                   etl_dw_staging.py
--   5  Transformation      stg_transform                             etl_dw_dimensions.py,
--   6  Load-Ready Publish  stg_loadready                             etl_dw_facts.py
--   7  Load                dim_* / fact_* (01_star_schema.sql)
--
-- Staging tables are never truncated: each run appends rows under its
-- run_id, so the full history of every load is kept.
-- ============================================================

DROP SCHEMA IF EXISTS staging_dw CASCADE;
CREATE SCHEMA staging_dw;

-- ------------------------------------------------------------
-- Run control. The staging process (layers 1-4) opens one run; the
-- dimension and fact processes (layers 5-7) open their own and record
-- in run_origen which staging run they read.
-- ------------------------------------------------------------
CREATE TABLE staging_dw.etl_run (
    run_id          SERIAL PRIMARY KEY,
    proceso         VARCHAR(30)  NOT NULL,   -- 'staging' | 'dimensiones' | 'hechos'
    run_origen      INTEGER REFERENCES staging_dw.etl_run(run_id),
    iniciado_en     TIMESTAMP    NOT NULL DEFAULT now(),
    finalizado_en   TIMESTAMP,
    estado          VARCHAR(20)  NOT NULL DEFAULT 'EN_CURSO',
    CHECK (proceso IN ('staging', 'dimensiones', 'hechos')),
    CHECK (estado  IN ('EN_CURSO', 'OK', 'ERROR'))
);

-- ------------------------------------------------------------
-- Layer 2 - Initial Staging
--
-- One table per source system. Each row is stored exactly as read,
-- as a JSONB payload, with no schema imposed yet.
-- ------------------------------------------------------------
CREATE TABLE staging_dw.stg_initial_classicmodels (
    stg_id          BIGSERIAL PRIMARY KEY,
    run_id          INTEGER     NOT NULL REFERENCES staging_dw.etl_run(run_id),
    tabla_origen    VARCHAR(60) NOT NULL,
    nro_fila        INTEGER     NOT NULL,
    payload         JSONB       NOT NULL,
    extraido_en     TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE TABLE staging_dw.stg_initial_customerservice (
    stg_id          BIGSERIAL PRIMARY KEY,
    run_id          INTEGER     NOT NULL REFERENCES staging_dw.etl_run(run_id),
    tabla_origen    VARCHAR(60) NOT NULL,
    nro_fila        INTEGER     NOT NULL,
    payload         JSONB       NOT NULL,
    extraido_en     TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE INDEX idx_ini_cm_run ON staging_dw.stg_initial_classicmodels(run_id, tabla_origen);
CREATE INDEX idx_ini_cs_run ON staging_dw.stg_initial_customerservice(run_id, tabla_origen);

-- Column profile (nulls, distinct values, min, max) of every column
-- that landed in Initial Staging, computed on every load.
CREATE TABLE staging_dw.stg_perfil (
    perfil_id       BIGSERIAL PRIMARY KEY,
    run_id          INTEGER     NOT NULL REFERENCES staging_dw.etl_run(run_id),
    fuente          VARCHAR(40) NOT NULL,
    tabla_origen    VARCHAR(60) NOT NULL,
    columna         VARCHAR(80) NOT NULL,
    filas           INTEGER     NOT NULL,
    nulos           INTEGER     NOT NULL,
    pct_nulos       NUMERIC(6,2) NOT NULL,
    distintos       INTEGER     NOT NULL,
    minimo          TEXT,
    maximo          TEXT
);

CREATE INDEX idx_perfil_run ON staging_dw.stg_perfil(run_id);

-- ------------------------------------------------------------
-- Layer 3 - Data Quality
--
-- Technical checks (missing or invalid data) and business checks
-- (referential integrity, inaccurate data, inconsistent definitions)
-- write one row here per rule a record breaks (bad-transactions log):
--
--   RECHAZADO    the record cannot continue and goes to stg_rejected
--   ADVERTENCIA  the record continues; the anomaly is only logged
-- ------------------------------------------------------------
CREATE TABLE staging_dw.stg_error_log (
    error_id        BIGSERIAL PRIMARY KEY,
    run_id          INTEGER      NOT NULL REFERENCES staging_dw.etl_run(run_id),
    fuente          VARCHAR(40)  NOT NULL,
    tabla_origen    VARCHAR(60)  NOT NULL,
    nro_fila        INTEGER      NOT NULL,
    llave_registro  TEXT,                     -- readable record identifier
    clase_dq        VARCHAR(10)  NOT NULL,    -- 'TECNICA' | 'NEGOCIO'
    categoria       VARCHAR(40)  NOT NULL,
    regla           VARCHAR(120) NOT NULL,    -- matches dq_rule.rule_name in the metadata repository
    accion          VARCHAR(20)  NOT NULL,
    detalle         TEXT,
    registrado_en   TIMESTAMP    NOT NULL DEFAULT now(),
    CHECK (clase_dq IN ('TECNICA', 'NEGOCIO')),
    CHECK (categoria IN ('CAMPO_FALTANTE', 'DATO_INVALIDO',
                         'INTEGRIDAD_REFERENCIAL', 'DATO_INEXACTO',
                         'DEFINICION_INCONSISTENTE')),
    CHECK (accion IN ('RECHAZADO', 'ADVERTENCIA'))
);

CREATE INDEX idx_error_run ON staging_dw.stg_error_log(run_id);

-- ------------------------------------------------------------
-- Layer 4 - Clean Staging
--
-- Clean and rejected records are stored in two separate tables; the
-- transformation layer only reads stg_clean. Records with warnings
-- only are stored as clean.
-- ------------------------------------------------------------
CREATE TABLE staging_dw.stg_clean (
    stg_id          BIGSERIAL PRIMARY KEY,
    run_id          INTEGER     NOT NULL REFERENCES staging_dw.etl_run(run_id),
    fuente          VARCHAR(40) NOT NULL,
    tabla_origen    VARCHAR(60) NOT NULL,
    nro_fila        INTEGER     NOT NULL,
    payload         JSONB       NOT NULL,
    limpiado_en     TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE TABLE staging_dw.stg_rejected (
    stg_id          BIGSERIAL PRIMARY KEY,
    run_id          INTEGER     NOT NULL REFERENCES staging_dw.etl_run(run_id),
    fuente          VARCHAR(40) NOT NULL,
    tabla_origen    VARCHAR(60) NOT NULL,
    nro_fila        INTEGER     NOT NULL,
    payload         JSONB       NOT NULL,
    motivos         TEXT        NOT NULL,     -- rules that rejected it
    rechazado_en    TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE INDEX idx_clean_run    ON staging_dw.stg_clean(run_id, tabla_origen);
CREATE INDEX idx_rejected_run ON staging_dw.stg_rejected(run_id, tabla_origen);

-- ------------------------------------------------------------
-- Layer 5 - Transformation
--
-- Clean data conformed by subject area (Cliente, Producto, Empleado,
-- Organizacion, Tiempo, Ventas, Servicio): joins, surrogate-key
-- lookups and calculated measures. operaciones records what was done.
-- ------------------------------------------------------------
CREATE TABLE staging_dw.stg_transform (
    stg_id           BIGSERIAL PRIMARY KEY,
    run_id           INTEGER     NOT NULL REFERENCES staging_dw.etl_run(run_id),
    area_conformada  VARCHAR(30) NOT NULL,   -- 'Cliente', 'Ventas', ...
    objetivo         VARCHAR(60) NOT NULL,   -- target table
    nro_fila         INTEGER     NOT NULL,
    payload          JSONB       NOT NULL,
    operaciones      VARCHAR(200),
    transformado_en  TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE INDEX idx_transform_run ON staging_dw.stg_transform(run_id, objetivo);

-- ------------------------------------------------------------
-- Layer 6 - Load-Ready Publish
--
-- Rows in their final shape; the load is a direct insert.
-- modelo_carga separates the dimension and fact load branches.
-- ------------------------------------------------------------
CREATE TABLE staging_dw.stg_loadready (
    stg_id           BIGSERIAL PRIMARY KEY,
    run_id           INTEGER     NOT NULL REFERENCES staging_dw.etl_run(run_id),
    modelo_carga     VARCHAR(20) NOT NULL,   -- 'DIMENSIONES' | 'HECHOS'
    objetivo         VARCHAR(60) NOT NULL,
    nro_fila         INTEGER     NOT NULL,
    payload          JSONB       NOT NULL,
    publicado_en     TIMESTAMP   NOT NULL DEFAULT now(),
    CHECK (modelo_carga IN ('DIMENSIONES', 'HECHOS'))
);

CREATE INDEX idx_loadready_run ON staging_dw.stg_loadready(run_id, objetivo);

-- ============================================================
-- Monitoring views
-- ============================================================

-- Row counts of every run in each layer.
CREATE VIEW staging_dw.vw_trazabilidad_capas AS
SELECT r.run_id,
       r.proceso,
       r.run_origen,
       r.estado,
       r.iniciado_en,
       (SELECT COUNT(*) FROM staging_dw.stg_initial_classicmodels   x WHERE x.run_id = r.run_id)
     + (SELECT COUNT(*) FROM staging_dw.stg_initial_customerservice x WHERE x.run_id = r.run_id)
                                                                     AS initial_staging,
       (SELECT COUNT(*) FROM staging_dw.stg_error_log x WHERE x.run_id = r.run_id) AS errores_dq,
       (SELECT COUNT(*) FROM staging_dw.stg_clean     x WHERE x.run_id = r.run_id) AS clean,
       (SELECT COUNT(*) FROM staging_dw.stg_rejected  x WHERE x.run_id = r.run_id) AS rejected,
       (SELECT COUNT(*) FROM staging_dw.stg_transform x WHERE x.run_id = r.run_id) AS transform,
       (SELECT COUNT(*) FROM staging_dw.stg_loadready x WHERE x.run_id = r.run_id) AS load_ready
FROM staging_dw.etl_run r
ORDER BY r.run_id;

-- Readable bad-transactions report.
CREATE VIEW staging_dw.vw_reporte_transacciones_malas AS
SELECT e.run_id,
       e.fuente,
       e.tabla_origen,
       e.llave_registro,
       e.categoria,
       e.clase_dq,
       e.regla,
       e.accion,
       e.detalle
FROM staging_dw.stg_error_log e
ORDER BY e.run_id, e.accion DESC, e.categoria, e.tabla_origen, e.llave_registro;
