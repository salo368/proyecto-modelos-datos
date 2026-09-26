-- ============================================================
-- Capas de staging del ETL del almacen - Entrega 2
--
-- Implementa la arquitectura de referencia para integracion de datos
-- de Anthony Giordano (Data Integration Blueprint and Modeling, 2011,
-- Cap. 2), tal como se dibuja en las diapositivas 14 a 19 de la
-- Clase 2. El diagrama tiene SIETE columnas y esta implementacion las
-- sigue una por una:
--
--   #  Capa del diagrama     Aqui                             Dia.
--   ----------------------------------------------------------------
--   1  Extract/Publish       modelo logico de extraccion por  15
--                            fuente (en el codigo del ETL)
--   2  Initial Staging       stg_initial_classicmodels        16
--                            stg_initial_customerservice
--                            stg_perfil (perfilamiento)
--   3  Data Quality          Tech DQ Checks + Bus DQ Check    17
--                            + Error Handling -> stg_error_log
--                            (reporte de transacciones malas)
--   4  Clean Staging         stg_clean      (pila gris)       18
--                            stg_rejected   (pila roja)
--   5  Transformation        stg_transform  (conformar por    19
--                            area tematica; joins, lookups,
--                            agregaciones)
--   6  Load-Ready Publish    stg_loadready                    -
--   7  Load                  dim_* (partes involucradas)      -
--                            fact_* (eventos)
--
-- Dos detalles del dibujo que esta implementacion respeta a proposito:
--
--   * Initial Staging tiene una pila POR FUENTE, de colores distintos.
--     Por eso hay dos tablas, una por sistema origen, y no una sola.
--
--   * Data Quality no tiene pila propia: es procesamiento. Lo que
--     produce es el reporte de transacciones malas y, a su derecha,
--     las dos pilas de Clean Staging. La separacion entre limpios y
--     rechazados (diapositiva 18) es una CAPA DE ALMACENAMIENTO, no
--     una columna de estado dentro de calidad.
--
-- NO VOLATILIDAD (dia. 16): ninguna de estas tablas se trunca. Cada
-- corrida agrega filas con su run_id y el historial queda disponible.
--
-- Ejecutar con:
--   python datawarehouse/ddl/run_sql.py datawarehouse/ddl/02_staging_dw.sql
-- ============================================================

DROP SCHEMA IF EXISTS staging_dw CASCADE;
CREATE SCHEMA staging_dw;

-- ------------------------------------------------------------
-- Control de corridas
--
-- Un proceso de staging (capas 1 a 4) produce una corrida; los
-- procesos de dimensiones y de hechos (capas 5 a 7) producen las
-- suyas y registran en run_origen de que corrida de staging leyeron.
-- Asi se puede reconstruir el recorrido completo de una carga.
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
-- CAPA 2 - INITIAL STAGING                         (diapositiva 16)
--
-- Una tabla por sistema origen, como las pilas de colores distintos
-- del diagrama. Guarda la fila tal como salio de la fuente, sin
-- interpretarla: el payload va en JSONB para aceptar el dato como
-- viene, sin imponerle todavia ningun esquema.
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

