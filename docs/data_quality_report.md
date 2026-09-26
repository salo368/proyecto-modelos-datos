# Calidad de datos por etapa

Qué le pasó a los datos en cada capa de la última carga completa: cuántos registros entraron, cuántos se descartaron, qué nulos se resolvieron y cuáles se conservaron, y sobre qué porcentaje de los datos se apoya cada análisis del almacén.

> Generado por `tools/generate_quality_report.py` a partir de lo que cada capa del pipeline dejó persistido en la base `staging`, de lo que quedó cargado en el almacén (`dw`) y del linaje del repositorio de metadatos. Ninguna cifra está escrita a mano: se regenera con cada `python run_all.py`.

## Resumen

| Estado del registro | Registros | % del total extraído |
|---|---:|---:|
| Limpio y sin ninguna anomalía | 4.313 | 99,5 % |
| Limpio, con advertencia trazada | 22 | 0,5 % |
| Rechazado | 0 | 0,0 % |
| **Total extraído** | **4.335** | **100 %** |

- **99,5 %** de los registros pasaron las reglas de calidad sin ninguna observación.
- **0,5 %** pasaron con una advertencia: se usan, pero la anomalía queda registrada en `staging_dw.vw_reporte_transacciones_malas` (base `staging`).
- **0,0 %** fueron rechazados: ningún registro incumplió una regla bloqueante.
- 374 registros (8,6 %) pertenecen a tablas que se extraen pero que el modelo actual no usa (`payments`, `cs_customer_products`). Se traen por el principio «traer todo pensando en necesidades futuras».

## Recorrido por capa

| Capa | Entra | Sale | Qué pasó |
|---|---:|---:|---|
| 1-2 · Extract + Initial Staging | 4.335 | 4.335 | 13 tablas leídas una vez; 85 columnas perfiladas, 14 con nulos |
| 3 · Data Quality | 4.335 | 4.335 | 22 hallazgos registrados en el reporte de transacciones malas |
| 4 · Clean Staging | 4.335 | 4.335 | 4.335 limpios, 0 rechazados |
| 5 · Transformation | 4.335 | 4.498 | 6 dimensiones y 2 hechos conformados |
| 6 · Load-Ready Publish | 4.498 | 4.498 | forma definitiva, sin transformaciones pendientes |
| 7 · Load | 4.498 | 4.498 | dimensiones por llave de negocio y hechos reemplazados, cada rama en una sola transacción. Aparte, el almacén tiene 4 miembros especiales (Desconocido y Sin asignar) |

Entre las capas 4 y 5 el número de filas cambia porque la transformación cambia el grano: varias tablas fuente se consolidan en una dimensión, `dim_tiempo` se genera sin fuente y las tablas no usadas por el modelo no continúan.

## Embudo por tabla fuente

| Fuente | Tabla | Extraídas | Con advertencia | Rechazadas | Limpias | Alimenta a |
|---|---|---:|---:|---:|---:|---|
| classicmodels | `customers` | 122 | 22 | — | 122 | `dim_cliente`, `fact_ventas` |
| classicmodels | `employees` | 23 | — | — | 23 | `dim_empleado`, `fact_ventas` |
| classicmodels | `offices` | 7 | — | — | 7 | `dim_oficina` |
| classicmodels | `orderdetails` | 2.996 | — | — | 2.996 | `fact_ventas` |
| classicmodels | `orders` | 326 | — | — | 326 | `dim_estado_orden`, `fact_ventas` |
| classicmodels | `payments` | 273 | — | — | 273 | *no la usa el modelo* |
| classicmodels | `productlines` | 7 | — | — | 7 | `dim_producto` |
| classicmodels | `products` | 110 | — | — | 110 | `dim_producto`, `fact_ventas` |
| customerservice | `cs_customer_calls` | 108 | — | — | 108 | `fact_llamadas_servicio` |
| customerservice | `cs_customer_products` | 101 | — | — | 101 | *no la usa el modelo* |
| customerservice | `cs_customers` | 122 | — | — | 122 | `dim_cliente` |
| customerservice | `cs_employees` | 30 | — | — | 30 | `dim_empleado` |
| customerservice | `cs_products` | 110 | — | — | 110 | `dim_producto` |

## Reglas de calidad (capa 3)

| Regla | Clase | Si falla | Revisados | Fallas | % fallas |
|---|---|---|---:|---:|---:|
| `formato_email` | Técnica | Advierte | 53 | 0 | 0,0 % |
| `campos_obligatorios` | Técnica | Rechaza | 4.335 | 0 | 0,0 % |
| `tipo_de_dato_valido` | Técnica | Rechaza | 3.935 | 0 | 0,0 % |
| `cliente_con_vendedor` | Negocio | Advierte | 122 | 22 | 18,0 % |
| `consistencia_entre_fuentes_cliente` | Negocio | Advierte | 122 | 0 | 0,0 % |
| `consistencia_entre_fuentes_producto` | Negocio | Advierte | 110 | 0 | 0,0 % |
| `precio_sugerido_coherente` | Negocio | Advierte | 110 | 0 | 0,0 % |
| `referencia_opcional_no_resuelta` | Negocio | Advierte | 145 | 0 | 0,0 % |
| `envio_consistente_con_estado` | Negocio | Rechaza | 326 | 0 | 0,0 % |
| `fecha_no_futura` | Negocio | Rechaza | 707 | 0 | 0,0 % |
| `integridad_referencial` | Negocio | Rechaza | 3.937 | 0 | 0,0 % |
| `padre_rechazado` | Negocio | Rechaza | 3.937 | 0 | 0,0 % |
| `secuencia_de_fechas` | Negocio | Rechaza | 326 | 0 | 0,0 % |
| `valores_positivos` | Negocio | Rechaza | 3.501 | 0 | 0,0 % |

