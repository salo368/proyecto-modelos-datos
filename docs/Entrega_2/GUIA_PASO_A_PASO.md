# Guía paso a paso — Entrega 2

Esta guía asume que **nunca has construido un almacén de datos**. Cada paso dice qué escribir, qué debería pasar, y qué hacer si sale mal.

> **Si solo querés verlo funcionar**, no necesitás esta guía: desde la raíz del proyecto corré `python run_all.py` y en unos minutos tenés todo montado y cargado. El README explica ese camino.
>
> Esta guía es para **entender qué hace cada pieza y por qué**. Recorre a mano lo mismo que `run_all.py` automatiza, explicando cada decisión. Si vas a defender el proyecto ante el profesor, leé esto.

Lee primero la sección "Qué vas a construir". Después seguí las partes en orden, sin saltarte ninguna.

---

## Qué vas a construir (leé esto antes de tocar nada)

Ahora mismo tenés dos bases de datos separadas:

- **classicmodels** (MySQL) — las ventas: clientes, productos, órdenes, pagos.
- **customerservice** (PostgreSQL) — el call center: quién llamó, por qué producto.

El problema: para responder *"¿los productos que más se venden son los que más quejas generan?"* tendrías que consultar las dos bases a la vez, y no se puede porque están en motores distintos.

La solución se llama **almacén de datos** (*data warehouse*): una tercera base, diseñada **no** para registrar operaciones sino para **analizarlas**. Copiás los datos de las dos fuentes hacia allá, ya limpios y organizados, y consultás una sola cosa.

### Las dos piezas del modelo

Un almacén se organiza en **hechos** y **dimensiones**:

- Un **hecho** es algo que pasó y que se puede medir. Una venta. Una llamada. Las filas de la tabla de hechos son muchísimas y tienen números que se suman.
- Una **dimensión** es el contexto de ese hecho: *quién*, *qué*, *cuándo*, *dónde*. Las filas son pocas y tienen texto que sirve para filtrar y agrupar.

Ejemplo concreto de este proyecto:

> El **hecho** es "se vendieron 30 unidades del producto S18_1749 a 12.50 dólares cada una".
> Las **dimensiones** dicen que eso fue el 6 de enero de 2003 (tiempo), al cliente Atelier graphique (cliente), de la línea Vintage Cars (producto), vendido por Gerard Hernandez (empleado), desde la oficina de París (oficina).

Cuando dibujás eso queda un **esquema estrella**: el hecho en el centro, las dimensiones alrededor.

### Por qué dos hechos y no uno

Vas a construir dos tablas de hechos:

- `fact_ventas` — una fila por cada línea de una orden. 2.996 filas.
- `fact_llamadas_servicio` — una fila por cada llamada. 108 filas.

No se pueden juntar en una sola tabla porque tienen **granos distintos** (una venta no es una llamada). Pero **comparten dimensiones**: el mismo cliente compra y llama, el mismo producto se vende y genera consultas. A esas dimensiones compartidas se les dice **conformadas**, y son exactamente el mecanismo que permite cruzar las dos fuentes.

### El proceso que mueve los datos

Se llama **ETL**, por *Extract, Transform, Load*:

1. **Extract** — leer de las fuentes.
2. **Transform** — limpiar, normalizar, calcular.
3. **Load** — escribir en el almacén.

Vas a escribirlo en Python, igual que en la Entrega 1.

### El orden importa

Las tablas de hechos apuntan a las dimensiones. Entonces:

> **Primero se cargan TODAS las dimensiones. Después los hechos.**

Si intentás al revés, la base te va a rechazar las filas porque apuntan a dimensiones que todavía no existen.

---

## Parte 0 — Preparar tu computador

### 0.1 Verificar que tenés Python

Abrí una terminal en la carpeta del proyecto y escribí:

```bash
python --version
```

**Deberías ver:** `Python 3.11.3` o similar (cualquier 3.9 o superior sirve).

**Si dice "no se reconoce":** instalá Python desde https://www.python.org/downloads/ y marcá la casilla *"Add Python to PATH"* durante la instalación.

### 0.2 Instalar las librerías

```bash
python -m pip install "sqlalchemy>=2.0.36" pymysql psycopg2-binary pandas python-dotenv requests
```

Qué hace cada una:

| Librería | Para qué |
|---|---|
| `sqlalchemy` | Hablar con cualquier base de datos desde Python |
| `pymysql` | El traductor específico para MySQL |
| `psycopg2-binary` | El traductor específico para PostgreSQL |
| `pandas` | Manipular tablas de datos en memoria |
| `python-dotenv` | Leer las contraseñas desde el archivo `.env` |
| `requests` | Hablar con la API de Metabase en la Parte 8 |

**Deberías ver:** `Successfully installed ...` al final.

> **El `>=2.0.36` importa, no lo quites.** pandas 3.x exige esa versión mínima de SQLAlchemy. Con una anterior, pandas **no falla**: deja de reconocer los engines de SQLAlchemy y cae en silencio a otro modo, y recién ahí revienta con `'Engine' object has no attribute 'cursor'`, que no dice nada sobre la causa real. Si te aparece ese error, el problema es la versión.

Para confirmar que quedaron bien emparejadas:

```bash
python -c "import pandas, sqlalchemy; print(pandas.__version__, sqlalchemy.__version__)"
```

### 0.3 Crear el archivo de credenciales

En la raíz del proyecto creá un archivo llamado exactamente `.env` (con el punto adelante). La forma corta es copiar el que ya viene:

```bash
cp .env.example .env     # macOS y Linux
copy .env.example .env   # Windows (cmd)
```

Queda así, y **funciona tal cual** contra el stack de Docker:

```
URL_MYSQLDATABASE=mysql+pymysql://root:javeriana@localhost:3307/classicmodels
DATABASE_URL=postgresql+psycopg2://postgres:javeriana@localhost:5433/customerservice
METADATA_REPO_URL=postgresql+psycopg2://postgres:javeriana@localhost:5434/metadata
DW_URL=postgresql+psycopg2://postgres:javeriana@localhost:5434/dw
METABASE_URL=http://localhost:3000
```

Qué apunta a dónde:

| Variable | Contenedor | Puerto en tu máquina |
|---|---|---|
| `URL_MYSQLDATABASE` | `mpd-mysql` | 3307 |
| `DATABASE_URL` | `mpd-postgres-cs` | 5433 |
| `METADATA_REPO_URL` | `mpd-postgres-dw`, base `metadata` | 5434 |
| `DW_URL` | `mpd-postgres-dw`, base `dw` | 5434 |

> **Las dos últimas líneas son el mismo servidor**, pero bases distintas: el repositorio de metadatos y el almacén conviven en una sola instancia de PostgreSQL. Es la misma topología que se usaría en la nube, y ahorra levantar un servicio aparte.

> **Los puertos no son los de siempre a propósito.** MySQL suele usar 3306 y PostgreSQL 5432; acá son 3307, 5433 y 5434 para no chocar si ya tenés alguno de esos motores instalado en tu máquina.

> **El `.env` nunca se sube a GitHub**, aunque estas credenciales sean locales. Ya está en el `.gitignore`. Si algún día apuntás este archivo a un servidor real, esa regla pasa a ser crítica.

### 0.4 Probar que conectás

Creá `scripts/test_conexion.py`:

```python
import os
from dotenv import load_dotenv
import sqlalchemy as sa

load_dotenv()

objetivos = {
    "classicmodels (MySQL)": os.getenv("URL_MYSQLDATABASE"),
    "customerservice (PostgreSQL)": os.getenv("DATABASE_URL"),
    "repositorio de metadatos": os.getenv("METADATA_REPO_URL"),
}

for nombre, url in objetivos.items():
    try:
        eng = sa.create_engine(url)
        with eng.connect() as con:
            con.execute(sa.text("SELECT 1"))
        print(f"OK   {nombre}")
    except Exception as e:
        print(f"FALLA {nombre}: {str(e)[:100]}")
```

