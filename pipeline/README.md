# Pipeline

El proceso que lleva los datos de las dos fuentes al almacén, siguiendo la arquitectura de referencia de integración de datos de Giordano (Clase 2). Es el "ETL" del "Mapa general de BI" (Clase 4-5): está entre las fuentes y el DW, **no dentro del DW**.

Por eso está separado del almacén en los dos niveles:

| | Pipeline | Almacén de datos |
|---|---|---|
| Carpeta | `pipeline/` | [`datawarehouse/`](../datawarehouse/README.md) |
| Base de datos | `staging` (schema `staging_dw`) | `dw` (EDW en `public`, data marts en `dm`) |
| Qué guarda | Lo que hizo cada capa en cada corrida, para auditar y retomar una carga | El modelo dimensional que se consulta para analizar el negocio |

Las capas 1 a 6 escriben solo en `staging`. La capa 7 (Load) es la única que escribe en `dw`. Solo dos capas más leen `dw`: la capa 5 de los hechos, para resolver las llaves subrogadas de las dimensiones ya cargadas, y la capa 6, que lee la definición de las tablas destino para verificar que las filas quepan.

![Pipeline y almacén](../docs/img/etl_pipeline.png)

## Una capa, un archivo

Cada capa escribe su propia tabla y lee la de la anterior, no su resultado en memoria. Si una capa falla, las anteriores ya dejaron su trabajo persistido y la corrida se retoma desde la capa que falló (ver [tolerancia a fallos](#tolerancia-a-fallos)).

| # | Capa | Archivo | Lee | Escribe |
|---|---|---|---|---|
| 1 | Extract/Publish | [`layer1_extract.py`](layer1_extract.py) | Las 13 tablas de las fuentes, una sola vez | Nada: entrega los extractos a la capa 2 |
| 2 | Initial Staging | [`layer2_initial_staging.py`](layer2_initial_staging.py) | Los extractos de la capa 1 | `stg_initial_classicmodels`, `stg_initial_customerservice` (fila original en JSONB) y `stg_perfil` (perfil por columna) |
| 3 | Data Quality | [`layer3_data_quality.py`](layer3_data_quality.py) | `stg_initial_*` | `stg_error_log`, una fila por regla incumplida, y `stg_dq_resumen`, cuántos registros revisó y cuántos falló cada regla |
| 4 | Clean Staging | [`layer4_clean_staging.py`](layer4_clean_staging.py) | `stg_initial_*` y `stg_error_log` | `stg_clean` y `stg_rejected`, separados físicamente |
| 5 | Transformation | [`layer5_transform_dimensions.py`](layer5_transform_dimensions.py), [`layer5_transform_facts.py`](layer5_transform_facts.py) | `stg_clean`; los hechos también leen las dimensiones del EDW para resolver llaves | `stg_transform`, por área temática, y `stg_dq_resumen` |
| 6 | Load-Ready Publish | [`layer6_load_ready.py`](layer6_load_ready.py) | `stg_transform` y la definición de las tablas destino en `dw` | `stg_loadready`, en su forma final y verificada contra el destino |
| 7 | Load | [`layer7_load.py`](layer7_load.py) | `stg_loadready` | `dim_*` (upsert por llave de negocio) o `fact_*` (reemplazo) en el EDW (base `dw`), y la fila de la carga en `dim_lote_carga`, en una sola transacción |

Cada módulo expone `run(...)` y, si otra capa lo necesita, un lector de su propia tabla: `read_initial`, `read_failures`, `read_clean` y `read_load_ready`.

La capa 6 no es una copia: antes de publicar compara cada tabla con su destino en el catálogo de `dw` (`information_schema`) y detiene la rama si una columna no existe en el destino, si falta una columna obligatoria, si hay un nulo en una columna `NOT NULL`, si un texto excede su `VARCHAR` o si un número no cabe en su `NUMERIC`, `SMALLINT` o `INTEGER`. Lista todos los problemas a la vez. Sin esa verificación, cada uno aparecería recién en el Load, como un error de base de datos sobre la primera fila que falla.

[`common.py`](common.py) no tiene lógica de ninguna capa. Contiene las conexiones (`STAGING` para las capas, `DW` solo para el Load, los lookups y la verificación de forma), el bloqueo del pipeline, el control de corridas y de capas, la escritura y lectura genérica de tablas de `staging_dw`, el registro de cada intento en el repositorio de metadatos (`etl_process`, `etl_execution`, `dq_result`) y `run_process`, que ejecuta las capas de un proceso y lo retoma si hace falta.

[`staging_dw.sql`](staging_dw.sql) crea, en la base `staging`, las tablas de todas las capas, las de control (`etl_run` y `etl_run_capa`) y dos vistas de monitoreo: `vw_trazabilidad_capas`, con cuántas filas pasó cada corrida por cada capa, cuántas veces se retomó y si fue depurada, y `vw_reporte_transacciones_malas`, con el contenido legible de `stg_error_log`.

## Tres procesos

Los procesos solo declaran sus capas y cómo resumir la corrida; abrir o retomar la corrida, ejecutar las capas y registrar todo en el repositorio de metadatos lo hace `run_process` en `common.py`. `run_all.py` los ejecuta en este orden:

| Proceso | Capas | Qué hace |
|---|---|---|
| [`run_staging.py`](run_staging.py) | 1 a 4 | Lee las 13 tablas de las fuentes una sola vez, incluidas `payments` y `cs_customer_products`, que el modelo actual no usa. Las perfila, evalúa las 17 reglas de calidad (las dos últimas propagan los rechazos a los registros que dependen de ellos y avisan de las órdenes que quedan incompletas) y separa limpios de rechazados |
| [`run_dimensions.py`](run_dimensions.py) | 5 a 7 | Lee `stg_clean` de la última corrida de staging exitosa (no las fuentes), conforma cada área temática y carga las seis dimensiones por llave de negocio, sin cambiar las llaves subrogadas ya asignadas |
| [`run_facts.py`](run_facts.py) | 5 a 7 | Lee la misma corrida de staging, y se niega a arrancar si las dimensiones del almacén vienen de otra. Hace los joins, resuelve las llaves subrogadas contra las dimensiones, calcula las medidas y reemplaza los dos hechos. Si una llave obligatoria queda sin resolver, detiene la carga en vez de escribir un hecho huérfano |

Los tres aceptan `--resume` (ver abajo). Las cargas no borran nada de `staging_dw`: cada corrida agrega sus filas bajo su `run_id`, y `etl_run.run_origen` dice qué corrida de staging leyó cada carga de dimensiones o hechos. Por lo mismo, `staging_dw.sql` es idempotente: `run_all.py` lo vuelve a ejecutar en cada corrida y el historial se conserva. Solo [la retención](#retención-del-staging) o `python run_all.py --reset` lo reducen.

## Tolerancia a fallos

### Retomar una corrida desde la capa que falló

Cada capa deja un punto de control en `staging_dw.etl_run_capa` al terminar. Si una corrida falla, se retoma con `--resume`:

```bash
python pipeline/run_staging.py --resume
python pipeline/run_dimensions.py --resume
python pipeline/run_facts.py --resume
```

- La corrida **conserva su `run_id`**, vuelve a `EN_CURSO` y suma uno a `reintentos`.
- Las capas que terminaron se **saltan**: si el staging falló en la capa 4, no se vuelve a leer las fuentes.
- La capa que falló empieza **desde cero**: antes de ejecutarla se borran las filas que alcanzó a escribir para esa corrida, así que un fallo a mitad de capa no deja filas duplicadas ni a medias.
- La capa 1 guarda los extractos en memoria, así que se registra y se repite junto con la capa 2.
- Solo se retoma la **última** corrida del proceso, y solo si falló. Si no hay nada que retomar, `--resume` abre una corrida nueva.
- Una corrida de dimensiones o hechos solo se retoma si leyó la misma corrida de staging que leería ahora. Si entretanto terminó una corrida de staging más nueva, se abre una corrida nueva.

`run_all.py` hace lo mismo: si un paso del pipeline falla, `python run_all.py --etl-only --from-step N` retoma la corrida fallida desde la capa donde se detuvo.

### Un proceso a la vez, y corridas huérfanas

Los tres procesos (y la retención) toman el mismo bloqueo, un *advisory lock* de PostgreSQL en la base `staging`. Si otro proceso lo tiene, el nuevo no arranca y lo dice. PostgreSQL libera el bloqueo cuando se cierra la conexión, así que un proceso que muere nunca lo deja tomado.

Con el bloqueo tomado ningún otro proceso puede estar corriendo, así que una corrida que sigue `EN_CURSO` quedó abandonada, por ejemplo por un `kill -9`. El siguiente proceso que arranca la cierra como `ERROR`, junto con su capa y su intento en el repositorio de metadatos, y desde ahí se puede retomar como cualquier corrida fallida.

### Qué queda intacto

| Si falla… | Qué queda intacto | Cómo se retoma |
|---|---|---|
| El staging (capas 1 a 4) | La última corrida de staging exitosa: la fallida queda en `ERROR` y ningún proceso la lee. El almacén no se toca | `run_staging.py --resume`, y después dimensiones y hechos |
| Las dimensiones (capas 5 a 7) | El staging y el almacén completo de la carga anterior | `run_dimensions.py --resume`; lee el mismo `stg_clean` sin tocar las fuentes |
| Los hechos (capas 5 a 7) | El staging, las dimensiones ya cargadas y los hechos de la carga anterior, cuyas llaves siguen siendo válidas | `run_facts.py --resume` |
| Un paso de `run_all.py` | Lo que dejaron los pasos anteriores | `python run_all.py --etl-only --from-step N`, con el número que indica el mensaje de error |

Cuatro garantías sostienen esa tabla:

- **Load todo o nada.** La capa 7 escribe todas las tablas de una rama (las seis dimensiones o los dos hechos) y la fila de la carga en `dim_lote_carga` en **una sola transacción**. Si algo falla a mitad de camino, PostgreSQL deshace el lote completo, incluido el `TRUNCATE` de los hechos. Sin eso, una falla después de la tercera tabla dejaría unas tablas nuevas y el resto viejas.
- **Llaves subrogadas estables.** Las dimensiones se cargan por *upsert* sobre su llave de negocio: los miembros nuevos se insertan y los existentes se sobrescriben (tipo 1) sin cambiar su `*_key`. Recargar las dimensiones no invalida los hechos ya cargados, así que nunca quedan vacíos entre una rama y la otra. Un miembro que desaparece de la fuente, o que la capa 3 rechaza en una corrida posterior, se conserva con sus últimos atributos, porque hechos anteriores pueden apuntarle. Los hechos, en cambio, se reemplazan completos. Por eso el Load es idempotente: repetirlo al retomar deja el mismo resultado.
- **Dimensiones y hechos de la misma corrida.** `run_facts.py` se niega a arrancar si las dimensiones del almacén no vienen de la última corrida de staging exitosa, y dice qué correr primero. Lo pregunta al **almacén** (`dim_lote_carga`), no al historial de corridas: si el almacén se reconstruye vacío o se restaura desde un backup, el control ve lo que realmente tiene.
- **Capas idempotentes por corrida.** Cada capa borra lo que había escrito para su corrida antes de empezar, así que repetirla al retomar no duplica filas.

Además, un registro rechazado no puede detener la carga de hechos, y `dim_tiempo` cubre los años completos de las fechas de ventas y llamadas en vez de un rango fijo. Lo que pasa con los registros que dependen de uno rechazado depende de la referencia:

| Referencia | Si el padre se rechaza | Ejemplo |
|---|---|---|
| Obligatoria | `padre_rechazado` rechaza al hijo, en cascada, hasta el último nivel | Un cliente rechazado arrastra sus órdenes, las líneas de esas órdenes, sus pagos y sus llamadas |
| Opcional: el vendedor del cliente y el jefe del empleado | `referencia_opcional_no_resuelta` solo advierte; el hijo sigue | Si se rechaza un vendedor, sus clientes y sus ventas se cargan, y las ventas apuntan al miembro especial `-1 Desconocido` de `dim_empleado` y `dim_oficina` |

El rechazo baja de la orden a sus líneas, pero no sube: si se rechaza una línea, la orden se carga con las demás. `orden_con_lineas_rechazadas` la marca con una advertencia, porque en el almacén su total y su número de líneas quedan por debajo de la fuente.

Una venta cuyo cliente no tiene vendedor apunta a `-2 Sin asignar`. Así `fact_ventas` no tiene llaves nulas y su monto sigue cuadrando con la fuente (ver [miembros especiales](../datawarehouse/edw/README.md#miembros-especiales)). Si el vendedor rechazado ya estaba en el almacén de una carga anterior, la dimensión lo conserva con sus últimos datos válidos y las ventas apuntan a él.

Lo comprueban tres pruebas contra el almacén real (ver [Pruebas](#pruebas)).

## Retención del staging

[`purge_staging.py`](purge_staging.py) limita el crecimiento del staging. `run_all.py` lo ejecuta con `--keep 3`, y conserva completas:

- las últimas N corridas de cada proceso, entre ellas la última, que se puede retomar si falló;
- la última corrida exitosa de cada proceso;
- las cargas que el almacén tiene hoy y las corridas de staging que leyeron (según `dim_lote_carga`);
- las corridas de staging que leyó cualquier carga conservada.

A las demás les borra las filas de las tablas voluminosas (`stg_initial_*`, `stg_clean`, `stg_transform`, `stg_loadready`) y las marca con `depurado_en`; ya no se pueden retomar. Conserva su control de corrida y de capas, el perfil, el reporte de transacciones malas, los rechazados y el resumen de calidad, que son la pista de auditoría y ocupan poco. Toma el mismo bloqueo que los procesos, así que nunca depura bajo un proceso en marcha.

## Reglas de calidad de la capa 3

| Regla | Clase | Acción |
|---|---|---|
| `campos_obligatorios` (columnas `NOT NULL` según `db_column` del repositorio de metadatos) | Técnica | Rechazo |
| `tipo_de_dato_valido` (fechas y números interpretables) | Técnica | Rechazo |
| `formato_email` | Técnica | Advertencia |
| `registro_duplicado` (copia exacta de otro registro con la misma llave: la primera sigue, las copias se rechazan) | Técnica | Rechazo |
| `llave_duplicada` (misma llave con contenido distinto: se rechazan todas las versiones, y sus hijos las siguen) | Técnica | Rechazo |
| `integridad_referencial` (referencias obligatorias, dentro de cada fuente y de las llamadas contra `classicmodels`) | Negocio | Rechazo |
| `valores_positivos` | Negocio | Rechazo |
| `secuencia_de_fechas` | Negocio | Rechazo |
| `envio_consistente_con_estado` | Negocio | Rechazo |
| `fecha_no_futura` (fecha de la orden, del pago o de la llamada posterior a la carga) | Negocio | Rechazo |
| `precio_sugerido_coherente` | Negocio | Advertencia |
| `cliente_con_vendedor` | Negocio | Advertencia |
| `consistencia_entre_fuentes_cliente` / `_producto` | Negocio | Advertencia |
| `referencia_opcional_no_resuelta` (vendedor del cliente o jefe del empleado inexistente o rechazado) | Negocio | Advertencia |
| `padre_rechazado` (se evalúa al final: rechaza, en cascada, los registros que apuntan a uno rechazado) | Negocio | Rechazo |
| `orden_con_lineas_rechazadas` (se evalúa después de `padre_rechazado`: la orden sigue, pero llega incompleta) | Negocio | Advertencia |

La llave de cada tabla es su llave primaria en la fuente. `cs_customer_calls` no tiene llave primaria, así que se usa la combinación de cliente, producto, agente y fecha y hora de la llamada.

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
| Clientes sin vendedor (`salesRepEmployeeNumber` nula en 22 de 122) | Sus ventas apuntan al miembro `-2 Sin asignar`, no a una llave nula | `venta_vendedor_no_resuelto` |

Las cifras de cada capa en la última carga (registros que entran y salen, nulos resueltos y conservados, y sobre qué parte de los datos se apoya cada análisis) están en [`docs/data_quality_report.md`](../docs/data_quality_report.md).

Los montos pasan por `float` en pandas y por JSON en el staging antes de llegar a `NUMERIC` en el almacén. No pierden precisión: `priceEach` tiene dos decimales y `quantityOrdered` es entero, así que cada producto tiene como mucho dos decimales y el redondeo a dos decimales recupera el valor exacto. La conciliación con las fuentes lo comprueba al centavo en cada carga.

## Pruebas

| Prueba | Qué comprueba |
|---|---|
| [`tests/test_dq_reject_path.py`](tests/test_dq_reject_path.py) | Capas 3 y 4: arma un lote sintético con un defecto por regla y verifica que los bloqueantes se rechacen, que el rechazo se propague por las referencias obligatorias (dos niveles y entre fuentes) y no por las opcionales, que una copia exacta se rechace dejando pasar la primera, que dos versiones de una llave se rechacen con sus hijos, que una orden con líneas rechazadas reciba la advertencia, que las advertencias pasen y que ningún registro sano se marque |
| [`tests/test_load_ready_shape.py`](tests/test_load_ready_shape.py) | Capa 6: filas copiadas del almacén pasan, y se detectan una columna inexistente, una obligatoria ausente, un nulo en `NOT NULL`, un texto demasiado largo y números fuera de `NUMERIC`, `SMALLINT` e `INTEGER`; un lote con dos problemas se detiene y los lista a ambos |
| [`tests/test_load_atomic.py`](tests/test_load_atomic.py) | Capa 7: provoca una falla a mitad de un Load que combina el upsert de una dimensión, el reemplazo de un hecho y el registro de la carga, y verifica que el almacén, `dim_lote_carga` incluida, quede exactamente como estaba |
| [`tests/test_resume.py`](tests/test_resume.py) | Retoma entre procesos: tras una corrida de staging nueva, verifica que los hechos se nieguen a correr antes que las dimensiones, que recargar las dimensiones no cambie sus llaves ni toque los hechos y que al final el almacén quede idéntico |
| [`tests/test_resume_layers.py`](tests/test_resume_layers.py) | Retoma por capa: con el bloqueo tomado, un proceso no arranca; un staging que falla después de la capa 3 se retoma en la misma corrida desde la 4, sin releer las fuentes y sin las filas que la capa 4 dejó a medias; unas dimensiones matadas después de la capa 6 quedan `EN_CURSO`, se cierran como abandonadas y se retoman en la capa 7; los metadatos guardan cada intento con su duración real y los resultados de las reglas; y el almacén termina idéntico |

`test_resume_layers.py` provoca las fallas con `PIPELINE_FAULT` (`error@N` lanza un error después de la capa N; `kill@N` termina el proceso ahí, como un `kill -9`). Es un gancho solo para pruebas: sin esa variable, los procesos no lo usan.
