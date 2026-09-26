-- ============================================================
-- Data Marts - Entrega 2
--
-- La Clase 4-5 (diapositiva 12, "Flujo de datos dentro de DW") dibuja
-- tres depositos en cadena:
--
--   ODS  --filtrar detalles, agregar-->  EDW  --agregar, segregar-->  DM
--
-- y la diapositiva 11 los caracteriza:
--
--   Tipo  Detalle                  Alcance          Uso
--   ODS   maximo nivel de detalle  empresa          tactico, dia a dia
--   EDW   detalle y agregaciones   empresa          tactico y estrategico
--   DM    agregaciones, poco det.  tema especifico  un grupo o unidad
--
-- En este almacen:
--
--   EDW  el modelo estrella del schema public: dim_* y fact_* al grano
--        mas fino, con alcance de toda la empresa (ventas y servicio).
--
--   DM   el schema dm. Cada data mart AGREGA (sube el grano) y SEGREGA
--        (se queda con un tema) a partir del EDW, que son exactamente
--        las dos operaciones rotuladas en la flecha EDW -> DM.
--
--   ODS  no se implementa. Un ODS sirve para consulta operativa del dia
--        a dia sobre dato integrado y reciente, y este proyecto es un
--        pipeline batch sobre dos snapshots estaticos: no hay operacion
--        diaria que consultar. La capa Clean Staging es la que contiene
--        el dato integrado y validado antes del EDW, pero no se expone
--        para consulta.
--
-- Correr DESPUES de 01_dw_schema.sql (las vistas dependen de las tablas).
--
-- Ejecutar con:
--   python datawarehouse/ddl/run_sql.py datawarehouse/ddl/03_data_marts.sql
-- ============================================================

CREATE SCHEMA IF NOT EXISTS dm;

-- Se elimina tambien la version anterior, que vivia en public.
DROP VIEW IF EXISTS public.vw_interaccion_cliente_producto CASCADE;
DROP VIEW IF EXISTS dm.vw_interaccion_cliente_producto     CASCADE;
DROP VIEW IF EXISTS dm.vw_ventas_mensuales_linea           CASCADE;

-- ------------------------------------------------------------
-- DM Servicio y Ventas: interaccion cliente x producto x mes
--
-- Agrega: sube del grano de linea de orden y de llamada al grano
--         cliente x producto x mes.
-- Segrega: se queda con un solo tema, la relacion entre lo que un
--         cliente compra y lo que consulta al centro de servicio.
--
-- Es el data mart que justifica haber integrado las dos fuentes:
-- responde que productos generan mas llamadas por unidad vendida,
-- pregunta que ninguna fuente contesta por si sola.
-- ------------------------------------------------------------
CREATE VIEW dm.vw_interaccion_cliente_producto AS
WITH ventas AS (
    SELECT f.cliente_key, f.producto_key, t.anio_mes,
           SUM(f.cantidad_ordenada) AS unidades_vendidas,
           SUM(f.monto_linea)       AS monto_vendido,
           SUM(f.margen_linea)      AS margen_total,
           COUNT(*)                 AS lineas_orden
    FROM public.fact_ventas f
    JOIN public.dim_tiempo  t ON f.tiempo_key = t.tiempo_key
    GROUP BY 1, 2, 3
),
llamadas AS (
    SELECT l.cliente_key, l.producto_key, t.anio_mes,
           SUM(l.cantidad_llamadas) AS num_llamadas
    FROM public.fact_llamadas_servicio l
    JOIN public.dim_tiempo t ON l.tiempo_key = t.tiempo_key
    GROUP BY 1, 2, 3
)
SELECT
    COALESCE(v.anio_mes, ll.anio_mes) AS anio_mes,
    c.numero_cliente, c.nombre_cliente, c.pais,
    p.codigo_producto, p.nombre_producto, p.linea_producto,
    COALESCE(v.unidades_vendidas, 0) AS unidades_vendidas,
    COALESCE(v.monto_vendido,     0) AS monto_vendido,
    COALESCE(v.margen_total,      0) AS margen_total,
    COALESCE(v.lineas_orden,      0) AS lineas_orden,
    COALESCE(ll.num_llamadas,     0) AS num_llamadas,
    CASE WHEN COALESCE(v.unidades_vendidas, 0) > 0
         THEN ROUND(COALESCE(ll.num_llamadas, 0)::numeric
                    / v.unidades_vendidas, 4)
    END AS llamadas_por_unidad
FROM ventas v
FULL OUTER JOIN llamadas ll
     ON v.cliente_key  = ll.cliente_key
    AND v.producto_key = ll.producto_key
    AND v.anio_mes     = ll.anio_mes
JOIN public.dim_cliente  c ON c.cliente_key  = COALESCE(v.cliente_key,  ll.cliente_key)
JOIN public.dim_producto p ON p.producto_key = COALESCE(v.producto_key, ll.producto_key);

-- ------------------------------------------------------------
-- DM Ventas: desempeno mensual por linea de producto
--
-- Agrega: de linea de orden a mes x linea de producto.
-- Segrega: solo ventas efectivas (excluye Cancelled, Disputed y On Hold
--          mediante dim_estado_orden.es_efectiva).
--
-- Es el data mart que consumiria un area comercial: cuanto se vende,
-- con que margen y en que familia de productos, mes a mes.
-- ------------------------------------------------------------
CREATE VIEW dm.vw_ventas_mensuales_linea AS
SELECT t.anio,
       t.trimestre,
       t.anio_mes,
       p.linea_producto,
       COUNT(DISTINCT f.numero_orden)   AS ordenes,
       SUM(f.cantidad_ordenada)         AS unidades,
       ROUND(SUM(f.monto_linea),  2)    AS monto_vendido,
       ROUND(SUM(f.margen_linea), 2)    AS margen,
       ROUND(100 * SUM(f.margen_linea) / NULLIF(SUM(f.monto_linea), 0), 2)
                                        AS margen_pct
FROM public.fact_ventas f
JOIN public.dim_tiempo       t ON f.tiempo_key   = t.tiempo_key
JOIN public.dim_producto     p ON f.producto_key = p.producto_key
JOIN public.dim_estado_orden e ON f.estado_key   = e.estado_key
WHERE e.es_efectiva
GROUP BY t.anio, t.trimestre, t.anio_mes, p.linea_producto;
