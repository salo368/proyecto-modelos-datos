# Pipeline

El proceso que lleva los datos de las dos fuentes al almacén, siguiendo la arquitectura de referencia de integración de datos de Giordano (Clase 2). Es el "ETL" del "Mapa general de BI" (Clase 4-5): está entre las fuentes y el DW, **no dentro del DW**.

Por eso está separado del almacén en los dos niveles:

| | Pipeline | Almacén de datos |
|---|---|---|
| Carpeta | `pipeline/` | [`datawarehouse/`](../datawarehouse/README.md) |
| Base de datos | `staging` (schema `staging_dw`) | `dw` (EDW en `public`, data marts en `dm`) |
| Qué guarda | Lo que hizo cada capa en cada corrida, para auditar y retomar una carga | El modelo dimensional que se consulta para analizar el negocio |

Las capas 1 a 6 trabajan solo en `staging`. La capa 7 (Load) es la única que escribe en `dw`. La capa 5 de los hechos lee `dw` solo para resolver las llaves subrogadas de las dimensiones ya cargadas.

![Pipeline y almacén](../docs/img/etl_pipeline.png)

## Una capa, un archivo

Cada capa escribe su propia tabla y lee la de la anterior, no su resultado en memoria. Si una capa falla, las anteriores ya dejaron su trabajo persistido.

| # | Capa | Archivo | Lee | Escribe |
|---|---|---|---|---|
| 1 | Extract/Publish | [`layer1_extract.py`](layer1_extract.py) | Las 13 tablas de las fuentes, una sola vez | Nada: entrega los extractos a la capa 2 |
| 2 | Initial Staging | [`layer2_initial_staging.py`](layer2_initial_staging.py) | Los extractos de la capa 1 | `stg_initial_classicmodels`, `stg_initial_customerservice` (fila original en JSONB) y `stg_perfil` (perfil por columna) |
| 3 | Data Quality | [`layer3_data_quality.py`](layer3_data_quality.py) | `stg_initial_*` | `stg_error_log`: una fila por regla incumplida |
| 4 | Clean Staging | [`layer4_clean_staging.py`](layer4_clean_staging.py) | `stg_initial_*` y `stg_error_log` | `stg_clean` y `stg_rejected`, separados físicamente |
| 5 | Transformation | [`layer5_transform_dimensions.py`](layer5_transform_dimensions.py), [`layer5_transform_facts.py`](layer5_transform_facts.py) | `stg_clean`; los hechos también leen las dimensiones del EDW para resolver llaves | `stg_transform`, por área temática |
| 6 | Load-Ready Publish | [`layer6_load_ready.py`](layer6_load_ready.py) | `stg_transform` | `stg_loadready`, en su forma final |
| 7 | Load | [`layer7_load.py`](layer7_load.py) | `stg_loadready` | `dim_*` (upsert por llave de negocio) o `fact_*` (reemplazo) en el EDW (base `dw`), en una sola transacción |

Cada módulo expone `run(...)` y, si otra capa lo necesita, un lector de su propia tabla: `read_initial`, `read_failures`, `read_clean` y `read_load_ready`.

[`common.py`](common.py) no tiene lógica de ninguna capa. Contiene las conexiones (`STAGING` para las capas, `DW` solo para el Load y los lookups), el control de corridas en `staging_dw.etl_run`, la escritura y lectura genérica de tablas de `staging_dw` y el registro de cada corrida en el repositorio de metadatos (`etl_process`, `etl_execution`, `dq_result`).

[`staging_dw.sql`](staging_dw.sql) crea, en la base `staging`, las tablas de todas las capas y dos vistas de monitoreo: `vw_trazabilidad_capas`, con cuántas filas pasó cada corrida por cada capa, y `vw_reporte_transacciones_malas`, con el contenido legible de `stg_error_log`.

## Tres procesos

Los procesos solo encadenan capas, abren y cierran la corrida y la registran en el repositorio de metadatos. `run_all.py` los ejecuta en este orden:

| Proceso | Capas | Qué hace |
|---|---|---|
| [`run_staging.py`](run_staging.py) | 1 a 4 | Lee las 13 tablas de las fuentes una sola vez, incluidas `payments` y `cs_customer_products`, que el modelo actual no usa. Las perfila, evalúa las 13 reglas de calidad (la última propaga los rechazos a los registros que dependen de ellos) y separa limpios de rechazados |
| [`run_dimensions.py`](run_dimensions.py) | 5 a 7 | Lee `stg_clean` de la última corrida de staging exitosa (no las fuentes), conforma cada área temática y carga las seis dimensiones por llave de negocio, sin cambiar las llaves subrogadas ya asignadas |
| [`run_facts.py`](run_facts.py) | 5 a 7 | Lee la misma corrida de staging, y se niega a arrancar si las dimensiones cargadas vienen de otra. Hace los joins, resuelve las llaves subrogadas contra las dimensiones, calcula las medidas y reemplaza los dos hechos. Si una llave obligatoria queda sin resolver, detiene la carga en vez de escribir un hecho huérfano |

Las tablas de `staging_dw` nunca se truncan: cada corrida agrega sus filas bajo su `run_id`, y `etl_run.run_origen` dice qué corrida de staging leyó cada carga de dimensiones o hechos. Por lo mismo, `staging_dw.sql` es idempotente: `run_all.py` lo vuelve a ejecutar en cada corrida y el historial se conserva. Solo `python run_all.py --reset` lo borra.

## Tolerancia a fallos

| Si falla… | Qué queda intacto | Cómo se retoma |
|---|---|---|
| El staging (capas 1 a 4) | La última corrida de staging exitosa: la fallida queda marcada `ERROR` y nunca se lee. El almacén no se toca | Se vuelve a correr `run_staging.py` y después dimensiones y hechos, en ese orden |
| Las dimensiones (capas 5 a 7) | El staging y el almacén completo de la carga anterior | Se vuelve a correr `run_dimensions.py`; lee el mismo `stg_clean` sin tocar las fuentes |
| Los hechos (capas 5 a 7) | El staging, las dimensiones ya cargadas y los hechos de la carga anterior, cuyas llaves siguen siendo válidas | Se vuelve a correr `run_facts.py` |
| Un paso de `run_all.py` | Lo que dejaron los pasos anteriores | `python run_all.py --etl-only --from-step N`, con el número que indica el mensaje de error |

Tres garantías sostienen esa tabla:

- **Load todo o nada.** La capa 7 escribe todas las tablas de una rama (las seis dimensiones o los dos hechos) en **una sola transacción**. Si algo falla a mitad de camino, PostgreSQL deshace el lote completo, incluido el `TRUNCATE` de los hechos. Sin eso, una falla después de la tercera tabla dejaría unas tablas nuevas y el resto viejas.
- **Llaves subrogadas estables.** Las dimensiones se cargan por *upsert* sobre su llave de negocio: los miembros nuevos se insertan y los existentes se sobrescriben (tipo 1) sin cambiar su `*_key`. Recargar las dimensiones no invalida los hechos ya cargados, así que nunca quedan vacíos entre una rama y la otra. Un miembro que desaparece de la fuente, o que la capa 3 rechaza en una corrida posterior, se conserva con sus últimos atributos, porque hechos anteriores pueden apuntarle. Los hechos, en cambio, se reemplazan completos.
- **Dimensiones y hechos de la misma corrida.** `run_facts.py` se niega a arrancar si las dimensiones cargadas no vienen de la última corrida de staging exitosa, y dice qué correr primero. Sin eso, los hechos de datos nuevos se resolverían contra dimensiones viejas.

Además, un registro rechazado no puede detener la carga de hechos: la regla `padre_rechazado` propaga el rechazo a todo lo que depende de él (un cliente rechazado arrastra sus órdenes, las líneas de esas órdenes, sus pagos y sus llamadas), y `dim_tiempo` cubre los años completos de las fechas de ventas y llamadas en vez de un rango fijo.

Una corrida cuyo proceso muere sin llegar a cerrarla (por ejemplo, con `kill -9`) queda en `EN_CURSO`: nunca se lee, porque los procesos solo leen corridas `OK`, pero tampoco se cierra sola.

