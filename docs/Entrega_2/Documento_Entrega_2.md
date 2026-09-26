# Documento de Entrega 2 — Proyecto Final

**Pontificia Universidad Javeriana — Modelos y Persistencia de Datos — 2026-01**

Elaborado por: Luis Daniel Sierra Pineda, David Cortes, Salomón Saenz

---

## Resumen ejecutivo

Esta entrega construye una solución de Inteligencia de Negocios sobre las dos fuentes del proyecto: `classicmodels` (MySQL, ventas) y `customerservice` (PostgreSQL, centro de atención al cliente). El resultado es un almacén de datos dimensional que permite analizar ventas y servicio de forma conjunta, algo que ninguna de las dos fuentes hace por sí sola.

El documento sigue las cinco secciones de la rúbrica:

| Sección | Peso | Artefactos que la respaldan |
|---|---|---|
| 1. Diseño físico del almacén y la base dimensional | 25 % | `datawarehouse/ddl/01_dw_schema.sql`, `docs/Entrega_2/img/dw_modelo_dimensional.png` |
| 2. Desarrollo de la solución | 25 % | `datawarehouse/`, `datawarehouse/queries/validacion.py` |
| 3. Diseño de metadatos | 15 % | `metadata_repository/ddl/metadata_dw_extension.sql`, `docs/Entrega_2/img/repositorio_metadatos.png` |
| 4. Diseño de ETLs | 15 % | `datawarehouse/etl/etl_dw_dimensions.py`, `etl_dw_facts.py` |
| 5. Diseño de reportes | 20 % | `reports/construir_dashboard.py`, capturas en `docs/Entrega_2/img/` |

---

## 1. Diseño físico del almacén y la base dimensional (25 %)

### 1.1 El hecho diseñado y por qué

El enunciado pide diseñar un hecho relevante para la toma de decisiones. El hecho principal es **`fact_ventas`**, al grano de **una línea de una orden de compra**. Es el grano más fino disponible en la fuente transaccional y, por lo tanto, el que permite el mayor número de análisis sin perder detalle.

Junto a él se modeló **`fact_llamadas_servicio`**, al grano de **una llamada al centro de servicio**. No se fusionaron en una sola tabla porque tienen granos distintos: una venta no es una llamada, y mezclarlas produciría medidas sin sentido.

Lo que los une son las **dimensiones conformadas**. Esta es la razón de fondo del diseño: el perfilamiento de la Entrega 1 midió que `customers`/`cs_customers` y `products`/`cs_products` solapan al **100 %** en su llave de negocio. Al compartir `dim_cliente`, `dim_producto` y `dim_tiempo`, los dos hechos se pueden consultar en una misma pregunta. Esta configuración —varios hechos que comparten dimensiones— se conoce como **constelación de hechos**.

La pregunta de negocio que motiva el diseño es:

> **¿Qué productos generan más llamadas de servicio por unidad vendida?**

Un valor alto señala productos que producen fricción de postventa desproporcionada frente a lo que facturan: candidatos a revisión de calidad, de documentación o de descripción en el catálogo. Responderla exige cruzar las dos fuentes, y solo el almacén lo permite.

### 1.2 Diagrama físico

![Modelo dimensional del almacén](img/dw_modelo_dimensional.png)

El diagrama se generó con Graphviz a partir del esquema real de la base, no de un dibujo hecho a mano, mediante `datawarehouse/ddl/generar_diagramas.py`. Las tablas rosadas son hechos; las verdes, dimensiones conformadas; las grises, dimensiones exclusivas de una fuente.

### 1.3 Las tablas y su significado

#### Hechos

**`fact_ventas`** — 2.996 filas. Grano: una línea de orden.

| Medida | Fórmula | Aditividad | Significado |
|---|---|---|---|
| `cantidad_ordenada` | `orderdetails.quantityOrdered` | Aditiva | Unidades pedidas en la línea |
| `precio_unitario` | `orderdetails.priceEach` | No aditiva | Precio pactado por unidad; se promedia ponderado, no se suma |
| `monto_linea` | `quantityOrdered * priceEach` | Aditiva | Valor facturado. Es la medida central del almacén |
| `costo_linea` | `quantityOrdered * products.buyPrice` | Aditiva | Costo de adquisición de lo vendido |
| `margen_linea` | `monto_linea - costo_linea` | Aditiva | Utilidad bruta |
| `precio_msrp` | `products.MSRP` | No aditiva | Precio sugerido; permite medir el descuento aplicado |
| `dias_hasta_envio` | `shippedDate - orderDate` | Semi-aditiva | Días entre pedido y despacho. Se promedia; nulo si no se despachó |

