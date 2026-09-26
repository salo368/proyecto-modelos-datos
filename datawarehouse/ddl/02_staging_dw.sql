-- ============================================================
-- Capas de staging del ETL del almacen - Entrega 2
--
-- Implementa la arquitectura de referencia para integracion de datos
-- de Anthony Giordano (Data Integration Blueprint and Modeling, 2011,
-- Cap. 2), tal como se presento en la Clase 2 del curso.
--
-- Cada capa es una TABLA FISICA PERSISTIDA, no un paso en memoria.
-- Esa es la diferencia entre "seguir el patron" y solo nombrarlo: se
-- puede consultar el estado del dato en cualquier punto del proceso,
-- y comparar corridas entre si.
--
-- Mapa capa -> diapositiva de la Clase 2:
--
--   stg_extract     dia. 15  "Leer una sola vez cada fuente y hacer
--                             todas las copias necesarias"
--                             (Read once, write many)
--                    dia. 16  "Almacenamiento no volatil"
--
--   stg_dq          dia. 17  Calidad de Datos, separada en sus dos
--                             clases: Tecnica (datos faltantes,
--                             invalidos) y de Negocio (definiciones
--                             inconsistentes, datos inexactos)
--                    dia. 18  Separar datos limpios de rechazados
--
--   stg_transform   dia. 19  "Joins, Lookups, Agregaciones".
--                             Aqui vive la busqueda de llaves
--                             subrogadas, que es exactamente el
--                             "Lookup" de esa diapositiva.
--
--   stg_loadready            Forma final, lista para publicar al
--                             destino sin mas transformaciones.
--
-- NO VOLATILIDAD: ninguna de estas tablas se trunca. Cada corrida
-- agrega filas con su run_id, de modo que el historial completo del
-- proceso queda disponible para auditoria y para comparar corridas.
--
-- Ejecutar con:
--   python datawarehouse/ddl/run_sql.py datawarehouse/ddl/02_staging_dw.sql
-- ============================================================

CREATE SCHEMA IF NOT EXISTS staging_dw;

DROP TABLE IF EXISTS staging_dw.stg_loadready CASCADE;
DROP TABLE IF EXISTS staging_dw.stg_transform CASCADE;
DROP TABLE IF EXISTS staging_dw.stg_dq        CASCADE;
DROP TABLE IF EXISTS staging_dw.stg_extract   CASCADE;
DROP TABLE IF EXISTS staging_dw.etl_run       CASCADE;

-- ------------------------------------------------------------
-- Control de corridas
--
-- Una fila por ejecucion del ETL. Todas las capas referencian su
-- run_id, de modo que se puede reconstruir exactamente que entro,
-- que se rechazo y que se cargo en cada corrida.
-- ------------------------------------------------------------
CREATE TABLE staging_dw.etl_run (
    run_id          SERIAL PRIMARY KEY,
    proceso         VARCHAR(60)  NOT NULL,   -- 'dimensiones' | 'hechos'
    iniciado_en     TIMESTAMP    NOT NULL DEFAULT now(),
    finalizado_en   TIMESTAMP,
    estado          VARCHAR(20)  NOT NULL DEFAULT 'EN_CURSO',
    CHECK (estado IN ('EN_CURSO', 'OK', 'ERROR'))
);

-- ------------------------------------------------------------
-- CAPA 1 - EXTRACT / LANDING            (Clase 2, diapositivas 15-16)
--
-- Copia 1:1 y sin interpretar de cada tabla de las fuentes. Se lee
-- CADA FUENTE UNA SOLA VEZ por corrida; tanto la carga de dimensiones
-- como la de hechos consumen desde aqui, nunca de la fuente original.
-- Eso es el "read once, write many" de la diapositiva 15.
--
-- El payload va en JSONB para que una sola tabla sirva a las nueve
-- tablas de origen sin imponerles un esquema comun: el landing debe
-- aceptar el dato como viene, sin decidir nada todavia.
-- ------------------------------------------------------------
CREATE TABLE staging_dw.stg_extract (
    stg_extract_id  BIGSERIAL PRIMARY KEY,
    run_id          INTEGER      NOT NULL REFERENCES staging_dw.etl_run(run_id),
    fuente          VARCHAR(40)  NOT NULL,   -- 'classicmodels' | 'customerservice'
    tabla_origen    VARCHAR(60)  NOT NULL,   -- 'customers', 'cs_customer_calls', ...
    nro_fila        INTEGER      NOT NULL,   -- orden dentro de la extraccion
    payload         JSONB        NOT NULL,   -- la fila completa, tal cual salio
    extraido_en     TIMESTAMP    NOT NULL DEFAULT now()
);

CREATE INDEX idx_stg_extract_run   ON staging_dw.stg_extract(run_id);
CREATE INDEX idx_stg_extract_tabla ON staging_dw.stg_extract(tabla_origen);

