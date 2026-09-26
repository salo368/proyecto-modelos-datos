"""
Registers the data warehouse in the metadata repository.

Fills dw_object, dw_measure and dw_attribute by introspecting the live
warehouse schema, so the catalogue always matches the deployed model.
Descriptions, additivity, SCD types and source -> warehouse lineage are
declared below because they cannot be derived from the schema.

The catalogue is rebuilt from scratch on every run.

Run after the dimension and fact ETLs.

Usage:
    python metadata_repository/etl/etl_dw_metadata.py
"""
import os

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

DW = sa.create_engine(os.getenv("DW_URL"))
META = sa.create_engine(os.getenv("METADATA_URL"))

# Schema that holds the data-mart views; facts and dimensions live in public.
DATA_MART_SCHEMA = "dm"

# ------------------------------------------------------------
# Slowly changing dimension type per dimension, with its rationale.
# All dimensions are type 1: the sources are static snapshots with no
# change capture, so there is no history to preserve.
# ------------------------------------------------------------
SCD = {
    "dim_tiempo": ("TIPO_1",
        "Dimension generada y deterministica: una fecha nunca cambia de "
        "atributos, asi que el concepto de historial no aplica."),
    "dim_cliente": ("TIPO_1",
        "El origen es un snapshot estatico sin captura de cambios, de modo "
        "que no hay versiones que preservar. Con un feed incremental seria "
        "la primera candidata a TIPO 2: el limite de credito y la direccion "
        "cambian y afectan el analisis historico."),
    "dim_producto": ("TIPO_1",
        "Mismo motivo que dim_cliente. Con datos vivos convendria TIPO 2 "
        "para que el margen de una venta antigua use el precio de compra "
        "vigente entonces, no el de hoy."),
    "dim_empleado": ("TIPO_1",
        "El origen no registra cambios de cargo ni de oficina, asi que no "
        "hay transiciones que versionar."),
    "dim_oficina": ("TIPO_1",
        "Catalogo de siete sedes, estable y sin historial en el origen."),
    "dim_estado_orden": ("TIPO_1",
        "Dimension derivada de un dominio cerrado de seis valores; no "
        "cambia entre cargas."),
}

# object name -> (type, grain, description, is_conformed)
OBJECTS = {
    "fact_ventas": (
        "FACT", "Una linea de una orden de compra.",
        "Hecho principal del almacen. Registra cada linea de detalle de las "
        "ordenes de classicmodels, con sus medidas de cantidad, monto, costo "
        "y margen.", False),
    "fact_llamadas_servicio": (
        "FACT", "Una llamada al centro de servicio al cliente.",
        "Hecho secundario. Registra cada llamada de customerservice, "
        "relacionada con el cliente que llamo, el producto consultado y el "
        "agente que atendio.", False),
    "dim_tiempo": (
        "DIMENSION", None,
        "Dimension de tiempo generada dia a dia entre 2003 y 2005. Conformada: "
        "la comparten los dos hechos.", True),
    "dim_cliente": (
        "DIMENSION", None,
        "Dimension de cliente. Conformada entre classicmodels y customerservice, "
        "que solapan al 100% por customerNumber. Las banderas presente_en_ventas "
        "y presente_en_servicio indican en que fuente aparece cada cliente.", True),
    "dim_producto": (
        "DIMENSION", None,
        "Dimension de producto. Conformada entre las dos fuentes, que solapan al "
        "100% por productCode. Incluye la linea de producto desnormalizada.", True),
    "dim_empleado": (
        "DIMENSION", None,
        "Dimension de empleado. NO conformada: las dos fuentes tienen solape 0% "
        "en la llave. Usa llave de negocio compuesta (numero_empleado, "
        "sistema_origen) para que ambas poblaciones convivan sin colisionar.", False),
    "dim_oficina": (
        "DIMENSION", None,
        "Dimension de oficina. Exclusiva de classicmodels: la sede desde la que "
        "trabaja el representante de ventas.", False),
    "dim_estado_orden": (
        "DIMENSION", None,
        "Dimension de estado de la orden. es_efectiva distingue las ventas "
        "cerradas de las canceladas, en disputa o en espera.", False),
    "vw_interaccion_cliente_producto": (
        "VIEW", "Cliente x producto x mes.",
        "Data mart (schema dm) que cruza los dos hechos al grano "
        "cliente-producto-mes. Responde que productos generan mas llamadas "
        "por unidad vendida, pregunta que ninguna fuente contesta por si sola.", False),
    "vw_ventas_mensuales_linea": (
        "VIEW", "Mes x linea de producto.",
        "Data mart (schema dm) de desempeno comercial: ordenes, unidades, monto "
        "y margen por mes y linea de producto, solo ventas efectivas.", False),
}