Dimensiones degeneradas: `numero_orden` y `numero_linea`. Son identificadores del sistema origen que no justifican una tabla propia, así que viven dentro del hecho.

**`fact_llamadas_servicio`** — 108 filas. Grano: una llamada.

| Medida | Fórmula | Aditividad | Significado |
|---|---|---|---|
| `cantidad_llamadas` | Constante 1 | Aditiva | Contador; permite sumar llamadas en cualquier dimensión |
| `longitud_texto` | `length(cs_customer_calls.text)` | Aditiva | Longitud de la nota del agente, como proxy de complejidad del caso |

Dimensión degenerada: `texto_llamada`.

#### Dimensiones

| Dimensión | Filas | Conformada | Qué representa |
|---|---|---|---|
| `dim_tiempo` | 1.096 | Sí | Un día entre 2003-01-01 y 2005-12-31. Generada, no extraída |
| `dim_cliente` | 122 | Sí | Cliente integrado de las dos fuentes, con banderas de presencia en cada una |
| `dim_producto` | 110 | Sí | Producto integrado, con la línea de producto desnormalizada |
| `dim_empleado` | 53 | No | Vendedores y agentes, separados por `sistema_origen` |
| `dim_oficina` | 7 | No | Sede del representante de ventas. Solo existe en classicmodels |
| `dim_estado_orden` | 6 | No | Estado de la orden; `es_efectiva` distingue la venta cerrada |

### 1.4 Qué elementos de las fuentes nutren el hecho

| Elemento del almacén | Fuente | Tablas que lo alimentan |
|---|---|---|
| `fact_ventas` | classicmodels (MySQL) | `orderdetails` ⋈ `orders` ⋈ `products` ⋈ `customers` ⋈ `employees` |
| `fact_llamadas_servicio` | customerservice (PostgreSQL) | `cs_customer_calls` |
| `dim_cliente` | **Ambas** | `customers` (autoritativa) + `cs_customers` (bandera de presencia) |
| `dim_producto` | **Ambas** | `products` ⋈ `productlines` + `cs_products` (bandera de presencia) |
| `dim_empleado` | **Ambas** | `employees` ∪ `cs_employees`, discriminados por `sistema_origen` |
| `dim_oficina` | classicmodels | `offices` |
| `dim_estado_orden` | classicmodels | Valores distintos de `orders.status` |
| `dim_tiempo` | Ninguna | Generada por código |

### 1.5 Dos decisiones de diseño que vale la pena justificar

**Llaves subrogadas.** Cada dimensión tiene dos llaves: la subrogada (`*_key`, un entero que inventa el almacén) y la de negocio (la que viene de la fuente). Los hechos apuntan a la subrogada. La razón es que la llave de negocio puede cambiar, repetirse entre fuentes o ser un texto largo; la subrogada es estable, compacta y rápida en los joins.

**`dim_empleado` con llave compuesta.** Los 23 empleados de classicmodels y los 30 de customerservice **no comparten ni una sola llave**: el solape medido en la Entrega 1 fue del 0 %. Fusionarlos habría exigido inventar equivalencias inexistentes. La solución fue una llave de negocio compuesta `(numero_empleado, sistema_origen)` con llave subrogada encima, de modo que ambas poblaciones conviven sin colisionar. Esto se verifica en el reporte de carga por agente: solo aparecen los 30 agentes de servicio, nunca los vendedores, pese a que comparten rango de numeración.

---

## 2. Desarrollo de la solución (25 %)

### 2.1 Las capas implementadas

La solución sigue la **arquitectura de referencia para integración de datos de Anthony Giordano** (*Data Integration Blueprint and Modeling*, 2011, Cap. 2), que es la que se presentó en la Clase 2 del curso.

El punto que vale la pena subrayar: **cada capa es una tabla física persistida**, no un paso en memoria. Esa es la diferencia entre seguir el patrón y solamente nombrarlo. Se puede consultar el estado exacto del dato en cualquier punto del proceso y comparar corridas entre sí.

> Referencia rápida de la arquitectura por capas, pensada para consulta durante la sustentación: [`CAPAS.md`](CAPAS.md).

| Capa | Tabla física | Diapositiva | Qué ocurre |
|---|---|---|---|
| **Extract / Landing** | `staging_dw.stg_extract` | 15, 16 | Copia 1:1 y sin interpretar de las 11 tablas de las dos fuentes |
| **Data Quality** | `staging_dw.stg_dq` | 17, 18 | Evaluación de calidad, separada en técnica y de negocio |
| **Transform** | `staging_dw.stg_transform` | 19 | Joins, lookups de llaves subrogadas y agregaciones |
| **Load-Ready Publish** | `staging_dw.stg_loadready` | — | Forma definitiva, sin transformaciones pendientes |
| **Load** | `dim_*`, `fact_*` | — | Escritura al modelo dimensional |

