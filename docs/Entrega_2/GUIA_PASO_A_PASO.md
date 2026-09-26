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

### 3.2 Los tres archivos DDL del almacén

El almacén se define en tres archivos, y cada uno corresponde a una parte distinta de la arquitectura que se vio en clase. **No copies su contenido de esta guía: abrilos, porque cada decisión está comentada al lado de la línea que la implementa.**

| Archivo | Qué crea | Qué parte de la clase implementa |
|---|---|---|
| [`datawarehouse/ddl/01_dw_schema.sql`](../../datawarehouse/ddl/01_dw_schema.sql) | Las 6 dimensiones y los 2 hechos del modelo estrella, en el schema `public` | El **EDW** de la Clase 4-5 (diapositiva 12) |
| [`datawarehouse/ddl/02_staging_dw.sql`](../../datawarehouse/ddl/02_staging_dw.sql) | Las tablas de las capas del ETL, en el schema `staging_dw` | Las **7 capas de Giordano** de la Clase 2 (diapositivas 14–19) |
| [`datawarehouse/ddl/03_data_marts.sql`](../../datawarehouse/ddl/03_data_marts.sql) | Dos vistas en el schema `dm` | Los **Data Marts** de la Clase 4-5 (diapositiva 12) |

Cuando abras `01_dw_schema.sql`, fijate en tres cosas:

- Cada dimensión tiene su llave subrogada (`SERIAL`) y su llave de negocio con restricción `UNIQUE`.
- `dim_empleado` tiene una llave de negocio **compuesta**: `UNIQUE (numero_empleado, sistema_origen)`.
- Al final hay índices sobre todas las llaves foráneas de los hechos. PostgreSQL no los crea solo, y sin ellos cada join recorre la tabla completa.

### 3.3 Ejecutarlos

El proyecto trae un script, [`datawarehouse/ddl/run_sql.py`](../../datawarehouse/ddl/run_sql.py), que corre cualquier archivo `.sql` contra la base que le digas. Por defecto usa el almacén (`DW_URL`).

Corré los tres, **en este orden** — los data marts son vistas sobre las tablas, así que las tablas tienen que existir antes:

```bash
python datawarehouse/ddl/run_sql.py datawarehouse/ddl/01_dw_schema.sql
python datawarehouse/ddl/run_sql.py datawarehouse/ddl/02_staging_dw.sql
python datawarehouse/ddl/run_sql.py datawarehouse/ddl/03_data_marts.sql
```

**Deberías ver** una línea `Ejecutado ... contra DW_URL` por cada uno.

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

Esto vale el 15 % de la nota. El repositorio de la Entrega 1 describe las **fuentes**; ahora tiene que describir también el **almacén**, los **procesos** que lo alimentan y **cómo se usa**.

> **Ojo:** estas tablas van en la base `metadata` (el repositorio de metadatos), **no** en `dw`.

### 4.1 Las cuatro categorías de la Clase 3

La Clase 3 define cuatro categorías de metadatos. La Entrega 1 cubrió dos; la Entrega 2 completa las otras dos:

| Categoría | Qué responde | Tablas |
|---|---|---|
| **Negocio** | Qué significa cada dato | `business_entity`, `business_attribute`, `column_business_mapping` |
| **Técnicos** | Dónde está y cómo es cada dato | `data_source`, `db_table`, `db_column`, `dw_object`, `dw_measure`, `dw_attribute` |
| **Procesos** | Qué le hicieron los programas al dato | `etl_process`, `etl_execution`, `dw_lineage`, `dq_rule`, `dq_result` |
| **Uso** | Quién lo consulta, con qué y cuánto | `usage_herramienta`, `usage_consulta`, `usage_consulta_objeto`, `usage_acceso_objeto` |

### 4.2 Los archivos

| Archivo | Qué agrega |
|---|---|
| [`metadata_repository/ddl/metadata_dw_extension.sql`](../../metadata_repository/ddl/metadata_dw_extension.sql) | 8 tablas: estructura del almacén, linaje, procesos y calidad |
| [`metadata_repository/ddl/metadata_uso_extension.sql`](../../metadata_repository/ddl/metadata_uso_extension.sql) | 4 tablas de metadatos de uso |
| [`metadata_repository/etl/dq_rules_seed.sql`](../../metadata_repository/etl/dq_rules_seed.sql) | El catálogo de reglas de calidad |

Al abrir `metadata_dw_extension.sql`, fijate en `dq_rule`: cada regla está clasificada tres veces — por **capa** del pipeline donde se evalúa, por **criterio DAMA** (Clase 1) y por **clase** técnica o de negocio (Clase 2, diapositiva 17). Son tres preguntas distintas y las tres se enseñaron.

### 4.3 Ejecutarlos

El segundo parámetro de `run_sql.py` le dice que use el repositorio en vez del almacén:

```bash
python datawarehouse/ddl/run_sql.py metadata_repository/ddl/metadata_dw_extension.sql METADATA_REPO_URL
python datawarehouse/ddl/run_sql.py metadata_repository/ddl/metadata_uso_extension.sql METADATA_REPO_URL
python datawarehouse/ddl/run_sql.py metadata_repository/etl/dq_rules_seed.sql METADATA_REPO_URL
```

