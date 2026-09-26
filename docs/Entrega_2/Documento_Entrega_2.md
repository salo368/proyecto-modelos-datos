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

La solución combina los dos marcos de arquitectura que se vieron en clase. Cada uno responde una pregunta distinta:

| Marco | Clase | Qué organiza |
|---|---|---|
| Arquitectura de referencia para integración de datos de **Anthony Giordano** (*Data Integration Blueprint and Modeling*, 2011, Cap. 2) | Clase 2, diapositivas 14–19 | Las etapas por las que pasa un dato desde la fuente hasta el almacén |
| Flujo de datos dentro del DW: **ODS → EDW → DM** | Clase 4-5, diapositivas 11–12 | Cómo se organiza el almacén una vez cargado |

![Pipeline con los conteos reales de la última carga](img/pipeline_capas.png)

*El diagrama se genera desde la base, con los conteos reales de cada capa. Referencia rápida para la sustentación: [`CAPAS.md`](CAPAS.md).*

### 2.1 Las siete capas de Giordano

El diagrama de la diapositiva 14 tiene siete columnas, y las diapositivas 15 a 19 señalan con una flecha cuál están explicando. La implementación las sigue una por una, y el punto que vale subrayar es que **cada capa es una tabla física persistida** en el schema `staging_dw`, no un paso en memoria:

| # | Capa | Tabla física | Dia. | Qué dibuja el diagrama |
|---|---|---|---|---|
| 1 | **Extract/Publish** | *(modelos de extracción en el código)* | 15 | Un modelo lógico de extracción por fuente |
| 2 | **Initial Staging** | `stg_initial_classicmodels`, `stg_initial_customerservice`, `stg_perfil` | 16 | Una pila por fuente, de colores distintos; perfilamiento |
| 3 | **Data Quality** | `stg_error_log` | 17 | *Tech DQ Checks*, *Bus DQ Check*, *Error Handling* → reporte de *Bad Transactions* |
| 4 | **Clean Staging** | `stg_clean`, `stg_rejected` | 18 | Dos pilas: gris (limpios) y roja (rechazados) |
| 5 | **Transformation** | `stg_transform` | 19 | Conformar por área temática: joins, lookups, agregaciones |
| 6 | **Load-Ready Publish** | `stg_loadready` | — | Forma definitiva, lista para cargar |
| 7 | **Load** | `dim_*`, `fact_*` | — | Se bifurca en dos modelos de carga: *Involved Party* y *Event* |

Tres detalles del diagrama que la implementación respeta a propósito:

- **Initial Staging tiene una pila por fuente.** Por eso hay dos tablas, una por sistema origen, y no una sola compartida.
- **Data Quality no tiene pila propia.** Es procesamiento: lo que produce es el reporte de transacciones malas y, a su derecha, las dos pilas de Clean Staging. La separación entre limpios y rechazados (diapositiva 18) es una **capa de almacenamiento**, no una columna de estado.
- **La carga se bifurca.** Las pilas *Involved Party* y *Event* del diagrama corresponden aquí a dimensiones y hechos, y cada rama es un proceso aparte que parte del mismo Clean Staging.

Los tres procesos ETL reproducen esa forma:

| Proceso | Capas | Qué hace |
|---|---|---|
| `etl_dw_staging.py` | 1 a 4 | La mitad frontal compartida: extrae una vez, perfila, evalúa calidad y separa |
| `etl_dw_dimensions.py` | 5 a 7 | Rama de dimensiones |
| `etl_dw_facts.py` | 5 a 7 | Rama de hechos |

### 2.2 Los principios de Giordano y cómo se cumplen

La Clase 2 enunció cuatro principios en las diapositivas 15 y 16. Cambian el diseño del proceso, no son recomendaciones estéticas:

**«Read once, write many»** (diapositiva 15). Las 13 tablas de las fuentes se leen **una sola vez por carga**. Las ramas de dimensiones y de hechos no se conectan a MySQL ni a PostgreSQL de origen: leen la misma pila de limpios. La tabla de control lo registra: ambas ramas declaran `run_origen` igual a la corrida de staging que consumieron.

**«Traer todo pensando en necesidades futuras»** (diapositiva 15). Se extraen también `payments` y `cs_customer_products`, que el modelo actual no usa. El modelo puede crecer sin volver a tocar la fuente.

**«Almacenamiento no volátil»** (diapositiva 16). Ninguna tabla de staging se trunca. Cada corrida agrega filas con su `run_id` y el historial completo queda disponible, incluidas las corridas que fallan.

**«Perfilamiento»** (diapositiva 16). Cada carga perfila lo que aterrizó en Initial Staging —nulos, distintos, mínimo y máximo por columna— en `stg_perfil`. El perfilamiento deja de ser un ejercicio único de la Entrega 1 y pasa a correr en cada carga.

### 2.3 La capa de calidad y la separación en dos pilas

La capa 3 evalúa **once reglas por registro**, separadas como las divide la diapositiva 17:

| Clase | Reglas | Acción al fallar |
|---|---|---|
| **Técnica** (*Tech DQ Checks*) | Campos obligatorios, tipo de dato válido | Rechazo |
| | Formato de correo | Advertencia |
| **Negocio** (*Bus DQ Check*) | Integridad referencial (dentro de cada fuente y entre fuentes), valores positivos, secuencia de fechas, envío coherente con el estado | Rechazo |
| | Precio sugerido coherente, cliente con vendedor, consistencia de definiciones entre fuentes | Advertencia |

Las columnas obligatorias **no están escritas en el ETL**: se leen del repositorio de metadatos (`db_column.is_nullable`), que es el metadato técnico catalogado en la Entrega 1. El metadato gobierna el proceso.

**Resultado sobre los datos reales:** 4.335 registros evaluados, **0 rechazados** y 22 advertencias. Cero rechazados es la verdad sobre estos datos: no tienen referencias rotas, valores negativos ni fechas incoherentes. Las 22 advertencias son los clientes sin representante de ventas asignado: la fuente admite el nulo (válido técnicamente), pero el negocio espera que todo cliente tenga vendedor. Es exactamente la diferencia entre calidad técnica y de negocio de la diapositiva 17.

**El camino de rechazo está probado.** Como los datos reales no lo ejercitan, `datawarehouse/queries/probar_calidad.py` arma un lote sintético con un defecto por cada tipo de regla, usando las mismas funciones del ETL y sin tocar el almacén. Verifica que los 7 defectos bloqueantes terminen en la pila roja, que las 4 advertencias pasen como limpias y que ningún registro sano se marque por error. Corre como paso del pipeline.

**Sobre los tres destinos de la diapositiva 18.** La diapositiva plantea limpios, por revisar y rechazados. Se implementan dos pilas, y es una decisión: «por revisar» presupone un custodio de datos que valide los casos dudosos antes de cada carga, y este almacén se reconstruye desatendido desde snapshots estáticos. Un estado que nadie revisa es una capa muerta. Los casos dudosos pasan como limpios y quedan trazados como advertencia en el reporte, de modo que la decisión es auditable. Con feeds vivos de calidad variable, el tercer estado sí se justificaría.

### 2.4 ODS → EDW → DM

La diapositiva 12 de la Clase 4-5 dibuja el flujo dentro del almacén, y la 11 caracteriza cada depósito:

| Depósito | Detalle | Alcance | En este proyecto |
|---|---|---|---|
| **ODS** | Máximo nivel de detalle | Empresa, día a día | No se implementa |
| **EDW** | Detalle y agregaciones | Empresa | Modelo estrella en el schema `public` |
| **DM** | Agregaciones, poco detalle | Tema específico | Schema `dm` con dos data marts |

La flecha EDW → DM está rotulada «Agregar. Segregar», y los dos data marts hacen exactamente eso:

| Data mart | Agrega | Segrega |
|---|---|---|
| `dm.vw_interaccion_cliente_producto` | De línea de orden y llamada a cliente × producto × mes | El tema servicio frente a ventas |
| `dm.vw_ventas_mensuales_linea` | De línea de orden a mes × línea de producto | Solo ventas efectivas |

**Por qué no hay ODS.** Un ODS sirve para consulta operativa del día a día sobre dato integrado y reciente. Este proyecto es un pipeline batch sobre dos snapshots estáticos: no hay operación diaria que consultar. Clean Staging contiene el dato integrado y validado antes del EDW, pero no se expone para consulta, y llamarlo ODS sería forzar el término.

### 2.5 Herramientas y justificación

| Componente | Herramienta | Por qué |
|---|---|---|
| Almacén y repositorio | PostgreSQL 16 en Docker | Dos bases separadas en una misma instancia: separación lógica sin infraestructura adicional |
| ETL | Python 3.11 + SQLAlchemy 2.1 + pandas 3.0 | Mismo stack de la Entrega 1, lo que permite reutilizar la arquitectura de Giordano en ambas entregas |
| Diagramas | Graphviz en contenedor Docker | Se generan desde el esquema y los conteos reales, no a mano |
| Reportes | Metabase (open source) sobre Docker | Cero costo, cero instalación, conexión nativa a PostgreSQL |
| Orquestación | `docker-compose` + `run_all.py` | Todo el proyecto se levanta y se carga con un comando, en cualquier máquina |

Se evaluó y se descartó AWS: ningún punto del enunciado exige nube, Redshift no está habilitado en la cuenta disponible y una instancia RDS habría costado entre 12 y 15 dólares mensuales sin aportar nada a la calificación.

### 2.6 Validación de la carga

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

Adicionalmente se verificó que **el backup restaura de verdad**: se crea una base desechable, se carga `dw_backup.sql` y se comparan conteos, monto total y las dos vistas de data marts contra el almacén original.

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

![Repositorio de metadatos con las dieciocho tablas](img/repositorio_metadatos.png)

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

El ETL son tres procesos que reproducen la forma del diagrama de Giordano: una mitad frontal compartida y una carga que se bifurca.

