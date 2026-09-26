# Documento de Entrega 1 — Proyecto Final

**Pontificia Universidad Javeriana — Modelado y persistencia de datos — 2026**

Elaborado por: Luis Daniel Sierra Pineda, David Cortes, Salomón Saenz

---

## Resumen ejecutivo

Este documento describe la Entrega 1 del proyecto final del curso, cuyo objetivo es integrar dos fuentes de datos de una organización —una base transaccional de ventas (`classicmodels`, MySQL) y una base del centro de atención al cliente (`customerservice`, PostgreSQL)— e implementar la capa de persistencia de un repositorio de metadatos que permita responder preguntas de descubrimiento, calidad y linaje semántico sobre ambas fuentes.

El documento está organizado en las cuatro secciones exigidas por el enunciado y cita, en cada una, los archivos del repositorio que la respaldan:

| Sección | Peso | Ubicación de los artefactos |
|---|---|---|
| 1. Descubrimiento de metadatos | 25% | `data_profiling/`, `output/metadata_tecnico.csv`, `output/columnas_por_tabla.md` |
| 2. Perfilamiento de datos | 25% | `data_profiling/reports*/`, `output/perfilamiento.csv`, `output/correspondencia_entidades.csv` |
| 3. Diseño físico del repositorio | 26% | `scripts/metadata_repository_ddl.sql`, `scripts/etl_metadata_repository.py`, `metadata_repo_backup.sql` |
| 4. Consultas | 24% | `scripts/consultas_repositorio.sql` |

---

## 1. Descubrimiento de metadatos (25%)

### 1.1 Fuentes involucradas

Se documentaron las dos fuentes indicadas en el enunciado, cargadas en servicios independientes de Railway para asegurar acceso remoto uniforme al grupo:

| Fuente | Motor | Schema | # Tablas | # Filas totales (aprox.) |
|---|---|---|---|---|
| `classicmodels` | MySQL 8 | `classicmodels` | 8 | ~3.500 |
| `customerservice` | PostgreSQL 18 | `public` | 5 | ~490 |

Los diagramas entidad-relación de cada fuente se generaron automáticamente con `eralchemy2` a partir del esquema real y se encuentran en `data_profiling/database_mysql.png` y `data_profiling/database_POSTGRES.png`.

### 1.2 Metadatos técnicos

Para cada tabla y columna de las dos fuentes se registraron los siguientes atributos técnicos, obtenidos mediante `SQLAlchemy.inspect()` y consolidados en `output/metadata_tecnico.csv` y `output/columnas_por_tabla.md`:

| Metadato técnico | Descripción |
|---|---|
| `tabla` | Nombre físico de la tabla en el motor |
| `columna` | Nombre físico de la columna |
| `tipo_dato` | Tipo nativo tal como lo reporta el motor (`int(11)`, `varchar(50)`, `character varying(50)`…) |
| `permite_nulo` | Si la columna admite `NULL` |
| `es_pk` | Si la columna es parte de la llave primaria |
| `es_fk` | Si la columna es llave foránea declarada |
| `referencia` | Tabla y columna referenciada por la FK, si aplica |

### 1.3 Metadatos de negocio

Además del metadato técnico, se identificaron ocho entidades de negocio que consolidan lo que las dos fuentes representan desde el punto de vista organizacional. Cada entidad se describe con nombre, definición y dominio de datos (ver también sección 4, consulta 3):

| Entidad | Dominio | Descripción |
|---|---|---|
| Cliente | Datos de Cliente | Persona o empresa que compra productos o realiza contacto con servicio al cliente |
| Empleado | Datos de Recurso Humano | Representantes de ventas y agentes de servicio |
| Producto | Datos de Producto | Artículos del catálogo que la compañía vende |
| Linea de Producto | Datos de Producto | Categoría o familia a la que pertenece un producto |
| Oficina | Datos Organizacionales | Sede física de la compañía |
| Orden de Compra | Datos Transaccionales de Ventas | Pedido realizado por un cliente, con encabezado y detalle |
| Pago | Datos Financieros | Registro de un pago asociado a órdenes |
| Llamada de Servicio | Datos de Servicio al Cliente | Registro de una llamada al call center |

### 1.4 Metadatos de linaje