Corré:

```bash
python scripts/test_conexion.py
```

**Deberías ver:**

```
OK   classicmodels (MySQL)
OK   customerservice (PostgreSQL)
OK   repositorio de metadatos
```

**Si alguna falla:** revisá que copiaste la línea completa del `.env` sin cortarla, y que no quedó un espacio al final.

---

## Parte 1 — Reorganizar el repositorio

Esto es puro mover archivos, pero hacelo **antes** de crear código nuevo para no tener que rehacerlo después.

### 1.1 Crear las carpetas

Desde la raíz del proyecto:

```bash
mkdir -p docs/enunciados docs/Entrega_1 docs/Entrega_2/img
mkdir -p sources
mkdir -p metadata_repository/ddl metadata_repository/etl metadata_repository/queries metadata_repository/backup
mkdir -p datawarehouse/ddl datawarehouse/etl datawarehouse/queries datawarehouse/backup
mkdir -p reports
```

### 1.2 Mover lo que ya existe

```bash
# Enunciados y documentos
mv "Proyecto - Entrega 1.pdf" docs/enunciados/
mv "Proyecto - Entrega 2.pdf" docs/enunciados/   # si ya lo copiaste al proyecto
mv Documento_Entrega_1.md docs/Entrega_1/
mv PLAN_Entrega_2.md docs/Entrega_2/PLAN.md
mv GUIA_PASO_A_PASO.md docs/Entrega_2/

# Backups de las fuentes
mv mysqlsampledatabase.sql sources/
mv customerservice.sql sources/

# Repositorio de metadatos
mv scripts/metadata_repository_ddl.sql metadata_repository/ddl/
mv scripts/metadata_staging_ddl.sql metadata_repository/ddl/
mv scripts/etl_metadata_repository.py metadata_repository/etl/
mv scripts/business_metadata_seed.sql metadata_repository/etl/
mv scripts/consultas_repositorio.sql metadata_repository/queries/
mv metadata_repo_backup.sql metadata_repository/backup/

# Perfilamiento de la Entrega 1
mv data_profiling profiling
mv output profiling/output
```

### 1.3 Arreglar los enlaces rotos

Los archivos `README.md` y `docs/Entrega_1/Documento_Entrega_1.md` tienen enlaces que ahora apuntan a rutas viejas. Buscá y reemplazá:

| Ruta vieja | Ruta nueva |
|---|---|
| `scripts/metadata_repository_ddl.sql` | `metadata_repository/ddl/metadata_repository_ddl.sql` |
| `scripts/metadata_staging_ddl.sql` | `metadata_repository/ddl/metadata_staging_ddl.sql` |
| `scripts/etl_metadata_repository.py` | `metadata_repository/etl/etl_metadata_repository.py` |
| `scripts/business_metadata_seed.sql` | `metadata_repository/etl/business_metadata_seed.sql` |
| `scripts/consultas_repositorio.sql` | `metadata_repository/queries/consultas_repositorio.sql` |
| `metadata_repo_backup.sql` | `metadata_repository/backup/metadata_repo_backup.sql` |
| `data_profiling/` | `profiling/` |
| `output/` | `profiling/output/` |
| `mysqlsampledatabase.sql` | `sources/mysqlsampledatabase.sql` |
| `customerservice.sql` | `sources/customerservice.sql` |

**Cómo sabés que funcionó:** abrí el `README.md` en VS Code y hacé Ctrl+clic en cada enlace. Si abre el archivo, está bien.

---

## Parte 2 — Crear la base del almacén

### 2.1 Por qué una base nueva y no un servicio nuevo

Railway cobra por servicio. Ya tenés tres corriendo. Pero un servidor PostgreSQL puede tener **varias bases de datos adentro**, y eso no cuesta nada extra. Entonces vas a crear la base `dw` dentro del servidor que ya hospeda el repositorio de metadatos.

### 2.2 Crearla

Creá `datawarehouse/ddl/00_crear_base.py`:

```python
"""Crea la base de datos 'dw' en el servidor PostgreSQL de Railway."""
import os
from dotenv import load_dotenv
import sqlalchemy as sa

load_dotenv()

# Conectamos a la base 'railway' para poder crear otra base desde ahi.
# AUTOCOMMIT es obligatorio: PostgreSQL no permite CREATE DATABASE
# dentro de una transaccion.
admin = sa.create_engine(os.getenv("METADATA_REPO_URL"), isolation_level="AUTOCOMMIT")

with admin.connect() as con:
    existe = con.execute(
        sa.text("SELECT 1 FROM pg_database WHERE datname = 'dw'")
    ).scalar()
    if existe:
        print("La base 'dw' ya existe. No se hace nada.")
    else:
        con.execute(sa.text("CREATE DATABASE dw"))
        print("Base 'dw' creada.")
```

Corré:

```bash
python datawarehouse/ddl/00_crear_base.py
```

**Deberías ver:** `Base 'dw' creada.`

**Si lo corrés dos veces:** dice `La base 'dw' ya existe`. Eso está bien, el script es seguro de repetir.

### 2.3 Verificar

```bash
python -c "import os;from dotenv import load_dotenv;import sqlalchemy as sa;load_dotenv();sa.create_engine(os.getenv('DW_URL')).connect();print('Conexion a dw OK')"
```

**Deberías ver:** `Conexion a dw OK`

---

## Parte 3 — Las tablas del almacén

### 3.1 Entender la estructura antes de copiarla

Cada dimensión tiene dos llaves:

- **Llave subrogada** (`*_key`): un número que inventa el almacén, empieza en 1 y sube. Es la que usan los hechos para apuntar.
- **Llave de negocio** (`*_id` o el código original): la que viene de la fuente, como `customerNumber` o `productCode`.

¿Por qué dos? Porque la llave de negocio puede cambiar, repetirse entre fuentes, o ser un texto largo. La subrogada es un entero estable y rápido. Es el estándar en almacenes de datos.

### 3.2 El archivo DDL

Creá `datawarehouse/ddl/01_dw_schema.sql`:

```sql
-- ============================================================
-- Almacen de Datos - Modelo dimensional (constelacion)
-- Proyecto: Modelos y Persistencia de Datos - Entrega 2
--
-- Dos hechos (fact_ventas, fact_llamadas_servicio) que comparten
-- las dimensiones conformadas dim_cliente, dim_producto y dim_tiempo.
--
-- Motor: PostgreSQL 18 (base 'dw' en Railway).
-- ============================================================

DROP TABLE IF EXISTS fact_ventas             CASCADE;
DROP TABLE IF EXISTS fact_llamadas_servicio  CASCADE;
DROP TABLE IF EXISTS dim_tiempo              CASCADE;
DROP TABLE IF EXISTS dim_cliente             CASCADE;
DROP TABLE IF EXISTS dim_producto            CASCADE;
DROP TABLE IF EXISTS dim_empleado            CASCADE;
DROP TABLE IF EXISTS dim_oficina             CASCADE;
DROP TABLE IF EXISTS dim_estado_orden        CASCADE;

-- ------------------------------------------------------------
-- DIMENSIONES CONFORMADAS (las comparten los dos hechos)
-- ------------------------------------------------------------

CREATE TABLE dim_tiempo (
    tiempo_key      INTEGER PRIMARY KEY,        -- formato AAAAMMDD, ej. 20030106
    fecha           DATE    NOT NULL UNIQUE,
    anio            SMALLINT NOT NULL,
    trimestre       SMALLINT NOT NULL,
    mes             SMALLINT NOT NULL,
    nombre_mes      VARCHAR(12) NOT NULL,
    dia             SMALLINT NOT NULL,
    dia_semana      SMALLINT NOT NULL,          -- 1 = lunes
    nombre_dia      VARCHAR(12) NOT NULL,
    es_fin_semana   BOOLEAN NOT NULL,
    anio_mes        CHAR(7) NOT NULL            -- '2003-01', util para agrupar
);

CREATE TABLE dim_cliente (
    cliente_key             SERIAL PRIMARY KEY,
    numero_cliente          INTEGER NOT NULL UNIQUE,   -- llave de negocio
    nombre_cliente          VARCHAR(100),
    contacto_nombre         VARCHAR(100),
    contacto_apellido       VARCHAR(100),
    telefono                VARCHAR(50),
    direccion_completa      VARCHAR(220),              -- addressLine1 + addressLine2
    ciudad                  VARCHAR(100),
    estado_region           VARCHAR(100),
    codigo_postal           VARCHAR(20),
    pais                    VARCHAR(100),
    limite_credito          NUMERIC(12,2),
    presente_en_ventas      BOOLEAN NOT NULL DEFAULT FALSE,
    presente_en_servicio    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE dim_producto (
    producto_key            SERIAL PRIMARY KEY,
    codigo_producto         VARCHAR(20) NOT NULL UNIQUE,  -- llave de negocio
    nombre_producto         VARCHAR(140),
    linea_producto          VARCHAR(60),
    descripcion_linea       TEXT,
    escala                  VARCHAR(20),
    proveedor               VARCHAR(100),
    precio_compra           NUMERIC(12,2),
    precio_msrp             NUMERIC(12,2),
    presente_en_ventas      BOOLEAN NOT NULL DEFAULT FALSE,
    presente_en_servicio    BOOLEAN NOT NULL DEFAULT FALSE
);

-- ------------------------------------------------------------
-- DIMENSION NO CONFORMADA
--
-- Los 23 empleados de classicmodels y los 30 de customerservice
-- no comparten ni una sola llave (solape 0% medido en la Entrega 1).
-- La llave subrogada mas el atributo sistema_origen permiten que
-- ambas poblaciones convivan en la misma tabla sin colisionar.
-- Esta es la solucion al problema de calidad de la Entrega 1.
-- ------------------------------------------------------------

CREATE TABLE dim_empleado (
    empleado_key        SERIAL PRIMARY KEY,
    numero_empleado     INTEGER NOT NULL,
    sistema_origen      VARCHAR(20) NOT NULL,   -- 'classicmodels' | 'customerservice'
    nombre              VARCHAR(100),
    apellido            VARCHAR(100),
    email               VARCHAR(140),
    cargo               VARCHAR(80),
    numero_oficina      VARCHAR(20),
    UNIQUE (numero_empleado, sistema_origen)    -- la llave real es compuesta
);

-- ------------------------------------------------------------
-- DIMENSIONES EXCLUSIVAS DE classicmodels
-- ------------------------------------------------------------

CREATE TABLE dim_oficina (
    oficina_key     SERIAL PRIMARY KEY,
    codigo_oficina  VARCHAR(20) NOT NULL UNIQUE,
    ciudad          VARCHAR(100),
    pais            VARCHAR(100),
    region          VARCHAR(100),
    territorio      VARCHAR(20)
);

CREATE TABLE dim_estado_orden (
    estado_key      SERIAL PRIMARY KEY,
    estado          VARCHAR(30) NOT NULL UNIQUE,
    es_efectiva     BOOLEAN NOT NULL   -- FALSE para Cancelled / Disputed / On Hold
);

-- ------------------------------------------------------------
-- HECHO PRINCIPAL: fact_ventas
-- Grano: una linea de una orden de compra.
-- ------------------------------------------------------------

CREATE TABLE fact_ventas (
    venta_key           BIGSERIAL PRIMARY KEY,

    -- Llaves foraneas hacia las dimensiones
    tiempo_key          INTEGER NOT NULL REFERENCES dim_tiempo(tiempo_key),
    cliente_key         INTEGER NOT NULL REFERENCES dim_cliente(cliente_key),
    producto_key        INTEGER NOT NULL REFERENCES dim_producto(producto_key),
    empleado_key        INTEGER          REFERENCES dim_empleado(empleado_key),
    oficina_key         INTEGER          REFERENCES dim_oficina(oficina_key),
    estado_key          INTEGER NOT NULL REFERENCES dim_estado_orden(estado_key),

    -- Dimensiones degeneradas (viven en el hecho, no valen una tabla propia)
    numero_orden        INTEGER NOT NULL,
    numero_linea        SMALLINT NOT NULL,

    -- Medidas
    cantidad_ordenada   INTEGER       NOT NULL,
    precio_unitario     NUMERIC(12,2) NOT NULL,
    monto_linea         NUMERIC(14,2) NOT NULL,   -- cantidad * precio
    costo_linea         NUMERIC(14,2),            -- cantidad * precio_compra
    margen_linea        NUMERIC(14,2),            -- monto - costo
    precio_msrp         NUMERIC(12,2),
    dias_hasta_envio    SMALLINT,                 -- NULL si la orden no se despacho

    UNIQUE (numero_orden, numero_linea)
);

-- ------------------------------------------------------------
-- HECHO SECUNDARIO: fact_llamadas_servicio
-- Grano: una llamada al centro de servicio.
-- ------------------------------------------------------------

CREATE TABLE fact_llamadas_servicio (
    llamada_key         BIGSERIAL PRIMARY KEY,

    tiempo_key          INTEGER NOT NULL REFERENCES dim_tiempo(tiempo_key),
    cliente_key         INTEGER NOT NULL REFERENCES dim_cliente(cliente_key),
    producto_key        INTEGER NOT NULL REFERENCES dim_producto(producto_key),
    empleado_key        INTEGER NOT NULL REFERENCES dim_empleado(empleado_key),

    texto_llamada       TEXT,                     -- dimension degenerada

    cantidad_llamadas   SMALLINT NOT NULL DEFAULT 1,
    longitud_texto      INTEGER
);

-- ------------------------------------------------------------
-- Indices sobre las llaves foraneas
-- (PostgreSQL no los crea solo, y sin ellos los JOIN son lentos)
-- ------------------------------------------------------------

CREATE INDEX idx_fv_tiempo   ON fact_ventas(tiempo_key);
CREATE INDEX idx_fv_cliente  ON fact_ventas(cliente_key);
CREATE INDEX idx_fv_producto ON fact_ventas(producto_key);
CREATE INDEX idx_fv_empleado ON fact_ventas(empleado_key);
CREATE INDEX idx_fl_tiempo   ON fact_llamadas_servicio(tiempo_key);
CREATE INDEX idx_fl_cliente  ON fact_llamadas_servicio(cliente_key);
CREATE INDEX idx_fl_producto ON fact_llamadas_servicio(producto_key);

-- ------------------------------------------------------------
-- Schema de staging para las capas intermedias del ETL
-- ------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS staging_dw;
```

### 3.3 Ejecutarlo

Creá `datawarehouse/ddl/run_sql.py` — este script sirve para correr cualquier archivo `.sql` contra el almacén:

