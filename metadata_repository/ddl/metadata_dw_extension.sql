-- ============================================================
-- Extension del Repositorio de Metadatos - Entrega 2
--
-- El repositorio de la Entrega 1 (6 tablas) describe las dos FUENTES.
-- Esta extension agrega 8 tablas para describir tambien el ALMACEN de
-- datos y los PROCESOS que lo alimentan, que es lo que pide el punto 3
-- del enunciado de la Entrega 2.
--
-- Los tres bloques nuevos son:
--   1. Estructura del almacen   dw_object, dw_measure, dw_attribute
--   2. Linaje fuente -> almacen dw_lineage
--   3. Operacion y calidad      etl_process, etl_execution,
--                               dq_rule, dq_result
--
-- IMPORTANTE: se ejecuta contra METADATA_REPO_URL (base 'railway'),
-- NO contra el almacen.
--
-- Ejecutar con:
--   python datawarehouse/ddl/run_sql.py \
--       metadata_repository/ddl/metadata_dw_extension.sql METADATA_REPO_URL
-- ============================================================

-- ------------------------------------------------------------
-- 1. ESTRUCTURA DEL ALMACEN
-- ------------------------------------------------------------

-- Cada hecho, dimension y vista del almacen. Es el equivalente de
-- db_table (Entrega 1) pero del lado dimensional.
CREATE TABLE IF NOT EXISTS dw_object (
    dw_object_id    SERIAL PRIMARY KEY,
    object_name     VARCHAR(100) NOT NULL UNIQUE,   -- 'fact_ventas', 'dim_cliente'
    object_type     VARCHAR(20)  NOT NULL,          -- 'FACT' | 'DIMENSION' | 'VIEW'
    grain           TEXT,                           -- solo para hechos
    description     TEXT NOT NULL,
    is_conformed    BOOLEAN NOT NULL DEFAULT FALSE, -- solo para dimensiones
    -- Tipo de dimension lentamente cambiante (Clase 4-5). Registrar el
    -- tipo es parte del metadato: sin el, quien consulta la dimension no
    -- sabe si esta viendo el estado actual o una version historica.
    scd_type        VARCHAR(10),                    -- 'TIPO_1' | 'TIPO_2' | 'TIPO_3' | NULL
    scd_justificacion TEXT,                         -- por que se eligio ese tipo
    row_count       INTEGER,
    loaded_at       TIMESTAMP NOT NULL DEFAULT now(),
    CHECK (object_type IN ('FACT', 'DIMENSION', 'VIEW')),
    CHECK (scd_type IS NULL OR scd_type IN ('TIPO_1', 'TIPO_2', 'TIPO_3'))
);

-- Las medidas de cada hecho. additivity es el metadato clave para que
-- una herramienta de BI sepa si puede sumar la columna en cualquier
-- dimension, solo en algunas, o en ninguna.
CREATE TABLE IF NOT EXISTS dw_measure (
    dw_measure_id   SERIAL PRIMARY KEY,
    dw_object_id    INTEGER NOT NULL REFERENCES dw_object(dw_object_id) ON DELETE CASCADE,
    measure_name    VARCHAR(100) NOT NULL,
    data_type       VARCHAR(50)  NOT NULL,
    additivity      VARCHAR(20)  NOT NULL,
    formula         TEXT,          -- 'quantityOrdered * priceEach'
    description     TEXT,
    UNIQUE (dw_object_id, measure_name),
    CHECK (additivity IN ('ADITIVA', 'SEMI_ADITIVA', 'NO_ADITIVA'))
);

