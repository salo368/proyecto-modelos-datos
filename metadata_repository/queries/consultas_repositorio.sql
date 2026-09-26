-- ============================================================
-- Consultas requeridas - Punto 3: Repositorio de Metadatos
-- Proyecto Final - Entrega 1 - Modelos y Persistencia de Datos
--
-- Correr contra la base de datos METADATA_REPO_URL (schema public),
-- una vez el ETL haya cargado el metadato tecnico y se hayan
-- ingresado manualmente el metadato de negocio y el linaje semantico
-- (business_entity, business_attribute, column_business_mapping).
-- ============================================================

-- ------------------------------------------------------------
-- 1. Cuales tablas se tienen en las fuentes de datos y en que
--    base de datos esta cada tabla
-- ------------------------------------------------------------
SELECT
    ds.source_name   AS base_de_datos,
    ds.db_engine,
    dt.schema_name,
    dt.table_name
FROM db_table dt
JOIN data_source ds ON dt.source_id = ds.source_id
ORDER BY ds.source_name, dt.table_name;


-- ------------------------------------------------------------
-- 2. Para una tabla especifica: que columnas tiene
--    (nombre, tipo de dato, si es parte de la llave primaria)
--    Ejemplo con 'orders' - cambiar el valor del filtro segun la tabla.
-- ------------------------------------------------------------
SELECT
    dc.column_name,
    dc.data_type,
    dc.is_primary_key
FROM db_column dc
JOIN db_table dt ON dc.table_id = dt.table_id
WHERE dt.table_name = 'orders'
ORDER BY dc.ordinal_position;


-- ------------------------------------------------------------
-- 3. Glosario de negocio: que entidades de negocio existen,
--    su descripcion y su dominio de datos
-- ------------------------------------------------------------
SELECT
    entity_name,
    entity_description,
    data_domain
FROM business_entity
ORDER BY entity_name;


-- ------------------------------------------------------------
-- 4. Para una entidad especifica: que atributos tiene
--    (nombre del atributo y definicion)
--    Ejemplo con 'Cliente' - cambiar el valor del filtro segun la entidad.
-- ------------------------------------------------------------
SELECT
    ba.attribute_name,
    ba.attribute_definition
FROM business_attribute ba
JOIN business_entity be ON ba.entity_id = be.entity_id
WHERE be.entity_name = 'Cliente'
ORDER BY ba.attribute_name;


-- ------------------------------------------------------------
-- 5. Reporte de ubicacion de entidades: todas las entidades de
--    negocio junto con la(s) tabla(s) que almacenan su informacion
--    (nombre de bd y nombre de tabla)
--    LEFT JOIN a proposito, igual que en la consulta 6: una entidad de
--    negocio que aun no tenga ningun atributo mapeado debe seguir
--    apareciendo en el reporte (con NULL en base_de_datos/table_name),
--    en vez de desaparecer silenciosamente.
-- ------------------------------------------------------------
SELECT DISTINCT
    be.entity_name,
    ds.source_name AS base_de_datos,
    dt.table_name
FROM business_entity be
LEFT JOIN business_attribute ba          ON ba.entity_id = be.entity_id
LEFT JOIN column_business_mapping cbm    ON cbm.attribute_id = ba.attribute_id
LEFT JOIN db_column dc                   ON dc.column_id = cbm.column_id
LEFT JOIN db_table dt                    ON dc.table_id = dt.table_id
LEFT JOIN data_source ds                 ON dt.source_id = ds.source_id
ORDER BY be.entity_name, ds.source_name, dt.table_name;


-- ------------------------------------------------------------
-- 6. Linaje semantico de columnas para la tabla cs_customers:
--    nombre de columna, tipo de dato, nombre de atributo de
--    negocio, definicion de atributo, nombre de entidad de negocio.
--    LEFT JOIN a proposito: asi se ven tambien las columnas que
--    aun no tienen mapeo de negocio (linaje incompleto), en vez
--    de que desaparezcan de la respuesta.
-- ------------------------------------------------------------
SELECT
    dc.column_name,
    dc.data_type,
    ba.attribute_name,
    ba.attribute_definition,
    be.entity_name
FROM db_column dc
JOIN db_table dt                         ON dc.table_id = dt.table_id
LEFT JOIN column_business_mapping cbm    ON cbm.column_id = dc.column_id
LEFT JOIN business_attribute ba          ON ba.attribute_id = cbm.attribute_id
LEFT JOIN business_entity be             ON be.entity_id = ba.entity_id
WHERE dt.table_name = 'cs_customers'
ORDER BY dc.ordinal_position;
