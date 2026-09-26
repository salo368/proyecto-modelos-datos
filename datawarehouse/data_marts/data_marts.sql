-- ============================================================
-- Data marts (schema dm)
--
-- Views built on top of the star schema in public. Each one raises
-- the grain and keeps a single subject:
--
--   dm.vw_interaccion_cliente_producto  effective sales and service
--                                       calls per customer x product x
--                                       month
--   dm.vw_ventas_mensuales_linea        effective sales per month x
--                                       product line
--
-- Both count only effective orders (dim_estado_orden.es_efectiva excludes
-- Cancelled, Disputed and On Hold): units of a cancelled order were
-- never sold.
--
-- Run after datawarehouse/edw/star_schema.sql.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS dm;

DROP VIEW IF EXISTS dm.vw_interaccion_cliente_producto     CASCADE;
DROP VIEW IF EXISTS dm.vw_ventas_mensuales_linea           CASCADE;

-- ------------------------------------------------------------
-- Sales and service per customer x product x month.
--
-- Aggregates both facts to the same grain and joins them with a FULL
-- OUTER JOIN, so it answers which products generate the most service
-- calls per unit sold. Sales are effective orders only; every call
-- counts.
-- ------------------------------------------------------------
CREATE VIEW dm.vw_interaccion_cliente_producto AS
WITH ventas AS (
    SELECT f.cliente_key, f.producto_key, t.anio_mes,
           SUM(f.cantidad_ordenada) AS unidades_vendidas,
           SUM(f.monto_linea)       AS monto_vendido,
           SUM(f.margen_linea)      AS margen_total,
           COUNT(*)                 AS lineas_orden
    FROM public.fact_ventas f
    JOIN public.dim_tiempo       t ON f.tiempo_key = t.tiempo_key
    JOIN public.dim_estado_orden e ON f.estado_key = e.estado_key
    WHERE e.es_efectiva
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
-- Monthly sales performance per product line. Effective orders only
-- (dim_estado_orden.es_efectiva excludes Cancelled, Disputed, On Hold).
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