| Proceso | Archivo | Capas | Lee de | Escribe en |
|---|---|---|---|---|
| Staging | `datawarehouse/etl/etl_dw_staging.py` | 1 a 4 | Las dos fuentes, **una sola vez** | `stg_initial_*`, `stg_perfil`, `stg_error_log`, `stg_clean`, `stg_rejected` |
| Dimensiones | `datawarehouse/etl/etl_dw_dimensions.py` | 5 a 7 | `stg_clean` | `stg_transform`, `stg_loadready`, `dim_*` |
| Hechos | `datawarehouse/etl/etl_dw_facts.py` | 5 a 7 | `stg_clean` y las dimensiones | `stg_transform`, `stg_loadready`, `fact_*` |

**El orden es obligatorio** por dos razones distintas. La primera es arquitectónica: dimensiones y hechos consumen la pila de limpios, así que staging tiene que haber terminado. La segunda es de integridad: los hechos guardan la llave subrogada de cada dimensión, así que las dimensiones tienen que existir antes.

### 4.2 Recorrido del dato por las capas

Salida real de `staging_dw.vw_trazabilidad_capas` tras una carga limpia:

| Corrida | Proceso | Lee de | Initial Staging | Errores DQ | Limpios | Rechazados | Transform | Load-Ready |
|---|---|---|---|---|---|---|---|---|
| 1 | staging | fuentes | 4.335 | 22 | 4.335 | 0 | — | — |
| 2 | dimensiones | corrida 1 | — | — | — | — | 1.394 | 1.394 |
| 3 | hechos | corrida 1 | — | — | — | — | 3.104 | 3.104 |

Los números cuentan la historia del diseño:

- **4.335 en Initial Staging** son las 13 tablas de las dos fuentes (3.864 de `classicmodels`, 471 de `customerservice`), leídas una vez.
- **22 errores y 0 rechazados**: las 22 entradas son advertencias, así que ningún registro sale del flujo.
- **Las dos ramas leen de la corrida 1**: consumen la misma extracción. Es la evidencia directa del «read once».
- **1.394 en Transform para dimensiones**: de las 13 tablas solo alimentan dimensiones las que describen actores y contexto, y varias se consolidan (`products` con `productlines`, `employees` con `cs_employees`).
- **3.104 en Transform para hechos**: 2.996 líneas de orden más 108 llamadas.

### 4.3 La capa Transformation: conformar por área temática

En el diagrama, la caja de transformación dice *Conform Loan Data* y *Conform Deposit Data*: conforma **por tema**, no por fuente. Aquí cada fila de `stg_transform` registra el área conformada y las operaciones que se le aplicaron:

| Área | Destino | Operaciones |
|---|---|---|
| Tiempo | `dim_tiempo` | Generación |
| Organización | `dim_oficina` | Proyección |
| Ventas | `dim_estado_orden` | Agregación de valores distintos |
| Cliente | `dim_cliente` | Join entre fuentes, consolidación de dirección |
| Producto | `dim_producto` | Join con `productlines`, join entre fuentes |
| Empleado | `dim_empleado` | Unión de fuentes, llave compuesta |
| Ventas | `fact_ventas` | Join (5 tablas), lookup (5 dimensiones), medidas calculadas |
| Servicio | `fact_llamadas_servicio` | Lookup (3 dimensiones), medidas calculadas |

Las tres operaciones de la diapositiva 19 aparecen juntas en `fact_ventas`:

**Joins.** Cruza cinco tablas de la pila de limpios (`orderdetails`, `orders`, `products`, `customers`, `employees`) para reunir medidas y llaves de negocio en una fila.

**Lookups.** La operación característica de un ETL dimensional: el hecho no guarda `customerNumber = 103`, guarda la `cliente_key` que le tocó a ese cliente en `dim_cliente`. El caso de `dim_empleado` muestra por qué el lookup necesita contexto: su llave es compuesta `(numero_empleado, sistema_origen)`, así que el lookup de un vendedor se resuelve siempre contra la población de `classicmodels` y el de un agente contra la de `customerservice`. Hoy los números de las dos fuentes no se solapan (0 % medido en la Entrega 1), pero son secuencias independientes de dos sistemas distintos y nada garantiza que no choquen mañana; la llave compuesta hace que el modelo no dependa de esa casualidad.

**Agregaciones.** Las medidas calculadas (`monto_linea`, `costo_linea`, `margen_linea`, `dias_hasta_envio`).

Si alguna llave obligatoria queda sin resolver, el proceso **falla en vez de cargar un hecho huérfano**. Un hecho que apunta a una dimensión inexistente corrompe todos los reportes que lo agreguen.

### 4.4 Registro en el repositorio de metadatos

Cada corrida se registra en dos lugares complementarios:

- `staging_dw.etl_run`, el control interno del pipeline, con la corrida de origen de cada rama.
- `etl_execution` en el repositorio de metadatos, la vista de gobierno: proceso, herramienta, filas leídas, escritas y rechazadas.

Además, cada regla evaluada deja su resultado en `dq_result`, ligado a la ejecución concreta. En `dq_rule`, cada regla lleva la capa donde se evalúa (`DATA_QUALITY`, `TRANSFORMATION` o `MONITOREO`), su criterio DAMA y su clase técnica o de negocio.

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
