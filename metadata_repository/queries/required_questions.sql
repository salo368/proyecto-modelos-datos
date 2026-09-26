-- ============================================================
-- The six questions the metadata repository must answer.
--
-- Run against METADATA_URL once etl/etl_source_metadata.py and
-- seeds/business_metadata.sql have been loaded.
-- ============================================================

-- ------------------------------------------------------------
-- 1. Which tables exist in the sources and in which database
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
-- 2. Columns of a given table: name, data type and whether it is
--    part of the primary key. Change the filter to query another table.
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
-- 3. Business glossary: entities, description and data domain
-- ------------------------------------------------------------
SELECT
    entity_name,
    entity_description,
    data_domain
FROM business_entity
ORDER BY entity_name;


-- ------------------------------------------------------------
-- 4. Attributes of a given business entity: name and definition.
--    Change the filter to query another entity.
-- ------------------------------------------------------------
SELECT
    ba.attribute_name,
    ba.attribute_definition
FROM business_attribute ba
JOIN business_entity be ON ba.entity_id = be.entity_id
WHERE be.entity_name = 'Cliente'
ORDER BY ba.attribute_name;


-- ------------------------------------------------------------
-- 5. Entity location report: every business entity with the source
--    database and table(s) that store it. LEFT JOINs keep entities
--    without mapped attributes in the result (with NULL location).
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
-- 6. Semantic lineage of cs_customers: column name, data type,
--    business attribute, attribute definition and business entity.
--    LEFT JOINs keep columns that have no business mapping yet.
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