Alrededor de esas capas están los tres entornos físicos:

| Entorno | Dónde vive | Rol |
|---|---|---|
| **Fuentes** | `mpd-mysql` y `mpd-postgres-cs` (Docker) | Sistemas de registro. No se modifican |
| **Almacén** | Base `dw` en `mpd-postgres-dw` | Staging + modelo dimensional |
| **Repositorio de metadatos** | Base `metadata`, misma instancia | Cataloga todo lo anterior |
| **Presentación** | Metabase (`mpd-metabase`) | Reportes; conecta solo al almacén |

### 2.2 Los dos principios de Giordano y cómo se cumplen

La Clase 2 enunció dos principios en las diapositivas 15 y 16. No son recomendaciones estéticas: cambian el diseño del proceso.

**«Read once, write many» (diapositiva 15).** Cada tabla de las fuentes se lee **una sola vez por carga**, hacia la capa Extract. El ETL de hechos —que necesita `orderdetails`, `orders`, `products`, `customers` y `employees`— **no vuelve a consultar MySQL ni PostgreSQL**: lee la copia que dejó el ETL de dimensiones en `staging_dw.stg_extract`. Por eso la extracción trae también tablas que el proceso de dimensiones no usa: las necesita el de hechos, y leerlas dos veces violaría el principio.

Esto es verificable: la salida del ETL de hechos declara de qué `run_id` de landing está leyendo, y las 11 tablas aparecen extraídas exactamente una vez por corrida.

**«Almacenamiento no volátil» (diapositiva 16).** Ninguna tabla de staging se trunca. Cada corrida agrega filas con su `run_id`, y el historial completo queda disponible. La vista `staging_dw.vw_trazabilidad_capas` resume cuántas filas pasó cada capa en cada corrida, **incluidas las corridas que fallaron** — que es precisamente cuando el historial sirve.

### 2.3 Sobre los tres destinos de calidad (diapositiva 18)

La diapositiva 18 plantea separar en tres: **datos limpios, datos por revisar y datos rechazados**. Este proyecto implementa **dos** (`OK` y `RECHAZADO`), y es una decisión deliberada, no una omisión.

El estado «por revisar» presupone un **custodio de datos** (*data steward*) que valide los casos dudosos antes de cada carga. Este almacén se reconstruye de forma automática y desatendida desde dos snapshots estáticos: no hay nadie en el circuito para atender una cola de revisión, y un estado que nadie revisa se convierte en una capa muerta que solo acumula filas.

Los casos que en un escenario con custodio irían a «por revisar» —por ejemplo, un cliente que aparece en una fuente y no en la otra— se resuelven aquí con una regla explícita y quedan trazados en `dq_result`, de modo que la decisión es auditable aunque no haya intervención humana. Si las fuentes pasaran a ser feeds vivos con datos de calidad variable, el tercer estado sí se justificaría.

### 2.4 Herramienta y justificación

| Componente | Herramienta | Por qué |
|---|---|---|
| Almacén y repositorio | PostgreSQL 16 en Docker | Dos bases separadas en una misma instancia: separación lógica sin costo de infraestructura adicional |
| ETL | Python 3.11 + SQLAlchemy 2.1 + pandas 3.0 | Mismo stack de la Entrega 1, lo que permite reutilizar el patrón por capas de Giordano en ambas entregas |
| Diagramas | Graphviz en contenedor Docker | Genera el diagrama desde el esquema real de la base, no de un dibujo a mano |
| Reportes | Metabase (open source) sobre Docker | Cero costo, cero instalación, conecta nativo a PostgreSQL |
| Orquestación | `docker-compose` + `run_all.py` | Todo el proyecto se levanta y se carga con un comando, en cualquier máquina |

Se evaluó y se descartó AWS: ningún punto del enunciado exige nube, Redshift no está habilitado en la cuenta disponible y una instancia RDS habría costado entre 12 y 15 dólares mensuales sin aportar nada a la calificación.

### 2.3 Validación de la carga

La solución no se da por buena porque el ETL termine sin error, sino porque los totales del almacén **cuadran con las fuentes**. `datawarehouse/queries/validacion.py` ejecuta nueve comparaciones:

