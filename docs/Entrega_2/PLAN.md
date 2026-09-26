# Plan de ejecución — Entrega 2

**Almacén de Ventas y Servicio**
Modelos y Persistencia de Datos · Pontificia Universidad Javeriana · 2026-01
Grupo: Luis Daniel Sierra Pineda, David Cortes, Salomón Saenz
Entrega: martes de la semana 9, antes de medianoche (BrightSpace)

> Versión web de este mismo plan: https://claude.ai/artifact/VDw4HV6CA2QEpBxigDnFRK
> En la Fase 1 este archivo se mueve a `docs/Entrega_2/PLAN.md`.

---

## 0. Las tres decisiones de arquitectura

### 0.1 Dónde vive el almacén — base `dw` en Railway

Una base de datos nueva dentro de la instancia PostgreSQL 18 que **ya** hospeda el repositorio de metadatos. Verificado en sesión: el usuario `postgres` es superuser y `CREATE DATABASE` está permitido, así que no hace falta un cuarto servicio en Railway y el costo adicional es **cero**.

**Se descartó AWS.** Ningún punto de los dos enunciados exige nube: la Entrega 1 solo *recomienda* Railway advirtiendo que cuesta USD 5, y la Entrega 2 dice literal «utilizando la tecnología de su elección». Además, en la cuenta AWS disponible:

- Redshift devuelve `OptInRequired` en todas las regiones (no está habilitado).
- QuickSight devuelve `UnsupportedUserEdition` (no está configurado).
- Una RDS PostgreSQL nueva costaría entre USD 12 y 15 al mes, porque la cuenta ya tiene la instancia `cdts-dev` corriendo y el free tier probablemente está consumido.

### 0.2 Cómo se modela el hecho — constelación con dimensiones conformadas

`fact_ventas` es el hecho principal, al grano de línea de orden. `fact_llamadas_servicio` lo acompaña al grano de llamada. Ambos comparten `dim_cliente`, `dim_producto` y `dim_tiempo`.

Es el mecanismo de Kimball para integrar fuentes, y estos datos lo permiten: en el perfilamiento de la Entrega 1 se verificó que cliente y producto solapan al **100 %** entre las dos bases, mientras que empleado solapa al **0 %** — que es justamente el problema de calidad que la Entrega 2 obliga a resolver.

### 0.3 Con qué se reporta — Power BI Desktop

Se instala una vez y después todo es arrastrar campos. El entregable es un archivo `.pbix` único, que es literalmente lo que pide el enunciado en «Archivo o Link del Reporte».

Alternativa sin instalar nada, si el instalador da problemas: Metabase en Docker, que ya está disponible en la máquina.

---

## 1. El modelo dimensional — 25 % de la nota

Dos hechos, seis dimensiones. Las tres dimensiones conformadas son las que hacen que las dos fuentes se puedan analizar juntas.

```
                  dim_tiempo ──┬── fact_ventas ──┬── dim_empleado
                 dim_cliente ──┤                 ├── dim_oficina
                dim_producto ──┤                 └── dim_estado_orden
                               │
                  dim_tiempo ──┼── fact_llamadas_servicio
                 dim_cliente ──┤
                dim_producto ──┤
                dim_empleado ──┘
```

### 1.1 Hechos

#### `fact_ventas` — 2.996 filas

| Aspecto | Detalle |
|---|---|
| **Grano** | Una línea de una orden de compra |
| **Fuente** | `orderdetails` ⋈ `orders` ⋈ `products` de classicmodels (MySQL) |

**Medidas:**

| Medida | Cálculo | Aditividad |
|---|---|---|
| `cantidad_ordenada` | `orderdetails.quantityOrdered` | Aditiva |
| `precio_unitario` | `orderdetails.priceEach` | No aditiva (promediar) |
| `monto_linea` | `quantityOrdered * priceEach` | Aditiva |
| `costo_linea` | `quantityOrdered * products.buyPrice` | Aditiva |
| `margen_linea` | `monto_linea - costo_linea` | Aditiva |
| `precio_msrp` | `products.MSRP` | No aditiva |
| `dias_hasta_envio` | `shippedDate - orderDate` | Semi-aditiva (promediar) |

**Dimensiones degeneradas:** `numero_orden`, `numero_linea`

#### `fact_llamadas_servicio` — 108 filas