Lo comprueban dos pruebas contra el almacén real: [`tests/test_load_atomic.py`](tests/test_load_atomic.py) provoca una falla a mitad de un Load y verifica que el conteo y el contenido (MD5) de cada tabla no cambien, y [`tests/test_resume.py`](tests/test_resume.py) reproduce la retoma de una carga después de una corrida de staging nueva.

## Reglas de calidad de la capa 3

| Regla | Clase | Acción |
|---|---|---|
| `campos_obligatorios` (columnas `NOT NULL` según `db_column` del repositorio de metadatos) | Técnica | Rechazo |
| `tipo_de_dato_valido` (fechas y números interpretables) | Técnica | Rechazo |
| `formato_email` | Técnica | Advertencia |
| `integridad_referencial` (dentro de cada fuente y de las llamadas contra `classicmodels`) | Negocio | Rechazo |
| `valores_positivos` | Negocio | Rechazo |
| `secuencia_de_fechas` | Negocio | Rechazo |
| `envio_consistente_con_estado` | Negocio | Rechazo |
| `fecha_no_futura` (fecha de la orden, del pago o de la llamada posterior a la carga) | Negocio | Rechazo |
| `precio_sugerido_coherente` | Negocio | Advertencia |
| `cliente_con_vendedor` | Negocio | Advertencia |
| `consistencia_entre_fuentes_cliente` / `_producto` | Negocio | Advertencia |
| `padre_rechazado` (se evalúa al final: rechaza, en cascada, los registros que apuntan a uno rechazado) | Negocio | Rechazo |

Con los datos originales, los 4.335 registros quedan en `stg_clean` y `stg_error_log` tiene 22 advertencias de `cliente_con_vendedor`.

## Hallazgos del perfilamiento resueltos en la capa 5

| Hallazgo | Tratamiento | Regla registrada |
|---|---|---|
| `productlines.htmlDescription` e `image` 100 % vacías | No pasan a `dim_producto` | `productline_columnas_vacias` |
| `customers.addressLine2` nula en 100 de 122 filas | Se une con `addressLine1` en `direccion_completa` | `cliente_direccion_linea2_nula` |
| `orders.comments` nula en 246 de 326 órdenes | No pasa al almacén | `orden_comentarios_nulos` |
| `shippedDate` nula en 141 líneas de órdenes no despachadas | `dias_hasta_envio` queda nulo | `orden_fecha_envio_nula` |
| Empleados sin llave común entre fuentes | Llave compuesta en `dim_empleado` | `empleado_conformidad_fuentes` |
| Clientes y productos presentes en ambas fuentes | Dimensiones conformadas | `cliente_conformidad_fuentes`, `producto_conformidad_fuentes` |
| Órdenes canceladas, en disputa o en espera | Se cargan; `es_efectiva` permite excluirlas | `estado_orden_no_efectivo` |

Las cifras de cada capa en la última carga (registros que entran y salen, nulos resueltos y conservados, y sobre qué parte de los datos se apoya cada análisis) están en [`docs/data_quality_report.md`](../docs/data_quality_report.md).

## Pruebas

| Prueba | Qué comprueba |
|---|---|
| [`tests/test_dq_reject_path.py`](tests/test_dq_reject_path.py) | Capas 3 y 4: arma un lote sintético con un defecto por regla y verifica que los bloqueantes se rechacen, que el rechazo se propague a los registros hijos (dos niveles y entre fuentes), que las advertencias pasen y que ningún registro sano se marque |
| [`tests/test_load_atomic.py`](tests/test_load_atomic.py) | Capa 7: provoca una falla a mitad de un Load que combina el upsert de una dimensión y el reemplazo de un hecho, y verifica que el almacén quede exactamente como estaba |
| [`tests/test_resume.py`](tests/test_resume.py) | Retoma: tras una corrida de staging nueva, verifica que los hechos se nieguen a correr antes que las dimensiones, que recargar las dimensiones no cambie sus llaves ni toque los hechos y que al final el almacén quede idéntico |