| Prueba | Fuente | Almacén | Estado |
|---|---|---|---|
| Monto total vendido | 9.604.190,61 | 9.604.190,61 | OK |
| Unidades vendidas | 105.516 | 105.516 | OK |
| Líneas de orden | 2.996 | 2.996 | OK |
| Órdenes distintas | 326 | 326 | OK |
| Llamadas de servicio | 108 | 108 | OK |
| Clientes | 122 | 122 | OK |
| Productos | 110 | 110 | OK |
| Oficinas | 7 | 7 | OK |
| Empleados (ambas fuentes) | 53 | 53 | OK |

Adicionalmente se verificó que el **backup restaura de verdad**: se creó una base desechable, se cargó `dw_backup.sql` y se compararon los conteos y el monto total contra el almacén original. Coincidieron en todo.

---

## 3. Diseño de metadatos (15 %)

### 3.1 Las cuatro categorías de metadatos

La Clase 3 define **cuatro** categorías de metadatos, y el repositorio las cubre todas:

| Categoría (Clase 3) | Qué es | Tablas que la implementan |
|---|---|---|
| **Negocio** | Capa semántica: glosario, términos de negocio | `business_entity`, `business_attribute` |
| **Técnicos** | Catálogos de la base: tablas, columnas, tipos | `data_source`, `db_table`, `db_column`, `dw_object`, `dw_measure`, `dw_attribute` |
| **Procesos** | Acciones que toman los programas; transformaciones | `etl_process`, `etl_execution`, `dw_lineage` |
| **Uso** | Patrones y frecuencia de acceso; con qué herramientas; queries vs tablas; joins | `usage_herramienta`, `usage_consulta`, `usage_consulta_objeto`, `usage_acceso_objeto` |

La Entrega 1 cubrió Negocio y Técnicos. La Entrega 2 agrega Procesos y Uso, más la extensión de Técnicos hacia el almacén. El repositorio pasó de 6 a **18 tablas**.

La categoría de **Uso** tiene una particularidad que vale la pena destacar: a diferencia de las otras tres, el uso no se declara, **se mide**. `usage_acceso_objeto` se puebla leyendo `pg_stat_user_tables` del almacén, que son los contadores que lleva el propio motor de PostgreSQL. No es una estimación ni una lista escrita a mano: es lo que efectivamente ocurrió. Un valor alto de `lecturas_secuenciales` frente a `lecturas_por_indice` es la señal clásica de un índice faltante.

### 3.2 Dimensiones lentamente cambiantes

La Clase 4-5 dedica una diapositiva al tema, así que la decisión quedó registrada como metadato en `dw_object.scd_type` y `dw_object.scd_justificacion`, no solo narrada aquí.

**Las seis dimensiones son Tipo 1** (sobrescritura, sin historial). La razón está en el origen: las dos fuentes se restauran desde dumps estáticos, no son feeds incrementales. No hay captura de cambios ni columnas temporales en el origen, de modo que no existe historia que preservar — un Tipo 2 generaría versiones vacías.

Si las fuentes pasaran a ser feeds vivos, `dim_cliente` y `dim_producto` serían las candidatas naturales a Tipo 2: el límite de crédito, la dirección y el precio de compra cambian con el tiempo, y un análisis histórico correcto debería usar el valor vigente en el momento de cada venta, no el actual.

### 3.3 Diagrama físico del repositorio completo

![Repositorio de metadatos con las catorce tablas](img/repositorio_metadatos.png)

Lo importante del diagrama está en el centro: **`db_column`**, la tabla de la Entrega 1 que cataloga las 85 columnas de las fuentes, se conecta a `dw_lineage` y a `dq_rule`. Gracias a eso el linaje ya no se corta en la frontera de las fuentes, sino que llega hasta el almacén.

### 3.4 Linaje de punta a punta: las dos direcciones

La Clase 3 distingue **dos recorridos sobre el mismo grafo**, y son preguntas de negocio distintas hechas por personas distintas. Ambas están implementadas en `metadata_repository/queries/linaje_e_impacto.sql`.

**Linaje de Datos** (destino → orígenes) responde *«¿de dónde viene este dato que me muestra un reporte?»*. Lo usa quien duda de una cifra. Encadenando `column_business_mapping` de la Entrega 1 con `dw_lineage` de la Entrega 2:

| Fuente | Columna de origen | Objeto del almacén | Destino | Entidad de negocio | Regla |
|---|---|---|---|---|---|
| classicmodels | `customers.customerNumber` | `dim_cliente` | `numero_cliente` | Cliente | Llave de negocio, copia directa |
| classicmodels | `customers.addressLine1` | `dim_cliente` | `direccion_completa` | Cliente | Concatenación con `addressLine2` |
| customerservice | `cs_customers.customernumber` | `dim_cliente` | `presente_en_servicio` | Cliente | Bandera de presencia |
| classicmodels | `orderdetails.quantityOrdered` | `fact_ventas` | `cantidad_ordenada` | Orden de Compra | Copia directa |
| classicmodels | `products.buyPrice` | `fact_ventas` | `costo_linea` | Producto | Cálculo |