| Aspecto | Detalle |
|---|---|
| **Grano** | Una llamada al centro de servicio |
| **Fuente** | `cs_customer_calls` de customerservice (PostgreSQL) |

**Medidas:**

| Medida | Cálculo | Aditividad |
|---|---|---|
| `cantidad_llamadas` | Constante 1 | Aditiva |
| `longitud_texto` | `length(text)` | Aditiva |

**Dimensión degenerada:** `texto_llamada`

### 1.2 Dimensiones

| Dimensión | Filas | Conformada | Notas |
|---|---|---|---|
| `dim_cliente` | 122 | **Sí** | Integra `customers` y `cs_customers`. Solape de llave 100 %, coincidencia total en teléfono, ciudad, estado, país y código postal. Banderas `presente_en_ventas` y `presente_en_servicio`. |
| `dim_producto` | 110 | **Sí** | Integra `products` y `cs_products`, solape 100 %. Trae línea de producto desnormalizada desde `productlines`, más escala y proveedor. |
| `dim_tiempo` | 1.096 | **Sí** | Generada día a día del 2003-01-01 al 2005-12-31. Cubre ventas (2003-01-06 a 2005-05-31) y llamadas (2003-02-19 a 2005-05-09). Atributos: año, trimestre, mes, nombre de mes, día, día de semana, `es_fin_semana`. |
| `dim_empleado` | 53 | **No** | 23 de classicmodels + 30 de customerservice, **sin una sola llave en común**. Llave subrogada + atributo `sistema_origen` para que ambas poblaciones convivan. **Esta es la respuesta al problema de calidad de la Entrega 1.** |
| `dim_oficina` | 7 | No | Solo classicmodels. Ciudad, país, región, territorio. |
| `dim_estado_orden` | 6 | No | Shipped, Resolved, Cancelled, On Hold, Disputed, In Process. Permite excluir canceladas de los reportes sin borrarlas del almacén. |

### 1.3 La vista que justifica haber integrado las dos fuentes

`vw_interaccion_cliente_producto` cruza los dos hechos al grano **cliente × producto × mes** y responde la pregunta que ninguna fuente contesta sola:

> **¿Qué productos generan más llamadas de servicio por unidad vendida?**

Ese es el reporte central de la Entrega 2.

---

## 2. Las siete fases

Cada fase depende de la anterior. El porcentaje indica a qué parte de la rúbrica alimenta.

### Fase 1 — Reorganizar el repositorio · medio día

1. Crear la estructura de carpetas por dominio (sección 5) y mover los archivos de la Entrega 1 a su lugar.
2. Actualizar todas las rutas del `README.md` y del `Documento_Entrega_1.md` que apunten a archivos movidos.
3. Verificar que ningún enlace quede roto antes de seguir.

**Entregable:** árbol de carpetas limpio, sin enlaces rotos.

### Fase 2 — Crear la base `dw` y su DDL · medio día · *25 % diseño físico*

1. Correr `CREATE DATABASE dw` en la instancia PostgreSQL de Railway.
2. Escribir `datawarehouse/ddl/dw_schema.sql` con las seis dimensiones y los dos hechos: llaves subrogadas `SERIAL`, llaves de negocio con restricción `UNIQUE`, y claves foráneas de hecho a dimensión.
3. Crear el schema `staging_dw` dentro de la misma base para las capas del ETL.
4. Generar el diagrama físico con `eralchemy2`, igual que en la Entrega 1, y guardarlo en `docs/Entrega_2/img/`.

**Entregable:** `dw_schema.sql` + diagrama físico del modelo estrella.

### Fase 3 — Extender el repositorio de metadatos · un día · *15 % metadatos*

1. Escribir `metadata_repository/ddl/metadata_dw_extension.sql` con las ocho tablas nuevas (sección 3).
2. Conectar las tablas nuevas con las que ya existen: `dw_lineage` apunta a `db_column` de la Entrega 1 en el origen y a `dw_measure` o `dw_attribute` en el destino.
3. Regenerar el diagrama físico completo del repositorio, ya con las catorce tablas.

**Entregable:** DDL de extensión + diagrama físico actualizado del repositorio.

### Fase 4 — ETL de dimensiones · un día · *15 % ETL*