El linaje semántico se materializa mediante la tabla puente `column_business_mapping`, que conecta cada columna técnica con el atributo de negocio que representa. Este linaje es el que permite responder la consulta 6 del enunciado. En total se cargaron **78 vínculos de linaje** entre columnas técnicas y atributos de negocio.

### 1.5 Estructuras en común y estructuras únicas

Del cruce entre las dos fuentes se identificaron **tres entidades comunes** (Cliente, Empleado, Producto), reportadas en `output/comparacion_entidades_comunes.csv`:

| Entidad | Tabla MySQL | Filas MySQL | Tabla PostgreSQL | Filas PostgreSQL |
|---|---|---|---|---|
| customers | `customers` | 122 | `cs_customers` | 122 |
| employees | `employees` | 23 | `cs_employees` | 30 |
| products | `products` | 110 | `cs_products` | 110 |

Las entidades exclusivas de cada fuente son:

- **Solo en `classicmodels`**: `offices`, `orders`, `orderdetails`, `payments`, `productlines`.
- **Solo en `customerservice`**: `cs_customer_calls`, `cs_customer_products`.

### 1.6 Relaciones inferidas entre fuentes

Como las dos bases viven en motores distintos no es posible declarar llaves foráneas físicas entre ellas. Para documentar las relaciones cruzadas se corrió `data_profiling/discover_relationships.py`, que infiere vínculos comparando dominios y coincidencia de valores; los resultados quedaron en `output/relaciones_inferidas.csv` y en `output/relaciones_fk.csv` (para las FKs físicas dentro de cada fuente).

---

## 2. Perfilamiento de datos (25%)

### 2.1 Alcance

Se perfilaron las **85 columnas** de las 13 tablas de las dos fuentes. Los reportes HTML detallados por tabla, generados con `ydata-profiling`, se encuentran en:

- `data_profiling/reports/` — 5 tablas de `customerservice`.
- `data_profiling/reports_mysql/` — 8 tablas de `classicmodels`.
- `data_profiling/reports_comparacion/` — comparación entre las 3 entidades comunes (customers, employees, products).

El resumen tabular consolidado está en `output/perfilamiento.csv`.

### 2.2 Dimensiones analizadas

Para cada columna se documentaron las cuatro dimensiones exigidas por el enunciado:

| Dimensión | Cómo se documenta |
|---|---|
| Rango de valores (numéricos y fechas) | Columnas `min` y `max` de `perfilamiento.csv` |
| Patrón de texto (strings) | Columna `patron_texto` (`libre/mixto`, `alfabetico`, `alfanumerico`, `solo_digitos`, `telefono_like`, `email`) |
| Porcentaje de nulos | Columnas `nulos` y `pct_nulos` |
| Correspondencia y duplicados entre estructuras comunes | `output/correspondencia_entidades.csv` |

### 2.3 Hallazgos de calidad

**Nulidad.** De 85 columnas, **14 tienen al menos un nulo**. Las peores por proporción de nulos son:

| Fuente | Tabla | Columna | % Nulos |
|---|---|---|---|
| classicmodels | `productlines` | `htmlDescription` | 100.00% |
| classicmodels | `productlines` | `image` | 100.00% |
| classicmodels | `customers` | `addressLine2` | 81.97% |
| customerservice | `cs_customers` | `addressline2` | 81.97% |
| classicmodels | `orders` | `comments` | 75.46% |

Las columnas 100% nulas de `productlines` sugieren campos declarados pero nunca poblados por el sistema origen: son candidatas a decomisar o a declararlas explícitamente como opcionales en el metadato de negocio.

**Patrones de texto.** La distribución de patrones detectados en las columnas de tipo string es la siguiente:

| Patrón | # Columnas |
|---|---|
| `libre/mixto` | 25 |
| `alfabetico` | 17 |
| `telefono_like` | 8 |
| `alfanumerico` | 8 |
| `solo_digitos` | 7 |
| `email` | 2 |

### 2.4 Correspondencia entre entidades comunes

El análisis de correspondencia por llave natural (`output/correspondencia_entidades.csv`) muestra el grado de compatibilidad entre las dos fuentes para cada entidad común:

| Entidad | Solo en classicmodels | Solo en customerservice | En ambas | Solapamiento (Jaccard) | Duplicados |
|---|---|---|---|---|---|
| customers | 0 | 0 | 122 | **100%** | 0 en ambas |
| employees | 23 | 30 | 0 | **0%** | 0 en ambas |
| products | 0 | 0 | 110 | **100%** | 0 en ambas |