-- ------------------------------------------------------------
-- CAPA 2 - DATA QUALITY                 (Clase 2, diapositivas 17-18)
--
-- La diapositiva 17 separa la calidad en dos clases, y esta tabla las
-- distingue con la columna clase_dq:
--
--   TECNICA   datos faltantes, datos invalidos
--             (lo detecta la maquina: nulos, tipos, formatos)
--
--   NEGOCIO   definiciones inconsistentes, datos inexactos
--             (requiere conocer la regla: un cliente que existe en una
--              fuente y no en la otra, un estado de orden que no cuenta
--              como venta cerrada)
--
-- La diapositiva 18 plantea tres destinos: limpios, por revisar y
-- rechazados. Este proyecto usa DOS (OK y RECHAZADO) de forma
-- deliberada: "por revisar" supone un custodio humano que valide los
-- casos dudosos antes de cada carga, y este almacen se reconstruye de
-- forma automatica y desatendida desde dos snapshots estaticos. Un
-- estado que nadie va a revisar seria una capa muerta. Los casos que
-- en un escenario con custodio irian a "por revisar" se resuelven aqui
-- con una regla explicita y quedan trazados en dq_result del
-- repositorio de metadatos.
-- ------------------------------------------------------------
CREATE TABLE staging_dw.stg_dq (
    stg_dq_id       BIGSERIAL PRIMARY KEY,
    run_id          INTEGER      NOT NULL REFERENCES staging_dw.etl_run(run_id),
    fuente          VARCHAR(40)  NOT NULL,
    tabla_origen    VARCHAR(60)  NOT NULL,
    nro_fila        INTEGER      NOT NULL,
    payload         JSONB        NOT NULL,
    clase_dq        VARCHAR(20)  NOT NULL,   -- 'TECNICA' | 'NEGOCIO' | 'NINGUNA'
    dq_status       VARCHAR(20)  NOT NULL,   -- 'OK' | 'RECHAZADO'
    dq_regla        VARCHAR(120),            -- regla que se disparo, si alguna
    dq_notas        TEXT,
    evaluado_en     TIMESTAMP    NOT NULL DEFAULT now(),
    CHECK (clase_dq  IN ('TECNICA', 'NEGOCIO', 'NINGUNA')),
    CHECK (dq_status IN ('OK', 'RECHAZADO'))
);

CREATE INDEX idx_stg_dq_run    ON staging_dw.stg_dq(run_id);
CREATE INDEX idx_stg_dq_status ON staging_dw.stg_dq(dq_status);

-- ------------------------------------------------------------
-- CAPA 3 - TRANSFORM                       (Clase 2, diapositiva 19)
--
-- "Joins, Lookups, Agregaciones". Las tres operaciones de esa
-- diapositiva ocurren aqui:
--
--   Joins        orderdetails con orders, products y customers
--   Lookups      traduccion de llave de negocio a llave subrogada
--                (customerNumber 103 -> cliente_key 7). Es el corazon
--                de un ETL dimensional y merece ser una capa visible,
--                no un diccionario escondido en memoria.
--   Agregaciones consolidacion de metricas por grano
--
-- objetivo indica a que tabla del almacen va dirigida la fila, de modo
-- que una sola tabla de staging sirve a las ocho tablas destino.
-- ------------------------------------------------------------
CREATE TABLE staging_dw.stg_transform (
    stg_transform_id BIGSERIAL PRIMARY KEY,
    run_id           INTEGER     NOT NULL REFERENCES staging_dw.etl_run(run_id),
    objetivo         VARCHAR(60) NOT NULL,   -- 'dim_cliente', 'fact_ventas', ...
    nro_fila         INTEGER     NOT NULL,
    payload          JSONB       NOT NULL,   -- fila ya transformada
    operaciones      VARCHAR(200),           -- 'join, lookup' - que se le aplico
    transformado_en  TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE INDEX idx_stg_transform_run      ON staging_dw.stg_transform(run_id);
CREATE INDEX idx_stg_transform_objetivo ON staging_dw.stg_transform(objetivo);

-- ------------------------------------------------------------
-- CAPA 4 - LOAD-READY PUBLISH
--
-- La fila en su forma definitiva. Entre esta capa y la tabla destino
-- no queda ninguna transformacion pendiente: es una insercion directa.
-- Separarla de Transform permite revisar exactamente que se va a
-- escribir antes de tocar el almacen.
-- ------------------------------------------------------------
CREATE TABLE staging_dw.stg_loadready (
    stg_loadready_id BIGSERIAL PRIMARY KEY,
    run_id           INTEGER     NOT NULL REFERENCES staging_dw.etl_run(run_id),
    objetivo         VARCHAR(60) NOT NULL,
    nro_fila         INTEGER     NOT NULL,
    payload          JSONB       NOT NULL,
    publicado_en     TIMESTAMP   NOT NULL DEFAULT now()
);

CREATE INDEX idx_stg_loadready_run      ON staging_dw.stg_loadready(run_id);
CREATE INDEX idx_stg_loadready_objetivo ON staging_dw.stg_loadready(objetivo);

-- ------------------------------------------------------------
-- Vista de trazabilidad del proceso
--
-- Resume cuantas filas paso cada capa en cada corrida. Es la evidencia
-- de que las capas existen y de que el dato fluye por todas ellas.
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW staging_dw.vw_trazabilidad_capas AS
SELECT r.run_id,
       r.proceso,
       r.estado,
       r.iniciado_en,
       (SELECT COUNT(*) FROM staging_dw.stg_extract   e WHERE e.run_id = r.run_id) AS filas_extract,
       (SELECT COUNT(*) FROM staging_dw.stg_dq        d WHERE d.run_id = r.run_id) AS filas_dq,
       (SELECT COUNT(*) FROM staging_dw.stg_dq        d WHERE d.run_id = r.run_id
                                                         AND d.dq_status = 'RECHAZADO') AS filas_rechazadas,
       (SELECT COUNT(*) FROM staging_dw.stg_transform t WHERE t.run_id = r.run_id) AS filas_transform,
       (SELECT COUNT(*) FROM staging_dw.stg_loadready l WHERE l.run_id = r.run_id) AS filas_loadready
FROM staging_dw.etl_run r
ORDER BY r.run_id;
