-- Technical metadata discovery - classicmodels (MySQL), from information_schema.

-- 1. Tables
SELECT
    TABLE_SCHEMA   AS nombre_bd,
    TABLE_NAME     AS nombre_tabla,
    TABLE_TYPE     AS tipo,
    TABLE_ROWS     AS filas_aprox
FROM information_schema.TABLES
WHERE TABLE_SCHEMA = 'classicmodels'
ORDER BY TABLE_NAME;

-- 2. Columns per table: name, data type, nullability
SELECT
    TABLE_NAME      AS nombre_tabla,
    COLUMN_NAME     AS nombre_columna,
    ORDINAL_POSITION AS posicion,
    DATA_TYPE       AS tipo_dato,
    CHARACTER_MAXIMUM_LENGTH AS longitud,
    NUMERIC_PRECISION AS precision_num,
    NUMERIC_SCALE   AS escala,
    IS_NULLABLE     AS permite_nulo,
    COLUMN_DEFAULT  AS valor_default
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'classicmodels'
ORDER BY TABLE_NAME, ORDINAL_POSITION;

-- 3. Primary keys
SELECT
    tc.TABLE_NAME    AS nombre_tabla,
    kcu.COLUMN_NAME  AS nombre_columna,
    tc.CONSTRAINT_TYPE AS tipo_llave
FROM information_schema.TABLE_CONSTRAINTS tc
JOIN information_schema.KEY_COLUMN_USAGE kcu
    ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
    AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
WHERE tc.TABLE_SCHEMA = 'classicmodels'
    AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
ORDER BY tc.TABLE_NAME;

-- 4. Foreign keys
SELECT
    kcu.TABLE_NAME        AS tabla_origen,
    kcu.COLUMN_NAME       AS columna_origen,
    kcu.REFERENCED_TABLE_NAME  AS tabla_referenciada,
    kcu.REFERENCED_COLUMN_NAME AS columna_referenciada
FROM information_schema.KEY_COLUMN_USAGE kcu
WHERE kcu.TABLE_SCHEMA = 'classicmodels'
    AND kcu.REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY kcu.TABLE_NAME;