-- Los atributos de cada dimension. Equivalente dimensional de
-- db_column (Entrega 1).
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
-- 2. LINAJE FUENTE -> ALMACEN
--
-- Engancha con db_column, la tabla de la Entrega 1 donde estan
-- catalogadas las 85 columnas de las dos fuentes. Asi el linaje queda
-- completo de punta a punta:
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
    transformation_rule TEXT NOT NULL,   -- 'copia directa', 'concatenacion', 'calculo'
    -- Cada fila apunta a UNA medida o a UN atributo, nunca a ambos ni a
    -- ninguno. source_column_id puede ser NULL para objetos generados
    -- (dim_tiempo) que no provienen de ninguna columna de origen.
    CHECK (
        (target_measure_id IS NOT NULL AND target_attribute_id IS NULL) OR
        (target_measure_id IS NULL     AND target_attribute_id IS NOT NULL)
    )
);

-- ------------------------------------------------------------
-- 3. OPERACION DE LOS PROCESOS ETL
-- ------------------------------------------------------------

-- Catalogo de procesos. El enunciado pide especificar que herramienta
-- se uso; aqui queda registrado como metadato, no solo en el documento.
CREATE TABLE IF NOT EXISTS etl_process (
    etl_process_id  SERIAL PRIMARY KEY,
    process_name    VARCHAR(100) NOT NULL UNIQUE,
    tool            VARCHAR(80)  NOT NULL,
    source_systems  VARCHAR(200) NOT NULL,
    target_system   VARCHAR(100) NOT NULL,
    description     TEXT
);

-- Bitacora de ejecuciones. Una fila por corrida de cada proceso.
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
-- 4. CALIDAD DE DATOS
--
-- Formaliza los hallazgos del perfilamiento de la Entrega 1: en vez de
-- quedar solo narrados en un documento, quedan como reglas evaluables
-- cuyo resultado se registra en cada corrida del ETL.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dq_rule (
    dq_rule_id       SERIAL PRIMARY KEY,
    rule_name        VARCHAR(120) NOT NULL UNIQUE,
    rule_type        VARCHAR(40)  NOT NULL,   -- categoria tecnica de la regla
    -- Criterio de calidad segun el marco de la Clase 1, tomado de
    -- The Art of Enterprise Information Architecture. Mantener las dos
    -- columnas permite que la regla sea operable por el ETL (rule_type)
    -- y a la vez trazable al marco conceptual del curso (criterio_dama).
    criterio_dama    VARCHAR(20),
    -- Clase de calidad segun Giordano (Clase 2, dia. 17): la tecnica la
    -- detecta la maquina, la de negocio requiere conocer la semantica.
    clase_dq         VARCHAR(10),
    -- En que capa del pipeline se evalua la regla:
    --   DATA_QUALITY    capa 3: se evalua registro por registro y puede
    --                   mandar el registro a la pila de rechazados
    --   TRANSFORMATION  capa 5: hallazgo del perfilamiento que se
    --                   resuelve con una decision de modelado
    --   MONITOREO       sobre la operacion del almacen, fuera del flujo
    capa             VARCHAR(20),
    source_column_id INTEGER REFERENCES db_column(column_id) ON DELETE SET NULL,
    expression       TEXT NOT NULL,
    severity         VARCHAR(20) NOT NULL,
    resolution       TEXT NOT NULL,   -- que hace el ETL cuando la regla falla
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
-- Indices de apoyo
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_dw_measure_object     ON dw_measure(dw_object_id);
CREATE INDEX IF NOT EXISTS idx_dw_attribute_object   ON dw_attribute(dw_object_id);
CREATE INDEX IF NOT EXISTS idx_dw_lineage_source     ON dw_lineage(source_column_id);
CREATE INDEX IF NOT EXISTS idx_dw_lineage_measure    ON dw_lineage(target_measure_id);
CREATE INDEX IF NOT EXISTS idx_dw_lineage_attribute  ON dw_lineage(target_attribute_id);
CREATE INDEX IF NOT EXISTS idx_etl_exec_process      ON etl_execution(etl_process_id);
CREATE INDEX IF NOT EXISTS idx_dq_result_rule        ON dq_result(dq_rule_id);
CREATE INDEX IF NOT EXISTS idx_dq_result_execution   ON dq_result(etl_execution_id);