**Análisis de Impacto** (origen → destino) responde *«si modifico esta tabla, ¿qué procesos se afectan?»*. Lo usa quien va a cambiar una fuente, antes de tocarla. La consulta cruza el linaje con los metadatos de uso, de modo que el resultado no se queda en «afecta a `dim_cliente`» sino que llega hasta «y por lo tanto rompe estos tres reportes que corren a diario».

Esa segunda dirección solo es posible porque existe la categoría de metadatos de Uso: sin `usage_consulta_objeto`, el análisis de impacto se detendría en la frontera del almacén y no podría decir qué reportes se caen.

### 3.5 Contenido actual del catálogo

| Categoría | Tabla | Filas | Contenido |
|---|---|---|---|
| Negocio | `business_entity` | 8 | Entidades con dominio y descripción |
| Negocio | `business_attribute` | 47 | Atributos de negocio |
| Negocio | `column_business_mapping` | 78 | Linaje semántico de la Entrega 1 |
| Técnico | `data_source` | 2 | Las dos fuentes |
| Técnico | `db_table` / `db_column` | 13 / 85 | Catálogo de las fuentes |
| Técnico | `dw_object` | 9 | 2 hechos, 6 dimensiones, 1 vista, con su tipo de SCD |
| Técnico | `dw_measure` | 9 | Medidas con aditividad y fórmula |
| Técnico | `dw_attribute` | 68 | Atributos con su rol |
| Proceso | `dw_lineage` | 48 | Vínculos fuente → almacén |
| Proceso | `etl_process` / `etl_execution` | 2 / 2 | Procesos y bitácora de corridas |
| Proceso | `dq_rule` / `dq_result` | 9 / 7 | Reglas de calidad y su evaluación |
| **Uso** | `usage_herramienta` | 3 | Metabase, ETL, scripts de validación |
| **Uso** | `usage_consulta` | 8 | Consultas con frecuencia y número de joins |
| **Uso** | `usage_consulta_objeto` | 25 | Qué consulta toca qué objeto |
| **Uso** | `usage_acceso_objeto` | 8 | Acceso real medido por el motor |

El catálogo se puebla automáticamente: `etl_dw_metadata.py` introspecciona el esquema real del almacén y `etl_uso_metadata.py` mide el acceso. Solo el linaje y el glosario de negocio se declaran a mano, porque son conocimiento que no se puede deducir de un esquema.

### 3.6 Un hallazgo de los metadatos de uso

La primera medición ya arrojó algo accionable, que es el objetivo de esta categoría:

| Objeto | Lecturas secuenciales | Lecturas por índice |
|---|---|---|
| `dim_cliente` | 3.113 | 0 |
| `dim_empleado` | 3.111 | 0 |
| `dim_producto` | 9 | 3.104 |
| `dim_tiempo` | 9 | 3.104 |

`dim_cliente` y `dim_empleado` se recorren completas miles de veces sin usar índice, mientras que `dim_producto` y `dim_tiempo`, con carga comparable, sí lo usan. Es la señal que la Clase 3 describe como propósito del monitoreo de uso. La causa probable está en cómo el planificador resuelve la validación de llaves foráneas y los *lookups* de estas dos dimensiones en particular; queda como línea de optimización documentada, respaldada por una medición y no por una intuición.

---

## 4. Diseño de ETLs (15 %)

### 4.1 Arquitectura del proceso

Se construyeron dos procesos que implementan la arquitectura de Giordano con **tablas físicas persistidas**, no con pasos en memoria:

| Proceso | Archivo | Qué carga |
|---|---|---|
| `etl_dw_dimensions` | `datawarehouse/etl/etl_dw_dimensions.py` | Extrae las 11 tablas fuente y carga las seis dimensiones |
| `etl_dw_facts` | `datawarehouse/etl/etl_dw_facts.py` | Carga los dos hechos y la vista integrada, leyendo del landing |

**El orden no es negociable** por dos razones distintas. La primera es de integridad: los hechos apuntan a las dimensiones por llave foránea, así que las dimensiones tienen que existir antes. La segunda es arquitectónica: el ETL de hechos **no lee las fuentes**, lee el landing que dejó el de dimensiones, cumpliendo el «read once, write many».

### 4.2 Recorrido de una fila por las capas

La tabla siguiente es la salida real de `staging_dw.vw_trazabilidad_capas` tras una carga limpia:

