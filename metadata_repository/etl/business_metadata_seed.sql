-- ============================================================
-- Metadato de negocio (ingreso manual) - Punto 3
-- Proyecto Final - Entrega 1 - Modelos y Persistencia de Datos
--
-- Correr contra la base de datos METADATA_REPO_URL (schema public),
-- DESPUES de que el ETL haya cargado el metadato tecnico
-- (data_source, db_table, db_column ya deben tener datos).
--
-- Idempotente: se puede correr varias veces sin duplicar filas
-- (ON CONFLICT DO NOTHING sobre las UNIQUE constraints del DDL).
-- ============================================================

-- ------------------------------------------------------------
-- 0. Verificacion previa: el ETL tecnico debe haber corrido primero,
--    de lo contrario los INSERT...SELECT...JOIN de abajo insertan 0
--    filas sin ningun error visible (join contra tablas vacias).
-- ------------------------------------------------------------
DO $$
BEGIN
    IF (SELECT count(*) FROM db_column) = 0 THEN
        RAISE EXCEPTION 'db_column esta vacio. Corre primero scripts/etl_metadata_repository.py '
            'contra METADATA_REPO_URL antes de este script.';
    END IF;
END $$;

-- ------------------------------------------------------------
-- 1. Entidades de negocio
-- ------------------------------------------------------------
INSERT INTO business_entity (entity_name, entity_description, data_domain) VALUES
('Cliente', 'Persona o empresa que compra productos de la compania o realiza contacto con el centro de servicio.', 'Datos de Cliente'),
('Empleado', 'Persona que trabaja en la compania, como representante de ventas o agente de servicio al cliente.', 'Datos de Recurso Humano'),
('Producto', 'Articulo del catalogo que la compania vende o que es objeto de consulta en servicio al cliente.', 'Datos de Producto'),
('Linea de Producto', 'Categoria o familia a la que pertenece un producto.', 'Datos de Producto'),
('Oficina', 'Sede fisica de la compania donde trabajan los empleados.', 'Datos Organizacionales'),
('Orden de Compra', 'Pedido realizado por un cliente, compuesto por un encabezado y sus lineas de detalle.', 'Datos Transaccionales de Ventas'),
('Pago', 'Registro de un pago realizado por un cliente asociado a sus ordenes de compra.', 'Datos Financieros'),
('Llamada de Servicio', 'Registro de una llamada realizada por un cliente al centro de servicio al cliente.', 'Datos de Servicio al Cliente')
ON CONFLICT (entity_name) DO NOTHING;