**Interpretación:**

- `customers` y `products` tienen la **misma llave natural** en las dos fuentes y coincidencia de valores del 100% en las columnas comparadas (`phone`, `city`, `state`, `country`, `postalCode` para clientes; `productName`, `productScale`, `productVendor` para productos). Estas dos entidades pueden integrarse directamente.
- `employees` **no comparte llave natural**: los `employeeNumber` de MySQL y los `employee_id` de PostgreSQL no se cruzan. Además, las columnas de nombre y apellido tampoco coinciden (0% de coincidencia por lastName / firstName). Integrar esta entidad requeriría una tabla de equivalencias mantenida manualmente o un match aproximado por nombre + oficina.

**No se detectaron duplicados** dentro de cada fuente para ninguna de las tres entidades comunes.

---

## 3. Diseño físico del repositorio de metadatos (26%)

### 3.1 Arquitectura

El repositorio se implementó como una base de datos relacional en **PostgreSQL 18**, alojada como un tercer servicio independiente en Railway. Su arquitectura, siguiendo el marco DAMA-DMBOK, es **híbrida**:

- **A nivel conceptual, distribuida**: `classicmodels` y `customerservice` siguen siendo el sistema de registro autoritativo de su propio metadato técnico. El repositorio es un consumidor derivado, no un reemplazo.
- **A nivel físico, centralizada**: todo el metadato consolidado —técnico, de negocio y de linaje— reside en una única base consultable con SQL plano. Esta centralización es la que hace posibles las seis consultas del enunciado.

### 3.2 Modelo físico

El modelo consta de **seis tablas** organizadas en tres bloques lógicos. El DDL completo está en `scripts/metadata_repository_ddl.sql` y el diagrama físico en `data_profiling/metadata_repository_erd.png`.

**Bloque de metadato técnico (poblado automáticamente por el ETL):**

| Tabla | Propósito | # Filas actuales |
|---|---|---|
| `data_source` | Catálogo de las dos fuentes (nombre, motor, descripción) | 2 |
| `db_table` | Todas las tablas de cada fuente | 13 |
| `db_column` | Todas las columnas, con tipo normalizado y nativo, PK, FK autorreferenciada | 85 |

**Bloque de metadato de negocio (poblado manualmente por SQL):**

| Tabla | Propósito | # Filas actuales |
|---|---|---|
| `business_entity` | Entidades de negocio con dominio y descripción | 8 |
| `business_attribute` | Atributos de cada entidad de negocio | 47 |

**Bloque de linaje semántico (poblado manualmente por SQL):**

| Tabla | Propósito | # Filas actuales |
|---|---|---|
| `column_business_mapping` | Puente `db_column` ↔ `business_attribute` | 78 |

Se definieron cinco índices de apoyo (`idx_db_table_source`, `idx_db_column_table`, `idx_business_attribute_entity`, `idx_mapping_column`, `idx_mapping_attribute`) para acelerar los joins de las consultas del enunciado.

### 3.3 Proceso ETL de metadatos técnicos

La integración de los metadatos técnicos se automatizó con un ETL en Python (`scripts/etl_metadata_repository.py`, construido con SQLAlchemy y pandas) siguiendo el patrón de arquitectura de integración de datos de Anthony Giordano (*Data Integration Blueprint and Modeling*). El proceso se organiza en **cinco etapas físicamente persistidas** en el schema `staging` del propio repositorio:

| Etapa (Giordano) | Propósito | Función | Tabla de staging |
|---|---|---|---|
| Extract (Landing) | Copia 1:1 del diccionario de datos de las dos fuentes con `SQLAlchemy.inspect()` | `extract()` | `staging.stg_extract` |
| Data Quality | Valida completitud, contradicciones (PK marcada como nullable) y duplicados; marca cada fila como `OK` o `RECHAZADO` | `data_quality()` | `staging.stg_dq` |
| Transform | Normaliza los tipos de dato entre motores manteniendo el tipo nativo original; enriquece con descripción de negocio | `transform()` | `staging.stg_transform` |
| Load Ready Publish | Deja los datos en la forma exacta que se cargará al repositorio final | `load_ready_publish()` | `staging.stg_loadready` |
| Target Load | `INSERT ... ON CONFLICT DO UPDATE` idempotente hacia las tablas destino; resuelve FKs autorreferenciadas en segunda pasada | `load()` | `data_source`, `db_table`, `db_column` |

