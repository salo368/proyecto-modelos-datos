# Descubrimiento y perfilamiento de las fuentes

Analiza la estructura y la calidad de `classicmodels` (MySQL, 8 tablas) y `customerservice` (PostgreSQL, 5 tablas), e identifica qué tienen en común. Los resultados alimentan el diseño del repositorio de metadatos y del almacén.

## Scripts

| Script | Lee | Produce |
|---|---|---|
| [`profile_from_dumps.py`](profile_from_dumps.py) | Los dumps de `sources/` (no necesita bases levantadas) | `output/metadata_tecnico.csv`, `output/perfilamiento.csv`, `output/comparacion_entidades_comunes.csv` |
| [`columns_report.py`](columns_report.py) | `output/metadata_tecnico.csv` | `output/columnas_por_tabla.md` |
| [`referential_profiling.py`](referential_profiling.py) | Las dos fuentes | `output/relaciones_fk.csv`, `output/correspondencia_entidades.csv` |
| [`discover_relationships.py`](discover_relationships.py) | Las dos fuentes | `output/relaciones_inferidas.csv` |
| [`ydata_table_profiles.py`](ydata_table_profiles.py) | Las dos fuentes | `reports/classicmodels/*.html`, `reports/customerservice/*.html` |
| [`ydata_compare_common_entities.py`](ydata_compare_common_entities.py) | Las dos fuentes | `reports/common_entities/*.html` |
| [`sql/discovery_classicmodels.sql`](sql/discovery_classicmodels.sql), [`sql/discovery_customerservice.sql`](sql/discovery_customerservice.sql) | `information_schema` de cada fuente | Tablas, columnas, llaves primarias y foráneas, para consulta manual |

Los cuatro primeros scripts forman parte de `run_all.py`. Los dos de `ydata_*` son opcionales porque tardan varios minutos y necesitan una dependencia extra:

```bash
pip install -r profiling/requirements.txt
python profiling/ydata_table_profiles.py
python profiling/ydata_compare_common_entities.py
```

## Qué contiene cada salida

| Archivo | Contenido |
|---|---|
| `metadata_tecnico.csv` | Una fila por columna de las 13 tablas: fuente, tabla, columna, tipo nativo, si admite nulos, si es llave primaria o foránea y a qué columna referencia |
| `columnas_por_tabla.md` | Lo mismo, como una tabla Markdown por tabla fuente |
| `perfilamiento.csv` | Una fila por columna: total de filas, nulos y % de nulos, valores distintos, mínimo y máximo (números y fechas) o longitud mínima y máxima más el patrón de texto detectado (`solo_digitos`, `email`, `telefono_like`, `alfabetico`, `alfanumerico`, `libre/mixto`) |
| `comparacion_entidades_comunes.csv` | Filas de las tres entidades presentes en ambas fuentes: clientes, empleados y productos |
| `relaciones_fk.csv` | Por cada llave foránea declarada: % de valores nulos, filas huérfanas y cardinalidad observada |
| `correspondencia_entidades.csv` | Por cada entidad común: llaves solo en una fuente o en ambas, solapamiento (Jaccard), duplicados y % de coincidencia campo a campo |
| `relaciones_inferidas.csv` | Relaciones por contención de valores (≥ 90 %), incluidas las que cruzan de una base a otra y las que no están declaradas como llave foránea |
| `reports/` | Reportes HTML de ydata-profiling por tabla y comparaciones lado a lado de las entidades comunes |

## Hallazgos que usa el resto del proyecto

| Hallazgo | Dónde se ve | Consecuencia |
|---|---|---|
| `customers` / `cs_customers` y `products` / `cs_products` comparten el 100 % de sus llaves y coinciden en teléfono, ciudad, país, código postal, nombre, escala y proveedor | `correspondencia_entidades.csv` | `dim_cliente` y `dim_producto` son dimensiones conformadas |
| `employees` (23) y `cs_employees` (30) no comparten ninguna llave ni ningún nombre | `correspondencia_entidades.csv` | `dim_empleado` usa la llave compuesta `(numero_empleado, sistema_origen)` |
| `productlines.htmlDescription` e `image` están 100 % vacías | `perfilamiento.csv` | No pasan a `dim_producto` |
| `customers.addressLine2` es mayoritariamente nula | `perfilamiento.csv` | Se consolida con `addressLine1` en `dim_cliente.direccion_completa` |
| `orders.comments` es texto libre mayoritariamente nulo | `perfilamiento.csv` | No pasa al almacén |
| 22 clientes no tienen representante de ventas (`salesRepEmployeeNumber` nulo) | `relaciones_fk.csv` | Regla de calidad de negocio `cliente_con_vendedor` (advertencia) |
| `cs_customer_calls` referencia clientes y productos que existen en `classicmodels` | `relaciones_inferidas.csv` | Las llamadas se pueden cargar contra las dimensiones conformadas |