**Verificá que ahora hay 18 tablas:**

```bash
python -c "
import os;from dotenv import load_dotenv;import sqlalchemy as sa
load_dotenv()
insp = sa.inspect(sa.create_engine(os.getenv('METADATA_REPO_URL')))
t = sorted(insp.get_table_names(schema='public'))
print(f'{len(t)} tablas'); [print(' -',x) for x in t]
"
```

**Deberías ver 18:** las 6 de la Entrega 1, las 8 de la extensión del almacén y las 4 de uso.

---

## Parte 5 — El ETL, capas 1 a 4: extraer, limpiar y separar

Antes de correr nada, abrí la diapositiva 14 de la Clase 2. Es un diagrama de **siete columnas**, y el ETL de este proyecto las sigue una por una. Esta parte cubre las cuatro primeras; la siguiente, las tres últimas.

```
 1 Extract   2 Initial     3 Data       4 Clean      5 Transfor-   6 Load-Ready  7 Load
   Publish     Staging       Quality      Staging      mation        Publish
 ─────────   ──────────   ──────────   ──────────   ───────────   ───────────   ───────
 un modelo   una pila     Tech DQ      pila gris    conformar     forma final   dimen-
 por fuente  por fuente   Bus DQ       (limpios)    por área      lista para    siones
                          Error        pila roja    temática      cargar        hechos
                          Handling     (rechaz.)
```

### 5.1 Por qué esta mitad va separada

Las capas 1 a 4 las comparten **las dos cargas**, la de dimensiones y la de hechos. Por eso viven en un proceso propio, [`datawarehouse/etl/etl_dw_staging.py`](../../datawarehouse/etl/etl_dw_staging.py), que corre una sola vez. Es el principio **«read once, write many»** de la diapositiva 15: las fuentes se leen una sola vez por carga, y todo lo demás trabaja sobre la copia.

### 5.2 Qué hace cada capa

| Capa | Dónde queda | Qué hace |
|---|---|---|
| **1 Extract/Publish** | En el código: `MODELOS_EXTRACCION` | Un modelo de extracción por fuente. Trae **las 13 tablas**, incluso las que el modelo no usa hoy: la diapositiva 15 dice «traer todo pensando en necesidades futuras» |
| **2 Initial Staging** | `stg_initial_classicmodels`, `stg_initial_customerservice` | Una tabla **por fuente**, como las pilas de colores del diagrama. Guarda la fila tal cual y después **perfila** lo que aterrizó (diapositiva 16) |
| **3 Data Quality** | `stg_error_log` | Once reglas por registro, técnicas y de negocio. Lo que falla queda en el reporte de transacciones malas |
| **4 Clean Staging** | `stg_clean`, `stg_rejected` | Separa **físicamente** limpios de rechazados. La transformación solo puede leer los limpios |

Un detalle que vale la pena notar: las columnas obligatorias que revisa la calidad técnica **no están escritas en el ETL**. Se leen del repositorio de metadatos (`db_column.is_nullable`), que es el metadato técnico de la Entrega 1. El metadato gobierna el proceso, que es lo que la Clase 3 dice que debe hacer.

### 5.3 Correrlo

```bash
python datawarehouse/etl/etl_dw_staging.py
```

**Deberías ver** (resumido):

```
[Capa 2] Initial Staging            (dia. 16: una tabla por fuente)
    Modelo de extraccion: classicmodels  ->  staging_dw.stg_initial_classicmodels
      customers                122 filas
      ...
    TOTAL en Initial Staging      4335 filas
    Perfilamiento de Initial Staging  (dia. 16)
      85 columnas perfiladas, 14 con nulos

[Capa 3] Data Quality               (dia. 17: tecnica y de negocio)
    Regla                                 Clase    Accion       Revisadas  Fallas
    campos_obligatorios                   TECNICA  RECHAZADO         4335       0
    integridad_referencial                NEGOCIO  RECHAZADO         4059       0
    cliente_con_vendedor                  NEGOCIO  ADVERTENCIA        122      22
    ...
    Error Handling -> 22 entradas en el reporte de transacciones malas

[Capa 4] Clean Staging              (dia. 18: separar limpios y rechazados)
    TOTAL                  limpios  4335   rechazados   0
```

### 5.4 Cómo leer ese resultado

**Cero rechazados es la verdad sobre estos datos, no un error.** Los dumps de `classicmodels` y `customerservice` no tienen violaciones de integridad referencial, ni valores negativos, ni fechas incoherentes. Lo que sí tienen son **22 clientes sin vendedor asignado**: la fuente admite el nulo (técnicamente válido), pero el negocio espera que todo cliente tenga vendedor. Es exactamente la diferencia entre calidad técnica y de negocio de la diapositiva 17, y por eso es una advertencia y no un rechazo.

Para ver el reporte de transacciones malas:

```sql
SELECT * FROM staging_dw.vw_reporte_transacciones_malas;
```

### 5.5 ¿Y si llega un dato malo?

