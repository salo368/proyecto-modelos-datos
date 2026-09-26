"""
Layer 3 - Data Quality.

Technical checks (missing or invalid data) and business checks
(referential integrity, inaccurate data, inconsistent definitions) on
what landed in Initial Staging. Every failure becomes a row of the
bad-transactions log, with the action the rule dictates:

    RECHAZADO    the record cannot continue; layer 4 sends it to stg_rejected
    ADVERTENCIA  the record continues; the anomaly is only logged

    Input   stg_initial_* (layer 2)
    Output  stg_error_log; stg_dq_resumen (records checked and failed per rule)
    Reader  read_failures(run_id), used by layer 4
"""
from collections import defaultdict

import pandas as pd
import sqlalchemy as sa

from common import META, STAGING, insert, write_quality
from layer2_initial_staging import read_initial

# Rule -> (dq class, category, action). Names match dq_rule.rule_name
# in the metadata repository.
RULES = {
    # --- technical checks ---
    "campos_obligatorios":    ("TECNICA", "CAMPO_FALTANTE",   "RECHAZADO"),
    "tipo_de_dato_valido":    ("TECNICA", "DATO_INVALIDO",    "RECHAZADO"),
    "formato_email":          ("TECNICA", "DATO_INVALIDO",    "ADVERTENCIA"),
    "registro_duplicado":     ("TECNICA", "DATO_DUPLICADO",   "RECHAZADO"),
    "llave_duplicada":        ("TECNICA", "DATO_DUPLICADO",   "RECHAZADO"),
    # --- business checks ---
    "integridad_referencial": ("NEGOCIO", "INTEGRIDAD_REFERENCIAL", "RECHAZADO"),
    "valores_positivos":      ("NEGOCIO", "DATO_INEXACTO",    "RECHAZADO"),
    "secuencia_de_fechas":    ("NEGOCIO", "DATO_INEXACTO",    "RECHAZADO"),
    "envio_consistente_con_estado": ("NEGOCIO", "DATO_INEXACTO", "RECHAZADO"),
    "fecha_no_futura":        ("NEGOCIO", "DATO_INEXACTO",    "RECHAZADO"),
    "precio_sugerido_coherente":    ("NEGOCIO", "DATO_INEXACTO", "ADVERTENCIA"),
    "cliente_con_vendedor":   ("NEGOCIO", "CAMPO_FALTANTE",   "ADVERTENCIA"),
    "consistencia_entre_fuentes_cliente":
                              ("NEGOCIO", "DEFINICION_INCONSISTENTE", "ADVERTENCIA"),
    "consistencia_entre_fuentes_producto":
                              ("NEGOCIO", "DEFINICION_INCONSISTENTE", "ADVERTENCIA"),
    "referencia_opcional_no_resuelta":
                              ("NEGOCIO", "INTEGRIDAD_REFERENCIAL", "ADVERTENCIA"),
    # --- propagation: evaluated last, over the rejections of every rule above ---
    "padre_rechazado":        ("NEGOCIO", "INTEGRIDAD_REFERENCIAL", "RECHAZADO"),
    "orden_con_lineas_rechazadas":
                              ("NEGOCIO", "INTEGRIDAD_REFERENCIAL", "ADVERTENCIA"),
}

# Columns that identify a record in the error log, and the key that must
# be unique in each table (registro_duplicado, llave_duplicada).
# cs_customer_calls has no primary key in its source, so its references
# plus the date and time of the call are used instead.
RECORD_KEYS = {
    "customers": ["customerNumber"], "employees": ["employeeNumber"],
    "offices": ["officeCode"], "products": ["productCode"],
    "productlines": ["productLine"], "orders": ["orderNumber"],
    "orderdetails": ["orderNumber", "productCode"],
    "payments": ["customerNumber", "checkNumber"],
    "cs_customers": ["customernumber"], "cs_products": ["productcode"],
    "cs_employees": ["employeenumber"],
    "cs_customer_calls": ["customernumber", "productcode", "employeenumber", "date"],
    "cs_customer_products": ["customernumber", "productcode"],
}

DATE_COLUMNS = {
    "orders": ["orderDate", "requiredDate", "shippedDate"],
    "payments": ["paymentDate"],
    "cs_customer_calls": ["date"],
}
NUMERIC_COLUMNS = {
    "orderdetails": ["quantityOrdered", "priceEach", "orderLineNumber"],
    "products": ["quantityInStock", "buyPrice", "MSRP"],
    "customers": ["creditLimit"],
    "payments": ["amount"],
}
# Dates of events that already happened: they cannot be later than the
# load. orders.orderDate and cs_customer_calls.date also become the
# tiempo_key of the facts, and dim_tiempo is generated from them.
EVENT_DATES = {
    "orders": ["orderDate"],
    "payments": ["paymentDate"],
    "cs_customer_calls": ["date"],
}

