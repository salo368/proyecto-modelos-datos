-- ============================================================
-- Data quality rule catalogue (dq_rule)
--
-- Every warehouse ETL run stores the outcome of these rules in
-- dq_result. The capa column says where each rule is evaluated:
--
--   DATA_QUALITY    row by row in pipeline/layer3_data_quality.py.
--                   BLOQUEANTE rules send the row to stg_rejected;
--                   ADVERTENCIA rules let it through and log it in
--                   stg_error_log.
--   TRANSFORMATION  profiling findings handled by a modelling decision
--                   in layer5_transform_dimensions.py / layer5_transform_facts.py.
--   MONITOREO       about warehouse operation; catalogued here, not
--                   evaluated by the load.
--
-- criterio_dama classifies each rule by quality dimension and
-- clase_dq by technical vs business quality.
--
-- Idempotent: ON CONFLICT (rule_name) DO UPDATE.
-- ============================================================

INSERT INTO dq_rule (rule_name, rule_type, criterio_dama, clase_dq, capa,
                     source_column_id, expression, severity, resolution)
SELECT v.rule_name, v.rule_type, v.criterio_dama, v.clase_dq, v.capa,
       dc.column_id, v.expression, v.severity, v.resolution
FROM (VALUES

    -- ==========================================================
    -- DATA_QUALITY: technical checks
    -- ==========================================================
    ('campos_obligatorios',
     'COMPLETITUD', 'EXHAUSTIVIDAD', 'TECNICA', 'DATA_QUALITY', NULL, NULL,
     'Toda columna con is_nullable = FALSE en db_column tiene valor',
     'BLOQUEANTE',
     'El registro va a la pila de rechazados. Las columnas obligatorias se '
     'leen del repositorio de metadatos, no estan escritas en el ETL.'),

    ('tipo_de_dato_valido',
     'FORMATO', 'EXACTITUD', 'TECNICA', 'DATA_QUALITY', NULL, NULL,
     'Las columnas de fecha se interpretan como fecha y las numericas como numero',
     'BLOQUEANTE',
     'El registro va a la pila de rechazados: un valor que no se puede '
     'interpretar no se puede transformar.'),

    ('formato_email',
     'FORMATO', 'EXACTITUD', 'TECNICA', 'DATA_QUALITY', 'employees', 'email',
     'email contiene @ y un dominio con punto',
     'ADVERTENCIA',
     'El registro pasa; la anomalia queda en el reporte de transacciones malas.'),

    -- ==========================================================
    -- DATA_QUALITY: business checks
    -- ==========================================================
    ('integridad_referencial',
     'INTEGRIDAD', 'CONSISTENCIA', 'NEGOCIO', 'DATA_QUALITY', NULL, NULL,
     'Toda referencia obligatoria apunta a un registro existente, dentro de cada fuente '
     'y entre fuentes (llamadas contra el maestro de clientes y productos de classicmodels)',
     'BLOQUEANTE',
     'El registro va a la pila de rechazados: cargarlo produciria un hecho '
     'huerfano en el almacen.'),

    ('valores_positivos',
     'RANGO', 'EXACTITUD', 'NEGOCIO', 'DATA_QUALITY', 'orderdetails', 'quantityOrdered',
     'cantidades, precios, costos y pagos > 0; limite de credito >= 0',
     'BLOQUEANTE',
     'El registro va a la pila de rechazados.'),

    ('secuencia_de_fechas',
     'COHERENCIA', 'EXACTITUD', 'NEGOCIO', 'DATA_QUALITY', 'orders', 'shippedDate',
     'shippedDate >= orderDate y requiredDate >= orderDate',
     'BLOQUEANTE',
     'El registro va a la pila de rechazados.'),

    ('envio_consistente_con_estado',
     'COHERENCIA', 'EXACTITUD', 'NEGOCIO', 'DATA_QUALITY', 'orders', 'status',
     'status = ''Shipped'' implica shippedDate no nula',
     'BLOQUEANTE',
     'El registro va a la pila de rechazados.'),

    ('fecha_no_futura',
     'RANGO', 'EXACTITUD', 'NEGOCIO', 'DATA_QUALITY', 'orders', 'orderDate',
     'orderDate, paymentDate y la fecha de la llamada <= fecha de la carga',
     'BLOQUEANTE',
     'El registro va a la pila de rechazados: un evento no puede ocurrir '
     'despues de la carga. dim_tiempo se genera sobre el periodo que cubren '
     'las ventas y las llamadas, asi que una fecha errada lo extenderia.'),

    ('precio_sugerido_coherente',
     'COHERENCIA', 'EXACTITUD', 'NEGOCIO', 'DATA_QUALITY', 'products', 'MSRP',
     'MSRP >= buyPrice',
     'ADVERTENCIA',
     'El registro pasa; se traza para revision del area comercial.'),

    ('cliente_con_vendedor',
     'COMPLETITUD', 'EXHAUSTIVIDAD', 'NEGOCIO', 'DATA_QUALITY',
     'customers', 'salesRepEmployeeNumber',
     'salesRepEmployeeNumber no nulo',
     'ADVERTENCIA',
     'La fuente admite el nulo (tecnicamente valido), pero el negocio espera '
     'que todo cliente tenga vendedor. El registro pasa y sus ventas apuntan '
     'al miembro especial -2 Sin asignar de dim_empleado y dim_oficina.'),

    ('consistencia_entre_fuentes_cliente',
     'CONFORMIDAD', 'CONSISTENCIA', 'NEGOCIO', 'DATA_QUALITY',
     'customers', 'customerNumber',
     'cs_customers coincide con customers en telefono, ciudad, pais y codigo postal',
     'ADVERTENCIA',
     'Si difieren, classicmodels es la fuente autoritativa de dim_cliente; '
     'la diferencia queda trazada.'),

    ('consistencia_entre_fuentes_producto',
     'CONFORMIDAD', 'CONSISTENCIA', 'NEGOCIO', 'DATA_QUALITY',
     'products', 'productCode',
     'cs_products coincide con products en nombre, escala y proveedor',
     'ADVERTENCIA',
     'Si difieren, classicmodels es la fuente autoritativa de dim_producto; '
     'la diferencia queda trazada.'),

    ('referencia_opcional_no_resuelta',
     'INTEGRIDAD', 'CONSISTENCIA', 'NEGOCIO', 'DATA_QUALITY',
     'customers', 'salesRepEmployeeNumber',
     'Las referencias opcionales (vendedor del cliente, jefe del empleado) '
     'apuntan a un registro existente y no rechazado',
     'ADVERTENCIA',
     'El registro pasa: el rechazo no se propaga por una referencia opcional. '
     'Sus ventas apuntan al miembro especial -1 Desconocido de dim_empleado '
     'y dim_oficina; reportsTo no se modela.'),

    ('padre_rechazado',
     'INTEGRIDAD', 'CONSISTENCIA', 'NEGOCIO', 'DATA_QUALITY', NULL, NULL,
     'Toda referencia obligatoria apunta a un registro que no fue rechazado '
     '(se evalua despues de las demas reglas)',
     'BLOQUEANTE',
     'El registro sigue a su padre a la pila de rechazados, en cascada '
     '(cliente -> ordenes -> lineas): si pasara, apuntaria a un miembro '
     'que no llega al almacen y detendria la carga de hechos.'),

    -- ==========================================================
    -- TRANSFORMATION: findings from source profiling
    -- ==========================================================
    ('productline_columnas_vacias',
     'COMPLETITUD', 'EXHAUSTIVIDAD', 'TECNICA', 'TRANSFORMATION',
     'productlines', 'htmlDescription',
     'COUNT(htmlDescription) = 0 AND COUNT(image) = 0',
     'INFORMATIVA',
     'Las dos columnas se extraen (traer todo) pero no pasan a dim_producto.'),

    ('cliente_direccion_linea2_nula',
     'COMPLETITUD', 'EXHAUSTIVIDAD', 'TECNICA', 'TRANSFORMATION',
     'customers', 'addressLine2',
     'pct_nulos(addressLine2) < 50',
     'INFORMATIVA',
     'Se consolida con addressLine1 en el atributo direccion_completa.'),

    ('orden_comentarios_nulos',
     'COMPLETITUD', 'RELEVANCIA', 'NEGOCIO', 'TRANSFORMATION',
     'orders', 'comments',
     'pct_nulos(comments) < 50',
     'INFORMATIVA',
     'Texto libre sin valor analitico: no se lleva a fact_ventas.'),

    ('orden_fecha_envio_nula',
     'COMPLETITUD', 'EXHAUSTIVIDAD', 'TECNICA', 'TRANSFORMATION',
     'orders', 'shippedDate',
     'shippedDate no nula',
     'INFORMATIVA',
     'Las ordenes aun no despachadas quedan con dias_hasta_envio NULL; '
     'dim_estado_orden explica el motivo.'),

    ('cliente_conformidad_fuentes',
     'CONFORMIDAD', 'CONSISTENCIA', 'NEGOCIO', 'TRANSFORMATION',
     'customers', 'customerNumber',
     'Todo customerNumber de classicmodels existe en cs_customers',
     'BLOQUEANTE',
     'Permite que dim_cliente sea conformada y que los dos hechos la compartan.'),

    ('producto_conformidad_fuentes',
     'CONFORMIDAD', 'CONSISTENCIA', 'NEGOCIO', 'TRANSFORMATION',
     'products', 'productCode',
     'Todo productCode de classicmodels existe en cs_products',
     'BLOQUEANTE',
     'Permite que dim_producto sea conformada y que los dos hechos la compartan.'),

    ('empleado_conformidad_fuentes',
     'CONFORMIDAD', 'CONSISTENCIA', 'NEGOCIO', 'TRANSFORMATION',
     'employees', 'employeeNumber',
     'Numeros de empleado compartidos entre las dos fuentes',
     'INFORMATIVA',
     'Las dos poblaciones no se solapan: dim_empleado usa llave de negocio '
     'compuesta (numero_empleado, sistema_origen) en vez de fusionarlas.'),

    ('venta_vendedor_no_resuelto',
     'COMPLETITUD', 'EXHAUSTIVIDAD', 'NEGOCIO', 'TRANSFORMATION',
     'customers', 'salesRepEmployeeNumber',
     'Toda linea de venta resuelve el vendedor y la oficina del cliente',
     'INFORMATIVA',
     'La linea no queda con llave nula: apunta al miembro especial -2 Sin '
     'asignar si el cliente no tiene vendedor, o -1 Desconocido si su '
     'vendedor no llego al almacen.'),

    ('estado_orden_no_efectivo',
     'INTEGRIDAD', 'EXACTITUD', 'NEGOCIO', 'TRANSFORMATION',
     'orders', 'status',
     'status en (Cancelled, Disputed, On Hold) no es venta cerrada',
     'INFORMATIVA',
     'Se cargan todas las ordenes; dim_estado_orden.es_efectiva permite '
     'excluirlas de los reportes sin borrarlas del almacen.'),

    -- ==========================================================
    -- MONITOREO: warehouse freshness
    -- ==========================================================
    ('almacen_frescura_de_carga',
     'FRESCURA', 'OPORTUNIDAD', 'TECNICA', 'MONITOREO', NULL, NULL,
     'now() - ultima carga exitosa en etl_execution < 24 horas',
     'ADVERTENCIA',
     'Si la ultima carga exitosa supera las 24 horas, los reportes estan '
     'mostrando datos vencidos y hay que relanzar el pipeline.')

) AS v(rule_name, rule_type, criterio_dama, clase_dq, capa, tabla, columna,
       expression, severity, resolution)
LEFT JOIN db_table  dt ON dt.table_name  = v.tabla
LEFT JOIN db_column dc ON dc.table_id    = dt.table_id
                      AND dc.column_name = v.columna
ON CONFLICT (rule_name) DO UPDATE
    SET rule_type     = EXCLUDED.rule_type,
        criterio_dama = EXCLUDED.criterio_dama,
        clase_dq      = EXCLUDED.clase_dq,
        capa          = EXCLUDED.capa,
        expression    = EXCLUDED.expression,
        severity      = EXCLUDED.severity,
        resolution    = EXCLUDED.resolution;
