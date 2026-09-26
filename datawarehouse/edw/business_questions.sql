-- ============================================================
-- Business questions answered from the data warehouse.
--
-- All queries run against the 'dw' database only; none reads the
-- original sources. They are the same queries behind the Metabase
-- dashboard (reports/build_dashboard.py).
-- ============================================================

-- ------------------------------------------------------------
-- 1. Service calls per unit sold, by product.
--    Sales come from classicmodels and calls from customerservice; the
--    conformed dim_cliente / dim_producto make the comparison possible.
--    A high value means after-sales friction relative to volume. Units
--    come from effective orders only (the data mart filters them).
-- ------------------------------------------------------------
SELECT nombre_producto,
       linea_producto,
       SUM(unidades_vendidas) AS unidades,
       SUM(num_llamadas)      AS llamadas,
       ROUND(SUM(num_llamadas)::numeric
             / NULLIF(SUM(unidades_vendidas), 0), 4) AS llamadas_por_unidad
FROM dm.vw_interaccion_cliente_producto
GROUP BY nombre_producto, linea_producto
HAVING SUM(unidades_vendidas) > 0
   AND SUM(num_llamadas)      > 0
ORDER BY llamadas_por_unidad DESC
LIMIT 15;


-- ------------------------------------------------------------
-- 2. Sales and margin per month (effective orders only).
-- ------------------------------------------------------------
SELECT t.anio_mes,
       COUNT(DISTINCT f.numero_orden) AS ordenes,
       SUM(f.cantidad_ordenada)       AS unidades,
       ROUND(SUM(f.monto_linea),  2)  AS monto_vendido,
       ROUND(SUM(f.margen_linea), 2)  AS margen,
       ROUND(100 * SUM(f.margen_linea) / NULLIF(SUM(f.monto_linea), 0), 2)
           AS margen_pct
FROM fact_ventas f
JOIN dim_tiempo       t ON f.tiempo_key = t.tiempo_key
JOIN dim_estado_orden e ON f.estado_key = e.estado_key
WHERE e.es_efectiva
GROUP BY t.anio_mes
ORDER BY t.anio_mes;


-- ------------------------------------------------------------
-- 3. Performance per product line
-- ------------------------------------------------------------
SELECT p.linea_producto,
       COUNT(*)                       AS lineas_vendidas,
       SUM(f.cantidad_ordenada)       AS unidades,
       ROUND(SUM(f.monto_linea),  2)  AS monto_vendido,
       ROUND(SUM(f.margen_linea), 2)  AS margen,
       ROUND(100 * SUM(f.margen_linea) / NULLIF(SUM(f.monto_linea), 0), 2)
           AS margen_pct
FROM fact_ventas f
JOIN dim_producto p ON f.producto_key = p.producto_key
GROUP BY p.linea_producto
ORDER BY monto_vendido DESC;


-- ------------------------------------------------------------
-- 4. Sales per sales-rep office
-- ------------------------------------------------------------
SELECT o.ciudad, o.pais, o.territorio,
       COUNT(DISTINCT f.numero_orden) AS ordenes,
       ROUND(SUM(f.monto_linea), 2)   AS monto_vendido
FROM fact_ventas f
JOIN dim_oficina o ON f.oficina_key = o.oficina_key
GROUP BY o.ciudad, o.pais, o.territorio
ORDER BY monto_vendido DESC;


-- ------------------------------------------------------------
-- 5. Customers: amount purchased (effective orders) vs. calls made
-- ------------------------------------------------------------
SELECT numero_cliente,
       nombre_cliente,
       pais,
       ROUND(SUM(monto_vendido), 2) AS monto_comprado,
       SUM(num_llamadas)            AS llamadas
FROM dm.vw_interaccion_cliente_producto
GROUP BY numero_cliente, nombre_cliente, pais
ORDER BY monto_comprado DESC
LIMIT 25;


-- ------------------------------------------------------------
-- 6. Call-center workload per agent. Only customerservice agents
--    appear: calls are looked up with sistema_origen = 'customerservice'.
-- ------------------------------------------------------------
SELECT e.numero_empleado,
       e.nombre || ' ' || e.apellido AS agente,
       e.sistema_origen,
       COUNT(*)                      AS llamadas_atendidas,
       ROUND(AVG(l.longitud_texto))  AS longitud_promedio_nota
FROM fact_llamadas_servicio l
JOIN dim_empleado e ON l.empleado_key = e.empleado_key
GROUP BY e.numero_empleado, e.nombre, e.apellido, e.sistema_origen
ORDER BY llamadas_atendidas DESC
LIMIT 15;