# (child table, column, parent table, parent column, description).
# integridad_referencial checks them against everything that landed;
# padre_rechazado, against the parents that were not rejected.
REFERENCES = [
    ("orderdetails", "orderNumber", "orders", "orderNumber", "orden inexistente"),
    ("orderdetails", "productCode", "products", "productCode", "producto inexistente"),
    ("orders", "customerNumber", "customers", "customerNumber", "cliente inexistente"),
    ("payments", "customerNumber", "customers", "customerNumber", "cliente inexistente"),
    ("customers", "salesRepEmployeeNumber", "employees", "employeeNumber", "vendedor inexistente"),
    ("employees", "officeCode", "offices", "officeCode", "oficina inexistente"),
    ("employees", "reportsTo", "employees", "employeeNumber", "jefe inexistente"),
    ("products", "productLine", "productlines", "productLine", "linea inexistente"),
    ("cs_customer_calls", "customernumber", "cs_customers", "customernumber", "cliente inexistente en customerservice"),
    ("cs_customer_calls", "productcode", "cs_products", "productcode", "producto inexistente en customerservice"),
    ("cs_customer_calls", "employeenumber", "cs_employees", "employeenumber", "agente inexistente"),
    ("cs_customer_products", "customernumber", "cs_customers", "customernumber", "cliente inexistente"),
    ("cs_customer_products", "productcode", "cs_products", "productcode", "producto inexistente"),
    # Cross-source: the conformed dimensions are built from
    # classicmodels, so a call whose customer or product is missing
    # there would become an orphan in fact_llamadas_servicio.
    ("cs_customer_calls", "customernumber", "customers", "customerNumber",
     "cliente sin equivalente en classicmodels (dimension conformada)"),
    ("cs_customer_calls", "productcode", "products", "productCode",
     "producto sin equivalente en classicmodels (dimension conformada)"),
]

# Header -> detail. A header that is kept while some of its details were
# rejected reaches the warehouse incomplete: orden_con_lineas_rechazadas
# warns about it.
HEADER_DETAIL = [("orders", "orderNumber", "orderdetails", "orderNumber")]

# References the model can leave unresolved. A missing or rejected parent
# only raises referencia_opcional_no_resuelta (a warning) and the record
# goes on: the sales rep of a customer becomes the special member
# 'Desconocido' of dim_empleado and dim_oficina
# (datawarehouse/edw/special_members.sql), and reportsTo is not modelled.
OPTIONAL_REFERENCES = {
    ("customers", "salesRepEmployeeNumber"),
    ("employees", "reportsTo"),
}


def required_columns():
    """NOT NULL columns per table, read from the metadata repository.

    The mandatory-field rule is driven by db_column.is_nullable (the
    catalogued source dictionary), not by a list in this file.
    """
    with META.connect() as con:
        rows = con.execute(sa.text("""
            SELECT dt.table_name, dc.column_name
            FROM db_column dc JOIN db_table dt ON dc.table_id = dt.table_id
            WHERE dc.is_nullable = FALSE
        """)).fetchall()
    required = defaultdict(list)
    for table, col in rows:
        required[table].append(col)
    return required


class QualityLog:
    """Collects the failures produced by the quality checks."""

    def __init__(self):
        self.failures = []                        # rows for stg_error_log
        self.evaluated = defaultdict(int)         # rule -> rows checked
        self.failed = defaultdict(int)            # rule -> rows that failed

    def check(self, rule, n):
        self.evaluated[rule] += n

    def fail(self, rule, source, table, row, detail):
        dq_class, category, action = RULES[rule]
        key = "|".join(str(row.get(k)) for k in RECORD_KEYS.get(table, []))
        self.failures.append({
            "fuente": source, "tabla_origen": table,
            "nro_fila": int(row["_nro_fila"]), "llave_registro": key,
            "clase_dq": dq_class, "categoria": category, "regla": rule,
            "accion": action, "detalle": detail,
        })
        self.failed[rule] += 1


