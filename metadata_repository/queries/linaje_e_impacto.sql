-- ============================================================
-- Linaje de punta a punta - Entrega 2
--
-- La Clase 3 distingue DOS recorridos sobre el mismo grafo de linaje,
-- y son preguntas de negocio distintas:
--
--   LINAJE DE DATOS        Destino -> Origenes
--                          "De donde viene este dato que me muestra
--                           un reporte?"
--                          Lo usa quien duda de una cifra.
--
--   ANALISIS DE IMPACTO    Origen -> Destino
--                          "Si modifico esta tabla, que procesos se
--                           afectan?"
--                          Lo usa quien va a cambiar una fuente.
--
-- El grafo es el mismo (dw_lineage mas column_business_mapping de la
-- Entrega 1); lo que cambia es la direccion en que se recorre y, sobre
-- todo, quien hace la pregunta y para que.
--
-- Correr contra METADATA_REPO_URL.
-- ============================================================


-- ------------------------------------------------------------
-- 1. LINAJE DE DATOS  (destino -> origenes)
--
-- Punta a punta: parte de una medida o atributo del almacen y llega
-- hasta la columna fisica de la fuente, pasando por la entidad de
-- negocio que le da significado.
--
-- Cadena completa:
--   business_entity <- business_attribute <- column_business_mapping
--                   <- db_column <- dw_lineage -> dw_measure/dw_attribute
-- ------------------------------------------------------------
SELECT
    o.object_name                                   AS objeto_almacen,
    COALESCE(m.measure_name, a.attribute_name)      AS campo_almacen,
    CASE WHEN m.dw_measure_id IS NOT NULL
         THEN 'medida' ELSE 'atributo' END          AS tipo_campo,
    ds.source_name                                  AS fuente,
    dt.table_name || '.' || dc.column_name          AS columna_origen,
    dc.native_data_type                             AS tipo_origen,
    l.transformation_rule                           AS regla_transformacion,
    be.entity_name                                  AS entidad_negocio,
    ba.attribute_name                               AS atributo_negocio
FROM dw_lineage l
LEFT JOIN dw_measure   m  ON l.target_measure_id   = m.dw_measure_id
LEFT JOIN dw_attribute a  ON l.target_attribute_id = a.dw_attribute_id
LEFT JOIN dw_object    o  ON o.dw_object_id = COALESCE(m.dw_object_id, a.dw_object_id)
LEFT JOIN db_column    dc ON l.source_column_id = dc.column_id
LEFT JOIN db_table     dt ON dc.table_id   = dt.table_id
LEFT JOIN data_source  ds ON dt.source_id  = ds.source_id
LEFT JOIN column_business_mapping cbm ON cbm.column_id   = dc.column_id
LEFT JOIN business_attribute      ba  ON ba.attribute_id = cbm.attribute_id
LEFT JOIN business_entity         be  ON be.entity_id    = ba.entity_id
ORDER BY o.object_name, campo_almacen;


-- ------------------------------------------------------------
-- 2. ANALISIS DE IMPACTO  (origen -> destino)
--
-- La pregunta inversa: si alguien va a cambiar, renombrar o eliminar
-- una columna de una fuente, que se rompe.
--
-- El resultado lista, por cada columna de origen, todo lo que depende
-- de ella: objetos del almacen, campos concretos, reportes que los
-- consumen y reglas de calidad que la vigilan.
-- ------------------------------------------------------------
SELECT
    ds.source_name                          AS fuente,
    dt.table_name                           AS tabla_origen,
    dc.column_name                          AS columna_origen,
    COUNT(DISTINCT o.dw_object_id)          AS objetos_dw_afectados,
    STRING_AGG(DISTINCT o.object_name, ', ' ORDER BY o.object_name)
                                            AS cuales_objetos,
    COUNT(DISTINCT COALESCE(m.dw_measure_id, a.dw_attribute_id))
                                            AS campos_afectados,
    COUNT(DISTINCT uc.usage_consulta_id)    AS reportes_afectados,
    STRING_AGG(DISTINCT uc.nombre, ', ')    AS cuales_reportes,
    COUNT(DISTINCT r.dq_rule_id)            AS reglas_calidad_asociadas