```python
"""Ejecuta un archivo .sql contra la base indicada.

Uso:
    python datawarehouse/ddl/run_sql.py datawarehouse/ddl/01_dw_schema.sql
    python datawarehouse/ddl/run_sql.py archivo.sql METADATA_REPO_URL
"""
import os
import sys
from dotenv import load_dotenv
import sqlalchemy as sa

load_dotenv()

ruta = sys.argv[1]
variable = sys.argv[2] if len(sys.argv) > 2 else "DW_URL"

url = os.getenv(variable)
if not url:
    raise SystemExit(f"No encontre la variable {variable} en el .env")

with open(ruta, encoding="utf-8") as f:
    sql = f.read()

eng = sa.create_engine(url, isolation_level="AUTOCOMMIT")
with eng.connect() as con:
    con.execute(sa.text(sql))

print(f"Ejecutado {ruta} contra {variable}")
```

Corré:

```bash
python datawarehouse/ddl/run_sql.py datawarehouse/ddl/01_dw_schema.sql
```

**Deberías ver:** `Ejecutado datawarehouse/ddl/01_dw_schema.sql contra DW_URL`

### 3.4 Verificar que las 8 tablas están

```bash
python -c "
import os;from dotenv import load_dotenv;import sqlalchemy as sa
load_dotenv()
insp = sa.inspect(sa.create_engine(os.getenv('DW_URL')))
for t in sorted(insp.get_table_names(schema='public')): print(' -', t)
"
```

**Deberías ver exactamente 8 tablas:**

```
 - dim_cliente
 - dim_empleado
 - dim_estado_orden
 - dim_oficina
 - dim_producto
 - dim_tiempo
 - fact_llamadas_servicio
 - fact_ventas
```

**Si falta alguna:** volvé a correr el paso 3.3. El DDL empieza con `DROP TABLE IF EXISTS`, así que es seguro repetirlo.

---

## Parte 4 — Extender el repositorio de metadatos

Esto vale el 15 % de la nota. El repositorio de la Entrega 1 describe las **fuentes**; ahora tiene que describir también el **almacén** y los **procesos** que lo alimentan.

> **Ojo:** estas tablas van en la base `railway` (el repositorio de metadatos), **no** en `dw`.

Creá `metadata_repository/ddl/metadata_dw_extension.sql`:

```sql
-- ============================================================
-- Extension del Repositorio de Metadatos para gestionar el
-- almacen de datos - Entrega 2.
--
-- Se agregan 8 tablas a las 6 que ya existen de la Entrega 1.
-- Correr contra METADATA_REPO_URL (base 'railway').
-- ============================================================

-- ------------------------------------------------------------
-- METADATO ESTRUCTURAL DEL ALMACEN
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS dw_object (
    dw_object_id    SERIAL PRIMARY KEY,
    object_name     VARCHAR(100) NOT NULL UNIQUE,   -- 'fact_ventas', 'dim_cliente'
    object_type     VARCHAR(20)  NOT NULL,          -- 'FACT' | 'DIMENSION' | 'VIEW'
    grain           TEXT,                           -- solo aplica a hechos
    description     TEXT NOT NULL,
    is_conformed    BOOLEAN NOT NULL DEFAULT FALSE, -- solo aplica a dimensiones
    row_count       INTEGER,
    loaded_at       TIMESTAMP NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dw_measure (
    dw_measure_id   SERIAL PRIMARY KEY,
    dw_object_id    INTEGER NOT NULL REFERENCES dw_object(dw_object_id) ON DELETE CASCADE,
    measure_name    VARCHAR(100) NOT NULL,
    data_type       VARCHAR(50)  NOT NULL,
    additivity      VARCHAR(20)  NOT NULL,   -- 'ADITIVA' | 'SEMI_ADITIVA' | 'NO_ADITIVA'
    formula         TEXT,                    -- 'quantityOrdered * priceEach'
    description     TEXT,
    UNIQUE (dw_object_id, measure_name)
);

CREATE TABLE IF NOT EXISTS dw_attribute (
    dw_attribute_id SERIAL PRIMARY KEY,
    dw_object_id    INTEGER NOT NULL REFERENCES dw_object(dw_object_id) ON DELETE CASCADE,
    attribute_name  VARCHAR(100) NOT NULL,
    data_type       VARCHAR(50)  NOT NULL,
    attribute_role  VARCHAR(30)  NOT NULL,   -- 'SURROGATE_KEY' | 'BUSINESS_KEY' | 'DESCRIPTIVE' | 'FLAG'
    description     TEXT,
    UNIQUE (dw_object_id, attribute_name)
);

-- ------------------------------------------------------------
-- LINAJE FUENTE -> ALMACEN
--
-- Conecta con db_column, que es la tabla de la Entrega 1 donde
-- estan catalogadas todas las columnas de las dos fuentes.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS dw_lineage (
    dw_lineage_id       SERIAL PRIMARY KEY,
    source_column_id    INTEGER REFERENCES db_column(column_id) ON DELETE SET NULL,
    target_measure_id   INTEGER REFERENCES dw_measure(dw_measure_id)   ON DELETE CASCADE,
    target_attribute_id INTEGER REFERENCES dw_attribute(dw_attribute_id) ON DELETE CASCADE,
    transformation_rule TEXT NOT NULL,   -- 'copia directa', 'concatenacion', 'calculo'
    -- Cada fila apunta a UNA medida o a UN atributo, nunca a los dos.
    CHECK (
        (target_measure_id IS NOT NULL AND target_attribute_id IS NULL) OR
        (target_measure_id IS NULL AND target_attribute_id IS NOT NULL)
    )
);

-- ------------------------------------------------------------
-- METADATO OPERACIONAL DE LOS PROCESOS ETL
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS etl_process (
    etl_process_id  SERIAL PRIMARY KEY,
    process_name    VARCHAR(100) NOT NULL UNIQUE,
    tool            VARCHAR(80)  NOT NULL,   -- 'Python 3.11 + SQLAlchemy + pandas'
    source_systems  VARCHAR(200) NOT NULL,
    target_system   VARCHAR(100) NOT NULL,
    description     TEXT
);

CREATE TABLE IF NOT EXISTS etl_execution (
    etl_execution_id SERIAL PRIMARY KEY,
    etl_process_id   INTEGER NOT NULL REFERENCES etl_process(etl_process_id),
    run_id           INTEGER NOT NULL,
    started_at       TIMESTAMP NOT NULL,
    finished_at      TIMESTAMP,
    status           VARCHAR(20) NOT NULL,   -- 'EN_CURSO' | 'OK' | 'ERROR'
    rows_read        INTEGER,
    rows_written     INTEGER,
    rows_rejected    INTEGER,
    error_message    TEXT
);

-- ------------------------------------------------------------
-- CALIDAD DE DATOS
-- Formaliza los hallazgos del perfilamiento de la Entrega 1.
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS dq_rule (
    dq_rule_id      SERIAL PRIMARY KEY,
    rule_name       VARCHAR(120) NOT NULL UNIQUE,
    rule_type       VARCHAR(40)  NOT NULL,   -- 'COMPLETITUD' | 'UNICIDAD' | 'INTEGRIDAD' | 'RANGO'
    source_column_id INTEGER REFERENCES db_column(column_id) ON DELETE SET NULL,
    expression      TEXT NOT NULL,
    severity        VARCHAR(20) NOT NULL,    -- 'BLOQUEANTE' | 'ADVERTENCIA' | 'INFORMATIVA'
    resolution      TEXT NOT NULL            -- que hace el ETL cuando la regla falla
);

CREATE TABLE IF NOT EXISTS dq_result (
    dq_result_id     SERIAL PRIMARY KEY,
    dq_rule_id       INTEGER NOT NULL REFERENCES dq_rule(dq_rule_id) ON DELETE CASCADE,
    etl_execution_id INTEGER NOT NULL REFERENCES etl_execution(etl_execution_id) ON DELETE CASCADE,
    evaluated_at     TIMESTAMP NOT NULL DEFAULT now(),
    rows_evaluated   INTEGER,
    rows_failed      INTEGER,
    passed           BOOLEAN NOT NULL
);

-- ------------------------------------------------------------
-- Indices de apoyo
-- ------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_dw_measure_object   ON dw_measure(dw_object_id);
CREATE INDEX IF NOT EXISTS idx_dw_attribute_object ON dw_attribute(dw_object_id);
CREATE INDEX IF NOT EXISTS idx_dw_lineage_source   ON dw_lineage(source_column_id);
CREATE INDEX IF NOT EXISTS idx_etl_exec_process    ON etl_execution(etl_process_id);
CREATE INDEX IF NOT EXISTS idx_dq_result_rule      ON dq_result(dq_rule_id);
```