def uniqueness_checks(data, log):
    """Records that share the key of their table.

    Exact copies of an earlier record (every column equal) are dropped:
    the first one goes on and the copies are rejected as
    registro_duplicado. Records that share the key but differ in any
    other column are all rejected as llave_duplicada, because nothing
    tells which version is right. Their children then follow them
    (padre_rechazado), since the key no longer reaches Clean Staging.
    """
    for table, (source, df) in data.items():
        key = [c for c in RECORD_KEYS.get(table, []) if c in df.columns]
        if not key:
            continue
        log.check("registro_duplicado", len(df))
        log.check("llave_duplicada", len(df))
        body = [c for c in df.columns if c != "_nro_fila"]
        repeated = df[df.duplicated(key, keep=False)]
        for values, group in repeated.groupby(key, dropna=False, sort=False):
            label = "|".join(str(v) for v in (values if isinstance(values, tuple) else (values,)))
            group = group.sort_values("_nro_fila")
            first = int(group["_nro_fila"].iloc[0])
            if len(group[body].drop_duplicates()) == 1:
                for _, row in group.iloc[1:].iterrows():
                    log.fail("registro_duplicado", source, table, row,
                             f"Copia exacta del registro {first} (llave {label})")
            else:
                rows = ", ".join(str(int(n)) for n in group["_nro_fila"])
                for _, row in group.iterrows():
                    log.fail("llave_duplicada", source, table, row,
                             f"La llave {label} aparece en {len(group)} registros "
                             f"distintos (filas {rows})")


def technical_checks(data, log):
    """Duplicated, missing and invalid data."""
    uniqueness_checks(data, log)
    required = required_columns()
    for table, (source, df) in data.items():
        # Missing data: NOT NULL columns according to the repository.
        cols = [c for c in required.get(table, []) if c in df.columns]
        if cols:
            log.check("campos_obligatorios", len(df))
            for _, row in df.iterrows():
                missing = [c for c in cols if pd.isna(row[c])]
                if missing:
                    log.fail("campos_obligatorios", source, table, row,
                             f"Faltan campos obligatorios: {', '.join(missing)}")

        # Invalid data: dates and numbers that cannot be parsed.
        dates = [c for c in DATE_COLUMNS.get(table, []) if c in df.columns]
        numbers = [c for c in NUMERIC_COLUMNS.get(table, []) if c in df.columns]
        if dates or numbers:
            log.check("tipo_de_dato_valido", len(df))
            invalid = pd.Series(False, index=df.index)
            reason = pd.Series("", index=df.index)
            for c in dates:
                parsed = pd.to_datetime(df[c], errors="coerce")
                bad = df[c].notna() & parsed.isna()
                invalid |= bad
                reason[bad] += f"{c} no es una fecha; "
            for c in numbers:
                parsed = pd.to_numeric(df[c], errors="coerce")
                bad = df[c].notna() & parsed.isna()
                invalid |= bad
                reason[bad] += f"{c} no es un numero; "
            for i in df.index[invalid]:
                log.fail("tipo_de_dato_valido", source, table, df.loc[i],
                         reason[i].strip())

    # E-mail format in both employee catalogues.
    for table in ("employees", "cs_employees"):
        if table in data:
            source, df = data[table]
            log.check("formato_email", len(df))
            for _, row in df.iterrows():
                e = row.get("email")
                if isinstance(e, str) and ("@" not in e or "." not in e.split("@")[-1]):
                    log.fail("formato_email", source, table, row,
                             f"Correo con formato invalido: {e}")


