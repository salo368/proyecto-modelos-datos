-- ============================================================
-- Almacen de Datos - Modelo dimensional (constelacion)
-- Proyecto: Modelos y Persistencia de Datos - Entrega 2
--
-- Dos tablas de hechos que comparten dimensiones conformadas:
--
--   fact_ventas             grano: una linea de una orden de compra
--   fact_llamadas_servicio  grano: una llamada al centro de servicio
--
-- Dimensiones conformadas (las usan los dos hechos):
--   dim_tiempo, dim_cliente, dim_producto
--
-- La conformacion es posible porque en el perfilamiento de la Entrega 1
-- se midio solape del 100% en las llaves de cliente y de producto entre
-- classicmodels y customerservice.
--
-- Motor: PostgreSQL 18 (base 'dw' en Railway).
-- Ejecutar con: python datawarehouse/ddl/run_sql.py datawarehouse/ddl/01_dw_schema.sql
-- ============================================================

DROP VIEW  IF EXISTS vw_interaccion_cliente_producto CASCADE;
DROP TABLE IF EXISTS fact_ventas             CASCADE;
DROP TABLE IF EXISTS fact_llamadas_servicio  CASCADE;
DROP TABLE IF EXISTS dim_tiempo              CASCADE;
DROP TABLE IF EXISTS dim_cliente             CASCADE;
DROP TABLE IF EXISTS dim_producto            CASCADE;
DROP TABLE IF EXISTS dim_empleado            CASCADE;
DROP TABLE IF EXISTS dim_oficina             CASCADE;
DROP TABLE IF EXISTS dim_estado_orden        CASCADE;

-- ------------------------------------------------------------
-- DIMENSIONES CONFORMADAS
-- ------------------------------------------------------------

-- Dimension de tiempo. No se extrae de ninguna fuente: se genera.
-- La llave subrogada es la fecha en formato AAAAMMDD, que es la
-- convencion habitual en Kimball porque es legible y ordenable.
CREATE TABLE dim_tiempo (
    tiempo_key      INTEGER PRIMARY KEY,
    fecha           DATE        NOT NULL UNIQUE,
    anio            SMALLINT    NOT NULL,
    trimestre       SMALLINT    NOT NULL,
    mes             SMALLINT    NOT NULL,
    nombre_mes      VARCHAR(12) NOT NULL,
    dia             SMALLINT    NOT NULL,
    dia_semana      SMALLINT    NOT NULL,   -- 1 = lunes, 7 = domingo
    nombre_dia      VARCHAR(12) NOT NULL,
    es_fin_semana   BOOLEAN     NOT NULL,
    anio_mes        CHAR(7)     NOT NULL    -- '2003-01', para agrupar por mes
);

-- Dimension de cliente. CONFORMADA entre las dos fuentes.
-- direccion_completa consolida addressLine1 y addressLine2: la segunda
-- esta vacia en el 81,97% de las filas (hallazgo de la Entrega 1), asi
-- que no vale la pena arrastrarla como columna aparte.
CREATE TABLE dim_cliente (
    cliente_key             SERIAL PRIMARY KEY,
    numero_cliente          INTEGER NOT NULL UNIQUE,   -- llave de negocio
    nombre_cliente          VARCHAR(100),
    contacto_nombre         VARCHAR(100),
    contacto_apellido       VARCHAR(100),
    telefono                VARCHAR(50),
    direccion_completa      VARCHAR(220),
    ciudad                  VARCHAR(100),
    estado_region           VARCHAR(100),
    codigo_postal           VARCHAR(20),
    pais                    VARCHAR(100),
    limite_credito          NUMERIC(12,2),
    presente_en_ventas      BOOLEAN NOT NULL DEFAULT FALSE,
    presente_en_servicio    BOOLEAN NOT NULL DEFAULT FALSE
);

-- Dimension de producto. CONFORMADA entre las dos fuentes.
-- La linea de producto se trae desnormalizada desde productlines: en un
-- modelo dimensional se prefiere una dimension plana sobre un copo de
-- nieve. De productlines solo se trae textDescription, porque
-- htmlDescription e image estan 100% vacias (hallazgo de la Entrega 1).
CREATE TABLE dim_producto (
    producto_key            SERIAL PRIMARY KEY,
    codigo_producto         VARCHAR(20) NOT NULL UNIQUE,   -- llave de negocio
    nombre_producto         VARCHAR(140),
    linea_producto          VARCHAR(60),
    descripcion_linea       TEXT,
    escala                  VARCHAR(20),
    proveedor               VARCHAR(100),
    precio_compra           NUMERIC(12,2),
    precio_msrp             NUMERIC(12,2),
    presente_en_ventas      BOOLEAN NOT NULL DEFAULT FALSE,
    presente_en_servicio    BOOLEAN NOT NULL DEFAULT FALSE
);

-- ------------------------------------------------------------
-- DIMENSION NO CONFORMADA
--
-- Los 23 empleados de classicmodels y los 30 de customerservice no
-- comparten ni una sola llave: el perfilamiento de la Entrega 1 midio
-- solape del 0%. No se pueden fusionar sin inventar equivalencias.
--
-- La solucion es una llave de negocio COMPUESTA
-- (numero_empleado, sistema_origen) con una llave subrogada encima,
-- de modo que las dos poblaciones convivan en la misma dimension sin
-- colisionar. Esta es la respuesta al hallazgo de calidad mas
-- importante de la Entrega 1.
-- ------------------------------------------------------------
CREATE TABLE dim_empleado (
    empleado_key        SERIAL PRIMARY KEY,
    numero_empleado     INTEGER     NOT NULL,
    sistema_origen      VARCHAR(20) NOT NULL,   -- 'classicmodels' | 'customerservice'
    nombre              VARCHAR(100),
    apellido            VARCHAR(100),
    email               VARCHAR(140),
    cargo               VARCHAR(80),
    numero_oficina      VARCHAR(20),
    UNIQUE (numero_empleado, sistema_origen)
);