Ejecutalo **contra el repositorio de metadatos**, no contra `dw`:

```bash
python datawarehouse/ddl/run_sql.py metadata_repository/ddl/metadata_dw_extension.sql METADATA_REPO_URL
```

**Verificá que ahora hay 14 tablas:**

```bash
python -c "
import os;from dotenv import load_dotenv;import sqlalchemy as sa
load_dotenv()
insp = sa.inspect(sa.create_engine(os.getenv('METADATA_REPO_URL')))
t = sorted(insp.get_table_names(schema='public'))
print(f'{len(t)} tablas:'); [print(' -',x) for x in t]
"
```

**Deberías ver 14:** las 6 de la Entrega 1 más las 8 nuevas.

---

## Parte 5 — ETL de dimensiones

Acordate: **primero todas las dimensiones, después los hechos.**

Creá `datawarehouse/etl/etl_dw_dimensions.py`:

```python
"""
ETL de dimensiones hacia el almacen de datos.

Sigue el mismo patron de capas de la Entrega 1 (Giordano):
Extract -> Data Quality -> Transform -> Load.

Carga, en este orden:
    dim_tiempo        (generada, no viene de ninguna fuente)
    dim_estado_orden  (desde orders.status)
    dim_oficina       (desde offices)
    dim_cliente       (CONFORMADA: customers + cs_customers)
    dim_producto      (CONFORMADA: products + productlines + cs_products)
    dim_empleado      (NO conformada: employees + cs_employees, con sistema_origen)

Uso:
    python datawarehouse/etl/etl_dw_dimensions.py
"""
import os
from datetime import date, timedelta

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

MYSQL = sa.create_engine(os.getenv("URL_MYSQLDATABASE"))
PG    = sa.create_engine(os.getenv("DATABASE_URL"))
DW    = sa.create_engine(os.getenv("DW_URL"))

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS  = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]


def cargar(df, tabla):
    """Escribe un DataFrame en una tabla del almacen, reemplazando lo anterior."""
    with DW.begin() as con:
        con.execute(sa.text(f"TRUNCATE TABLE {tabla} RESTART IDENTITY CASCADE"))
    df.to_sql(tabla, DW, if_exists="append", index=False)
    print(f"  {tabla}: {len(df)} filas")


# ------------------------------------------------------------
# dim_tiempo - se genera, no se extrae de ninguna fuente.
# Cubre 2003-2005, que es el rango de ventas y llamadas.
# ------------------------------------------------------------
def dim_tiempo():
    filas = []
    d, fin = date(2003, 1, 1), date(2005, 12, 31)
    while d <= fin:
        filas.append({
            "tiempo_key":    int(d.strftime("%Y%m%d")),
            "fecha":         d,
            "anio":          d.year,
            "trimestre":     (d.month - 1) // 3 + 1,
            "mes":           d.month,
            "nombre_mes":    MESES[d.month - 1],
            "dia":           d.day,
            "dia_semana":    d.isoweekday(),
            "nombre_dia":    DIAS[d.isoweekday() - 1],
            "es_fin_semana": d.isoweekday() >= 6,
            "anio_mes":      d.strftime("%Y-%m"),
        })
        d += timedelta(days=1)
    cargar(pd.DataFrame(filas), "dim_tiempo")


# ------------------------------------------------------------
# dim_estado_orden - los 6 estados que existen en orders.status.
# es_efectiva = False marca las ordenes que no deberian contarse
# como venta cerrada. Resuelve el hallazgo de calidad #7.
# ------------------------------------------------------------
def dim_estado_orden():
    df = pd.read_sql("SELECT DISTINCT status AS estado FROM orders", MYSQL)
    no_efectivos = {"Cancelled", "Disputed", "On Hold"}
    df["es_efectiva"] = ~df["estado"].isin(no_efectivos)
    cargar(df, "dim_estado_orden")


def dim_oficina():
    df = pd.read_sql("""
        SELECT officeCode AS codigo_oficina, city AS ciudad, country AS pais,
               territory AS territorio, state AS region
        FROM offices
    """, MYSQL)
    cargar(df, "dim_oficina")


# ------------------------------------------------------------
# dim_cliente - DIMENSION CONFORMADA.
#
# En la Entrega 1 se midio que customers y cs_customers solapan al
# 100% por customerNumber. Se toma classicmodels como fuente
# autoritativa (tiene mas atributos) y se marca con banderas en
# cual de las dos fuentes aparece cada cliente.
#
# Resuelve el hallazgo de calidad #3: addressLine2 esta vacia en el
# 81,97% de las filas, asi que se concatena con addressLine1 en un
# solo atributo en vez de arrastrar una columna casi vacia.
# ------------------------------------------------------------
def dim_cliente():
    cm = pd.read_sql("""
        SELECT customerNumber   AS numero_cliente,
               customerName     AS nombre_cliente,
               contactFirstName AS contacto_nombre,
               contactLastName  AS contacto_apellido,
               phone            AS telefono,
               addressLine1, addressLine2,
               city             AS ciudad,
               state            AS estado_region,
               postalCode       AS codigo_postal,
               country          AS pais,
               creditLimit      AS limite_credito
        FROM customers
    """, MYSQL)

    # Hallazgo #3: consolidar las dos lineas de direccion en una.
    cm["direccion_completa"] = (
        cm["addressLine1"].fillna("") +
        cm["addressLine2"].fillna("").apply(lambda x: f", {x}" if x else "")
    ).str.strip(", ")
    cm = cm.drop(columns=["addressLine1", "addressLine2"])

    cs = pd.read_sql("SELECT customernumber AS numero_cliente FROM cs_customers", PG)

    cm["presente_en_ventas"]   = True
    cm["presente_en_servicio"] = cm["numero_cliente"].isin(cs["numero_cliente"])

    solape = int(cm["presente_en_servicio"].sum())
    print(f"  [calidad] clientes en ambas fuentes: {solape} de {len(cm)}")

    cargar(cm, "dim_cliente")


# ------------------------------------------------------------
# dim_producto - DIMENSION CONFORMADA.
#
# Resuelve el hallazgo de calidad #1: productlines.htmlDescription e
# .image estan 100% vacias, asi que no se traen al almacen. Solo se
# trae textDescription.
# ------------------------------------------------------------
def dim_producto():
    cm = pd.read_sql("""
        SELECT p.productCode    AS codigo_producto,
               p.productName    AS nombre_producto,
               p.productLine    AS linea_producto,
               pl.textDescription AS descripcion_linea,
               p.productScale   AS escala,
               p.productVendor  AS proveedor,
               p.buyPrice       AS precio_compra,
               p.MSRP           AS precio_msrp
        FROM products p
        JOIN productlines pl ON p.productLine = pl.productLine
    """, MYSQL)

    cs = pd.read_sql("SELECT productcode AS codigo_producto FROM cs_products", PG)

    cm["presente_en_ventas"]   = True
    cm["presente_en_servicio"] = cm["codigo_producto"].isin(cs["codigo_producto"])

    print(f"  [calidad] productos en ambas fuentes: "
          f"{int(cm['presente_en_servicio'].sum())} de {len(cm)}")

    cargar(cm, "dim_producto")


# ------------------------------------------------------------
# dim_empleado - DIMENSION NO CONFORMADA.
#
# Resuelve el hallazgo de calidad #2, el mas importante: los
# empleados de las dos fuentes tienen solape 0%. No se pueden
# fusionar. La solucion es una llave compuesta
# (numero_empleado, sistema_origen) con llave subrogada encima,
# de modo que las dos poblaciones convivan sin colisionar.
# ------------------------------------------------------------
def dim_empleado():
    cm = pd.read_sql("""
        SELECT employeeNumber AS numero_empleado,
               firstName      AS nombre,
               lastName       AS apellido,
               email, jobTitle AS cargo,
               officeCode     AS numero_oficina
        FROM employees
    """, MYSQL)
    cm["sistema_origen"] = "classicmodels"

    cs = pd.read_sql("""
        SELECT employeenumber AS numero_empleado,
               firstname      AS nombre,
               lastname       AS apellido,
               email
        FROM cs_employees
    """, PG)
    cs["sistema_origen"] = "customerservice"
    cs["cargo"] = "Agente de Servicio al Cliente"
    cs["numero_oficina"] = None

    solape = set(cm["numero_empleado"]) & set(cs["numero_empleado"])
    print(f"  [calidad] empleados con llave compartida: {len(solape)} "
          f"-> se usa llave compuesta con sistema_origen")

    cargar(pd.concat([cm, cs], ignore_index=True), "dim_empleado")


if __name__ == "__main__":
    print("Cargando dimensiones...")
    dim_tiempo()
    dim_estado_orden()
    dim_oficina()
    dim_cliente()
    dim_producto()
    dim_empleado()
    print("Dimensiones cargadas.")
```