Cada ejecución del ETL queda identificada con un `run_id`, lo que permite auditar el historial sin sobrescribir corridas anteriores. La herramienta seleccionada es **Python 3.11 + SQLAlchemy 2.x + pandas + python-dotenv**, con las cadenas de conexión inyectadas por variables de entorno (`URL_MYSQLDATABASE`, `DATABASE_URL`, `METADATA_REPO_URL`).

### 3.4 Carga de metadato de negocio

El metadato de negocio y el linaje semántico se cargan de forma manual mediante `scripts/business_metadata_seed.sql`, tal como lo pide el enunciado. El script:

1. Verifica previamente que el ETL técnico ya haya poblado `db_column` (falla con un mensaje claro si no es así).
2. Es idempotente: se puede correr varias veces sin duplicar filas gracias a `ON CONFLICT DO NOTHING` sobre las `UNIQUE` constraints del DDL.
3. Al final reporta cualquier mapeo de linaje esperado que no se haya podido insertar (por ejemplo, una columna que fue renombrada en la fuente).

### 3.5 Backup del repositorio

El archivo `metadata_repo_backup.sql` (en la raíz del proyecto) contiene el DDL de las seis tablas más los `INSERT` con todos los datos actuales del repositorio. Se generó a partir del servicio de Railway ya poblado y puede restaurarse sobre cualquier PostgreSQL vacío con:

```bash
psql "postgresql://usuario:pass@host:puerto/db" -f metadata_repo_backup.sql
```

---

## 4. Consultas (24%)

Las seis consultas exigidas por el enunciado se implementaron en `scripts/consultas_repositorio.sql` y se corrieron contra el servicio de Railway para capturar los resultados que se muestran a continuación.

### 4.1 Consulta 1 — Tablas por fuente

> ¿Cuáles tablas se tienen en las fuentes de datos y en qué base de datos está cada tabla?

```sql
SELECT ds.source_name AS base_de_datos, ds.db_engine, dt.schema_name, dt.table_name
FROM db_table dt
JOIN data_source ds ON dt.source_id = ds.source_id
ORDER BY ds.source_name, dt.table_name;
```

**Resultado (13 filas):**

| base_de_datos | db_engine | schema_name | table_name |
|---|---|---|---|
| classicmodels | MySQL | classicmodels | customers |
| classicmodels | MySQL | classicmodels | employees |
| classicmodels | MySQL | classicmodels | offices |
| classicmodels | MySQL | classicmodels | orderdetails |
| classicmodels | MySQL | classicmodels | orders |
| classicmodels | MySQL | classicmodels | payments |
| classicmodels | MySQL | classicmodels | productlines |
| classicmodels | MySQL | classicmodels | products |
| customerservice | PostgreSQL | public | cs_customer_calls |
| customerservice | PostgreSQL | public | cs_customer_products |
| customerservice | PostgreSQL | public | cs_customers |
| customerservice | PostgreSQL | public | cs_employees |
| customerservice | PostgreSQL | public | cs_products |

### 4.2 Consulta 2 — Columnas de una tabla específica

> Para una tabla específica, ¿qué columnas tiene? (nombre, tipo de dato, si es parte de la llave primaria)

Ejemplo con la tabla `orders`:

```sql
SELECT dc.column_name, dc.data_type, dc.is_primary_key
FROM db_column dc
JOIN db_table dt ON dc.table_id = dt.table_id
WHERE dt.table_name = 'orders'
ORDER BY dc.ordinal_position;
```

**Resultado (7 filas):**

| column_name | data_type | is_primary_key |
|---|---|---|
| orderNumber | INTEGER | True |
| orderDate | DATE | False |
| requiredDate | DATE | False |
| shippedDate | DATE | False |
| status | VARCHAR(15) | False |
| comments | TEXT | False |
| customerNumber | INTEGER | False |

### 4.3 Consulta 3 — Glosario de negocio

> ¿Qué entidades de negocio existen en la organización, cuál es la descripción de cada una y su dominio de datos?

```sql
SELECT entity_name, entity_description, data_domain
FROM business_entity
ORDER BY entity_name;
```

**Resultado (8 filas):**

