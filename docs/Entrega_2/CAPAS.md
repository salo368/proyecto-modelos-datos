# Las capas de la solución

Referencia rápida para explicar la arquitectura. Hay **dos sentidos distintos** de la palabra «capa» en este proyecto y conviene no mezclarlos, porque responden a preguntas diferentes.

---

## 1. Capas del ETL — la ruta que recorre un dato

Son las etapas por las que pasa un dato desde la fuente hasta el almacén. Siguen la arquitectura de referencia para integración de datos de **Anthony Giordano** (*Data Integration Blueprint and Modeling*, 2011, Cap. 2), presentada en la **Clase 2** del curso.

Lo que distingue esta implementación: **cada capa es una tabla física persistida**, no un paso en memoria. Se puede consultar el estado exacto del dato en cualquier punto del proceso.

| # | Capa | Tabla | Diapositiva | Qué ocurre |
|---|---|---|---|---|
| 1 | **Extract / Landing** | `staging_dw.stg_extract` | 15, 16 | Copia cruda, 1:1, sin interpretar. Las 11 tablas fuente, leídas una sola vez |
| 2 | **Data Quality** | `staging_dw.stg_dq` | 17, 18 | Evalúa calidad técnica y de negocio. Marca `OK` o `RECHAZADO` |
| 3 | **Transform** | `staging_dw.stg_transform` | 19 | Joins, lookups de llaves subrogadas, agregaciones |
| 4 | **Load-Ready Publish** | `staging_dw.stg_loadready` | — | Forma definitiva. Entre esto y el destino no queda nada por transformar |
| 5 | **Load** | `dim_*`, `fact_*` | — | Escritura al modelo dimensional |

**En una frase:** el dato entra crudo, se valida, se transforma, se deja listo y se publica — y en cada paso queda una copia consultable.

### Qué hace exactamente cada capa

**Extract / Landing.** Lee las once tablas de las dos fuentes y las deposita tal como vinieron, sin decidir nada todavía. El payload va en `JSONB` para que una sola tabla sirva a orígenes con esquemas distintos: el landing debe aceptar el dato como es, no imponerle una forma.

**Data Quality.** La diapositiva 17 separa la calidad en dos clases, y la columna `clase_dq` las distingue:

- **Técnica** — datos faltantes o inválidos, detectables sin conocer el negocio. Por ejemplo, una llave primaria nula.
- **Negocio** — definiciones inconsistentes o datos inexactos, que exigen conocer la semántica. Por ejemplo, un cliente que existe en ventas pero no en servicio.

**Transform.** Las tres operaciones que nombra la diapositiva 19:

- *Joins* — `fact_ventas` cruza cinco tablas del landing.
- *Lookups* — la traducción de llave de negocio a llave subrogada: `customerNumber 103` se convierte en `cliente_key 7`. Es la operación característica de un ETL dimensional.
- *Agregaciones* — medidas calculadas como `monto_linea` y `margen_linea`.

**Load-Ready Publish.** La fila en su forma final. Separarla de Transform permite revisar qué se va a escribir antes de tocar el almacén.

**Load.** Inserción directa en las tablas del modelo dimensional.

---

## 2. Capas de la arquitectura física — dónde vive cada cosa

Son los entornos donde corre la solución, no las etapas del dato.

| Capa | Contenedor | Rol |
|---|---|---|
| **Fuentes** | `mpd-mysql`, `mpd-postgres-cs` | Sistemas de registro. No se modifican |
| **Almacén** | `mpd-postgres-dw`, base `dw` | Staging + modelo dimensional |
| **Repositorio de metadatos** | `mpd-postgres-dw`, base `metadata` | Cataloga todo lo anterior |
| **Presentación** | `mpd-metabase` | Reportes. Solo lee del almacén |

---

## 3. Cómo se relacionan los dos sentidos

Las capas del ETL **viven dentro de** la capa de almacén. El schema `staging_dw` y las tablas `dim_*`/`fact_*` están en la misma base `dw`, pero cumplen roles distintos: **staging es el proceso, el modelo dimensional es el producto**.