# (object, column) -> (additivity, formula, description)
MEASURES = {
    ("fact_ventas", "cantidad_ordenada"): (
        "ADITIVA", "orderdetails.quantityOrdered",
        "Unidades del producto pedidas en la linea."),
    ("fact_ventas", "precio_unitario"): (
        "NO_ADITIVA", "orderdetails.priceEach",
        "Precio pactado por unidad. No se suma: se promedia ponderado."),
    ("fact_ventas", "monto_linea"): (
        "ADITIVA", "quantityOrdered * priceEach",
        "Valor facturado de la linea. Es la medida central del almacen."),
    ("fact_ventas", "costo_linea"): (
        "ADITIVA", "quantityOrdered * products.buyPrice",
        "Costo de adquisicion de las unidades vendidas."),
    ("fact_ventas", "margen_linea"): (
        "ADITIVA", "monto_linea - costo_linea",
        "Utilidad bruta de la linea."),
    ("fact_ventas", "precio_msrp"): (
        "NO_ADITIVA", "products.MSRP",
        "Precio sugerido de venta. Sirve para medir descuento aplicado."),
    ("fact_ventas", "dias_hasta_envio"): (
        "SEMI_ADITIVA", "orders.shippedDate - orders.orderDate",
        "Dias entre el pedido y el despacho. Se promedia, no se suma. "
        "NULL en las ordenes que no se despacharon."),
    ("fact_llamadas_servicio", "cantidad_llamadas"): (
        "ADITIVA", "1",
        "Contador de llamadas. Permite sumar llamadas en cualquier dimension."),
    ("fact_llamadas_servicio", "longitud_texto"): (
        "ADITIVA", "length(cs_customer_calls.text)",
        "Longitud de la nota del agente, como proxy de complejidad del caso."),
}