Corré:

```bash
python datawarehouse/etl/etl_dw_dimensions.py
```

**Deberías ver algo como:**

```
Cargando dimensiones...
  dim_tiempo: 1096 filas
  dim_estado_orden: 6 filas
  dim_oficina: 7 filas
  [calidad] clientes en ambas fuentes: 122 de 122
  dim_cliente: 122 filas
  [calidad] productos en ambas fuentes: 110 de 110
  dim_producto: 110 filas
  [calidad] empleados con llave compartida: 0 -> se usa llave compuesta con sistema_origen
  dim_empleado: 53 filas
Dimensiones cargadas.
```

> Esas tres líneas `[calidad]` son **oro para el documento**: son la evidencia numérica de que resolviste los problemas de la Entrega 1. Tomales pantallazo.

---

## Parte 6 — ETL de hechos

Ahora sí los hechos. La parte nueva acá es la **búsqueda de llaves subrogadas** (*surrogate key lookup*): el hecho no guarda `customerNumber = 103`, guarda `cliente_key = 7`, que es la llave que le tocó a ese cliente en `dim_cliente`. Hay que traducir.

Creá `datawarehouse/etl/etl_dw_facts.py`:

```python
"""
ETL de hechos hacia el almacen de datos.

Requiere que las dimensiones ya esten cargadas
(python datawarehouse/etl/etl_dw_dimensions.py).

Carga:
    fact_ventas             desde classicmodels (orderdetails + orders + products)
    fact_llamadas_servicio  desde customerservice (cs_customer_calls)

Y crea la vista integrada vw_interaccion_cliente_producto.

Uso:
    python datawarehouse/etl/etl_dw_facts.py
"""
import os

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

MYSQL = sa.create_engine(os.getenv("URL_MYSQLDATABASE"))
PG    = sa.create_engine(os.getenv("DATABASE_URL"))
DW    = sa.create_engine(os.getenv("DW_URL"))


def mapa(tabla, llave_negocio, llave_subrogada, extra=None):
    """Devuelve un diccionario {llave_de_negocio: llave_subrogada}.

    Es la traduccion que necesita el hecho: en la fuente el cliente es
    el numero 103, pero en el almacen es la fila cliente_key = 7.
    """
    cols = f"{llave_negocio}, {llave_subrogada}"
    if extra:
        cols += f", {extra}"
    df = pd.read_sql(f"SELECT {cols} FROM {tabla}", DW)
    if extra:
        return {(r[llave_negocio], r[extra]): r[llave_subrogada] for _, r in df.iterrows()}
    return dict(zip(df[llave_negocio], df[llave_subrogada]))


def cargar(df, tabla):
    with DW.begin() as con:
        con.execute(sa.text(f"TRUNCATE TABLE {tabla} RESTART IDENTITY CASCADE"))
    df.to_sql(tabla, DW, if_exists="append", index=False)
    print(f"  {tabla}: {len(df)} filas")


# ------------------------------------------------------------
# fact_ventas - grano: una linea de una orden.
# ------------------------------------------------------------
def fact_ventas():
    df = pd.read_sql("""
        SELECT od.orderNumber      AS numero_orden,
               od.orderLineNumber  AS numero_linea,
               o.orderDate, o.shippedDate, o.status,
               o.customerNumber,
               od.productCode,
               od.quantityOrdered  AS cantidad_ordenada,
               od.priceEach        AS precio_unitario,
               p.buyPrice, p.MSRP  AS precio_msrp,
               c.salesRepEmployeeNumber,
               e.officeCode
        FROM orderdetails od
        JOIN orders    o ON od.orderNumber    = o.orderNumber
        JOIN products  p ON od.productCode    = p.productCode
        JOIN customers c ON o.customerNumber  = c.customerNumber
        LEFT JOIN employees e ON c.salesRepEmployeeNumber = e.employeeNumber
    """, MYSQL)

    # --- Medidas calculadas ---
    df["monto_linea"] = (df["cantidad_ordenada"] * df["precio_unitario"]).round(2)
    df["costo_linea"] = (df["cantidad_ordenada"] * df["buyPrice"]).round(2)
    df["margen_linea"] = (df["monto_linea"] - df["costo_linea"]).round(2)

    # Hallazgo de calidad #5: shippedDate es nula en las 14 ordenes que
    # no se despacharon. Se deja NULL en vez de inventar un valor.
    df["dias_hasta_envio"] = (
        pd.to_datetime(df["shippedDate"]) - pd.to_datetime(df["orderDate"])
    ).dt.days

    # --- Traduccion a llaves subrogadas ---
    k_cli = mapa("dim_cliente",      "numero_cliente",  "cliente_key")
    k_pro = mapa("dim_producto",     "codigo_producto", "producto_key")
    k_ofi = mapa("dim_oficina",      "codigo_oficina",  "oficina_key")
    k_est = mapa("dim_estado_orden", "estado",          "estado_key")
    k_emp = mapa("dim_empleado",     "numero_empleado", "empleado_key", extra="sistema_origen")

    df["tiempo_key"]   = pd.to_datetime(df["orderDate"]).dt.strftime("%Y%m%d").astype(int)
    df["cliente_key"]  = df["customerNumber"].map(k_cli)
    df["producto_key"] = df["productCode"].map(k_pro)
    df["oficina_key"]  = df["officeCode"].map(k_ofi)
    df["estado_key"]   = df["status"].map(k_est)
    df["empleado_key"] = df["salesRepEmployeeNumber"].map(
        lambda n: k_emp.get((n, "classicmodels")) if pd.notna(n) else None
    )

    salida = df[[
        "tiempo_key", "cliente_key", "producto_key", "empleado_key",
        "oficina_key", "estado_key", "numero_orden", "numero_linea",
        "cantidad_ordenada", "precio_unitario", "monto_linea",
        "costo_linea", "margen_linea", "precio_msrp", "dias_hasta_envio",
    ]].copy()

    # Las llaves subrogadas deben ser enteros que admitan nulos.
    for c in ["empleado_key", "oficina_key", "dias_hasta_envio"]:
        salida[c] = salida[c].astype("Int64")

    cargar(salida, "fact_ventas")


# ------------------------------------------------------------
# fact_llamadas_servicio - grano: una llamada.
# ------------------------------------------------------------
def fact_llamadas():
    df = pd.read_sql("""
        SELECT employeenumber, customernumber, productcode, text, date
        FROM cs_customer_calls
    """, PG)

    k_cli = mapa("dim_cliente",  "numero_cliente",  "cliente_key")
    k_pro = mapa("dim_producto", "codigo_producto", "producto_key")
    k_emp = mapa("dim_empleado", "numero_empleado", "empleado_key", extra="sistema_origen")

    df["tiempo_key"]        = pd.to_datetime(df["date"]).dt.strftime("%Y%m%d").astype(int)
    df["cliente_key"]       = df["customernumber"].map(k_cli)
    df["producto_key"]      = df["productcode"].map(k_pro)
    df["empleado_key"]      = df["employeenumber"].map(
        lambda n: k_emp.get((n, "customerservice"))
    )
    df["texto_llamada"]     = df["text"]
    df["cantidad_llamadas"] = 1
    df["longitud_texto"]    = df["text"].fillna("").str.len()

    salida = df[[
        "tiempo_key", "cliente_key", "producto_key", "empleado_key",
        "texto_llamada", "cantidad_llamadas", "longitud_texto",
    ]]
    cargar(salida, "fact_llamadas_servicio")


# ------------------------------------------------------------
# La vista que cruza los dos hechos.
# Este es el entregable que justifica haber integrado las fuentes.
# ------------------------------------------------------------
def vista_integrada():
    sql = """
    DROP VIEW IF EXISTS vw_interaccion_cliente_producto;
    CREATE VIEW vw_interaccion_cliente_producto AS
    WITH ventas AS (
        SELECT f.cliente_key, f.producto_key, t.anio_mes,
               SUM(f.cantidad_ordenada) AS unidades_vendidas,
               SUM(f.monto_linea)       AS monto_vendido,
               SUM(f.margen_linea)      AS margen_total,
               COUNT(*)                 AS lineas_orden
        FROM fact_ventas f
        JOIN dim_tiempo t ON f.tiempo_key = t.tiempo_key
        GROUP BY 1, 2, 3
    ),
    llamadas AS (
        SELECT l.cliente_key, l.producto_key, t.anio_mes,
               SUM(l.cantidad_llamadas) AS num_llamadas
        FROM fact_llamadas_servicio l
        JOIN dim_tiempo t ON l.tiempo_key = t.tiempo_key
        GROUP BY 1, 2, 3
    )
    SELECT
        COALESCE(v.anio_mes,     ll.anio_mes)     AS anio_mes,
        c.numero_cliente,
        c.nombre_cliente,
        p.codigo_producto,
        p.nombre_producto,
        p.linea_producto,
        COALESCE(v.unidades_vendidas, 0) AS unidades_vendidas,
        COALESCE(v.monto_vendido,   0)   AS monto_vendido,
        COALESCE(v.margen_total,    0)   AS margen_total,
        COALESCE(v.lineas_orden,    0)   AS lineas_orden,
        COALESCE(ll.num_llamadas,   0)   AS num_llamadas,
        CASE WHEN COALESCE(v.unidades_vendidas, 0) > 0
             THEN ROUND(COALESCE(ll.num_llamadas, 0)::numeric
                        / v.unidades_vendidas, 4)
        END AS llamadas_por_unidad
    FROM ventas v
    FULL OUTER JOIN llamadas ll
         ON v.cliente_key  = ll.cliente_key
        AND v.producto_key = ll.producto_key
        AND v.anio_mes     = ll.anio_mes
    JOIN dim_cliente  c ON c.cliente_key  = COALESCE(v.cliente_key,  ll.cliente_key)
    JOIN dim_producto p ON p.producto_key = COALESCE(v.producto_key, ll.producto_key);
    """
    with DW.begin() as con:
        con.execute(sa.text(sql))
    n = pd.read_sql("SELECT COUNT(*) AS n FROM vw_interaccion_cliente_producto", DW)
    print(f"  vw_interaccion_cliente_producto: {int(n['n'][0])} filas")


if __name__ == "__main__":
    print("Cargando hechos...")
    fact_ventas()
    fact_llamadas()
    vista_integrada()
    print("Hechos cargados.")
```

