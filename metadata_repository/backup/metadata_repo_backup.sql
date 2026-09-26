-- ============================================================
-- Backup: Repositorio de Metadatos (Entregas 1 y 2)
-- Proyecto: Modelos y Persistencia de Datos - Entrega 2
-- Generado: 2026-09-25
--
-- Motor: PostgreSQL 18 (Railway).
-- Herramienta: script propio en Python con SQLAlchemy.
-- No se uso pg_dump porque el binario local es de PostgreSQL 15 y
-- aborta contra un servidor 18 por incompatibilidad de version.
--
-- Restaurar sobre una base vacia con:
--   psql "$URL" -f metadata_repository/backup/metadata_repo_backup.sql
--
-- Contenido:
--   data_source: 2 filas
--   db_table: 13 filas
--   db_column: 85 filas
--   business_entity: 8 filas
--   business_attribute: 47 filas
--   column_business_mapping: 78 filas
--   dw_object: 9 filas
--   dw_measure: 9 filas
--   dw_attribute: 68 filas
--   dw_lineage: 46 filas
--   etl_process: 2 filas
--   etl_execution: 2 filas
--   dq_rule: 8 filas
--   dq_result: 7 filas
-- ============================================================

-- Limpieza previa (idempotente)
DROP TABLE IF EXISTS dq_result CASCADE;
DROP TABLE IF EXISTS dq_rule CASCADE;
DROP TABLE IF EXISTS etl_execution CASCADE;
DROP TABLE IF EXISTS etl_process CASCADE;
DROP TABLE IF EXISTS dw_lineage CASCADE;
DROP TABLE IF EXISTS dw_attribute CASCADE;
DROP TABLE IF EXISTS dw_measure CASCADE;
DROP TABLE IF EXISTS dw_object CASCADE;
DROP TABLE IF EXISTS column_business_mapping CASCADE;
DROP TABLE IF EXISTS business_attribute CASCADE;
DROP TABLE IF EXISTS business_entity CASCADE;
DROP TABLE IF EXISTS db_column CASCADE;
DROP TABLE IF EXISTS db_table CASCADE;
DROP TABLE IF EXISTS data_source CASCADE;

CREATE TABLE data_source (
    source_id SERIAL PRIMARY KEY,
    source_name VARCHAR(100) NOT NULL,
    db_engine VARCHAR(50) NOT NULL,
    description TEXT
);