1. Escribir `datawarehouse/etl/etl_dw_dimensions.py` reutilizando el patrón Giordano de cinco capas de la Entrega 1, para mantener coherencia entre entregas.
2. Resolver en la capa Transform los siete problemas de calidad de la sección 4.
3. Registrar cada corrida en `etl_execution` y cada validación en `dq_result` del repositorio de metadatos.
4. Capturar pantallazos de la consola y de las tablas de staging: el enunciado pide imágenes del proceso.

**Entregable:** script de dimensiones + seis dimensiones cargadas + evidencia visual.

### Fase 5 — ETL de hechos y vista integrada · un día · *15 % ETL + 25 % solución*

1. Escribir `etl_dw_facts.py`, que resuelve las llaves subrogadas contra las dimensiones ya cargadas.
2. Cargar `fact_ventas` desde MySQL y `fact_llamadas_servicio` desde PostgreSQL.
3. Crear `vw_interaccion_cliente_producto` cruzando ambos hechos al grano cliente × producto × mes.
4. **Validar contra la fuente:** la suma de `monto_linea` debe dar exactamente **USD 9.604.190,61**.

**Entregable:** almacén cargado y cuadrado contra las fuentes.

### Fase 6 — Reportes en Power BI · un día · *20 % reportes*

1. Instalar Power BI Desktop y conectarlo **a la base `dw`**, nunca a las fuentes originales: el enunciado lo prohíbe de forma explícita.
2. **Reporte 1 — Ventas:** monto y margen por mes, línea de producto y oficina.
3. **Reporte 2 — Intensidad de servicio:** llamadas por unidad vendida, por producto. Este es el que demuestra el valor de integrar las dos fuentes.
4. **Reporte 3 — Cliente:** los que más compran frente a los que más llaman.
5. Guardar como `reports/entrega_2.pbix` y exportar los pantallazos al documento.

**Entregable:** `entrega_2.pbix` conectado al almacén + capturas.

### Fase 7 — Documento, backups y cierre · un día · *todas*

1. Escribir `docs/Entrega_2/Documento_Entrega_2.md` con las cinco secciones exactas de la rúbrica y sus porcentajes.
2. Generar el backup del almacén y el del repositorio de metadatos con el generador en Python de la Entrega 1 (el `pg_dump` local es versión 15 y el servidor es 18: aborta por incompatibilidad).
3. Indicar en cada entregable qué herramienta se usó — el enunciado lo pide tres veces por separado.
4. Actualizar el `README.md` raíz para que cubra las dos entregas.

**Entregable:** documento + dos backups + ETLs + `.pbix`, listos para subir a BrightSpace.

---

## 3. Los metadatos que faltan — 15 % de la nota

El repositorio de la Entrega 1 describe las fuentes. Ahora tiene que describir también el almacén y los procesos que lo alimentan. Se agregan **ocho tablas** a las seis que ya existen.

| Tabla nueva | Qué registra | Por qué la pide el enunciado |
|---|---|---|
| `dw_object` | Cada hecho, dimensión y vista del almacén, con su grano y descripción. | Sin esto el repositorio no sabe que el almacén existe. |
| `dw_measure` | Las medidas de cada hecho, con su tipo de aditividad y su fórmula. | «Explique el significado de las medidas que diseñó.» |
| `dw_attribute` | Los atributos de cada dimensión y su rol. | Equivalente dimensional de `db_column`. |
| `dw_lineage` | De qué columna de qué fuente sale cada medida o atributo, y con qué regla de transformación. | Extiende el linaje de la Entrega 1 hasta el almacén. |
| `etl_process` | Catálogo de procesos ETL: nombre, herramienta, origen, destino. | «No olvide registrar los metadatos» del punto 4. |
| `etl_execution` | Bitácora por corrida: inicio, fin, filas leídas, escritas y rechazadas. | Metadato operacional para gestionar el almacén. |
| `dq_rule` | Las reglas de calidad declaradas sobre cada columna. | Formaliza los hallazgos de la Entrega 1. |
| `dq_result` | El resultado de cada regla en cada corrida. | Demuestra que los problemas de calidad se resolvieron. |

---

## 4. Los problemas de calidad de la Entrega 1

> «Recuerde resolver los problemas de calidad encontrados en la entrega 1.» — enunciado, punto 4

Son estos siete, con el número exacto que arrojó el perfilamiento.

