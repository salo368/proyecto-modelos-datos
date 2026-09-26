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