| entity_name | entity_description | data_domain |
|---|---|---|
| Cliente | Persona o empresa que compra productos de la compañía o realiza contacto con el centro de servicio. | Datos de Cliente |
| Empleado | Persona que trabaja en la compañía, como representante de ventas o agente de servicio al cliente. | Datos de Recurso Humano |
| Linea de Producto | Categoría o familia a la que pertenece un producto. | Datos de Producto |
| Llamada de Servicio | Registro de una llamada realizada por un cliente al centro de servicio al cliente. | Datos de Servicio al Cliente |
| Oficina | Sede física de la compañía donde trabajan los empleados. | Datos Organizacionales |
| Orden de Compra | Pedido realizado por un cliente, compuesto por un encabezado y sus líneas de detalle. | Datos Transaccionales de Ventas |
| Pago | Registro de un pago realizado por un cliente asociado a sus órdenes de compra. | Datos Financieros |
| Producto | Artículo del catálogo que la compañía vende o que es objeto de consulta en servicio al cliente. | Datos de Producto |

### 4.4 Consulta 4 — Atributos de una entidad

> Para una entidad específica, ¿qué atributos tiene? (nombre y definición)

Ejemplo con la entidad `Cliente`:

```sql
SELECT ba.attribute_name, ba.attribute_definition
FROM business_attribute ba
JOIN business_entity be ON ba.entity_id = be.entity_id
WHERE be.entity_name = 'Cliente'
ORDER BY ba.attribute_name;
```

**Resultado (12 filas):**

| attribute_name | attribute_definition |
|---|---|
| Apellido de Contacto | Apellido de la persona de contacto del cliente. |
| Ciudad de Cliente | Ciudad de residencia o domicilio del cliente. |
| Codigo Postal de Cliente | Código postal del domicilio del cliente. |
| Direccion Linea 1 | Primera línea de la dirección física del cliente. |
| Direccion Linea 2 | Segunda línea (complemento) de la dirección física del cliente. |
| Estado o Region de Cliente | Estado, departamento o región del domicilio del cliente. |
| Limite de Credito | Monto máximo de crédito autorizado para el cliente. |
| Nombre de Cliente | Nombre o razón social del cliente. |
| Nombre de Contacto | Nombre de la persona de contacto del cliente. |
| Numero de Cliente | Identificador único del cliente. |
| Pais de Cliente | País de domicilio del cliente. |
| Telefono de Cliente | Número telefónico de contacto del cliente. |

### 4.5 Consulta 5 — Reporte de ubicación de entidades

> Mostrar todas las entidades de negocio, junto con la(s) tabla(s) que almacenan la información relacionada con esa entidad (nombre de bd y nombre de tabla).

Se usa `LEFT JOIN` deliberadamente en toda la cadena para que una entidad que aún no tenga mapeo aparezca con `NULL`, en vez de desaparecer silenciosamente.

```sql
SELECT DISTINCT be.entity_name, ds.source_name AS base_de_datos, dt.table_name
FROM business_entity be
LEFT JOIN business_attribute ba       ON ba.entity_id = be.entity_id
LEFT JOIN column_business_mapping cbm ON cbm.attribute_id = ba.attribute_id
LEFT JOIN db_column dc                ON dc.column_id = cbm.column_id
LEFT JOIN db_table dt                 ON dc.table_id = dt.table_id
LEFT JOIN data_source ds              ON dt.source_id = ds.source_id
ORDER BY be.entity_name, ds.source_name, dt.table_name;
```

**Resultado (23 filas):**

| entity_name | base_de_datos | table_name |
|---|---|---|
| Cliente | classicmodels | customers |
| Cliente | classicmodels | orders |
| Cliente | classicmodels | payments |
| Cliente | customerservice | cs_customer_calls |
| Cliente | customerservice | cs_customer_products |
| Cliente | customerservice | cs_customers |
| Empleado | classicmodels | customers |
| Empleado | classicmodels | employees |
| Empleado | customerservice | cs_customer_calls |
| Empleado | customerservice | cs_employees |
| Linea de Producto | classicmodels | productlines |
| Linea de Producto | classicmodels | products |
| Llamada de Servicio | customerservice | cs_customer_calls |
| Oficina | classicmodels | employees |
| Oficina | classicmodels | offices |
| Orden de Compra | classicmodels | orderdetails |
| Orden de Compra | classicmodels | orders |
| Pago | classicmodels | payments |
| Producto | classicmodels | orderdetails |
| Producto | classicmodels | products |
| Producto | customerservice | cs_customer_calls |
| Producto | customerservice | cs_customer_products |
| Producto | customerservice | cs_products |