# (object, column) -> (source table, source column, transformation rule)
LINEAGE = {
    # --- fact_ventas ---
    ("fact_ventas", "cantidad_ordenada"): ("orderdetails", "quantityOrdered", "copia directa"),
    ("fact_ventas", "precio_unitario"):   ("orderdetails", "priceEach", "copia directa"),
    ("fact_ventas", "monto_linea"):       ("orderdetails", "priceEach", "calculo: quantityOrdered * priceEach"),
    ("fact_ventas", "costo_linea"):       ("products", "buyPrice", "calculo: quantityOrdered * buyPrice"),
    ("fact_ventas", "margen_linea"):      ("products", "buyPrice", "calculo: monto_linea - costo_linea"),
    ("fact_ventas", "precio_msrp"):       ("products", "MSRP", "copia directa"),
    ("fact_ventas", "dias_hasta_envio"):  ("orders", "shippedDate", "calculo: shippedDate - orderDate; NULL si no se despacho"),
    ("fact_ventas", "numero_orden"):      ("orders", "orderNumber", "dimension degenerada"),
    ("fact_ventas", "numero_linea"):      ("orderdetails", "orderLineNumber", "dimension degenerada"),

    # --- fact_llamadas_servicio ---
    ("fact_llamadas_servicio", "cantidad_llamadas"): ("cs_customer_calls", "customernumber", "constante 1 por fila"),
    ("fact_llamadas_servicio", "longitud_texto"):    ("cs_customer_calls", "text", "calculo: length(text)"),
    ("fact_llamadas_servicio", "texto_llamada"):     ("cs_customer_calls", "text", "dimension degenerada"),

    # --- dim_cliente (conformed) ---
    ("dim_cliente", "numero_cliente"):     ("customers", "customerNumber", "llave de negocio, copia directa"),
    ("dim_cliente", "nombre_cliente"):     ("customers", "customerName", "copia directa"),
    ("dim_cliente", "contacto_nombre"):    ("customers", "contactFirstName", "copia directa"),
    ("dim_cliente", "contacto_apellido"):  ("customers", "contactLastName", "copia directa"),
    ("dim_cliente", "telefono"):           ("customers", "phone", "copia directa"),
    ("dim_cliente", "direccion_completa"): ("customers", "addressLine1", "concatenacion: addressLine1 + addressLine2 (esta ultima nula en 81,97%)"),
    ("dim_cliente", "ciudad"):             ("customers", "city", "copia directa"),
    ("dim_cliente", "estado_region"):      ("customers", "state", "copia directa"),
    ("dim_cliente", "codigo_postal"):      ("customers", "postalCode", "copia directa"),
    ("dim_cliente", "pais"):               ("customers", "country", "copia directa"),
    ("dim_cliente", "limite_credito"):     ("customers", "creditLimit", "copia directa"),
    ("dim_cliente", "presente_en_ventas"):   ("customers", "customerNumber", "bandera: existe en classicmodels"),
    ("dim_cliente", "presente_en_servicio"): ("cs_customers", "customernumber", "bandera: existe en customerservice"),

    # --- dim_producto (conformed) ---
    ("dim_producto", "codigo_producto"):   ("products", "productCode", "llave de negocio, copia directa"),
    ("dim_producto", "nombre_producto"):   ("products", "productName", "copia directa"),
    ("dim_producto", "linea_producto"):    ("products", "productLine", "copia directa"),
    ("dim_producto", "descripcion_linea"): ("productlines", "textDescription", "desnormalizacion desde productlines"),
    ("dim_producto", "escala"):            ("products", "productScale", "copia directa"),
    ("dim_producto", "proveedor"):         ("products", "productVendor", "copia directa"),
    ("dim_producto", "precio_compra"):     ("products", "buyPrice", "copia directa"),
    ("dim_producto", "precio_msrp"):       ("products", "MSRP", "copia directa"),
    ("dim_producto", "presente_en_ventas"):   ("products", "productCode", "bandera: existe en classicmodels"),
    ("dim_producto", "presente_en_servicio"): ("cs_products", "productcode", "bandera: existe en customerservice"),

    # --- dim_empleado (not conformed) ---
    ("dim_empleado", "numero_empleado"): ("employees", "employeeNumber", "llave de negocio compuesta con sistema_origen"),
    ("dim_empleado", "nombre"):          ("employees", "firstName", "union de employees y cs_employees"),
    ("dim_empleado", "apellido"):        ("employees", "lastName", "union de employees y cs_employees"),
    ("dim_empleado", "email"):           ("employees", "email", "union de employees y cs_employees"),
    ("dim_empleado", "cargo"):           ("employees", "jobTitle", "de classicmodels; constante para los agentes de servicio"),
    ("dim_empleado", "numero_oficina"):  ("employees", "officeCode", "solo classicmodels; NULL para agentes de servicio"),

    # --- dim_oficina ---
    ("dim_oficina", "codigo_oficina"): ("offices", "officeCode", "llave de negocio, copia directa"),
    ("dim_oficina", "ciudad"):         ("offices", "city", "copia directa"),
    ("dim_oficina", "pais"):           ("offices", "country", "copia directa"),
    ("dim_oficina", "region"):         ("offices", "state", "copia directa"),
    ("dim_oficina", "territorio"):     ("offices", "territory", "copia directa"),

    # --- dim_estado_orden ---
    ("dim_estado_orden", "estado"):      ("orders", "status", "valores distintos de orders.status"),
    ("dim_estado_orden", "es_efectiva"): ("orders", "status", "derivada: FALSE si status es Cancelled, Disputed u On Hold"),
}

BUSINESS_KEYS = {"numero_cliente", "codigo_producto", "numero_empleado",
                 "codigo_oficina", "estado", "fecha"}
DEGENERATE_COLUMNS = {"numero_orden", "numero_linea", "texto_llamada"}