-- ------------------------------------------------------------
-- DIMENSIONES EXCLUSIVAS DE classicmodels
-- ------------------------------------------------------------

CREATE TABLE dim_oficina (
    oficina_key     SERIAL PRIMARY KEY,
    codigo_oficina  VARCHAR(20) NOT NULL UNIQUE,
    ciudad          VARCHAR(100),
    pais            VARCHAR(100),
    region          VARCHAR(100),
    territorio      VARCHAR(20)
);

-- es_efectiva distingue las ordenes que cuentan como venta cerrada de
-- las que no (Cancelled, Disputed, On Hold). Permite excluirlas en los
-- reportes sin borrarlas del almacen, que es el tratamiento correcto:
-- el dato existe, simplemente no se agrega en ciertos analisis.
CREATE TABLE dim_estado_orden (
    estado_key      SERIAL PRIMARY KEY,
    estado          VARCHAR(30) NOT NULL UNIQUE,
    es_efectiva     BOOLEAN     NOT NULL
);

-- ------------------------------------------------------------
-- HECHO PRINCIPAL: fact_ventas
-- Grano: una linea de una orden de compra (2.996 filas esperadas).
-- Nutrido por orderdetails, orders, products, customers y employees
-- de classicmodels.
-- ------------------------------------------------------------
CREATE TABLE fact_ventas (
    venta_key           BIGSERIAL PRIMARY KEY,

    -- Llaves foraneas hacia las dimensiones
    tiempo_key          INTEGER NOT NULL REFERENCES dim_tiempo(tiempo_key),
    cliente_key         INTEGER NOT NULL REFERENCES dim_cliente(cliente_key),
    producto_key        INTEGER NOT NULL REFERENCES dim_producto(producto_key),
    empleado_key        INTEGER          REFERENCES dim_empleado(empleado_key),
    oficina_key         INTEGER          REFERENCES dim_oficina(oficina_key),
    estado_key          INTEGER NOT NULL REFERENCES dim_estado_orden(estado_key),

    -- Dimensiones degeneradas: identificadores del sistema origen que
    -- no justifican una tabla de dimension propia.
    numero_orden        INTEGER  NOT NULL,
    numero_linea        SMALLINT NOT NULL,

    -- Medidas
    cantidad_ordenada   INTEGER       NOT NULL,   -- aditiva
    precio_unitario     NUMERIC(12,2) NOT NULL,   -- no aditiva (promediar)
    monto_linea         NUMERIC(14,2) NOT NULL,   -- aditiva: cantidad * precio
    costo_linea         NUMERIC(14,2),            -- aditiva: cantidad * precio_compra
    margen_linea        NUMERIC(14,2),            -- aditiva: monto - costo
    precio_msrp         NUMERIC(12,2),            -- no aditiva
    dias_hasta_envio    SMALLINT,                 -- semi-aditiva; NULL si no se despacho

    UNIQUE (numero_orden, numero_linea)
);

-- ------------------------------------------------------------
-- HECHO SECUNDARIO: fact_llamadas_servicio
-- Grano: una llamada al centro de servicio (108 filas esperadas).
-- Nutrido por cs_customer_calls de customerservice.
-- ------------------------------------------------------------
CREATE TABLE fact_llamadas_servicio (
    llamada_key         BIGSERIAL PRIMARY KEY,

    tiempo_key          INTEGER NOT NULL REFERENCES dim_tiempo(tiempo_key),
    cliente_key         INTEGER NOT NULL REFERENCES dim_cliente(cliente_key),
    producto_key        INTEGER NOT NULL REFERENCES dim_producto(producto_key),
    empleado_key        INTEGER NOT NULL REFERENCES dim_empleado(empleado_key),

    texto_llamada       TEXT,                     -- dimension degenerada

    cantidad_llamadas   SMALLINT NOT NULL DEFAULT 1,   -- aditiva
    longitud_texto      INTEGER                        -- aditiva
);

-- ------------------------------------------------------------
-- Indices sobre las llaves foraneas.
-- PostgreSQL crea indice automatico para la llave primaria y para las
-- restricciones UNIQUE, pero NO para las llaves foraneas. Sin estos
-- indices cada JOIN del hecho contra una dimension recorre la tabla
-- completa.
-- ------------------------------------------------------------
CREATE INDEX idx_fv_tiempo   ON fact_ventas(tiempo_key);
CREATE INDEX idx_fv_cliente  ON fact_ventas(cliente_key);
CREATE INDEX idx_fv_producto ON fact_ventas(producto_key);
CREATE INDEX idx_fv_empleado ON fact_ventas(empleado_key);
CREATE INDEX idx_fv_oficina  ON fact_ventas(oficina_key);
CREATE INDEX idx_fv_estado   ON fact_ventas(estado_key);

CREATE INDEX idx_fl_tiempo   ON fact_llamadas_servicio(tiempo_key);
CREATE INDEX idx_fl_cliente  ON fact_llamadas_servicio(cliente_key);
CREATE INDEX idx_fl_producto ON fact_llamadas_servicio(producto_key);
CREATE INDEX idx_fl_empleado ON fact_llamadas_servicio(empleado_key);

-- ------------------------------------------------------------
-- Schema de staging para las capas intermedias del ETL,
-- siguiendo el mismo patron de la Entrega 1.
-- ------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS staging_dw;