-- ------------------------------------------------------------
-- 2. Atributos de negocio
-- ------------------------------------------------------------
INSERT INTO business_attribute (entity_id, attribute_name, attribute_definition)
SELECT be.entity_id, v.attribute_name, v.attribute_definition
FROM (VALUES
    -- Cliente
    ('Cliente', 'Numero de Cliente', 'Identificador unico del cliente.'),
    ('Cliente', 'Nombre de Cliente', 'Nombre o razon social del cliente.'),
    ('Cliente', 'Apellido de Contacto', 'Apellido de la persona de contacto del cliente.'),
    ('Cliente', 'Nombre de Contacto', 'Nombre de la persona de contacto del cliente.'),
    ('Cliente', 'Telefono de Cliente', 'Numero telefonico de contacto del cliente.'),
    ('Cliente', 'Direccion Linea 1', 'Primera linea de la direccion fisica del cliente.'),
    ('Cliente', 'Direccion Linea 2', 'Segunda linea (complemento) de la direccion fisica del cliente.'),
    ('Cliente', 'Ciudad de Cliente', 'Ciudad de residencia o domicilio del cliente.'),
    ('Cliente', 'Estado o Region de Cliente', 'Estado, departamento o region del domicilio del cliente.'),
    ('Cliente', 'Codigo Postal de Cliente', 'Codigo postal del domicilio del cliente.'),
    ('Cliente', 'Pais de Cliente', 'Pais de domicilio del cliente.'),
    ('Cliente', 'Limite de Credito', 'Monto maximo de credito autorizado para el cliente.'),

    -- Empleado
    ('Empleado', 'Numero de Empleado', 'Identificador unico del empleado.'),
    ('Empleado', 'Apellido de Empleado', 'Apellido del empleado.'),
    ('Empleado', 'Nombre de Empleado', 'Nombre del empleado.'),
    ('Empleado', 'Correo Electronico', 'Correo electronico de contacto del empleado.'),
    ('Empleado', 'Extension Telefonica', 'Extension telefonica interna del empleado.'),
    ('Empleado', 'Cargo', 'Cargo o puesto que ocupa el empleado en la compania.'),
    ('Empleado', 'Numero de Empleado Supervisor', 'Identificador del empleado al que este empleado reporta (jefe directo).'),

    -- Producto
    ('Producto', 'Codigo de Producto', 'Identificador unico del producto en el catalogo.'),
    ('Producto', 'Nombre de Producto', 'Nombre comercial del producto.'),
    ('Producto', 'Escala de Producto', 'Escala de fabricacion del producto (ej. 1:10, 1:24).'),
    ('Producto', 'Fabricante o Proveedor', 'Fabricante o proveedor que suministra el producto.'),
    ('Producto', 'Descripcion de Producto', 'Descripcion textual de las caracteristicas del producto.'),
    ('Producto', 'Cantidad en Inventario', 'Unidades disponibles del producto en inventario.'),
    ('Producto', 'Precio de Compra', 'Precio al que la compania adquiere el producto.'),
    ('Producto', 'Precio Sugerido de Venta', 'Precio de venta al publico sugerido (MSRP).'),

    -- Linea de Producto
    ('Linea de Producto', 'Codigo de Linea', 'Nombre/codigo de la linea o categoria de producto.'),
    ('Linea de Producto', 'Descripcion de Linea', 'Descripcion textual de la linea de producto.'),

    -- Oficina
    ('Oficina', 'Codigo de Oficina', 'Identificador unico de la oficina o sede.'),
    ('Oficina', 'Ciudad de Oficina', 'Ciudad donde se ubica la oficina.'),
    ('Oficina', 'Telefono de Oficina', 'Numero telefonico principal de la oficina.'),
    ('Oficina', 'Direccion de Oficina', 'Direccion fisica de la oficina.'),
    ('Oficina', 'Pais de Oficina', 'Pais donde se ubica la oficina.'),
    ('Oficina', 'Territorio', 'Territorio comercial al que pertenece la oficina.'),

    -- Orden de Compra
    ('Orden de Compra', 'Numero de Orden', 'Identificador unico de la orden de compra.'),
    ('Orden de Compra', 'Fecha de Orden', 'Fecha en que se realizo la orden.'),
    ('Orden de Compra', 'Fecha Requerida', 'Fecha en la que el cliente requiere la entrega.'),
    ('Orden de Compra', 'Fecha de Envio', 'Fecha real de envio de la orden.'),
    ('Orden de Compra', 'Estado de Orden', 'Estado actual de la orden (ej. Shipped, Cancelled).'),
    ('Orden de Compra', 'Cantidad Ordenada', 'Cantidad de unidades pedidas de un producto en la orden.'),
    ('Orden de Compra', 'Precio Unitario', 'Precio unitario acordado para el producto en esa orden.'),

    -- Pago
    ('Pago', 'Numero de Cheque', 'Identificador del cheque o comprobante de pago.'),
    ('Pago', 'Fecha de Pago', 'Fecha en que se registro el pago.'),
    ('Pago', 'Monto de Pago', 'Valor monetario del pago realizado.'),

    -- Llamada de Servicio
    ('Llamada de Servicio', 'Comentario de Llamada', 'Texto u observacion registrada durante la llamada de servicio.'),
    ('Llamada de Servicio', 'Fecha de Llamada', 'Fecha y hora en que se realizo la llamada de servicio.')
) AS v(entity_name, attribute_name, attribute_definition)
JOIN business_entity be ON be.entity_name = v.entity_name
ON CONFLICT (entity_id, attribute_name) DO NOTHING;