| Corrida | Proceso | Estado | Extract | Data Quality | Transform | Load-Ready |
|---|---|---|---|---|---|---|
| 1 | dimensiones | OK | 3.961 | 3.961 | 1.394 | 1.394 |
| 2 | hechos | OK | 0 | 0 | 3.104 | 3.104 |

Los números cuentan la historia del diseño:

- **3.961 filas en Extract** son las 11 tablas de las dos fuentes, leídas una sola vez.
- **1.394 en Transform** para dimensiones: menos que la entrada, porque de las 11 tablas extraídas solo 6 alimentan dimensiones y varias se consolidan (`products` con `productlines`, `employees` con `cs_employees`).
- **0 en Extract para hechos**: la evidencia directa de que ese proceso no volvió a tocar las fuentes.
- **3.104 en Transform para hechos**: 2.996 líneas de orden más 108 llamadas.

### 4.3 La capa Transform: joins, lookups y agregaciones

La diapositiva 19 de la Clase 2 nombra las tres operaciones de esta capa, y las tres ocurren aquí:

**Joins.** `fact_ventas` cruza cinco tablas del landing (`orderdetails`, `orders`, `products`, `customers`, `employees`) para reunir las medidas y las llaves de negocio en una sola fila.

**Lookups.** Es la operación característica de un ETL dimensional: el hecho no guarda `customerNumber = 103`, guarda `cliente_key = 7`, que es la fila que le tocó a ese cliente en `dim_cliente`. En esta implementación el lookup deja rastro: el resultado queda en `stg_transform` con la anotación de qué operaciones se aplicaron, en vez de vivir y desaparecer en un diccionario de Python.

El caso de `dim_empleado` muestra por qué el lookup importa: su llave es compuesta `(numero_empleado, sistema_origen)`, de modo que el número 26 de `classicmodels` y el 26 de `customerservice` resuelven a llaves subrogadas distintas, que es lo correcto porque son dos personas diferentes.

**Agregaciones.** Las medidas calculadas (`monto_linea`, `costo_linea`, `margen_linea`, `dias_hasta_envio`) y la derivación de `dim_estado_orden` a partir de los valores distintos de `orders.status`.

Si alguna llave obligatoria queda sin resolver, el proceso **falla en vez de cargar datos huérfanos**. Es una decisión deliberada: un hecho que apunta a una dimensión inexistente corrompe todos los reportes que lo agreguen.

### 4.4 Registro en el repositorio de metadatos

Cada corrida se registra en dos lugares complementarios:

- `staging_dw.etl_run` — control interno del proceso, con el detalle por capa.
- `etl_execution` en el repositorio de metadatos — la vista de gobierno, con proceso, herramienta, filas leídas, escritas y rechazadas.

Además, cada regla de calidad evaluada deja su resultado en `dq_result`, ligado a la ejecución concreta que la evaluó.

### 4.5 Los problemas de calidad de la Entrega 1, resueltos

El enunciado pide explícitamente resolverlos. Cada uno se trató en la capa Transform y quedó registrado como regla evaluada:

| Hallazgo | Evaluadas | Afectadas | Tratamiento en el ETL |
|---|---|---|---|
| `productlines.htmlDescription` e `image` 100 % nulas | 2 | 2 | Excluidas del almacén; solo se trae `textDescription` |
| Empleados sin llave común entre fuentes | 53 | 0 | Llave compuesta `(numero_empleado, sistema_origen)` |
| `customers.addressLine2` 81,97 % nula | 122 | 100 | Consolidada con `addressLine1` en `direccion_completa` |
| `orders.comments` 75,46 % nula | — | — | Texto libre sin valor analítico: no entra al hecho |
| `orders.shippedDate` nula sin despacho | 2.996 | 141 | `dias_hasta_envio` queda nulo; `dim_estado_orden` explica el motivo |
| Nombres en minúscula en PostgreSQL frente a camelCase en MySQL | 85 | 85 | Normalización de nombres en la capa Transform |
| Órdenes canceladas mezcladas con despachadas | 6 | 3 | Se cargan todas; `es_efectiva` permite excluirlas del reporte |

La columna «afectadas» sale de `dq_result`, no de una estimación: es lo que midió el ETL al correr.

### 4.6 Clasificación de las reglas según los dos marcos del curso

Cada regla se clasifica en dos ejes distintos, porque responden preguntas distintas y ambos se enseñaron:

**Criterios de calidad de la Clase 1** (*The Art of Enterprise Information Architecture*):

