-- ============================================================
-- Reglas de calidad de datos - Entrega 2
--
-- Formaliza los hallazgos del perfilamiento de la Entrega 1 como
-- reglas evaluables. Cada corrida del ETL registra su resultado en
-- dq_result, de modo que se demuestra con datos -y no solo narrando-
-- que los problemas de calidad quedaron resueltos.
--
-- Cada regla se clasifica en dos marcos distintos que enseno el curso:
--
--   criterio_dama   Los seis criterios de calidad de la Clase 1
--                   (The Art of Enterprise Information Architecture):
--                   Exactitud, Exhaustividad, Consistencia,
--                   Oportunidad, Relevancia, Confianza.
--
--   clase_dq        La division de Giordano de la Clase 2, dia. 17:
--                   TECNICA  datos faltantes o invalidos, detectables
--                            sin conocer la regla de negocio.
--                   NEGOCIO  definiciones inconsistentes o datos
--                            inexactos, que exigen conocer la semantica.
--
-- Sobre CONFIANZA: la Clase 1 la define como la combinacion de los
-- otros cinco criterios mas metadatos y gobierno, no como un criterio
-- medible por si solo. Por eso ninguna regla la usa directamente: es
-- el resultado agregado de que las demas pasen.
--
-- Idempotente: se puede correr varias veces.
--
-- Ejecutar con:
--   python datawarehouse/ddl/run_sql.py \
--       metadata_repository/etl/dq_rules_seed.sql METADATA_REPO_URL
-- ============================================================

INSERT INTO dq_rule (rule_name, rule_type, criterio_dama, clase_dq,
                     source_column_id, expression, severity, resolution)
SELECT v.rule_name, v.rule_type, v.criterio_dama, v.clase_dq,
       dc.column_id, v.expression, v.severity, v.resolution
FROM (VALUES

    -- Hallazgo 1: productlines.htmlDescription e image estan 100% vacias.
    ('productline_columnas_vacias',
     'COMPLETITUD', 'EXHAUSTIVIDAD', 'TECNICA', 'productlines', 'htmlDescription',
     'COUNT(htmlDescription) = 0 AND COUNT(image) = 0',
     'INFORMATIVA',
     'Las dos columnas se excluyen de dim_producto. Solo se trae textDescription.'),

    -- Hallazgo 2: los empleados de las dos fuentes no comparten llave.
    ('empleado_conformidad_fuentes',
     'CONFORMIDAD', 'CONSISTENCIA', 'NEGOCIO', 'employees', 'employeeNumber',
     'classicmodels.employees.employeeNumber INTERSECT cs_employees.employeenumber = vacio',
     'BLOQUEANTE',
     'dim_empleado usa llave de negocio compuesta (numero_empleado, sistema_origen) '
     'con llave subrogada encima, para que las dos poblaciones convivan sin colisionar.'),

    -- Hallazgo 3: addressLine2 vacia en el 81,97% de las filas.
    ('cliente_direccion_linea2_nula',
     'COMPLETITUD', 'EXHAUSTIVIDAD', 'TECNICA', 'customers', 'addressLine2',
     'pct_nulos(addressLine2) < 50',
     'ADVERTENCIA',
     'Se consolida con addressLine1 en el atributo direccion_completa de dim_cliente.'),

    -- Hallazgo 4: orders.comments vacia en el 75,46% de las filas.
    ('orden_comentarios_nulos',
     'COMPLETITUD', 'RELEVANCIA', 'NEGOCIO', 'orders', 'comments',
     'pct_nulos(comments) < 50',
     'INFORMATIVA',
     'Texto libre sin valor analitico: no se lleva a fact_ventas.'),

    -- Hallazgo 5: shippedDate nula en las ordenes no despachadas.
    ('orden_fecha_envio_nula',
     'COMPLETITUD', 'EXHAUSTIVIDAD', 'TECNICA', 'orders', 'shippedDate',
     'shippedDate IS NOT NULL OR status <> ''Shipped''',
     'ADVERTENCIA',
     'dias_hasta_envio queda NULL en fact_ventas; dim_estado_orden explica el motivo.'),

    -- Hallazgo 6: los clientes si conforman entre las dos fuentes.
    ('cliente_conformidad_fuentes',
     'CONFORMIDAD', 'CONSISTENCIA', 'NEGOCIO', 'customers', 'customerNumber',
     'customers.customerNumber = cs_customers.customernumber (solape 100%)',
     'BLOQUEANTE',
     'Permite que dim_cliente sea conformada y que los dos hechos la compartan.'),

    -- Hallazgo 6b: los productos tambien conforman.
    ('producto_conformidad_fuentes',
     'CONFORMIDAD', 'CONSISTENCIA', 'NEGOCIO', 'products', 'productCode',
     'products.productCode = cs_products.productcode (solape 100%)',
     'BLOQUEANTE',
     'Permite que dim_producto sea conformada y que los dos hechos la compartan.'),

    -- Hallazgo 7: ordenes canceladas mezcladas con las despachadas.
    ('estado_orden_no_efectivo',
     'INTEGRIDAD', 'EXACTITUD', 'NEGOCIO', 'orders', 'status',
     'status IN (''Cancelled'', ''Disputed'', ''On Hold'') marca venta no efectiva',
     'ADVERTENCIA',
     'Se cargan todas las ordenes, pero dim_estado_orden.es_efectiva permite '
     'excluirlas de los reportes sin borrarlas del almacen.'),

    -- Regla de OPORTUNIDAD: cierra el sexto criterio de la Clase 1.
    -- La oportunidad pregunta "cuanto se demora la propagacion de los
    -- cambios". Se mide con la antiguedad de la ultima carga exitosa,
    -- que esta en etl_execution.
    ('almacen_frescura_de_carga',
     'FRESCURA', 'OPORTUNIDAD', 'TECNICA', NULL, NULL,
     'now() - MAX(etl_execution.finished_at WHERE status = ''OK'') < 24 horas',
     'ADVERTENCIA',
     'Si la ultima carga exitosa supera las 24 horas, los reportes estan '
     'mostrando datos vencidos y hay que relanzar el pipeline.')

) AS v(rule_name, rule_type, criterio_dama, clase_dq, tabla, columna,
       expression, severity, resolution)
LEFT JOIN db_table  dt ON dt.table_name  = v.tabla
LEFT JOIN db_column dc ON dc.table_id    = dt.table_id
                      AND dc.column_name = v.columna
ON CONFLICT (rule_name) DO UPDATE
    SET resolution    = EXCLUDED.resolution,
        severity      = EXCLUDED.severity,
        criterio_dama = EXCLUDED.criterio_dama,
        clase_dq      = EXCLUDED.clase_dq;