def business_checks(data, log):
    """Referential integrity, inaccurate data and inconsistent definitions."""

    def keys(table, col):
        return set(data[table][1][col].dropna()) if table in data else set()

    # --- Referential integrity, within each source and across sources ---
    counted = set()
    for child, col, parent, parent_col, desc in REFERENCES:
        if child not in data or parent not in data:
            continue
        rule = ("referencia_opcional_no_resuelta" if (child, col) in OPTIONAL_REFERENCES
                else "integridad_referencial")
        source, df = data[child]
        valid = keys(parent, parent_col)
        if (rule, child) not in counted:
            log.check(rule, len(df))
            counted.add((rule, child))
        for _, row in df.iterrows():
            v = row.get(col)
            if pd.notna(v) and v not in valid:
                log.fail(rule, source, child, row, f"{col}={v}: {desc}")

    # --- Values that must be positive (credit limit may be zero) ---
    positives = [("orderdetails", ["quantityOrdered", "priceEach"]),
                 ("products", ["buyPrice", "MSRP"]),
                 ("payments", ["amount"]),
                 ("customers", ["creditLimit"])]
    for table, cols in positives:
        if table not in data:
            continue
        source, df = data[table]
        log.check("valores_positivos", len(df))
        for _, row in df.iterrows():
            bad = [c for c in cols
                   if pd.notna(row.get(c)) and float(row[c]) < (0 if c == "creditLimit" else 0.000001)]
            if bad:
                log.fail("valores_positivos", source, table, row,
                         f"Valores no positivos: {', '.join(bad)}")

    # --- Date sequence and status consistency of orders ---
    if "orders" in data:
        source, df = data["orders"]
        ordered = pd.to_datetime(df["orderDate"], errors="coerce")
        required = pd.to_datetime(df["requiredDate"], errors="coerce")
        shipped = pd.to_datetime(df["shippedDate"], errors="coerce")
        log.check("secuencia_de_fechas", len(df))
        log.check("envio_consistente_con_estado", len(df))
        for i in df.index:
            if pd.notna(shipped[i]) and shipped[i] < ordered[i]:
                log.fail("secuencia_de_fechas", source, "orders", df.loc[i],
                         "La fecha de envio es anterior a la del pedido")
            elif pd.notna(required[i]) and required[i] < ordered[i]:
                log.fail("secuencia_de_fechas", source, "orders", df.loc[i],
                         "La fecha requerida es anterior a la del pedido")
            if df.at[i, "status"] == "Shipped" and pd.isna(shipped[i]):
                log.fail("envio_consistente_con_estado", source, "orders", df.loc[i],
                         "Orden marcada Shipped sin fecha de envio")

    # --- Events dated after the load ---
    today = pd.Timestamp.today().normalize()
    for table, cols in EVENT_DATES.items():
        if table not in data:
            continue
        source, df = data[table]
        cols = [c for c in cols if c in df.columns]
        log.check("fecha_no_futura", len(df))
        for i in df.index:
            late = [c for c in cols
                    if pd.to_datetime(df.at[i, c], errors="coerce") > today]
            if late:
                log.fail("fecha_no_futura", source, table, df.loc[i],
                         f"Fecha posterior a la carga: {', '.join(late)}")

    # --- Suggested price below cost ---
    if "products" in data:
        source, df = data["products"]
        log.check("precio_sugerido_coherente", len(df))
        for _, row in df.iterrows():
            if pd.notna(row["MSRP"]) and pd.notna(row["buyPrice"]) \
                    and float(row["MSRP"]) < float(row["buyPrice"]):
                log.fail("precio_sugerido_coherente", source, "products", row,
                         f"MSRP {row['MSRP']} menor al costo {row['buyPrice']}")

    # --- Customer without sales rep: nullable in the source, but the
    # business expects every customer to have one ---
    if "customers" in data:
        source, df = data["customers"]
        log.check("cliente_con_vendedor", len(df))
        for _, row in df.iterrows():
            if pd.isna(row.get("salesRepEmployeeNumber")):
                log.fail("cliente_con_vendedor", source, "customers", row,
                         "Cliente sin representante de ventas asignado")

    # --- Same entity described differently in the two sources ---
    def compare(cs_table, cm_table, cs_key, cm_key, pairs, rule):
        if cs_table not in data or cm_table not in data:
            return
        source, cs = data[cs_table]
        cm = data[cm_table][1].set_index(cm_key)
        log.check(rule, len(cs))
        norm = lambda v: None if pd.isna(v) else str(v).strip()
        for _, row in cs.iterrows():
            k = row[cs_key]
            if k not in cm.index:
                continue                      # already reported as integrity failure
            ref = cm.loc[k]
            different = [c_cs for c_cs, c_cm in pairs
                         if norm(row.get(c_cs)) != norm(ref.get(c_cm))]
            if different:
                log.fail(rule, source, cs_table, row,
                         f"Difiere de classicmodels en: {', '.join(different)}")

    compare("cs_customers", "customers", "customernumber", "customerNumber",
            [("phone", "phone"), ("city", "city"), ("country", "country"),
             ("postalcode", "postalCode")],
            "consistencia_entre_fuentes_cliente")
    compare("cs_products", "products", "productcode", "productCode",
            [("productname", "productName"), ("productscale", "productScale"),
             ("productvendor", "productVendor")],
            "consistencia_entre_fuentes_producto")