Como los datos reales son limpios, el camino de rechazo no se ejercita en una carga normal. Para probarlo hay un script que arma un lote **sintético** con un defecto por cada tipo de regla, sin tocar el almacén:

```bash
python datawarehouse/queries/probar_calidad.py
```

**Deberías ver** once filas en `OK`: los 7 defectos bloqueantes terminan en `rechazado`, las 4 advertencias pasan como `limpio`, y ningún registro sano se marca por error.

> Si el profesor pregunta qué pasa con un dato malo, esta es la respuesta con evidencia: la prueba muestra cada regla atrapando su defecto y mandando el registro adonde corresponde.

### 5.6 Los tres destinos de la diapositiva 18

La diapositiva 18 dice «separar: datos limpios, por revisar y rechazados». Aquí hay **dos** pilas, y es una decisión, no un olvido. «Por revisar» supone un custodio de datos que valide los casos dudosos antes de cada carga; este almacén se reconstruye desatendido desde snapshots estáticos, así que un estado que nadie revisa sería una capa muerta. Los casos dudosos pasan como limpios y quedan trazados como `ADVERTENCIA`.

---

## Parte 6 — El ETL, capas 5 a 7: conformar y cargar

### 6.1 La bifurcación final del diagrama

En la columna *Load* el diagrama se divide en dos modelos de carga: *Involved Party* y *Event*. En este almacén esa bifurcación son **dimensiones** y **hechos**, y cada rama es un proceso:

| Rama | Archivo | Carga |
|---|---|---|
| Dimensiones | [`etl_dw_dimensions.py`](../../datawarehouse/etl/etl_dw_dimensions.py) | Las 6 dimensiones |
| Hechos | [`etl_dw_facts.py`](../../datawarehouse/etl/etl_dw_facts.py) | Los 2 hechos |

Ninguno de los dos se conecta a MySQL ni a PostgreSQL de las fuentes: leen la pila de limpios de Clean Staging.

### 6.2 Conformar por área temática

La caja de *Transformation* del diagrama dice «Conform Loan Data» y «Conform Deposit Data»: conformar por **tema**, no por fuente. Aquí las áreas son:

| Área | Destino | Operación |
|---|---|---|
| Tiempo | `dim_tiempo` | Generación (no viene de ninguna fuente) |
| Organización | `dim_oficina` | Proyección |
| Ventas | `dim_estado_orden` | Agregación de valores distintos |
| Cliente | `dim_cliente` | Join entre las dos fuentes + consolidación de dirección |
| Producto | `dim_producto` | Join con `productlines` + join entre fuentes |
| Empleado | `dim_empleado` | Unión de fuentes con llave compuesta |
| Ventas | `fact_ventas` | Join de 5 tablas, lookup de 5 dimensiones, medidas calculadas |
| Servicio | `fact_llamadas_servicio` | Lookup de 3 dimensiones, medidas calculadas |

`fact_ventas` es donde aparecen juntas las tres operaciones de la diapositiva 19: **joins**, **lookups** (llave de negocio → llave subrogada) y **agregaciones**.

### 6.3 Correrlo — el orden importa

```bash
python datawarehouse/etl/etl_dw_dimensions.py
python datawarehouse/etl/etl_dw_facts.py
```

Primero dimensiones, después hechos: los hechos guardan la llave subrogada de cada dimensión, así que la dimensión tiene que existir antes.

**Deberías ver**, en la rama de dimensiones:

```
ETL de dimensiones - run_id=2, lee Clean Staging del run 1
Las fuentes NO se leen aqui (dia. 15: read once, write many)
[Capa 5] Transformation             (dia. 19: conformar por area)
    Tiempo       dim_tiempo          1096  generacion
    ...
    Empleado     dim_empleado          53  union de fuentes, llave compuesta
[Capa 7] Load
    ...
Dimensiones cargadas: 1394 filas.
```

y en la de hechos:

```
ETL de hechos - run_id=3, lee Clean Staging del run 1
    Ventas    fact_ventas               2996  join (5 tablas), lookup (5 dimensiones), calculo de medidas
    Servicio  fact_llamadas_servicio     108  lookup (3 dimensiones), calculo de medidas
Hechos cargados: 3104 filas.
```

La línea **«lee Clean Staging del run 1»** en las dos ramas es la evidencia del «read once»: ambas consumen la misma extracción.

### 6.4 Ver el recorrido completo

```sql
SELECT * FROM staging_dw.vw_trazabilidad_capas;
```

Muestra, por cada corrida, cuántas filas pasaron por cada capa. Y `datawarehouse/ddl/generar_diagramas.py` dibuja el pipeline completo con esos mismos conteos en `docs/Entrega_2/img/pipeline_capas.png`.

**Si te da un error de llave foránea (`violates foreign key constraint`):** corriste hechos sin dimensiones. Corré primero `etl_dw_dimensions.py`.

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
FROM dm.vw_interaccion_cliente_producto
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
datawarehouse/backup/dw_backup.sql  (546 KB, 8 tablas)
metadata_repository/backup/metadata_repo_backup.sql  (50 KB, 18 tablas)
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