FROM db_column dc
JOIN db_table    dt ON dc.table_id  = dt.table_id
JOIN data_source ds ON dt.source_id = ds.source_id
LEFT JOIN dw_lineage   l  ON l.source_column_id   = dc.column_id
LEFT JOIN dw_measure   m  ON l.target_measure_id  = m.dw_measure_id
LEFT JOIN dw_attribute a  ON l.target_attribute_id = a.dw_attribute_id
LEFT JOIN dw_object    o  ON o.dw_object_id = COALESCE(m.dw_object_id, a.dw_object_id)
LEFT JOIN usage_consulta_objeto uco ON uco.dw_object_id = o.dw_object_id
LEFT JOIN usage_consulta        uc  ON uc.usage_consulta_id = uco.usage_consulta_id
LEFT JOIN dq_rule               r   ON r.source_column_id = dc.column_id
GROUP BY ds.source_name, dt.table_name, dc.column_name
HAVING COUNT(DISTINCT o.dw_object_id) > 0
ORDER BY objetos_dw_afectados DESC, reportes_afectados DESC,
         dt.table_name, dc.column_name;


-- ------------------------------------------------------------
-- 3. Analisis de impacto para UNA columna concreta
--
-- Es la consulta que se corre en la practica: antes de tocar
-- customers.customerNumber, ver exactamente que depende de ella.
-- Cambiar la tabla y columna del WHERE segun el caso.
-- ------------------------------------------------------------
SELECT
    dt.table_name || '.' || dc.column_name     AS voy_a_modificar,
    o.object_name                              AS se_afecta_objeto,
    COALESCE(m.measure_name, a.attribute_name) AS se_afecta_campo,
    l.transformation_rule                      AS como_se_usa,
    uc.nombre                                  AS reporte_que_lo_consume,
    uc.frecuencia                              AS cada_cuanto_corre
FROM db_column dc
JOIN db_table  dt ON dc.table_id = dt.table_id
JOIN dw_lineage l ON l.source_column_id = dc.column_id
LEFT JOIN dw_measure   m ON l.target_measure_id   = m.dw_measure_id
LEFT JOIN dw_attribute a ON l.target_attribute_id = a.dw_attribute_id
LEFT JOIN dw_object    o ON o.dw_object_id = COALESCE(m.dw_object_id, a.dw_object_id)
LEFT JOIN usage_consulta_objeto uco ON uco.dw_object_id = o.dw_object_id
LEFT JOIN usage_consulta        uc  ON uc.usage_consulta_id = uco.usage_consulta_id
WHERE dt.table_name = 'customers'
  AND dc.column_name = 'customerNumber'
ORDER BY o.object_name, se_afecta_campo, uc.nombre;


-- ------------------------------------------------------------
-- 4. Cobertura del linaje
--
-- Que campos del almacen NO tienen origen declarado, y si eso es
-- correcto. Las llaves subrogadas y dim_tiempo no deben tenerlo: las
-- genera el almacen, no vienen de ninguna fuente.
-- ------------------------------------------------------------
WITH campos AS (
    SELECT o.object_name, m.measure_name AS campo,
           m.dw_measure_id AS id, 'measure' AS tipo
    FROM dw_measure m JOIN dw_object o ON m.dw_object_id = o.dw_object_id
    UNION ALL
    SELECT o.object_name, a.attribute_name, a.dw_attribute_id, 'attribute'
    FROM dw_attribute a JOIN dw_object o ON a.dw_object_id = o.dw_object_id
)
SELECT c.object_name,
       c.campo,
       CASE
           WHEN c.campo LIKE '%\_key'      THEN 'Correcto: llave subrogada generada por el almacen'
           WHEN c.object_name = 'dim_tiempo' THEN 'Correcto: dimension generada por codigo'
           WHEN c.campo = 'sistema_origen'   THEN 'Correcto: literal asignado por el ETL'
           ELSE 'REVISAR: deberia tener origen declarado'
       END AS diagnostico
FROM campos c
LEFT JOIN dw_lineage l
       ON (c.tipo = 'measure'   AND l.target_measure_id   = c.id)
       OR (c.tipo = 'attribute' AND l.target_attribute_id = c.id)
WHERE l.dw_lineage_id IS NULL
ORDER BY diagnostico, c.object_name, c.campo;