## Nulos: de la fuente al almacén

Para cada columna fuente con nulos, qué pasó con ellos. Las cifras del destino están en filas del destino, que pueden tener otro grano (por ejemplo, una orden tiene varias líneas).

| Columna fuente | Nulos | % | Destino | Nulos en destino | Tratamiento | Qué significa |
|---|---:|---:|---|---:|---|---|
| `cs_customers.addressline2` | 100 | 82,0 % | — | — | No pasa al modelo | segunda línea de dirección opcional |
| `cs_customers.postalcode` | 7 | 5,7 % | — | — | No pasa al modelo | algunos países no usan código postal |
| `cs_customers.state` | 73 | 59,8 % | — | — | No pasa al modelo | muchos países no usan estado o región |
| `customers.addressLine2` | 100 | 82,0 % | `dim_cliente.direccion_completa` | 0 | Resuelto en la transformación: el destino no tiene nulos | segunda línea de dirección opcional |
| `customers.postalCode` | 7 | 5,7 % | `dim_cliente.codigo_postal` | 7 | Se conserva como NULL | algunos países no usan código postal |
| `customers.salesRepEmployeeNumber` | 22 | 18,0 % | `fact_ventas.empleado_key` | 0 | Sin efecto en el destino: ninguna fila del destino proviene de los registros con nulo | cliente sin representante de ventas asignado |
| `customers.state` | 73 | 59,8 % | `dim_cliente.estado_region` | 73 | Se conserva como NULL | muchos países no usan estado o región |
| `employees.reportsTo` | 1 | 4,3 % | — | — | No pasa al modelo | el presidente no reporta a nadie |
| `offices.addressLine2` | 2 | 28,6 % | — | — | No pasa al modelo | segunda línea de dirección opcional |
| `offices.state` | 3 | 42,9 % | `dim_oficina.region` | 3 | Se conserva como NULL | oficinas fuera de países con estados |
| `orders.comments` | 246 | 75,5 % | — | — | No pasa al modelo | comentario libre opcional |
| `orders.shippedDate` | 14 | 4,3 % | `fact_ventas.dias_hasta_envio` | 141 | Se conserva como NULL | órdenes aún no despachadas; el nulo es un dato válido |
| `productlines.htmlDescription` | 7 | 100,0 % | — | — | No pasa al modelo | columna nunca poblada en la fuente |
| `productlines.image` | 7 | 100,0 % | — | — | No pasa al modelo | columna nunca poblada en la fuente |

## Sobre qué datos se apoyan los análisis

`fact_ventas` tiene 2.996 líneas por 9.604.190,61 en total. Estas son las decisiones que recortan la base de cada tipo de análisis:

| Situación | Líneas | % líneas | Monto | % monto |
|---|---:|---:|---:|---:|
| Órdenes no efectivas (canceladas, en disputa o en espera) | 137 | 4,6 % | 469.588,57 | 4,9 % |
| Órdenes aún no despachadas (sin días hasta el envío) | 141 | 4,7 % | 475.294,17 | 4,9 % |
| Ventas sin vendedor resuelto («Sin asignar» o «Desconocido») | 0 | 0,0 % | 0,00 | 0,0 % |

Las situaciones se solapan y no deben sumarse: 100 de las líneas no despachadas pertenecen también a órdenes no efectivas (una orden cancelada tampoco sale de la bodega).

En la práctica:

- Los análisis de ventas y margen que usan solo **ventas efectivas** se apoyan en el **95,1 %** del monto. El resto existe en el almacén y se puede incluir filtrando por `dim_estado_orden.es_efectiva`.
- El **promedio de días hasta el envío** se calcula sobre el **95,3 %** de las líneas; las demás son órdenes que todavía no salieron y no tienen fecha de envío.
- Los análisis **por vendedor u oficina** cubren el **100 %** del monto: los clientes sin vendedor asignado no tienen compras.
- 24 de 122 clientes (19,7 %) no tienen ninguna compra. Cuentan en `dim_cliente` pero no pesan en ninguna medida de ventas.
- 1 de 110 productos (0,9 %) no se vendió nunca.
- Las 108 llamadas de servicio quedaron todas asociadas a un cliente, un producto y un agente: ninguna quedó huérfana.

## Lo que el pipeline no verifica

Para no sobrestimar lo que dicen los datos:

- **El contenido de las notas de llamada** (`texto_llamada`) se carga como texto libre. Se mide su longitud, pero no se valida qué dice.
- **La consistencia entre fuentes** se compara solo en teléfono, ciudad, país y código postal para clientes, y en nombre, escala y proveedor para productos. Las direcciones y el resto de atributos no se contrastan; `classicmodels` se toma como fuente autoritativa.
- **La frescura del dato en origen.** Las fuentes son copias estáticas: la regla de oportunidad mide cuándo se cargó el almacén, no qué tan reciente es la información de las fuentes.
- **Las tablas que el modelo no usa** (`payments`, `cs_customer_products`) pasan por las reglas de calidad pero no por las decisiones de modelado.

