# Almacén empresarial (EDW)

El almacén propiamente dicho: un modelo dimensional en constelación, con dos hechos que comparten dimensiones conformadas, en el schema `public` de la base `dw`. Lo carga la capa 7 del [pipeline](../../pipeline/README.md), que trabaja en su propia base (`staging`), y sobre él se construyen los [data marts](../data_marts/README.md) y el dashboard.

![Modelo dimensional](../../docs/img/dw_star_schema.png)

La pregunta de negocio que guía el diseño es **qué productos generan más llamadas de servicio por unidad vendida**. Las ventas están en `classicmodels` y las llamadas en `customerservice`. Como clientes y productos tienen la misma llave en ambas fuentes, los dos hechos se pueden cruzar a través de dimensiones conformadas.

## Hechos

**`fact_ventas`**. Grano: una línea de una orden de compra (2.996 filas). Se alimenta de `orderdetails`, `orders`, `products`, `customers` y `employees`.

| Medida | Cálculo | Aditividad |
|---|---|---|
| `cantidad_ordenada` | `quantityOrdered` | Aditiva |
| `precio_unitario` | `priceEach` | No aditiva |
| `monto_linea` | `quantityOrdered * priceEach` | Aditiva |
| `costo_linea` | `quantityOrdered * buyPrice` | Aditiva |
| `margen_linea` | `monto_linea - costo_linea` | Aditiva |
| `precio_msrp` | `MSRP` | No aditiva |
| `dias_hasta_envio` | `shippedDate - orderDate`; nulo si la orden no se despachó | Semi-aditiva |

Dimensiones degeneradas: `numero_orden`, `numero_linea`.

El vendedor de una venta (`empleado_key` y `oficina_key`) es el vendedor que el cliente tiene asignado en la fuente, porque `orders` no guarda quién hizo cada venta. Con dimensiones de tipo 1 y hechos que se reemplazan en cada carga, si un cliente cambiara de vendedor, todo su historial de ventas pasaría al nuevo. Con las fuentes estáticas actuales no ocurre; con datos vivos, la corrección es que la fuente registre el vendedor en la orden.

**`fact_llamadas_servicio`**. Grano: una llamada (108 filas). Se alimenta de `cs_customer_calls`.

| Medida | Cálculo | Aditividad |
|---|---|---|
| `cantidad_llamadas` | Constante 1 | Aditiva |
| `longitud_texto` | `length(text)` | Aditiva |

Dimensión degenerada: `texto_llamada`. Es texto libre de hasta 200 caracteres dentro del hecho; con 108 llamadas no pesa, pero con volumen convendría llevarlo a una tabla aparte y dejar en el hecho solo su llave.

## Dimensiones

| Dimensión | Filas | Conformada | Origen |
|---|---|---|---|
| `dim_tiempo` | 1.096 | Sí | Generada: todos los días de los años que cubren las ventas y las llamadas (hoy, 2003-01-01 a 2005-12-31); llave `AAAAMMDD` |
| `dim_cliente` | 122 | Sí | `customers`; `cs_customers` aporta la bandera `presente_en_servicio`. `direccion_completa` une `addressLine1` y `addressLine2` |
| `dim_producto` | 110 | Sí | `products` con `productlines` desnormalizada; `cs_products` aporta `presente_en_servicio` |
| `dim_empleado` | 53 + 2 | No | Unión de `employees` (23 vendedores) y `cs_employees` (30 agentes) con llave de negocio compuesta `(numero_empleado, sistema_origen)`, más los dos miembros especiales |
| `dim_oficina` | 7 + 2 | No | `offices`, más los dos miembros especiales |
| `dim_estado_orden` | 6 | No | Valores distintos de `orders.status`; `es_efectiva` es falso para Cancelled, Disputed y On Hold |
| `dim_lote_carga` | 1 por carga | No | Dimensión de auditoría: la escribe la capa 7 del pipeline (ver abajo) |

Cada dimensión tiene llave subrogada (`*_key`) y llave de negocio. Todas son de tipo 1, porque las fuentes son snapshots sin historial: cada carga inserta los miembros nuevos y sobrescribe los atributos de los existentes por llave de negocio, sin cambiar su llave subrogada. Así, recargar las dimensiones no invalida los hechos ya cargados.

### Miembros especiales

Ningún hecho tiene llaves foráneas nulas. Donde una venta no puede resolver su vendedor, apunta a una fila especial de `dim_empleado` y `dim_oficina`, creada por [`special_members.sql`](special_members.sql):

| Llave | Nombre | Cuándo se usa |
|---|---|---|
| `-1` | Desconocido (Desconocida en `dim_oficina`) | El cliente tiene vendedor en la fuente, pero ese vendedor no llegó al almacén: no existe o la capa de calidad lo rechazó |
| `-2` | Sin asignar | El cliente no tiene vendedor en la fuente |

Así, un `JOIN` con estas dimensiones no pierde ventas, los reportes muestran el motivo en vez de un hueco y el monto total del almacén sigue cuadrando con la fuente. Las llaves negativas no chocan con las generadas por `SERIAL`, y la carga por llave de negocio nunca las toca. Las pruebas que comparan conteos con las fuentes las excluyen (`*_key > 0`).

Solo estas dos dimensiones los tienen, porque el vendedor es la única referencia opcional que llega a un hecho. Las demás son obligatorias: si el cliente, el producto o la orden de una venta no llega al almacén, el pipeline rechaza la venta (regla `padre_rechazado`).

### Auditoría de cargas

`dim_lote_carga` tiene una fila por cada carga del pipeline que llegó al almacén: el `run_id` de la carga (`lote_carga_key`), si fue de dimensiones o de hechos, qué corrida de staging leyó, cuándo se cargó y cuántas filas escribió. La capa 7 la escribe **en la misma transacción** que los datos, así que si la carga se deshace, su registro también.

Cada fila de las dimensiones y los hechos lleva `lote_carga_key`, la carga que la escribió por última vez, así que cualquier fila del almacén se puede rastrear hasta su corrida en la base `staging`. Los hechos la referencian con llave foránea, como a cualquier dimensión; en las dimensiones es una columna de auditoría sin llave foránea, para que el modelo siga siendo una estrella y no un copo de nieve. Los miembros especiales, que no vienen de ninguna carga, la tienen en `NULL`.

El almacén se describe así a sí mismo. Por eso el proceso de hechos consulta `dim_lote_carga` antes de cargar: si el almacén se reconstruye vacío o se restaura desde un backup, el control ve lo que el almacén realmente tiene, no lo que dice el historial de corridas.

## Archivos

| Archivo | Contenido |
|---|---|
| [`star_schema.sql`](star_schema.sql) | Dimensiones, hechos, dimensión de auditoría e índices sobre las llaves foráneas |
| [`special_members.sql`](special_members.sql) | Miembros especiales `-1` Desconocido y `-2` Sin asignar de `dim_empleado` y `dim_oficina` |
| [`business_questions.sql`](business_questions.sql) | Consultas de negocio sobre el EDW, equivalentes a las del dashboard |
| [`backup/dw_backup.sql`](backup/dw_backup.sql) | Backup del EDW y de los data marts, con todos los datos |

## Backup

`backup/dw_backup.sql` lo genera `python tools/generate_backup.py dw`: contiene el DDL de `star_schema.sql` y de `../data_marts/data_marts.sql`, seguido de los datos de las nueve tablas (incluida `dim_lote_carga`). No incluye la base `staging` del pipeline, que se reconstruye al ejecutarlo. Se restaura sobre una base vacía con:

```bash
psql "<url-de-la-base>" -f datawarehouse/edw/backup/dw_backup.sql
```
