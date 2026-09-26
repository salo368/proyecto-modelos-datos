-- ============================================================
-- Metadatos de Uso - Entrega 2
--
-- La Clase 3 define CUATRO categorias de metadatos, no tres:
--
--     Negocio | Tecnicos | Procesos | USO
--
-- Las tres primeras ya estaban cubiertas:
--     Negocio    business_entity, business_attribute
--     Tecnicos   data_source, db_table, db_column, dw_object,
--                dw_measure, dw_attribute
--     Procesos   etl_process, etl_execution
--
-- Esta extension cierra la cuarta. Segun la diapositiva de la Clase 3,
-- los metadatos de uso responden:
--
--     - Patrones y frecuencias de acceso (diario, mensual, durante el dia)
--     - Monitoreo de uso
--     - Con que herramientas se accede
--     - Queries vs Tablas
--     - Joins
--
-- La diferencia con las otras categorias es que el uso no se declara:
-- se MIDE. Por eso usage_acceso_objeto se puebla desde las estadisticas
-- reales del motor (pg_stat_user_tables), no desde una lista escrita a
-- mano.
--
-- Ejecutar con:
--   python datawarehouse/ddl/run_sql.py \
--       metadata_repository/ddl/metadata_uso_extension.sql METADATA_REPO_URL
-- ============================================================

-- ------------------------------------------------------------
-- Con que herramientas se accede al almacen
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usage_herramienta (
    usage_herramienta_id SERIAL PRIMARY KEY,
    nombre           VARCHAR(80)  NOT NULL UNIQUE,   -- 'Metabase', 'ETL Python'
    tipo             VARCHAR(40)  NOT NULL,          -- 'BI' | 'ETL' | 'CLIENTE_SQL'
    proposito        TEXT         NOT NULL,
    acceso           VARCHAR(20)  NOT NULL,          -- 'LECTURA' | 'ESCRITURA' | 'AMBOS'
    CHECK (tipo   IN ('BI', 'ETL', 'CLIENTE_SQL', 'APLICACION')),
    CHECK (acceso IN ('LECTURA', 'ESCRITURA', 'AMBOS'))
);

-- ------------------------------------------------------------
-- Queries vs Tablas
--
-- Cada consulta conocida contra el almacen, con su frecuencia esperada
-- y cuantos joins hace. La diapositiva de la Clase 3 nombra
-- explicitamente "Queries vs Tablas" y "Joins" como metadato de uso:
-- saber que una consulta cruza cinco tablas es lo que permite decidir
-- donde poner un indice o cuando conviene una tabla agregada.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usage_consulta (
    usage_consulta_id SERIAL PRIMARY KEY,
    nombre            VARCHAR(120) NOT NULL UNIQUE,
    usage_herramienta_id INTEGER NOT NULL
        REFERENCES usage_herramienta(usage_herramienta_id) ON DELETE CASCADE,
    proposito         TEXT,
    frecuencia        VARCHAR(20) NOT NULL,   -- cada cuanto se espera correr
    nro_joins         INTEGER,                -- cuantas tablas cruza
    CHECK (frecuencia IN ('CONTINUA', 'DIARIA', 'SEMANAL', 'MENSUAL', 'BAJO_DEMANDA'))
);

-- ------------------------------------------------------------
-- Que objetos toca cada consulta (relacion consulta <-> objeto del DW)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS usage_consulta_objeto (
    usage_consulta_id INTEGER NOT NULL
        REFERENCES usage_consulta(usage_consulta_id) ON DELETE CASCADE,
    dw_object_id      INTEGER NOT NULL
        REFERENCES dw_object(dw_object_id) ON DELETE CASCADE,
    PRIMARY KEY (usage_consulta_id, dw_object_id)
);

-- ------------------------------------------------------------
-- Monitoreo de uso: lo que REALMENTE se accedio
--
-- Se puebla desde pg_stat_user_tables del almacen, que es el contador
-- que lleva el propio motor. A diferencia de las tablas anteriores,
-- esto no es una declaracion de intencion sino una medicion.
--
-- lecturas_secuenciales alto frente a lecturas_por_indice indica que
-- las consultas estan recorriendo la tabla completa, que es la senal
-- clasica de un indice faltante.
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------
-- Vista de apoyo: perfil de uso por objeto del almacen
--
-- Cruza lo declarado (que consultas dicen tocar el objeto) con lo
-- medido (cuantas veces se leyo de verdad).
-- ------------------------------------------------------------
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