| Hallazgo | Medida | Cómo se resuelve en el ETL |
|---|---|---|
| `productlines.htmlDescription` y `.image` vacías | 100 % nulas | Se excluyen del almacén; la exclusión se documenta como regla en `dq_rule`. |
| Empleados sin llave común entre las dos fuentes | 0 % solape | Llave subrogada + atributo `sistema_origen` en `dim_empleado`. |
| `customers.addressLine2` mayormente vacía | 81,97 % nula | Se consolida con `addressLine1` en un atributo `direccion_completa`. |
| `orders.comments` mayormente vacía | 75,46 % nula | Texto libre sin valor analítico: no entra al hecho. |
| `orders.shippedDate` nula en órdenes no despachadas | 14 órdenes | `dias_hasta_envio` queda nulo y `dim_estado_orden` explica por qué. |
| PostgreSQL devuelve los nombres en minúscula (`customernumber`) y MySQL en camelCase (`customerNumber`) | 85 columnas | Normalización de nombres en la capa Transform, igual que ya se hizo con los tipos de dato. |
| Órdenes canceladas o en disputa mezcladas con las despachadas | 13 órdenes | Se cargan todas, pero `dim_estado_orden` permite filtrarlas en los reportes. |

---

## 5. Cómo queda el repositorio

Organizado por dominio, no por entrega, para que la Entrega 3 solo tenga que agregar carpetas.

```
.
├── README.md                          cubre las dos entregas
├── docs/
│   ├── enunciados/                    los PDF del curso
│   ├── Entrega_1/                     Documento_Entrega_1.md
│   └── Entrega_2/
│       ├── PLAN.md                    este archivo
│       ├── Documento_Entrega_2.md
│       └── img/                       diagramas y capturas
├── sources/                           backups de las 2 fuentes
│   ├── mysqlsampledatabase.sql
│   └── customerservice.sql
├── metadata_repository/
│   ├── ddl/                           repositorio + staging + extensión dw
│   ├── etl/                           etl_metadata_repository.py
│   ├── queries/                       las 6 consultas de la Entrega 1
│   └── backup/
├── datawarehouse/
│   ├── ddl/                           dw_schema.sql
│   ├── etl/                           dimensiones, hechos
│   ├── queries/                       validaciones y vista integrada
│   └── backup/
├── profiling/                         todo el perfilamiento de la Entrega 1
└── reports/                           entrega_2.pbix + capturas
```

---

## 6. Rúbrica contra entregable

| Ítem de la rúbrica | Peso | Dónde queda | Fase |
|---|---|---|---|
| Diseño físico del almacén y la base dimensional | 25 % | Documento §1 + diagrama del modelo estrella | 2 |
| Desarrollo de la solución | 25 % | Documento §2 + capturas de las capas | 2, 5 |
| Diseño de metadatos | 15 % | Documento §3 + diagrama de las 14 tablas | 3 |
| Diseño de ETLs | 15 % | Documento §4 + capturas de los procesos | 4, 5 |
| Diseño de reportes | 20 % | Documento §5 + `entrega_2.pbix` | 6 |
| Backup del almacén y del repositorio | — | `datawarehouse/backup/` y `metadata_repository/backup/` | 7 |
| Archivos ETL, con herramienta especificada | — | Python 3.11 con SQLAlchemy y pandas | 7 |
| Archivo o link del reporte, con herramienta | — | Power BI Desktop | 7 |

---

## 7. Dos cosas que hay que atender antes de arrancar

### 7.1 Las credenciales quedaron expuestas

Las cadenas de conexión de Railway y las claves de AWS circularon en texto plano por el chat del grupo. Hay que rotarlas:

- **Railway:** regenerar las contraseñas de los tres servicios.
- **AWS:** borrar la llave `AKIA…Y4NR` desde la consola de IAM. Es la más delicada: tiene `AdministratorAccess` sobre una cuenta con infraestructura de otro proyecto corriendo (`cdts-dev`).
- **GitHub:** cambiar la contraseña de la cuenta que se compartió.

### 7.2 El `pg_dump` local no sirve para estos backups

La máquina tiene PostgreSQL 15 y Railway corre PostgreSQL 18, así que `pg_dump` aborta por incompatibilidad de versión. El backup del repositorio de la Entrega 1 ya se generó con un script propio en Python; hay que reutilizar ese mismo generador para el almacén en lugar de pelear con el binario.