| Criterio | Reglas | Cuáles |
|---|---|---|
| Exhaustividad | 3 | Columnas vacías, `addressLine2`, `shippedDate` |
| Consistencia | 3 | Las tres reglas de conformidad entre fuentes |
| Exactitud | 1 | Estados de orden que no cuentan como venta cerrada |
| Relevancia | 1 | `orders.comments`: presente pero sin valor analítico |
| Oportunidad | 1 | Frescura de la última carga exitosa |
| Confianza | — | No se mide directamente |

**Confianza** no tiene regla propia a propósito. La Clase 1 la define como la *combinación* de los otros cinco criterios más metadatos y gobierno, no como algo medible por separado: es el resultado agregado de que las demás pasen.

**Oportunidad** sí se cerró con una regla nueva (`almacen_frescura_de_carga`), que compara el momento actual contra la última carga exitosa registrada en `etl_execution`. Si superan las 24 horas, los reportes están mostrando datos vencidos.

**Clases de calidad según Giordano** (Clase 2, diapositiva 17):

| Clase | Reglas | Naturaleza |
|---|---|---|
| Técnica | 4 | Datos faltantes o inválidos; los detecta la máquina sin conocer el negocio |
| Negocio | 5 | Definiciones inconsistentes o datos inexactos; exigen conocer la semántica |

La distinción es operativa, no decorativa: las reglas técnicas se evalúan fila por fila en la capa de Data Quality y pueden rechazar registros; las de negocio se evalúan sobre el conjunto y su resultado alimenta decisiones de modelado, como la llave compuesta de `dim_empleado`.

---

## 5. Diseño de reportes (20 %)

### 5.1 Herramienta

**Metabase** (open source) desplegado en un contenedor Docker con volumen persistente. Se eligió por costo cero, cero instalación y conexión nativa a PostgreSQL.

Los reportes se construyeron mediante la **API REST de Metabase** (`reports/construir_dashboard.py`), de modo que el montaje es reproducible: cualquiera del equipo levanta el contenedor, corre el script y obtiene el mismo dashboard.

### 5.2 Cumplimiento de la restricción del enunciado

> «No se conecte a las fuentes de datos originales, debe conectar a su tabla de hecho del almacén de datos.»

El único origen registrado en Metabase es la base **`dw`**. Ni `classicmodels` ni `customerservice` están configurados como orígenes. Todas las consultas de los reportes leen `fact_ventas`, `fact_llamadas_servicio` o la vista `vw_interaccion_cliente_producto`.

### 5.3 Los reportes

| # | Reporte | Qué muestra | Tablas del almacén |
|---|---|---|---|
| 1 | Ventas y margen por mes | Evolución mensual, solo órdenes efectivas | `fact_ventas` ⋈ `dim_tiempo` ⋈ `dim_estado_orden` |
| 2 | **Intensidad de servicio por producto** | Llamadas por unidad vendida | `vw_interaccion_cliente_producto` |
| 3 | Margen por línea de producto | Monto y margen por familia | `fact_ventas` ⋈ `dim_producto` |
| 4 | Clientes: compras frente a llamadas | Dispersión de cada cliente | `vw_interaccion_cliente_producto` |
| 5 | Ventas por oficina | Monto por sede del representante | `fact_ventas` ⋈ `dim_oficina` |
| 6 | Carga del centro de servicio por agente | Llamadas atendidas por agente | `fact_llamadas_servicio` ⋈ `dim_empleado` |

El **reporte 2 es el central** de la entrega: es el único que cruza las dos fuentes, y solo es posible porque `dim_cliente` y `dim_producto` son conformadas. Los resultados sitúan a *American Airlines: B767-300* a la cabeza, con 0,0078 llamadas por unidad vendida, seguido de *1962 City of Detroit Streetcar* con 0,0062.

El **reporte 6 sirve de verificación del modelo**: muestra únicamente los 30 agentes de `customerservice`, nunca los 23 vendedores de `classicmodels`, pese a compartir rango de numeración. Es la evidencia de que la llave compuesta de `dim_empleado` funciona.

---

## 6. Entregables