CREATE TABLE db_table (
    table_id SERIAL PRIMARY KEY,
    source_id INTEGER NOT NULL,
    schema_name VARCHAR(100) NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    table_description TEXT,
    row_count_approx INTEGER,
    loaded_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE db_column (
    column_id SERIAL PRIMARY KEY,
    table_id INTEGER NOT NULL,
    column_name VARCHAR(100) NOT NULL,
    ordinal_position INTEGER,
    data_type VARCHAR(100) NOT NULL,
    native_data_type VARCHAR(150),
    is_nullable BOOLEAN NOT NULL DEFAULT true,
    is_primary_key BOOLEAN NOT NULL DEFAULT false,
    is_foreign_key BOOLEAN NOT NULL DEFAULT false,
    fk_ref_column_id INTEGER,
    loaded_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE business_entity (
    entity_id SERIAL PRIMARY KEY,
    entity_name VARCHAR(150) NOT NULL,
    entity_description TEXT NOT NULL,
    data_domain VARCHAR(150) NOT NULL
);

CREATE TABLE business_attribute (
    attribute_id SERIAL PRIMARY KEY,
    entity_id INTEGER NOT NULL,
    attribute_name VARCHAR(150) NOT NULL,
    attribute_definition TEXT NOT NULL
);

CREATE TABLE column_business_mapping (
    mapping_id SERIAL PRIMARY KEY,
    column_id INTEGER NOT NULL,
    attribute_id INTEGER NOT NULL
);

CREATE TABLE dw_object (
    dw_object_id SERIAL PRIMARY KEY,
    object_name VARCHAR(100) NOT NULL,
    object_type VARCHAR(20) NOT NULL,
    grain TEXT,
    description TEXT NOT NULL,
    is_conformed BOOLEAN NOT NULL DEFAULT false,
    row_count INTEGER,
    loaded_at TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE dw_measure (
    dw_measure_id SERIAL PRIMARY KEY,
    dw_object_id INTEGER NOT NULL,
    measure_name VARCHAR(100) NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    additivity VARCHAR(20) NOT NULL,
    formula TEXT,
    description TEXT
);

CREATE TABLE dw_attribute (
    dw_attribute_id SERIAL PRIMARY KEY,
    dw_object_id INTEGER NOT NULL,
    attribute_name VARCHAR(100) NOT NULL,
    data_type VARCHAR(50) NOT NULL,
    attribute_role VARCHAR(30) NOT NULL,
    description TEXT
);

CREATE TABLE dw_lineage (
    dw_lineage_id SERIAL PRIMARY KEY,
    source_column_id INTEGER,
    target_measure_id INTEGER,
    target_attribute_id INTEGER,
    transformation_rule TEXT NOT NULL
);

CREATE TABLE etl_process (
    etl_process_id SERIAL PRIMARY KEY,
    process_name VARCHAR(100) NOT NULL,
    tool VARCHAR(80) NOT NULL,
    source_systems VARCHAR(200) NOT NULL,
    target_system VARCHAR(100) NOT NULL,
    description TEXT
);

CREATE TABLE etl_execution (
    etl_execution_id SERIAL PRIMARY KEY,
    etl_process_id INTEGER NOT NULL,
    run_id INTEGER NOT NULL,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    status VARCHAR(20) NOT NULL,
    rows_read INTEGER,
    rows_written INTEGER,
    rows_rejected INTEGER,
    error_message TEXT
);

CREATE TABLE dq_rule (
    dq_rule_id SERIAL PRIMARY KEY,
    rule_name VARCHAR(120) NOT NULL,
    rule_type VARCHAR(40) NOT NULL,
    source_column_id INTEGER,
    expression TEXT NOT NULL,
    severity VARCHAR(20) NOT NULL,
    resolution TEXT NOT NULL
);

CREATE TABLE dq_result (
    dq_result_id SERIAL PRIMARY KEY,
    dq_rule_id INTEGER NOT NULL,
    etl_execution_id INTEGER NOT NULL,
    evaluated_at TIMESTAMP NOT NULL DEFAULT now(),
    rows_evaluated INTEGER,
    rows_failed INTEGER,
    passed BOOLEAN NOT NULL
);

-- ============================================================
-- Datos
-- ============================================================

-- data_source: 2 filas
INSERT INTO data_source (source_id, source_name, db_engine, description) VALUES
    (1, 'classicmodels', 'MySQL', 'Base de datos transaccional de ventas (MySQL): clientes, empleados, oficinas, ordenes de compra, pagos junto con el catalogo de productos.'),
    (2, 'customerservice', 'PostgreSQL', 'Base de datos del centro de servicio al cliente (PostgreSQL): clientes, empleados, catalogo de productos, llamadas de servicio junto con el registro de productos de interes de cada cliente.');

-- db_table: 13 filas
INSERT INTO db_table (table_id, source_id, schema_name, table_name, table_description, row_count_approx, loaded_at) VALUES
    (1, 1, 'classicmodels', 'customers', 'Clientes de la compania que realizan ordenes de compra.', 122, '2026-09-26 03:26:27.993839'),
    (2, 1, 'classicmodels', 'employees', 'Empleados de la compania, incluye representantes de ventas y su jerarquia.', 23, '2026-09-26 03:26:27.993839'),
    (3, 1, 'classicmodels', 'offices', 'Oficinas o sedes fisicas de la compania.', 7, '2026-09-26 03:26:27.993839'),
    (4, 1, 'classicmodels', 'orderdetails', 'Detalle (lineas) de cada orden de compra: producto, cantidad y precio.', 2996, '2026-09-26 03:26:27.993839'),
    (5, 1, 'classicmodels', 'orders', 'Encabezado de las ordenes de compra realizadas por los clientes.', 326, '2026-09-26 03:26:27.993839'),
    (6, 1, 'classicmodels', 'payments', 'Pagos realizados por los clientes asociados a sus ordenes de compra.', 273, '2026-09-26 03:26:27.993839'),
    (7, 1, 'classicmodels', 'productlines', 'Lineas o categorias de productos.', 7, '2026-09-26 03:26:27.993839'),
    (8, 1, 'classicmodels', 'products', 'Catalogo de productos que la compania vende.', 110, '2026-09-26 03:26:27.993839'),
    (9, 2, 'public', 'cs_customers', 'Clientes registrados en el sistema de call center.', 122, '2026-09-26 03:26:27.993839'),
    (10, 2, 'public', 'cs_customer_calls', 'Registro de llamadas de servicio al cliente.', 108, '2026-09-26 03:26:27.993839'),
    (11, 2, 'public', 'cs_employees', 'Empleados que atienden llamadas en el call center.', 30, '2026-09-26 03:26:27.993839'),
    (12, 2, 'public', 'cs_products', 'Catalogo de productos referenciado en las llamadas de servicio.', 110, '2026-09-26 03:26:27.993839'),
    (13, 2, 'public', 'cs_customer_products', 'Relacion entre clientes y productos consultados en servicio.', 101, '2026-09-26 03:26:27.993839');

-- db_column: 85 filas
INSERT INTO db_column (column_id, table_id, column_name, ordinal_position, data_type, native_data_type, is_nullable, is_primary_key, is_foreign_key, fk_ref_column_id, loaded_at) VALUES
    (1, 1, 'customerNumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (2, 1, 'customerName', 2, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (3, 1, 'contactLastName', 3, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (4, 1, 'contactFirstName', 4, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (5, 1, 'phone', 5, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (6, 1, 'addressLine1', 6, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (7, 1, 'addressLine2', 7, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (8, 1, 'city', 8, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (9, 1, 'state', 9, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (10, 1, 'postalCode', 10, 'VARCHAR(15)', 'VARCHAR(15)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (11, 1, 'country', 11, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (13, 1, 'creditLimit', 13, 'DECIMAL', 'DECIMAL(10, 2)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (14, 2, 'employeeNumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (15, 2, 'lastName', 2, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (16, 2, 'firstName', 3, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (17, 2, 'extension', 4, 'VARCHAR(10)', 'VARCHAR(10)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (18, 2, 'email', 5, 'VARCHAR(100)', 'VARCHAR(100)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (21, 2, 'jobTitle', 8, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (22, 3, 'officeCode', 1, 'VARCHAR(10)', 'VARCHAR(10)', FALSE, TRUE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (23, 3, 'city', 2, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (24, 3, 'phone', 3, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (25, 3, 'addressLine1', 4, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (26, 3, 'addressLine2', 5, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (27, 3, 'state', 6, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (28, 3, 'country', 7, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (29, 3, 'postalCode', 8, 'VARCHAR(15)', 'VARCHAR(15)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (30, 3, 'territory', 9, 'VARCHAR(10)', 'VARCHAR(10)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (33, 4, 'quantityOrdered', 3, 'INTEGER', 'INTEGER', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (34, 4, 'priceEach', 4, 'DECIMAL', 'DECIMAL(10, 2)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (35, 4, 'orderLineNumber', 5, 'INTEGER', 'SMALLINT', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (36, 5, 'orderNumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (37, 5, 'orderDate', 2, 'DATE', 'DATE', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (38, 5, 'requiredDate', 3, 'DATE', 'DATE', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (39, 5, 'shippedDate', 4, 'DATE', 'DATE', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (40, 5, 'status', 5, 'VARCHAR(15)', 'VARCHAR(15)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (41, 5, 'comments', 6, 'TEXT', 'TEXT', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (44, 6, 'checkNumber', 2, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, TRUE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (45, 6, 'paymentDate', 3, 'DATE', 'DATE', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (46, 6, 'amount', 4, 'DECIMAL', 'DECIMAL(10, 2)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (47, 7, 'productLine', 1, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, TRUE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (48, 7, 'textDescription', 2, 'VARCHAR(4000)', 'VARCHAR(4000)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (49, 7, 'htmlDescription', 3, 'TEXT', 'MEDIUMTEXT', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (50, 7, 'image', 4, 'BINARY', 'MEDIUMBLOB', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (51, 8, 'productCode', 1, 'VARCHAR(15)', 'VARCHAR(15)', FALSE, TRUE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (52, 8, 'productName', 2, 'VARCHAR(70)', 'VARCHAR(70)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (54, 8, 'productScale', 4, 'VARCHAR(10)', 'VARCHAR(10)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (55, 8, 'productVendor', 5, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (56, 8, 'productDescription', 6, 'TEXT', 'TEXT', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (57, 8, 'quantityInStock', 7, 'INTEGER', 'SMALLINT', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (58, 8, 'buyPrice', 8, 'DECIMAL', 'DECIMAL(10, 2)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (59, 8, 'MSRP', 9, 'DECIMAL', 'DECIMAL(10, 2)', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (60, 9, 'customernumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (61, 9, 'contactlastname', 2, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (62, 9, 'contactfirstname', 3, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (63, 9, 'phone', 4, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (64, 9, 'addressline1', 5, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (65, 9, 'addressline2', 6, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (66, 9, 'city', 7, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (67, 9, 'state', 8, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (68, 9, 'postalcode', 9, 'VARCHAR(15)', 'VARCHAR(15)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (69, 9, 'country', 10, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (73, 10, 'text', 4, 'VARCHAR(200)', 'VARCHAR(200)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (74, 10, 'date', 5, 'TIMESTAMP', 'TIMESTAMP', FALSE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (75, 11, 'employeenumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (76, 11, 'lastname', 2, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (77, 11, 'firstname', 3, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (78, 11, 'email', 4, 'VARCHAR(100)', 'VARCHAR(100)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (79, 12, 'productcode', 1, 'VARCHAR(15)', 'VARCHAR(15)', FALSE, TRUE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (80, 12, 'productname', 2, 'VARCHAR(70)', 'VARCHAR(70)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (81, 12, 'productscale', 3, 'VARCHAR(10)', 'VARCHAR(10)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (82, 12, 'productvendor', 4, 'VARCHAR(50)', 'VARCHAR(50)', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (83, 12, 'productdescription', 5, 'TEXT', 'TEXT', TRUE, FALSE, FALSE, NULL, '2026-09-26 03:26:27.993839'),
    (19, 2, 'officeCode', 6, 'VARCHAR(10)', 'VARCHAR(10)', FALSE, FALSE, TRUE, 22, '2026-09-26 03:26:27.993839'),
    (12, 1, 'salesRepEmployeeNumber', 12, 'INTEGER', 'INTEGER', TRUE, FALSE, TRUE, 14, '2026-09-26 03:26:27.993839'),
    (20, 2, 'reportsTo', 7, 'INTEGER', 'INTEGER', TRUE, FALSE, TRUE, 14, '2026-09-26 03:26:27.993839'),
    (31, 4, 'orderNumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, TRUE, 36, '2026-09-26 03:26:27.993839'),
    (32, 4, 'productCode', 2, 'VARCHAR(15)', 'VARCHAR(15)', FALSE, TRUE, TRUE, 51, '2026-09-26 03:26:27.993839'),
    (42, 5, 'customerNumber', 7, 'INTEGER', 'INTEGER', FALSE, FALSE, TRUE, 1, '2026-09-26 03:26:27.993839'),
    (43, 6, 'customerNumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, TRUE, 1, '2026-09-26 03:26:27.993839'),
    (53, 8, 'productLine', 3, 'VARCHAR(50)', 'VARCHAR(50)', FALSE, FALSE, TRUE, 47, '2026-09-26 03:26:27.993839'),
    (70, 10, 'employeenumber', 1, 'INTEGER', 'INTEGER', FALSE, FALSE, TRUE, 75, '2026-09-26 03:26:27.993839'),
    (71, 10, 'customernumber', 2, 'INTEGER', 'INTEGER', FALSE, FALSE, TRUE, 60, '2026-09-26 03:26:27.993839'),
    (72, 10, 'productcode', 3, 'VARCHAR(15)', 'VARCHAR(15)', FALSE, FALSE, TRUE, 79, '2026-09-26 03:26:27.993839'),
    (84, 13, 'customernumber', 1, 'INTEGER', 'INTEGER', FALSE, TRUE, TRUE, 60, '2026-09-26 03:26:27.993839'),
    (85, 13, 'productcode', 2, 'VARCHAR(15)', 'VARCHAR(15)', FALSE, TRUE, TRUE, 79, '2026-09-26 03:26:27.993839');

-- business_entity: 8 filas
INSERT INTO business_entity (entity_id, entity_name, entity_description, data_domain) VALUES
    (1, 'Cliente', 'Persona o empresa que compra productos de la compania o realiza contacto con el centro de servicio.', 'Datos de Cliente'),
    (2, 'Empleado', 'Persona que trabaja en la compania, como representante de ventas o agente de servicio al cliente.', 'Datos de Recurso Humano'),
    (3, 'Producto', 'Articulo del catalogo que la compania vende o que es objeto de consulta en servicio al cliente.', 'Datos de Producto'),
    (4, 'Linea de Producto', 'Categoria o familia a la que pertenece un producto.', 'Datos de Producto'),
    (5, 'Oficina', 'Sede fisica de la compania donde trabajan los empleados.', 'Datos Organizacionales'),
    (6, 'Orden de Compra', 'Pedido realizado por un cliente, compuesto por un encabezado y sus lineas de detalle.', 'Datos Transaccionales de Ventas'),
    (7, 'Pago', 'Registro de un pago realizado por un cliente asociado a sus ordenes de compra.', 'Datos Financieros'),
    (8, 'Llamada de Servicio', 'Registro de una llamada realizada por un cliente al centro de servicio al cliente.', 'Datos de Servicio al Cliente');

-- business_attribute: 47 filas
INSERT INTO business_attribute (attribute_id, entity_id, attribute_name, attribute_definition) VALUES
    (1, 1, 'Limite de Credito', 'Monto maximo de credito autorizado para el cliente.'),
    (2, 1, 'Pais de Cliente', 'Pais de domicilio del cliente.'),
    (3, 1, 'Codigo Postal de Cliente', 'Codigo postal del domicilio del cliente.'),
    (4, 1, 'Estado o Region de Cliente', 'Estado, departamento o region del domicilio del cliente.'),
    (5, 1, 'Ciudad de Cliente', 'Ciudad de residencia o domicilio del cliente.'),
    (6, 1, 'Direccion Linea 2', 'Segunda linea (complemento) de la direccion fisica del cliente.'),
    (7, 1, 'Direccion Linea 1', 'Primera linea de la direccion fisica del cliente.'),
    (8, 1, 'Telefono de Cliente', 'Numero telefonico de contacto del cliente.'),
    (9, 1, 'Nombre de Contacto', 'Nombre de la persona de contacto del cliente.'),
    (10, 1, 'Apellido de Contacto', 'Apellido de la persona de contacto del cliente.'),
    (11, 1, 'Nombre de Cliente', 'Nombre o razon social del cliente.'),
    (12, 1, 'Numero de Cliente', 'Identificador unico del cliente.'),
    (13, 2, 'Numero de Empleado Supervisor', 'Identificador del empleado al que este empleado reporta (jefe directo).'),
    (14, 2, 'Cargo', 'Cargo o puesto que ocupa el empleado en la compania.'),
    (15, 2, 'Extension Telefonica', 'Extension telefonica interna del empleado.'),
    (16, 2, 'Correo Electronico', 'Correo electronico de contacto del empleado.'),
    (17, 2, 'Nombre de Empleado', 'Nombre del empleado.'),
    (18, 2, 'Apellido de Empleado', 'Apellido del empleado.'),
    (19, 2, 'Numero de Empleado', 'Identificador unico del empleado.'),
    (20, 3, 'Precio Sugerido de Venta', 'Precio de venta al publico sugerido (MSRP).'),
    (21, 3, 'Precio de Compra', 'Precio al que la compania adquiere el producto.'),
    (22, 3, 'Cantidad en Inventario', 'Unidades disponibles del producto en inventario.'),
    (23, 3, 'Descripcion de Producto', 'Descripcion textual de las caracteristicas del producto.'),
    (24, 3, 'Fabricante o Proveedor', 'Fabricante o proveedor que suministra el producto.'),
    (25, 3, 'Escala de Producto', 'Escala de fabricacion del producto (ej. 1:10, 1:24).'),
    (26, 3, 'Nombre de Producto', 'Nombre comercial del producto.'),
    (27, 3, 'Codigo de Producto', 'Identificador unico del producto en el catalogo.'),
    (28, 4, 'Descripcion de Linea', 'Descripcion textual de la linea de producto.'),
    (29, 4, 'Codigo de Linea', 'Nombre/codigo de la linea o categoria de producto.'),
    (30, 5, 'Territorio', 'Territorio comercial al que pertenece la oficina.'),
    (31, 5, 'Pais de Oficina', 'Pais donde se ubica la oficina.'),
    (32, 5, 'Direccion de Oficina', 'Direccion fisica de la oficina.'),
    (33, 5, 'Telefono de Oficina', 'Numero telefonico principal de la oficina.'),
    (34, 5, 'Ciudad de Oficina', 'Ciudad donde se ubica la oficina.'),
    (35, 5, 'Codigo de Oficina', 'Identificador unico de la oficina o sede.'),
    (36, 6, 'Precio Unitario', 'Precio unitario acordado para el producto en esa orden.'),
    (37, 6, 'Cantidad Ordenada', 'Cantidad de unidades pedidas de un producto en la orden.'),
    (38, 6, 'Estado de Orden', 'Estado actual de la orden (ej. Shipped, Cancelled).'),
    (39, 6, 'Fecha de Envio', 'Fecha real de envio de la orden.'),
    (40, 6, 'Fecha Requerida', 'Fecha en la que el cliente requiere la entrega.'),
    (41, 6, 'Fecha de Orden', 'Fecha en que se realizo la orden.'),
    (42, 6, 'Numero de Orden', 'Identificador unico de la orden de compra.'),
    (43, 7, 'Monto de Pago', 'Valor monetario del pago realizado.'),
    (44, 7, 'Fecha de Pago', 'Fecha en que se registro el pago.'),
    (45, 7, 'Numero de Cheque', 'Identificador del cheque o comprobante de pago.'),
    (46, 8, 'Fecha de Llamada', 'Fecha y hora en que se realizo la llamada de servicio.'),
    (47, 8, 'Comentario de Llamada', 'Texto u observacion registrada durante la llamada de servicio.');

-- column_business_mapping: 78 filas
INSERT INTO column_business_mapping (mapping_id, column_id, attribute_id) VALUES
    (1, 12, 19),
    (2, 13, 1),
    (3, 11, 2),
    (4, 10, 3),
    (5, 9, 4),
    (6, 8, 5),
    (7, 7, 6),
    (8, 6, 7),
    (9, 5, 8),
    (10, 4, 9),
    (11, 3, 10),
    (12, 2, 11),
    (13, 1, 12),
    (14, 19, 35),
    (15, 20, 13),
    (16, 21, 14),
    (17, 17, 15),
    (18, 18, 16),
    (19, 16, 17),
    (20, 15, 18),
    (21, 14, 19),
    (22, 30, 30),
    (23, 28, 31),
    (24, 25, 32),
    (25, 24, 33),
    (26, 23, 34),
    (27, 22, 35),
    (28, 34, 36),
    (29, 33, 37),
    (30, 32, 27),
    (31, 31, 42),
    (32, 42, 12),
    (33, 40, 38),
    (34, 39, 39),
    (35, 38, 40),
    (36, 37, 41),
    (37, 36, 42),
    (38, 46, 43),
    (39, 45, 44),
    (40, 44, 45),
    (41, 43, 12),
    (42, 48, 28),
    (43, 47, 29),
    (44, 53, 29),
    (45, 59, 20),
    (46, 58, 21),
    (47, 57, 22),
    (48, 56, 23),
    (49, 55, 24),
    (50, 54, 25),
    (51, 52, 26),
    (52, 51, 27),
    (53, 69, 2),
    (54, 68, 3),
    (55, 67, 4),
    (56, 66, 5),
    (57, 65, 6),
    (58, 64, 7),
    (59, 63, 8),
    (60, 62, 9),
    (61, 61, 10),
    (62, 60, 12),
    (63, 74, 46),
    (64, 73, 47),
    (65, 72, 27),
    (66, 71, 12),
    (67, 70, 19),
    (68, 78, 16),
    (69, 77, 17),
    (70, 76, 18),
    (71, 75, 19),
    (72, 83, 23),
    (73, 82, 24),
    (74, 81, 25),
    (75, 80, 26),
    (76, 79, 27),
    (77, 85, 27),
    (78, 84, 12);

-- dw_object: 9 filas
INSERT INTO dw_object (dw_object_id, object_name, object_type, grain, description, is_conformed, row_count, loaded_at) VALUES
    (1, 'dim_cliente', 'DIMENSION', NULL, 'Dimension de cliente. Conformada entre classicmodels y customerservice, que solapan al 100% por customerNumber. Las banderas presente_en_ventas y presente_en_servicio indican en que fuente aparece cada cliente.', TRUE, 122, '2026-09-26 03:26:36.618193'),
    (2, 'dim_empleado', 'DIMENSION', NULL, 'Dimension de empleado. NO conformada: las dos fuentes tienen solape 0% en la llave. Usa llave de negocio compuesta (numero_empleado, sistema_origen) para que ambas poblaciones convivan sin colisionar.', FALSE, 53, '2026-09-26 03:26:36.618193'),
    (3, 'dim_estado_orden', 'DIMENSION', NULL, 'Dimension de estado de la orden. es_efectiva distingue las ventas cerradas de las canceladas, en disputa o en espera.', FALSE, 6, '2026-09-26 03:26:36.618193'),
    (4, 'dim_oficina', 'DIMENSION', NULL, 'Dimension de oficina. Exclusiva de classicmodels: la sede desde la que trabaja el representante de ventas.', FALSE, 7, '2026-09-26 03:26:36.618193'),
    (5, 'dim_producto', 'DIMENSION', NULL, 'Dimension de producto. Conformada entre las dos fuentes, que solapan al 100% por productCode. Incluye la linea de producto desnormalizada.', TRUE, 110, '2026-09-26 03:26:36.618193'),
    (6, 'dim_tiempo', 'DIMENSION', NULL, 'Dimension de tiempo generada dia a dia entre 2003 y 2005. Conformada: la comparten los dos hechos.', TRUE, 1096, '2026-09-26 03:26:36.618193'),
    (7, 'fact_llamadas_servicio', 'FACT', 'Una llamada al centro de servicio al cliente.', 'Hecho secundario. Registra cada llamada de customerservice, relacionada con el cliente que llamo, el producto consultado y el agente que atendio.', FALSE, 108, '2026-09-26 03:26:36.618193'),
    (8, 'fact_ventas', 'FACT', 'Una linea de una orden de compra.', 'Hecho principal del almacen. Registra cada linea de detalle de las ordenes de classicmodels, con sus medidas de cantidad, monto, costo y margen.', FALSE, 2996, '2026-09-26 03:26:36.618193'),
    (9, 'vw_interaccion_cliente_producto', 'VIEW', 'Cliente x producto x mes.', 'Vista que cruza los dos hechos al grano cliente-producto-mes. Es la que permite responder que productos generan mas llamadas por unidad vendida, pregunta que ninguna fuente contesta por si sola.', FALSE, 3100, '2026-09-26 03:26:36.618193');

-- dw_measure: 9 filas
INSERT INTO dw_measure (dw_measure_id, dw_object_id, measure_name, data_type, additivity, formula, description) VALUES
    (1, 7, 'cantidad_llamadas', 'SMALLINT', 'ADITIVA', '1', 'Contador de llamadas. Permite sumar llamadas en cualquier dimension.'),
    (2, 7, 'longitud_texto', 'INTEGER', 'ADITIVA', 'length(cs_customer_calls.text)', 'Longitud de la nota del agente, como proxy de complejidad del caso.'),
    (3, 8, 'cantidad_ordenada', 'INTEGER', 'ADITIVA', 'orderdetails.quantityOrdered', 'Unidades del producto pedidas en la linea.'),
    (4, 8, 'precio_unitario', 'NUMERIC(12, 2)', 'NO_ADITIVA', 'orderdetails.priceEach', 'Precio pactado por unidad. No se suma: se promedia ponderado.'),
    (5, 8, 'monto_linea', 'NUMERIC(14, 2)', 'ADITIVA', 'quantityOrdered * priceEach', 'Valor facturado de la linea. Es la medida central del almacen.'),
    (6, 8, 'costo_linea', 'NUMERIC(14, 2)', 'ADITIVA', 'quantityOrdered * products.buyPrice', 'Costo de adquisicion de las unidades vendidas.'),
    (7, 8, 'margen_linea', 'NUMERIC(14, 2)', 'ADITIVA', 'monto_linea - costo_linea', 'Utilidad bruta de la linea.'),
    (8, 8, 'precio_msrp', 'NUMERIC(12, 2)', 'NO_ADITIVA', 'products.MSRP', 'Precio sugerido de venta. Sirve para medir descuento aplicado.'),
    (9, 8, 'dias_hasta_envio', 'SMALLINT', 'SEMI_ADITIVA', 'orders.shippedDate - orders.orderDate', 'Dias entre el pedido y el despacho. Se promedia, no se suma. NULL en las ordenes que no se despacharon.');

-- dw_attribute: 68 filas
INSERT INTO dw_attribute (dw_attribute_id, dw_object_id, attribute_name, data_type, attribute_role, description) VALUES
    (1, 1, 'cliente_key', 'INTEGER', 'SURROGATE_KEY', NULL),
    (2, 1, 'numero_cliente', 'INTEGER', 'BUSINESS_KEY', NULL),
    (3, 1, 'nombre_cliente', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (4, 1, 'contacto_nombre', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (5, 1, 'contacto_apellido', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (6, 1, 'telefono', 'VARCHAR(50)', 'DESCRIPTIVE', NULL),
    (7, 1, 'direccion_completa', 'VARCHAR(220)', 'DESCRIPTIVE', NULL),
    (8, 1, 'ciudad', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (9, 1, 'estado_region', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (10, 1, 'codigo_postal', 'VARCHAR(20)', 'DESCRIPTIVE', NULL),
    (11, 1, 'pais', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (12, 1, 'limite_credito', 'NUMERIC(12, 2)', 'DESCRIPTIVE', NULL),
    (13, 1, 'presente_en_ventas', 'BOOLEAN', 'FLAG', NULL),
    (14, 1, 'presente_en_servicio', 'BOOLEAN', 'FLAG', NULL),
    (15, 2, 'empleado_key', 'INTEGER', 'SURROGATE_KEY', NULL),
    (16, 2, 'numero_empleado', 'INTEGER', 'BUSINESS_KEY', NULL),
    (17, 2, 'sistema_origen', 'VARCHAR(20)', 'DESCRIPTIVE', NULL),
    (18, 2, 'nombre', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (19, 2, 'apellido', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (20, 2, 'email', 'VARCHAR(140)', 'DESCRIPTIVE', NULL),
    (21, 2, 'cargo', 'VARCHAR(80)', 'DESCRIPTIVE', NULL),
    (22, 2, 'numero_oficina', 'VARCHAR(20)', 'DESCRIPTIVE', NULL),
    (23, 3, 'estado_key', 'INTEGER', 'SURROGATE_KEY', NULL),
    (24, 3, 'estado', 'VARCHAR(30)', 'BUSINESS_KEY', NULL),
    (25, 3, 'es_efectiva', 'BOOLEAN', 'FLAG', NULL),
    (26, 4, 'oficina_key', 'INTEGER', 'SURROGATE_KEY', NULL),
    (27, 4, 'codigo_oficina', 'VARCHAR(20)', 'BUSINESS_KEY', NULL),
    (28, 4, 'ciudad', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (29, 4, 'pais', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (30, 4, 'region', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (31, 4, 'territorio', 'VARCHAR(20)', 'DESCRIPTIVE', NULL),
    (32, 5, 'producto_key', 'INTEGER', 'SURROGATE_KEY', NULL),
    (33, 5, 'codigo_producto', 'VARCHAR(20)', 'BUSINESS_KEY', NULL),
    (34, 5, 'nombre_producto', 'VARCHAR(140)', 'DESCRIPTIVE', NULL),
    (35, 5, 'linea_producto', 'VARCHAR(60)', 'DESCRIPTIVE', NULL),
    (36, 5, 'descripcion_linea', 'TEXT', 'DESCRIPTIVE', NULL),
    (37, 5, 'escala', 'VARCHAR(20)', 'DESCRIPTIVE', NULL),
    (38, 5, 'proveedor', 'VARCHAR(100)', 'DESCRIPTIVE', NULL),
    (39, 5, 'precio_compra', 'NUMERIC(12, 2)', 'DESCRIPTIVE', NULL),
    (40, 5, 'precio_msrp', 'NUMERIC(12, 2)', 'DESCRIPTIVE', NULL),
    (41, 5, 'presente_en_ventas', 'BOOLEAN', 'FLAG', NULL),
    (42, 5, 'presente_en_servicio', 'BOOLEAN', 'FLAG', NULL),
    (43, 6, 'tiempo_key', 'INTEGER', 'SURROGATE_KEY', NULL),
    (44, 6, 'fecha', 'DATE', 'BUSINESS_KEY', NULL),
    (45, 6, 'anio', 'SMALLINT', 'DESCRIPTIVE', NULL),
    (46, 6, 'trimestre', 'SMALLINT', 'DESCRIPTIVE', NULL),
    (47, 6, 'mes', 'SMALLINT', 'DESCRIPTIVE', NULL),
    (48, 6, 'nombre_mes', 'VARCHAR(12)', 'DESCRIPTIVE', NULL),
    (49, 6, 'dia', 'SMALLINT', 'DESCRIPTIVE', NULL),
    (50, 6, 'dia_semana', 'SMALLINT', 'DESCRIPTIVE', NULL),
    (51, 6, 'nombre_dia', 'VARCHAR(12)', 'DESCRIPTIVE', NULL),
    (52, 6, 'es_fin_semana', 'BOOLEAN', 'FLAG', NULL),
    (53, 6, 'anio_mes', 'CHAR(7)', 'DESCRIPTIVE', NULL),
    (54, 7, 'llamada_key', 'BIGINT', 'SURROGATE_KEY', NULL),
    (55, 7, 'tiempo_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (56, 7, 'cliente_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (57, 7, 'producto_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (58, 7, 'empleado_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (59, 7, 'texto_llamada', 'TEXT', 'DEGENERATE', NULL),
    (60, 8, 'venta_key', 'BIGINT', 'SURROGATE_KEY', NULL),
    (61, 8, 'tiempo_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (62, 8, 'cliente_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (63, 8, 'producto_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (64, 8, 'empleado_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (65, 8, 'oficina_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (66, 8, 'estado_key', 'INTEGER', 'FOREIGN_KEY', NULL),
    (67, 8, 'numero_orden', 'INTEGER', 'DEGENERATE', NULL),
    (68, 8, 'numero_linea', 'SMALLINT', 'DEGENERATE', NULL);

-- dw_lineage: 46 filas
INSERT INTO dw_lineage (dw_lineage_id, source_column_id, target_measure_id, target_attribute_id, transformation_rule) VALUES
    (1, 1, NULL, 2, 'llave de negocio, copia directa'),
    (2, 2, NULL, 3, 'copia directa'),
    (3, 4, NULL, 4, 'copia directa'),
    (4, 3, NULL, 5, 'copia directa'),
    (5, 5, NULL, 6, 'copia directa'),
    (6, 6, NULL, 7, 'concatenacion: addressLine1 + addressLine2 (esta ultima nula en 81,97%)'),
    (7, 8, NULL, 8, 'copia directa'),
    (8, 9, NULL, 9, 'copia directa'),
    (9, 10, NULL, 10, 'copia directa'),
    (10, 11, NULL, 11, 'copia directa'),
    (11, 13, NULL, 12, 'copia directa'),
    (12, 60, NULL, 14, 'bandera: existe en customerservice'),
    (13, 14, NULL, 16, 'llave de negocio compuesta con sistema_origen'),
    (14, 16, NULL, 18, 'union de employees y cs_employees'),
    (15, 15, NULL, 19, 'union de employees y cs_employees'),
    (16, 18, NULL, 20, 'union de employees y cs_employees'),
    (17, 21, NULL, 21, 'de classicmodels; constante para los agentes de servicio'),
    (18, 19, NULL, 22, 'solo classicmodels; NULL para agentes de servicio'),
    (19, 40, NULL, 24, 'valores distintos de orders.status'),
    (20, 40, NULL, 25, 'derivada: FALSE si status es Cancelled, Disputed u On Hold'),
    (21, 22, NULL, 27, 'llave de negocio, copia directa'),
    (22, 23, NULL, 28, 'copia directa'),
    (23, 28, NULL, 29, 'copia directa'),
    (24, 27, NULL, 30, 'copia directa'),
    (25, 30, NULL, 31, 'copia directa'),
    (26, 51, NULL, 33, 'llave de negocio, copia directa'),
    (27, 52, NULL, 34, 'copia directa'),
    (28, 53, NULL, 35, 'copia directa'),
    (29, 48, NULL, 36, 'desnormalizacion desde productlines'),
    (30, 54, NULL, 37, 'copia directa'),
    (31, 55, NULL, 38, 'copia directa'),
    (32, 58, NULL, 39, 'copia directa'),
    (33, 59, NULL, 40, 'copia directa'),
    (34, 79, NULL, 42, 'bandera: existe en customerservice'),
    (35, 73, NULL, 59, 'dimension degenerada'),
    (36, 71, 1, NULL, 'constante 1 por fila'),
    (37, 73, 2, NULL, 'calculo: length(text)'),
    (38, 36, NULL, 67, 'dimension degenerada'),
    (39, 35, NULL, 68, 'dimension degenerada'),
    (40, 33, 3, NULL, 'copia directa'),
    (41, 34, 4, NULL, 'copia directa'),
    (42, 34, 5, NULL, 'calculo: quantityOrdered * priceEach'),
    (43, 58, 6, NULL, 'calculo: quantityOrdered * buyPrice'),
    (44, 58, 7, NULL, 'calculo: monto_linea - costo_linea'),
    (45, 59, 8, NULL, 'copia directa'),
    (46, 39, 9, NULL, 'calculo: shippedDate - orderDate; NULL si no se despacho');

-- etl_process: 2 filas
INSERT INTO etl_process (etl_process_id, process_name, tool, source_systems, target_system, description) VALUES
    (1, 'etl_dw_dimensions', 'Python 3.11 + SQLAlchemy 2.x + pandas', 'classicmodels (MySQL), customerservice (PostgreSQL)', 'dw (PostgreSQL)', 'Carga las seis dimensiones del almacen, incluidas las tres conformadas entre las dos fuentes.'),
    (2, 'etl_dw_facts', 'Python 3.11 + SQLAlchemy 2.x + pandas', 'classicmodels (MySQL), customerservice (PostgreSQL)', 'dw (PostgreSQL)', 'Carga fact_ventas y fact_llamadas_servicio resolviendo llaves subrogadas, y crea la vista integrada.');

-- etl_execution: 2 filas
INSERT INTO etl_execution (etl_execution_id, etl_process_id, run_id, started_at, finished_at, status, rows_read, rows_written, rows_rejected, error_message) VALUES
    (1, 1, 1, '2026-09-25 22:26:32.217167', '2026-09-25 22:26:33.143656', 'OK', 530, 1394, 0, NULL),
    (2, 2, 1, '2026-09-25 22:26:34.368499', '2026-09-25 22:26:35.813199', 'OK', 3104, 3104, 0, NULL);

-- dq_rule: 8 filas
INSERT INTO dq_rule (dq_rule_id, rule_name, rule_type, source_column_id, expression, severity, resolution) VALUES
    (1, 'cliente_conformidad_fuentes', 'CONFORMIDAD', 1, 'customers.customerNumber = cs_customers.customernumber (solape 100%)', 'BLOQUEANTE', 'Permite que dim_cliente sea conformada y que los dos hechos la compartan.'),
    (2, 'cliente_direccion_linea2_nula', 'COMPLETITUD', 7, 'pct_nulos(addressLine2) < 50', 'ADVERTENCIA', 'Se consolida con addressLine1 en el atributo direccion_completa de dim_cliente.'),
    (3, 'empleado_conformidad_fuentes', 'CONFORMIDAD', 14, 'classicmodels.employees.employeeNumber INTERSECT cs_employees.employeenumber = vacio', 'BLOQUEANTE', 'dim_empleado usa llave de negocio compuesta (numero_empleado, sistema_origen) con llave subrogada encima, para que las dos poblaciones convivan sin colisionar.'),
    (4, 'estado_orden_no_efectivo', 'INTEGRIDAD', 40, 'status IN (''Cancelled'', ''Disputed'', ''On Hold'') marca venta no efectiva', 'ADVERTENCIA', 'Se cargan todas las ordenes, pero dim_estado_orden.es_efectiva permite excluirlas de los reportes sin borrarlas del almacen.'),
    (5, 'orden_fecha_envio_nula', 'COMPLETITUD', 39, 'shippedDate IS NOT NULL OR status <> ''Shipped''', 'ADVERTENCIA', 'dias_hasta_envio queda NULL en fact_ventas; dim_estado_orden explica el motivo.'),
    (6, 'orden_comentarios_nulos', 'COMPLETITUD', 41, 'pct_nulos(comments) < 50', 'INFORMATIVA', 'Texto libre sin valor analitico: no se lleva a fact_ventas.'),
    (7, 'productline_columnas_vacias', 'COMPLETITUD', 49, 'COUNT(htmlDescription) = 0 AND COUNT(image) = 0', 'INFORMATIVA', 'Las dos columnas se excluyen de dim_producto. Solo se trae textDescription.'),
    (8, 'producto_conformidad_fuentes', 'CONFORMIDAD', 51, 'products.productCode = cs_products.productcode (solape 100%)', 'BLOQUEANTE', 'Permite que dim_producto sea conformada y que los dos hechos la compartan.');

-- dq_result: 7 filas
INSERT INTO dq_result (dq_result_id, dq_rule_id, etl_execution_id, evaluated_at, rows_evaluated, rows_failed, passed) VALUES
    (1, 4, 1, '2026-09-26 03:26:33.144875', 6, 3, TRUE),
    (2, 2, 1, '2026-09-26 03:26:33.144875', 122, 100, TRUE),
    (3, 1, 1, '2026-09-26 03:26:33.144875', 122, 0, TRUE),
    (4, 7, 1, '2026-09-26 03:26:33.144875', 2, 2, TRUE),
    (5, 8, 1, '2026-09-26 03:26:33.144875', 110, 0, TRUE),
    (6, 3, 1, '2026-09-26 03:26:33.144875', 53, 0, TRUE),
    (7, 5, 2, '2026-09-26 03:26:35.814865', 2996, 141, TRUE);

-- Sincronizacion de secuencias SERIAL
SELECT setval('data_source_source_id_seq', 2, true);
SELECT setval('db_table_table_id_seq', 13, true);
SELECT setval('db_column_column_id_seq', 85, true);
SELECT setval('business_entity_entity_id_seq', 8, true);
SELECT setval('business_attribute_attribute_id_seq', 47, true);
SELECT setval('column_business_mapping_mapping_id_seq', 78, true);
SELECT setval('dw_object_dw_object_id_seq', 9, true);
SELECT setval('dw_measure_dw_measure_id_seq', 9, true);
SELECT setval('dw_attribute_dw_attribute_id_seq', 68, true);
SELECT setval('dw_lineage_dw_lineage_id_seq', 46, true);
SELECT setval('etl_process_etl_process_id_seq', 2, true);
SELECT setval('etl_execution_etl_execution_id_seq', 2, true);
SELECT setval('dq_rule_dq_rule_id_seq', 8, true);
SELECT setval('dq_result_dq_result_id_seq', 7, true);
