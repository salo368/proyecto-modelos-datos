-- Descubrimiento de metadatos técnicos - customerservice (PostgreSQL)
-- Ejecutar contra la BD restaurada en Railway

-- 1. Listado de tablas
SELECT
    table_catalog AS nombre_bd,
    table_schema  AS esquema,
    table_name    AS nombre_tabla,
    table_type    AS tipo
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- 2. Columnas por tabla: nombre, tipo de dato, nulabilidad
SELECT
    table_name        AS nombre_tabla,
    column_name        AS nombre_columna,
    ordinal_position   AS posicion,
    data_type          AS tipo_dato,
    character_maximum_length AS longitud,
    numeric_precision  AS precision_num,
    numeric_scale      AS escala,
    is_nullable        AS permite_nulo,
    column_default     AS valor_default
FROM information_schema.columns
WHERE table_schema = 'public'
ORDER BY table_name, ordinal_position;

-- 3. Llaves primarias
SELECT
    tc.table_name   AS nombre_tabla,
    kcu.column_name AS nombre_columna,
    tc.constraint_type AS tipo_llave
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = 'public'
    AND tc.constraint_type = 'PRIMARY KEY'
ORDER BY tc.table_name;

-- 4. Llaves foráneas (relaciones entre tablas)
SELECT
    tc.table_name          AS tabla_origen,
    kcu.column_name        AS columna_origen,
    ccu.table_name         AS tabla_referenciada,
    ccu.column_name        AS columna_referenciada
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
    ON tc.constraint_name = kcu.constraint_name
    AND tc.table_schema = kcu.table_schema
JOIN information_schema.constraint_column_usage ccu
    ON tc.constraint_name = ccu.constraint_name
    AND tc.table_schema = ccu.table_schema
WHERE tc.table_schema = 'public'
    AND tc.constraint_type = 'FOREIGN KEY'
ORDER BY tc.table_name;
