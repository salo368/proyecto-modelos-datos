# Data marts

Vistas por tema en el schema `dm`, construidas sobre el [EDW](../edw/README.md). No guardan datos propios: cada vista sube el grano de los hechos y se recalcula al consultarla, así que siempre refleja la última carga.

| Vista | Grano | Contenido |
|---|---|---|
| `dm.vw_interaccion_cliente_producto` | Cliente × producto × mes | Unidades, monto, margen y líneas vendidas en órdenes efectivas junto a todas las llamadas recibidas (`FULL OUTER JOIN` de los dos hechos) y `llamadas_por_unidad` |
| `dm.vw_ventas_mensuales_linea` | Mes × línea de producto | Órdenes, unidades, monto, margen y % de margen de las órdenes efectivas |

Las dos cuentan solo órdenes efectivas (`dim_estado_orden.es_efectiva`): las unidades de una orden cancelada, en disputa o en espera no se vendieron, así que no entran en `llamadas_por_unidad` ni en el margen. El EDW conserva esas órdenes para quien las necesite.

[`data_marts.sql`](data_marts.sql) las crea y debe correr después de [`../edw/star_schema.sql`](../edw/star_schema.sql). Su definición también va en el backup del EDW.