-- ------------------------------------------------------------
-- 3. Linaje semantico: mapeo columna tecnica <-> atributo de negocio
-- ------------------------------------------------------------
INSERT INTO column_business_mapping (column_id, attribute_id)
SELECT dc.column_id, ba.attribute_id
FROM (VALUES
    -- Cliente <- classicmodels.customers
    ('classicmodels', 'customers', 'customerNumber', 'Cliente', 'Numero de Cliente'),
    ('classicmodels', 'customers', 'customerName', 'Cliente', 'Nombre de Cliente'),
    ('classicmodels', 'customers', 'contactLastName', 'Cliente', 'Apellido de Contacto'),
    ('classicmodels', 'customers', 'contactFirstName', 'Cliente', 'Nombre de Contacto'),
    ('classicmodels', 'customers', 'phone', 'Cliente', 'Telefono de Cliente'),
    ('classicmodels', 'customers', 'addressLine1', 'Cliente', 'Direccion Linea 1'),
    ('classicmodels', 'customers', 'addressLine2', 'Cliente', 'Direccion Linea 2'),
    ('classicmodels', 'customers', 'city', 'Cliente', 'Ciudad de Cliente'),
    ('classicmodels', 'customers', 'state', 'Cliente', 'Estado o Region de Cliente'),
    ('classicmodels', 'customers', 'postalCode', 'Cliente', 'Codigo Postal de Cliente'),
    ('classicmodels', 'customers', 'country', 'Cliente', 'Pais de Cliente'),
    ('classicmodels', 'customers', 'creditLimit', 'Cliente', 'Limite de Credito'),
    ('classicmodels', 'customers', 'salesRepEmployeeNumber', 'Empleado', 'Numero de Empleado'),

    -- Cliente <- customerservice.cs_customers (linaje completo, requerido por consulta 6)
    ('customerservice', 'cs_customers', 'customernumber', 'Cliente', 'Numero de Cliente'),
    ('customerservice', 'cs_customers', 'contactlastname', 'Cliente', 'Apellido de Contacto'),
    ('customerservice', 'cs_customers', 'contactfirstname', 'Cliente', 'Nombre de Contacto'),
    ('customerservice', 'cs_customers', 'phone', 'Cliente', 'Telefono de Cliente'),
    ('customerservice', 'cs_customers', 'addressline1', 'Cliente', 'Direccion Linea 1'),
    ('customerservice', 'cs_customers', 'addressline2', 'Cliente', 'Direccion Linea 2'),
    ('customerservice', 'cs_customers', 'city', 'Cliente', 'Ciudad de Cliente'),
    ('customerservice', 'cs_customers', 'state', 'Cliente', 'Estado o Region de Cliente'),
    ('customerservice', 'cs_customers', 'postalcode', 'Cliente', 'Codigo Postal de Cliente'),
    ('customerservice', 'cs_customers', 'country', 'Cliente', 'Pais de Cliente'),

    -- Empleado <- classicmodels.employees
    ('classicmodels', 'employees', 'employeeNumber', 'Empleado', 'Numero de Empleado'),
    ('classicmodels', 'employees', 'lastName', 'Empleado', 'Apellido de Empleado'),
    ('classicmodels', 'employees', 'firstName', 'Empleado', 'Nombre de Empleado'),
    ('classicmodels', 'employees', 'email', 'Empleado', 'Correo Electronico'),
    ('classicmodels', 'employees', 'extension', 'Empleado', 'Extension Telefonica'),
    ('classicmodels', 'employees', 'jobTitle', 'Empleado', 'Cargo'),
    ('classicmodels', 'employees', 'reportsTo', 'Empleado', 'Numero de Empleado Supervisor'),
    ('classicmodels', 'employees', 'officeCode', 'Oficina', 'Codigo de Oficina'),

    -- Empleado <- customerservice.cs_employees
    ('customerservice', 'cs_employees', 'employeenumber', 'Empleado', 'Numero de Empleado'),
    ('customerservice', 'cs_employees', 'lastname', 'Empleado', 'Apellido de Empleado'),
    ('customerservice', 'cs_employees', 'firstname', 'Empleado', 'Nombre de Empleado'),
    ('customerservice', 'cs_employees', 'email', 'Empleado', 'Correo Electronico'),

    -- Producto <- classicmodels.products
    ('classicmodels', 'products', 'productCode', 'Producto', 'Codigo de Producto'),
    ('classicmodels', 'products', 'productName', 'Producto', 'Nombre de Producto'),
    ('classicmodels', 'products', 'productScale', 'Producto', 'Escala de Producto'),
    ('classicmodels', 'products', 'productVendor', 'Producto', 'Fabricante o Proveedor'),
    ('classicmodels', 'products', 'productDescription', 'Producto', 'Descripcion de Producto'),
    ('classicmodels', 'products', 'quantityInStock', 'Producto', 'Cantidad en Inventario'),
    ('classicmodels', 'products', 'buyPrice', 'Producto', 'Precio de Compra'),
    ('classicmodels', 'products', 'MSRP', 'Producto', 'Precio Sugerido de Venta'),
    ('classicmodels', 'products', 'productLine', 'Linea de Producto', 'Codigo de Linea'),

    -- Producto <- customerservice.cs_products
    ('customerservice', 'cs_products', 'productcode', 'Producto', 'Codigo de Producto'),
    ('customerservice', 'cs_products', 'productname', 'Producto', 'Nombre de Producto'),
    ('customerservice', 'cs_products', 'productscale', 'Producto', 'Escala de Producto'),
    ('customerservice', 'cs_products', 'productvendor', 'Producto', 'Fabricante o Proveedor'),
    ('customerservice', 'cs_products', 'productdescription', 'Producto', 'Descripcion de Producto'),

    -- Linea de Producto <- classicmodels.productlines
    ('classicmodels', 'productlines', 'productLine', 'Linea de Producto', 'Codigo de Linea'),
    ('classicmodels', 'productlines', 'textDescription', 'Linea de Producto', 'Descripcion de Linea'),

    -- Oficina <- classicmodels.offices
    ('classicmodels', 'offices', 'officeCode', 'Oficina', 'Codigo de Oficina'),
    ('classicmodels', 'offices', 'city', 'Oficina', 'Ciudad de Oficina'),
    ('classicmodels', 'offices', 'phone', 'Oficina', 'Telefono de Oficina'),
    ('classicmodels', 'offices', 'addressLine1', 'Oficina', 'Direccion de Oficina'),
    ('classicmodels', 'offices', 'country', 'Oficina', 'Pais de Oficina'),
    ('classicmodels', 'offices', 'territory', 'Oficina', 'Territorio'),

    -- Orden de Compra <- classicmodels.orders / orderdetails
    ('classicmodels', 'orders', 'orderNumber', 'Orden de Compra', 'Numero de Orden'),
    ('classicmodels', 'orders', 'orderDate', 'Orden de Compra', 'Fecha de Orden'),
    ('classicmodels', 'orders', 'requiredDate', 'Orden de Compra', 'Fecha Requerida'),
    ('classicmodels', 'orders', 'shippedDate', 'Orden de Compra', 'Fecha de Envio'),
    ('classicmodels', 'orders', 'status', 'Orden de Compra', 'Estado de Orden'),
    ('classicmodels', 'orders', 'customerNumber', 'Cliente', 'Numero de Cliente'),
    ('classicmodels', 'orderdetails', 'orderNumber', 'Orden de Compra', 'Numero de Orden'),
    ('classicmodels', 'orderdetails', 'productCode', 'Producto', 'Codigo de Producto'),
    ('classicmodels', 'orderdetails', 'quantityOrdered', 'Orden de Compra', 'Cantidad Ordenada'),
    ('classicmodels', 'orderdetails', 'priceEach', 'Orden de Compra', 'Precio Unitario'),

    -- Pago <- classicmodels.payments
    ('classicmodels', 'payments', 'customerNumber', 'Cliente', 'Numero de Cliente'),
    ('classicmodels', 'payments', 'checkNumber', 'Pago', 'Numero de Cheque'),
    ('classicmodels', 'payments', 'paymentDate', 'Pago', 'Fecha de Pago'),
    ('classicmodels', 'payments', 'amount', 'Pago', 'Monto de Pago'),

    -- Llamada de Servicio <- customerservice.cs_customer_calls
    ('customerservice', 'cs_customer_calls', 'employeenumber', 'Empleado', 'Numero de Empleado'),
    ('customerservice', 'cs_customer_calls', 'customernumber', 'Cliente', 'Numero de Cliente'),
    ('customerservice', 'cs_customer_calls', 'productcode', 'Producto', 'Codigo de Producto'),
    ('customerservice', 'cs_customer_calls', 'text', 'Llamada de Servicio', 'Comentario de Llamada'),
    ('customerservice', 'cs_customer_calls', 'date', 'Llamada de Servicio', 'Fecha de Llamada'),

    -- Interes de Cliente por Producto <- customerservice.cs_customer_products
    ('customerservice', 'cs_customer_products', 'customernumber', 'Cliente', 'Numero de Cliente'),
    ('customerservice', 'cs_customer_products', 'productcode', 'Producto', 'Codigo de Producto')
) AS v(source_name, table_name, column_name, entity_name, attribute_name)
JOIN data_source ds        ON ds.source_name = v.source_name
JOIN db_table dt            ON dt.source_id = ds.source_id AND dt.table_name = v.table_name
JOIN db_column dc           ON dc.table_id = dt.table_id AND dc.column_name = v.column_name
JOIN business_entity be     ON be.entity_name = v.entity_name
JOIN business_attribute ba  ON ba.entity_id = be.entity_id AND ba.attribute_name = v.attribute_name
ON CONFLICT (column_id, attribute_id) DO NOTHING;