Este resultado evidencia el valor del linaje: la entidad `Cliente`, por ejemplo, no vive en una sola tabla sino que está distribuida en seis tablas físicas de las dos fuentes (tres en `classicmodels` y tres en `customerservice`), un hecho que no es visible por inspección directa de los esquemas sino a través del repositorio.

### 4.6 Consulta 6 — Linaje semántico de `cs_customers`

> Para la tabla `cs_customers`, mostrar por cada columna: nombre de columna, tipo de dato, nombre de atributo de negocio, definición de atributo y nombre de entidad.

Se usa `LEFT JOIN` para que las columnas sin mapeo (linaje incompleto) sigan apareciendo con `NULL` en las columnas de negocio.

```sql
SELECT dc.column_name, dc.data_type, ba.attribute_name, ba.attribute_definition, be.entity_name
FROM db_column dc
JOIN db_table dt                      ON dc.table_id = dt.table_id
LEFT JOIN column_business_mapping cbm ON cbm.column_id = dc.column_id
LEFT JOIN business_attribute ba       ON ba.attribute_id = cbm.attribute_id
LEFT JOIN business_entity be          ON be.entity_id = ba.entity_id
WHERE dt.table_name = 'cs_customers'
ORDER BY dc.ordinal_position;
```

**Resultado (10 filas):**

| column_name | data_type | attribute_name | attribute_definition | entity_name |
|---|---|---|---|---|
| customernumber | INTEGER | Numero de Cliente | Identificador único del cliente. | Cliente |
| contactlastname | VARCHAR(50) | Apellido de Contacto | Apellido de la persona de contacto del cliente. | Cliente |
| contactfirstname | VARCHAR(50) | Nombre de Contacto | Nombre de la persona de contacto del cliente. | Cliente |
| phone | VARCHAR(50) | Telefono de Cliente | Número telefónico de contacto del cliente. | Cliente |
| addressline1 | VARCHAR(50) | Direccion Linea 1 | Primera línea de la dirección física del cliente. | Cliente |
| addressline2 | VARCHAR(50) | Direccion Linea 2 | Segunda línea (complemento) de la dirección física del cliente. | Cliente |
| city | VARCHAR(50) | Ciudad de Cliente | Ciudad de residencia o domicilio del cliente. | Cliente |
| state | VARCHAR(50) | Estado o Region de Cliente | Estado, departamento o región del domicilio del cliente. | Cliente |
| postalcode | VARCHAR(15) | Codigo Postal de Cliente | Código postal del domicilio del cliente. | Cliente |
| country | VARCHAR(50) | País de Cliente | País de domicilio del cliente. | Cliente |

---

## 5. Entregables

| Entregable | Ubicación |
|---|---|
| Documento con las 4 secciones (este archivo) | `Documento_Entrega_1.md` |
| Backup del repositorio de metadatos (PostgreSQL, con datos) | `metadata_repo_backup.sql` |
| Backup de `classicmodels` (MySQL) | `mysqlsampledatabase.sql` |
| Backup de `customerservice` (PostgreSQL) | `customerservice.sql` |
| ETL de metadatos técnicos (Python 3.11 + SQLAlchemy + pandas) | `scripts/etl_metadata_repository.py` |
| DDL del repositorio | `scripts/metadata_repository_ddl.sql` |
| DDL del área de staging | `scripts/metadata_staging_ddl.sql` |
| Seed de metadato de negocio y linaje | `scripts/business_metadata_seed.sql` |
| Consultas del enunciado | `scripts/consultas_repositorio.sql` |
| Reportes HTML de perfilamiento | `data_profiling/reports*/` |
| Diagramas ER de las fuentes y del repositorio | `data_profiling/*.png` |

**Herramienta seleccionada para el ETL:** Python 3.11 con SQLAlchemy 2.x, pandas 2.x y python-dotenv, ejecutado desde línea de comandos. El repositorio de metadatos vive en un servicio PostgreSQL 18 de Railway, con las cadenas de conexión provistas por un archivo `.env` local (no versionado por seguridad). El README de la raíz del repositorio detalla el paso a paso de reproducción.