def orphans(data, rejected, reference):
    """(source, row, value) of each child record, not yet rejected, whose
    reference points to a key that only rejected parents carry."""
    child, col, parent, parent_col, _ = reference
    if not rejected[parent]:
        return
    parents = data[parent][1]
    dropped = parents["_nro_fila"].isin(rejected[parent])
    # A key survives if any record that carries it was kept.
    gone = (set(parents.loc[dropped, parent_col].dropna())
            - set(parents.loc[~dropped, parent_col].dropna()))
    source, df = data[child]
    for _, row in df.iterrows():
        v = row.get(col)
        if int(row["_nro_fila"]) not in rejected[child] and pd.notna(v) and v in gone:
            yield source, row, v


def cascade_rejections(data, log):
    """Reject the records whose parent was rejected, down every level.

    integridad_referencial compares each reference with everything that
    landed in Initial Staging, so the children of a rejected record pass
    it: the orders of a rejected customer and the lines of those orders.
    Left in Clean Staging, they would point to a dimension member that
    never reaches the warehouse and the fact load would stop. The
    rejection is propagated along the mandatory REFERENCES until no new
    record falls. Along OPTIONAL_REFERENCES it is not: the child only
    gets a warning and keeps going.
    """
    rejected = defaultdict(set)                   # table -> rejected row numbers
    for f in log.failures:
        if f["accion"] == "RECHAZADO":
            rejected[f["tabla_origen"]].add(f["nro_fila"])
    present = [r for r in REFERENCES if r[0] in data]
    mandatory = [r for r in present if (r[0], r[1]) not in OPTIONAL_REFERENCES]
    optional = [r for r in present if (r[0], r[1]) in OPTIONAL_REFERENCES]
    for child in {r[0] for r in mandatory}:
        log.check("padre_rechazado", len(data[child][1]))

    changed = True
    while changed:
        changed = False
        for ref in mandatory:
            child, col, parent = ref[:3]
            for source, row, v in orphans(data, rejected, ref):
                log.fail("padre_rechazado", source, child, row,
                         f"{col}={v}: el registro de {parent} fue rechazado")
                rejected[child].add(int(row["_nro_fila"]))
                changed = True

    for ref in optional:
        child, col, parent = ref[:3]
        for source, row, v in orphans(data, rejected, ref):
            log.fail("referencia_opcional_no_resuelta", source, child, row,
                     f"{col}={v}: el registro de {parent} fue rechazado")

    incomplete_headers(data, rejected, log)


def incomplete_headers(data, rejected, log):
    """Warn about the kept headers that lost some of their details.

    The rejection goes down from an order to its lines, but not up: an
    order whose line was rejected is still loaded, with fewer lines than
    in the source. Its total and its line count in the warehouse are
    then short, so the order is logged with a warning.
    """
    for header, key, detail, detail_key in HEADER_DETAIL:
        if header not in data or detail not in data:
            continue
        source, headers = data[header]
        details = data[detail][1]
        log.check("orden_con_lineas_rechazadas", len(headers))
        dropped = details["_nro_fila"].isin(rejected[detail])
        lost = details.loc[dropped].groupby(detail_key).size()
        total = details.groupby(detail_key).size()
        for _, row in headers.iterrows():
            k = row.get(key)
            if int(row["_nro_fila"]) in rejected[header] or k not in lost.index:
                continue
            log.fail("orden_con_lineas_rechazadas", source, header, row,
                     f"{int(lost[k])} de {int(total[k])} lineas rechazadas: "
                     "la orden llega incompleta al almacen")


def run(run_id):
    print("\n[Layer 3] Data Quality")
    data = read_initial(run_id)
    log = QualityLog()
    technical_checks(data, log)
    business_checks(data, log)
    cascade_rejections(data, log)

    insert("stg_error_log", [{"run_id": run_id, **f} for f in log.failures])
    write_quality(run_id, 3, [(r, log.evaluated[r], log.failed[r]) for r in RULES])

    print(f"    {'Rule':<38}{'Class':<9}{'Action':<13}{'Checked':>9}{'Failed':>8}")
    for rule, (dq_class, _, action) in RULES.items():
        print(f"    {rule:<38}{dq_class:<9}{action:<13}"
              f"{log.evaluated[rule]:>9}{log.failed[rule]:>8}")
    print(f"    {len(log.failures)} entries written to stg_error_log")
    return len(log.failures)


def read_failures(run_id):
    """Failures Data Quality logged for a run, as dicts."""
    with STAGING.connect() as con:
        rows = con.execute(sa.text(
            "SELECT tabla_origen, nro_fila, regla, accion "
            "FROM staging_dw.stg_error_log WHERE run_id = :r"),
            {"r": run_id}).mappings().all()
    return [dict(r) for r in rows]