Corré:

```bash
python datawarehouse/etl/etl_dw_facts.py
```

**Deberías ver:**

```
Cargando hechos...
  fact_ventas: 2996 filas
  fact_llamadas_servicio: 108 filas
  vw_interaccion_cliente_producto: ~2700 filas
Cargando hechos... listo
```

**Si te da un error de llave foránea (`violates foreign key constraint`):** significa que alguna dimensión no está cargada. Volvé a correr la Parte 5 completa.

---

## Parte 7 — Validar que el almacén quedó bien

Este paso es el que te salva de entregar algo con números mal. Creá `datawarehouse/queries/validacion.py`:

```python
"""Compara los totales del almacen contra las fuentes originales."""
import os
import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()
MYSQL = sa.create_engine(os.getenv("URL_MYSQLDATABASE"))
PG    = sa.create_engine(os.getenv("DATABASE_URL"))
DW    = sa.create_engine(os.getenv("DW_URL"))

def uno(engine, sql):
    return pd.read_sql(sql, engine).iloc[0, 0]

pruebas = [
    ("Monto total vendido",
     uno(MYSQL, "SELECT ROUND(SUM(quantityOrdered*priceEach),2) FROM orderdetails"),
     uno(DW,    "SELECT ROUND(SUM(monto_linea),2) FROM fact_ventas")),
    ("Lineas de orden",
     uno(MYSQL, "SELECT COUNT(*) FROM orderdetails"),
     uno(DW,    "SELECT COUNT(*) FROM fact_ventas")),
    ("Llamadas de servicio",
     uno(PG,    "SELECT COUNT(*) FROM cs_customer_calls"),
     uno(DW,    "SELECT COUNT(*) FROM fact_llamadas_servicio")),
    ("Clientes",
     uno(MYSQL, "SELECT COUNT(*) FROM customers"),
     uno(DW,    "SELECT COUNT(*) FROM dim_cliente")),
    ("Productos",
     uno(MYSQL, "SELECT COUNT(*) FROM products"),
     uno(DW,    "SELECT COUNT(*) FROM dim_producto")),
]

print(f"{'Prueba':<24} {'Fuente':>16} {'Almacen':>16}   Estado")
print("-" * 70)
todo_ok = True
for nombre, fuente, almacen in pruebas:
    ok = float(fuente) == float(almacen)
    todo_ok &= ok
    print(f"{nombre:<24} {fuente:>16} {almacen:>16}   {'OK' if ok else 'DIFIERE'}")

print()
print("Todas las validaciones pasaron." if todo_ok
      else "Hay diferencias. Revisa el ETL antes de seguir.")
```

Corré:

```bash
python datawarehouse/queries/validacion.py
```

**Deberías ver todo en OK**, con el monto total en `9604190.61`.

> Tomale pantallazo a esta salida. Va en el documento como evidencia de que el almacén cuadra con las fuentes.

### 7.1 La consulta que responde la pregunta de negocio

