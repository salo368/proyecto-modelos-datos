# Reportes

El dashboard **"Entrega 2 - Almacen Ventas y Servicio"** vive en Metabase (http://localhost:3000, usuario `grupo@javeriana.edu.co`, clave `Javeriana2026!`).

[`build_dashboard.py`](build_dashboard.py) lo construye completo mediante la API REST de Metabase, así que el montaje es reproducible:

1. Crea el usuario administrador si la instancia es nueva; si no, inicia sesión.
2. Elimina la base de ejemplo que trae Metabase y archiva sus dashboards.
3. Registra la base `dw` como **único** origen de datos. Ni `classicmodels` ni `customerservice` se registran en Metabase.
4. Crea (o actualiza, si ya existen) seis preguntas en SQL nativo.
5. Crea el dashboard con las seis tarjetas, dos por fila.

```bash
python reports/build_dashboard.py
```

Si el almacén está en el stack local, el script le indica a Metabase que lo alcance como `postgres-dw:5432` dentro de la red de Docker; si `DW_URL` apunta a un servidor remoto, usa esa dirección y activa SSL.

## Reportes

| # | Reporte | Visualización | Lee |
|---|---|---|---|
| 1 | Ventas y margen por mes (solo órdenes efectivas) | Combinado | `fact_ventas`, `dim_tiempo`, `dim_estado_orden` |
| 2 | Intensidad de servicio por producto: llamadas por unidad vendida | Barras | `dm.vw_interaccion_cliente_producto` |
| 3 | Margen por línea de producto: monto vendido y margen | Barras horizontales | `fact_ventas`, `dim_producto` |
| 4 | Clientes: compras frente a llamadas | Dispersión | `dm.vw_interaccion_cliente_producto` |
| 5 | Ventas por oficina del representante | Barras | `fact_ventas`, `dim_oficina` |
| 6 | Carga del centro de servicio por agente | Tabla | `fact_llamadas_servicio`, `dim_empleado` |

El reporte 2 es el que cruza las dos fuentes. Con los datos originales, los productos con más llamadas por unidad vendida son *American Airlines: B767-300* (7 llamadas / 894 unidades), *1962 City of Detroit Streetcar* (6 / 966) y *1912 Ford Model T Delivery Wagon* (5 / 991).

Las mismas consultas, con algunas columnas adicionales, están en [`datawarehouse/edw/business_questions.sql`](../datawarehouse/edw/business_questions.sql) para ejecutarlas desde cualquier cliente SQL.