```
FUENTES                      ALMACÉN (base dw)                      PRESENTACIÓN
──────────────         ───────────────────────────────            ──────────────

mpd-mysql      ──┐      staging_dw:                                  Metabase
 classicmodels   │        stg_extract                           ┌──►  6 reportes
                 ├──►         │                                 │    (solo lee
mpd-postgres-cs ─┘        stg_dq                                │     el almacén)
 customerservice              │                                 │
                          stg_transform                         │
                              │                                 │
                          stg_loadready                         │
                              │                                 │
                              ▼                                 │
                      public:  dim_*  +  fact_*  ───────────────┘
                              │
                              ▼
        REPOSITORIO DE METADATOS (base metadata, 18 tablas)
        cataloga las fuentes, el almacén, los procesos y el uso
```

---

## 4. Los dos principios que gobiernan el diseño

Si preguntan por qué las capas están así y no de otra forma, estos son los argumentos. Ambos salen de la Clase 2 y **cambian el diseño del proceso**, no son recomendaciones estéticas.

### «Read once, write many» (diapositiva 15)

Cada tabla de las fuentes se lee **una sola vez por carga**, hacia Extract. El ETL de hechos —que necesita `orderdetails`, `orders`, `products`, `customers` y `employees`— **no vuelve a consultar MySQL ni PostgreSQL**: lee la copia que dejó el ETL de dimensiones en el landing.

Por eso la extracción trae también tablas que el proceso de dimensiones no usa: las necesita el de hechos, y leerlas dos veces violaría el principio.

### «Almacenamiento no volátil» (diapositiva 16)

Ninguna tabla de staging se trunca. Cada corrida agrega filas con su `run_id`, de modo que el historial completo queda disponible — **incluidas las corridas que fallaron**, que es precisamente cuando el historial sirve.

---

## 5. La prueba de que las capas existen

```sql
SELECT * FROM staging_dw.vw_trazabilidad_capas;
```

| run_id | proceso | estado | extract | dq | rechazadas | transform | loadready |
|---|---|---|---|---|---|---|---|
| 1 | dimensiones | OK | 3.961 | 3.961 | 0 | 1.394 | 1.394 |
| 2 | hechos | OK | **0** | 0 | 0 | 3.104 | 3.104 |

Los números cuentan la historia del diseño:

- **3.961 en Extract** son las 11 tablas de las dos fuentes, leídas una sola vez.
- **1.394 en Transform** para dimensiones: menos que la entrada, porque de las 11 tablas extraídas solo 6 alimentan dimensiones y varias se consolidan (`products` con `productlines`, `employees` con `cs_employees`).
- **0 en Extract para hechos** es la evidencia directa del «read once»: ese proceso no extrajo nada porque reutilizó el landing de la corrida anterior.
- **3.104 en Transform para hechos**: 2.996 líneas de orden más 108 llamadas.

---

## 6. Sobre los tres destinos de calidad

La diapositiva 18 plantea separar en tres: **datos limpios, por revisar y rechazados**. Este proyecto implementa **dos** (`OK` y `RECHAZADO`), por decisión y no por omisión.

«Por revisar» presupone un **custodio de datos** que valide los casos dudosos antes de cada carga. Este almacén se reconstruye de forma automática y desatendida desde dos snapshots estáticos: no hay nadie en el circuito para atender una cola de revisión, y un estado que nadie revisa se convierte en una capa muerta que solo acumula filas.

Los casos que en un escenario con custodio irían a «por revisar» se resuelven con una regla explícita y quedan trazados en `dq_result`, de modo que la decisión es auditable aunque no haya intervención humana. Si las fuentes pasaran a ser feeds vivos con calidad variable, el tercer estado sí se justificaría.

---

## Dónde está cada cosa en el repositorio

| Qué | Archivo |
|---|---|
| DDL de las capas, con el mapeo a cada diapositiva | `datawarehouse/ddl/02_staging_dw.sql` |
| ETL de dimensiones (extrae y carga las 6 dimensiones) | `datawarehouse/etl/etl_dw_dimensions.py` |
| ETL de hechos (lee del landing, no de las fuentes) | `datawarehouse/etl/etl_dw_facts.py` |
| Vista de trazabilidad | `staging_dw.vw_trazabilidad_capas` |
| Explicación extendida | `docs/Entrega_2/Documento_Entrega_2.md`, sección 2 |
