-- ============================================================
-- Consultas de negocio sobre el almacen - Entrega 2
--
-- Todas corren contra la base 'dw'. Ninguna toca las fuentes
-- originales, como exige el enunciado.
-- ============================================================

-- ------------------------------------------------------------
-- 1. LA PREGUNTA QUE JUSTIFICA HABER INTEGRADO LAS DOS FUENTES
--
-- Que productos generan mas llamadas de servicio por unidad vendida.
-- Ninguna de las dos fuentes responde esto por si sola: las ventas
-- estan en classicmodels (MySQL) y las llamadas en customerservice
-- (PostgreSQL). Solo se puede contestar gracias a que dim_cliente y
-- dim_producto son dimensiones conformadas.
--
-- Lectura: un valor alto significa que el producto genera mucha
-- friccion de postventa en relacion con lo que se vende. Son
-- candidatos a revision de calidad o de documentacion.
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
-- 2. Ventas y margen por mes
-- Solo ordenes efectivas: excluye Cancelled, Disputed y On Hold
-- gracias a dim_estado_orden.es_efectiva.
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
-- 3. Desempeno por linea de producto
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
-- 4. Ventas por oficina del representante
-- ------------------------------------------------------------
SELECT o.ciudad, o.pais, o.territorio,
       COUNT(DISTINCT f.numero_orden) AS ordenes,
       ROUND(SUM(f.monto_linea), 2)   AS monto_vendido
FROM fact_ventas f
JOIN dim_oficina o ON f.oficina_key = o.oficina_key
GROUP BY o.ciudad, o.pais, o.territorio
ORDER BY monto_vendido DESC;


-- ------------------------------------------------------------
-- 5. Clientes: cuanto compran frente a cuanto llaman
-- Alimenta el grafico de dispersion del reporte 3.
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
-- 6. Carga de trabajo del centro de servicio por agente
-- Demuestra que la llave compuesta de dim_empleado funciona: aqui
-- solo aparecen los 30 agentes de customerservice, nunca los 23
-- vendedores de classicmodels, aunque comparten rango de numeros.
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