| Entregable | Ubicación | Herramienta |
|---|---|---|
| Documento (este archivo) | `docs/Entrega_2/Documento_Entrega_2.md` | — |
| **Backup del almacén** | `datawarehouse/backup/dw_backup.sql` | Script propio en Python con SQLAlchemy |
| **Backup del repositorio de metadatos** | `metadata_repository/backup/metadata_repo_backup.sql` | Script propio en Python con SQLAlchemy |
| **Archivos ETL** | `datawarehouse/etl/etl_dw_dimensions.py`, `etl_dw_facts.py`, `metadata_repository/etl/etl_dw_metadata.py` | Python 3.11 + SQLAlchemy 2.1 + pandas 3.0 |
| **Reporte** | `reports/construir_dashboard.py` + capturas en `docs/Entrega_2/img/` | Metabase sobre Docker |
| DDL del almacén | `datawarehouse/ddl/01_dw_schema.sql` | PostgreSQL 16 |
| DDL de las capas de Giordano | `datawarehouse/ddl/02_staging_dw.sql` | PostgreSQL 16 |
| DDL de la extensión de metadatos | `metadata_repository/ddl/metadata_dw_extension.sql` | PostgreSQL 16 |
| DDL de metadatos de uso | `metadata_repository/ddl/metadata_uso_extension.sql` | PostgreSQL 16 |
| Medición de uso del almacén | `metadata_repository/etl/etl_uso_metadata.py` | Python + `pg_stat_user_tables` |
| Linaje de datos y análisis de impacto | `metadata_repository/queries/linaje_e_impacto.sql` | SQL |
| Consultas de negocio | `datawarehouse/queries/pregunta_negocio.sql` | SQL |
| Validación contra fuentes | `datawarehouse/queries/validacion.py` | Python |
| Verificación del backup | `datawarehouse/backup/probar_restauracion.py` | Python |
| Diagramas físicos | `docs/Entrega_2/img/*.png` | Graphviz en Docker |

> **Nota sobre los backups.** No se usó `pg_dump` porque el binario disponible en las máquinas del equipo es de PostgreSQL 15 y el servidor de Railway corre PostgreSQL 18, combinación que `pg_dump` rechaza por incompatibilidad de versión. En su lugar se escribió un generador propio que produce un archivo SQL equivalente y portable. Su funcionamiento se verificó restaurando el backup sobre una base desechable y comparando conteos y totales.

## 7. Cómo reproducir todo

El proyecto se monta completo con un solo comando, en cualquier máquina con Docker y Python 3.9 o superior. No hace falta ninguna cuenta en la nube ni credenciales:

```bash
git clone <url-del-repositorio>
cd PROYECTOFINAL_MODELOS_Y_PERSISTENCIA_DE_DATOS_SALUDA
python run_all.py
```

`run_all.py` levanta el stack de `docker-compose.yml` —las dos fuentes, el repositorio de metadatos, el almacén y Metabase—, restaura las bases desde los dumps de `sources/`, espera a que los motores estén listos y ejecuta los doce pasos del pipeline en orden. Funciona igual en Windows, macOS y Linux.

Al terminar:

| Servicio | Dirección | Acceso |
|---|---|---|
| Reportes (Metabase) | http://localhost:3000 | `grupo@javeriana.edu.co` / `Javeriana2026!` |
| Almacén de datos | `localhost:5434`, base `dw` | `postgres` / `javeriana` |
| Repositorio de metadatos | `localhost:5434`, base `metadata` | `postgres` / `javeriana` |
| classicmodels | `localhost:3307` | `root` / `javeriana` |
| customerservice | `localhost:5433` | `postgres` / `javeriana` |

### 7.1 Pasos sueltos

Cada etapa se puede correr por separado si hace falta:

```bash
python datawarehouse/ddl/run_sql.py datawarehouse/ddl/01_dw_schema.sql   # esquema del almacén
python datawarehouse/etl/etl_dw_dimensions.py                            # dimensiones (primero)
python datawarehouse/etl/etl_dw_facts.py                                 # hechos (después)
python metadata_repository/etl/etl_dw_metadata.py                        # catálogo de metadatos
python datawarehouse/queries/validacion.py                               # validar contra fuentes
python datawarehouse/ddl/generar_diagramas.py                            # diagramas físicos
python datawarehouse/backup/generar_backup.py dw                         # backup del almacén
python datawarehouse/backup/probar_restauracion.py                       # verificar el backup
python reports/construir_dashboard.py                                    # reportes
```

### 7.2 Portabilidad

El mismo código corre contra el stack local de Docker o contra un servidor remoto: lo único que cambia son las cadenas de conexión del archivo `.env`, que no se versiona. El repositorio incluye `.env.example` con los valores del stack local, y `run_all.py` lo copia automáticamente la primera vez.

`reports/construir_dashboard.py` detecta cuál de los dos casos aplica: si el almacén está en `localhost`, traduce la dirección al nombre del servicio dentro de la red de Docker (`postgres-dw:5432`), porque Metabase corre en un contenedor y no alcanza el `localhost` de la máquina anfitriona; si el almacén es remoto, usa la cadena tal cual y activa SSL.

El detalle paso a paso, pensado para quien nunca ha construido un almacén de datos, está en `docs/Entrega_2/GUIA_PASO_A_PASO.md`.