-- ------------------------------------------------------------
-- 4. Verificacion posterior: deteccion de tuplas del bloque VALUES de
--    la seccion 3 que no encontraron columna/atributo (columna
--    renombrada, distinta mayuscula/minuscula, tabla sin cargar aun).
--    Si aparece un WARNING, revisar manualmente esa tupla contra
--    db_column / business_attribute antes de dar por buena la carga.
-- ------------------------------------------------------------
DO $$
DECLARE
    esperados INTEGER := 78;  -- numero de tuplas en el bloque VALUES de la seccion 3
    reales    INTEGER;
BEGIN
    SELECT count(*) INTO reales FROM column_business_mapping;
    IF reales < esperados THEN
        RAISE WARNING 'column_business_mapping tiene % filas, se esperaban %. '
            'Alguna tupla del bloque VALUES de la seccion 3 no encontro columna o atributo '
            '(revisar mayusculas/minusculas del nombre de columna o de tabla).', reales, esperados;
    END IF;
END $$;

-- Cobertura de linaje de cs_customers en particular, porque la consulta 6
-- del enunciado depende de que sus columnas tengan mapeo completo.
SELECT
    dt.table_name,
    count(dc.column_id)     AS columnas_totales,
    count(cbm.mapping_id)   AS columnas_con_linaje
FROM db_table dt
JOIN db_column dc                      ON dc.table_id = dt.table_id
LEFT JOIN column_business_mapping cbm  ON cbm.column_id = dc.column_id
WHERE dt.table_name = 'cs_customers'
GROUP BY dt.table_name;