```sql
-- Los 15 productos que mas llamadas generan por unidad vendida.
SELECT nombre_producto,
       linea_producto,
       SUM(unidades_vendidas) AS unidades,
       SUM(num_llamadas)      AS llamadas,
       ROUND(SUM(num_llamadas)::numeric / NULLIF(SUM(unidades_vendidas),0), 4)
           AS llamadas_por_unidad
FROM vw_interaccion_cliente_producto
GROUP BY nombre_producto, linea_producto
HAVING SUM(unidades_vendidas) > 0
ORDER BY llamadas_por_unidad DESC
LIMIT 15;
```

Guardala en `datawarehouse/queries/pregunta_negocio.sql`.

---

## Parte 8 — Los reportes en Metabase

Se eligió Metabase sobre Docker en vez de Power BI: no hay que instalar nada, y el dashboard se construye por script, así que cualquiera del equipo lo reproduce con un comando.

### 8.1 Levantar el contenedor

```bash
docker volume create metabase-data

MSYS_NO_PATHCONV=1 docker run -d --name metabase   -p 3000:3000   -v metabase-data:/metabase-data   -e MB_DB_FILE=/metabase-data/metabase.db   -e MB_SESSION_SECRET_KEY=javeriana-entrega2-clave-de-sesion-local   metabase/metabase:latest
```

> **`MSYS_NO_PATHCONV=1` no es opcional en Git Bash.** Sin eso, Git Bash convierte `/metabase-data/metabase.db` en una ruta de Windows y Metabase arranca, falla al abrir su base interna y se apaga. El síntoma en los logs es `AccessDeniedException: /C:`.

Metabase tarda entre 40 y 90 segundos en quedar operativo. Para saber cuándo está listo:

```bash
curl -s http://localhost:3000/api/health
```

**Deberías ver:** `{"status":"ok"}`. Mientras arranca devuelve `{"status":"initializing","progress":0.3}`.

### 8.2 Construir el dashboard

```bash
python -m pip install requests
python reports/construir_dashboard.py
```

**Deberías ver:**

```
Conectando con Metabase...
  Instancia nueva: creando usuario administrador...
Limpiando el contenido de ejemplo...
  Sample Database eliminada.
Registrando el almacen como origen de datos...
  Almacen registrado (id=2).
  Esquema sincronizado: 9 tablas.
Creando los reportes...
  creado: Ventas y margen por mes
  ... (6 en total)
Armando el dashboard...
  creado con 6 tarjetas.

Listo.
  Dashboard : http://localhost:3000/dashboard/2
```

El script es idempotente: si lo corrés otra vez, reconoce lo que ya existe y no duplica nada.

### 8.3 Qué hace el script

1. Crea el usuario administrador (`grupo@javeriana.edu.co` / `Javeriana2026!`).
2. **Borra la Sample Database** que Metabase trae de fábrica, con sus ~40 preguntas de ejemplo. Sin esto las capturas saldrían llenas de datos ficticios que no son del proyecto.
3. Registra la base `dw` como único origen.
4. Crea las 6 preguntas con SQL nativo contra el almacén.
5. Arma el dashboard con las tarjetas en dos columnas.

> **La restricción del enunciado queda cumplida por construcción:** el único origen registrado en Metabase es `dw`. Ni `classicmodels` ni `customerservice` están configurados, así que es imposible que un reporte toque las fuentes originales.

### 8.4 Lo que tenés que hacer vos

Abrí **http://localhost:3000/dashboard/2** e iniciá sesión con el usuario de arriba.

Capturá para el documento:

| Captura | Dónde | Para qué |
|---|---|---|
| El dashboard completo | La vista principal | Evidencia del entregable de reportes |
| Reporte "Intensidad de servicio por producto" | Clic en la tarjeta | Es el reporte central: cruza las dos fuentes |
| Reporte "Carga del centro de servicio por agente" | Clic en la tarjeta | Prueba que la llave compuesta de `dim_empleado` funciona |
| La pantalla de orígenes de datos | Configuración → Bases de datos | Prueba que solo está `dw`, ninguna fuente original |

Guardalas en `docs/Entrega_2/img/`.

### 8.5 Para apagarlo y volver a encenderlo

```bash
docker stop metabase     # apagar
docker start metabase    # encender, conserva todo
```

El volumen `metabase-data` guarda el trabajo, así que reiniciar no pierde nada.

---

## Parte 9 — Los backups

El enunciado pide el backup **del almacén** y **del repositorio de metadatos**.

> **No uses `pg_dump`.** Tu máquina tiene PostgreSQL 15 y Railway corre PostgreSQL 18; `pg_dump` aborta con *"no coincide la versión del servidor"*. Por eso el proyecto trae su propio generador.

```bash
python datawarehouse/backup/generar_backup.py dw
python datawarehouse/backup/generar_backup.py metadata
```

**Deberías ver:**

```
datawarehouse/backup/dw_backup.sql  (540 KB, 8 tablas)
metadata_repository/backup/metadata_repo_backup.sql  (38 KB, 14 tablas)
```

### 9.1 Probar que el backup de verdad restaura

Un backup que nadie probó no es un backup. Esta prueba crea una base desechable, restaura el archivo ahí y compara los conteos contra el almacén real:

```bash
python datawarehouse/backup/probar_restauracion.py
```

**Deberías ver todas las filas en OK**, incluido el monto total de 9.604.190,61, y al final `RESTAURACION VERIFICADA.` La base de prueba se borra sola.

---

---

## Si algo falla

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `No module named 'pymysql'` | Instalaste las librerías en otra versión de Python | Corré `python -m pip install ...` con el mismo `python` que usás para ejecutar |
| `No encontre la variable DW_URL` | El `.env` no está en la carpeta desde la que corrés | Corré los comandos desde la raíz del proyecto |
| `database "dw" does not exist` | No corriste la Parte 2 | `python datawarehouse/ddl/00_crear_base.py` |
| `violates foreign key constraint` | Cargaste hechos sin dimensiones | Corré primero `etl_dw_dimensions.py` |
| `relation "fact_ventas" does not exist` | No corriste el DDL | Volvé a la Parte 3.3 |
| `NotNullViolation` en `cliente_key` | Un cliente del hecho no existe en la dimensión | Revisá que `dim_cliente` tenga las 122 filas |
| Power BI no ve las tablas | Pusiste la base equivocada | La base es `dw`, no `railway` |
| `pg_dump: no coincide la versión` | Binario 15 contra servidor 18 | Usá el generador en Python, no `pg_dump` |

---

## Glosario

| Término | Qué significa |
|---|---|
| **Almacén de datos** | Base diseñada para analizar, no para registrar operaciones. |
| **Hecho** | Tabla con lo que pasó y sus números. Muchas filas. |
| **Dimensión** | Tabla con el contexto: quién, qué, cuándo, dónde. Pocas filas. |
| **Grano** | Qué representa exactamente una fila del hecho. Definirlo mal arruina el modelo. |
| **Esquema estrella** | El hecho en el centro, las dimensiones alrededor. |
| **Constelación** | Varios hechos que comparten dimensiones. |
| **Dimensión conformada** | La misma dimensión usada por varios hechos. Es lo que permite cruzar fuentes. |
| **Llave subrogada** | Entero que inventa el almacén para identificar una fila de dimensión. |
| **Llave de negocio** | El identificador que viene de la fuente (`customerNumber`). |
| **Dimensión degenerada** | Un identificador que vive en el hecho porque no vale una tabla propia (`numero_orden`). |
| **Aditiva / semi-aditiva / no aditiva** | Si la medida se puede sumar en todas las dimensiones, en algunas, o en ninguna. |
| **ETL** | Extract, Transform, Load: el proceso que mueve los datos. |
| **Staging** | Zona intermedia donde el ETL deja resultados parciales para poder auditarlos. |