-- Perfilamiento de lo que acaba de aterrizar (diapositiva 16).
-- Es el mismo analisis de la Entrega 1, pero ahora corre dentro del
-- pipeline en cada carga, sobre el dato que efectivamente se va a usar.
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
-- CAPA 3 - DATA QUALITY                            (diapositiva 17)
--
-- En el diagrama esta capa es una caja con tres procesos:
--   Tech DQ Checks   calidad TECNICA: datos faltantes, datos invalidos
--   Bus DQ Check     calidad de NEGOCIO: definiciones inconsistentes,
--                    datos inexactos, integridad referencial
--   Error Handling   registra cada falla y decide que hacer con el
--                    registro
--
-- Lo que produce es el reporte de "Bad Transactions" que cuelga de la
-- caja en el diagrama. Esta tabla es ese reporte: una fila por cada
-- regla que un registro incumplio, con la accion tomada.
--
--   RECHAZADO    el registro no puede seguir (llave faltante, referencia
--                a algo inexistente): va a la pila roja
--   ADVERTENCIA  el registro sigue, pero la anomalia queda trazada
-- ------------------------------------------------------------
CREATE TABLE staging_dw.stg_error_log (
    error_id        BIGSERIAL PRIMARY KEY,
    run_id          INTEGER      NOT NULL REFERENCES staging_dw.etl_run(run_id),
    fuente          VARCHAR(40)  NOT NULL,
    tabla_origen    VARCHAR(60)  NOT NULL,
    nro_fila        INTEGER      NOT NULL,
    llave_registro  TEXT,                     -- identificador legible del registro
    clase_dq        VARCHAR(10)  NOT NULL,    -- 'TECNICA' | 'NEGOCIO'
    categoria       VARCHAR(40)  NOT NULL,    -- como en el reporte del diagrama
    regla           VARCHAR(120) NOT NULL,    -- enlaza con dq_rule del repositorio
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
-- CAPA 4 - CLEAN STAGING                           (diapositiva 18)
--
-- "Separar". El diagrama dibuja dos pilas a la salida de calidad: la
-- gris (datos limpios) y la roja (datos rechazados). Son dos tablas
-- fisicas distintas, no un filtro sobre una misma tabla: lo rechazado
-- queda aislado y la capa de transformacion SOLO puede leer lo limpio.
--
-- La diapositiva 18 menciona un tercer destino, "por revisar". No se
-- implementa, y es una decision: ese estado presupone un custodio que
-- valide los casos dudosos antes de cada carga, y este almacen se
-- reconstruye de forma desatendida desde snapshots estaticos. Un
-- estado que nadie revisa es una capa muerta. Los casos dudosos pasan
-- como limpios y quedan trazados como ADVERTENCIA en stg_error_log.
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
    motivos         TEXT        NOT NULL,     -- reglas que lo rechazaron
    rechazado_en    TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE INDEX idx_clean_run    ON staging_dw.stg_clean(run_id, tabla_origen);
CREATE INDEX idx_rejected_run ON staging_dw.stg_rejected(run_id, tabla_origen);

-- ------------------------------------------------------------
-- CAPA 5 - TRANSFORMATION                          (diapositiva 19)
--
-- En el diagrama, esta capa CONFORMA el dato por area tematica
-- ("Conform Loan Data", "Conform Deposit Data"): toma lo limpio de
-- todas las fuentes y lo lleva a un modelo comun. Aqui las areas son
-- Cliente, Producto, Empleado, Organizacion, Tiempo, Ventas y Servicio.
--
-- Dentro de cada area ocurren las tres operaciones de la diapositiva:
--   Joins         cruzar tablas del area (orderdetails + orders + ...)
--   Lookups       traducir llave de negocio a llave subrogada
--   Agregaciones  medidas calculadas y consolidaciones
-- ------------------------------------------------------------
CREATE TABLE staging_dw.stg_transform (
    stg_id           BIGSERIAL PRIMARY KEY,
    run_id           INTEGER     NOT NULL REFERENCES staging_dw.etl_run(run_id),
    area_conformada  VARCHAR(30) NOT NULL,   -- 'Cliente', 'Ventas', ...
    objetivo         VARCHAR(60) NOT NULL,   -- tabla destino
    nro_fila         INTEGER     NOT NULL,
    payload          JSONB       NOT NULL,
    operaciones      VARCHAR(200),
    transformado_en  TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE INDEX idx_transform_run ON staging_dw.stg_transform(run_id, objetivo);

-- ------------------------------------------------------------
-- CAPA 6 - LOAD-READY PUBLISH
--
-- La fila en su forma definitiva. Entre esta capa y el destino no
-- queda ninguna transformacion: es una insercion directa. modelo_carga
-- reproduce la bifurcacion final del diagrama, que reparte la carga en
-- dos modelos: partes involucradas y eventos.
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
-- Vistas de evidencia
-- ============================================================

-- Recorrido de cada corrida por las siete capas. Es la prueba de que
-- las capas existen y de que el dato fluye por todas ellas.
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

-- El reporte de "Bad Transactions" del diagrama, en forma legible.
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