def attribute_role(column, is_pk, table):
    if is_pk:
        return "SURROGATE_KEY"
    if column.endswith("_key"):
        return "FOREIGN_KEY"
    if column.startswith("presente_en") or column.startswith("es_"):
        return "FLAG"
    if table.startswith("fact_") and column in DEGENERATE_COLUMNS:
        return "DEGENERATE"
    if column in BUSINESS_KEYS:
        return "BUSINESS_KEY"
    return "DESCRIPTIVE"


def main():
    insp = sa.inspect(DW)
    tables = insp.get_table_names(schema="public")
    views = insp.get_view_names(schema=DATA_MART_SCHEMA)
    schema_of = {**{t: "public" for t in tables},
                 **{v: DATA_MART_SCHEMA for v in views}}

    with META.begin() as m:
        m.execute(sa.text("DELETE FROM dw_lineage"))
        m.execute(sa.text("DELETE FROM dw_measure"))
        m.execute(sa.text("DELETE FROM dw_attribute"))
        m.execute(sa.text("DELETE FROM dw_object"))

        # (table, column) -> column_id of the catalogued source columns.
        source_columns = {
            (r.table_name, r.column_name): r.column_id
            for r in m.execute(sa.text("""
                SELECT dt.table_name, dc.column_name, dc.column_id
                FROM db_column dc JOIN db_table dt ON dc.table_id = dt.table_id
            """))
        }

        n_objects = n_measures = n_attributes = n_lineage = 0

        for name in sorted(tables) + sorted(views):
            if name not in OBJECTS:
                continue
            object_type, grain, description, conformed = OBJECTS[name]

            with DW.connect() as d:
                rows = d.execute(sa.text(
                    f"SELECT COUNT(*) FROM {schema_of[name]}.{name}")).scalar()

            scd_type, scd_reason = SCD.get(name, (None, None))
            object_id = m.execute(sa.text("""
                INSERT INTO dw_object (object_name, object_type, grain,
                                       description, is_conformed, row_count,
                                       scd_type, scd_justificacion)
                VALUES (:n, :t, :g, :d, :c, :r, :st, :sj)
                RETURNING dw_object_id
            """), {"n": name, "t": object_type, "g": grain, "d": description,
                   "c": conformed, "r": rows,
                   "st": scd_type, "sj": scd_reason}).scalar()
            n_objects += 1

            if object_type == "VIEW":
                continue

            pk = set(insp.get_pk_constraint(name, schema="public")
                     .get("constrained_columns") or [])

            for col in insp.get_columns(name, schema="public"):
                col_name, col_type = col["name"], str(col["type"])
                key = (name, col_name)

                if key in MEASURES:
                    additivity, formula, desc = MEASURES[key]
                    target_id = m.execute(sa.text("""
                        INSERT INTO dw_measure (dw_object_id, measure_name, data_type,
                                                additivity, formula, description)
                        VALUES (:o, :n, :t, :a, :f, :d)
                        RETURNING dw_measure_id
                    """), {"o": object_id, "n": col_name, "t": col_type,
                           "a": additivity, "f": formula, "d": desc}).scalar()
                    target_column = "target_measure_id"
                    n_measures += 1
                else:
                    target_id = m.execute(sa.text("""
                        INSERT INTO dw_attribute (dw_object_id, attribute_name,
                                                  data_type, attribute_role)
                        VALUES (:o, :n, :t, :r)
                        RETURNING dw_attribute_id
                    """), {"o": object_id, "n": col_name, "t": col_type,
                           "r": attribute_role(col_name, col_name in pk, name)}).scalar()
                    target_column = "target_attribute_id"
                    n_attributes += 1

                if key in LINEAGE:
                    src_table, src_column, rule = LINEAGE[key]
                    m.execute(sa.text(f"""
                        INSERT INTO dw_lineage (source_column_id, {target_column},
                                                transformation_rule)
                        VALUES (:s, :d, :r)
                    """), {"s": source_columns.get((src_table, src_column)),
                           "d": target_id, "r": rule})
                    n_lineage += 1

    print("Warehouse catalogue registered in the metadata repository:")
    print(f"  dw_object    : {n_objects} objects")
    print(f"  dw_measure   : {n_measures} measures")
    print(f"  dw_attribute : {n_attributes} attributes")
    print(f"  dw_lineage   : {n_lineage} source -> warehouse links")


if __name__ == "__main__":
    main()
