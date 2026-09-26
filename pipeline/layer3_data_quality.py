"""
Layer 3 - Data Quality.

Technical checks (missing or invalid data) and business checks
(referential integrity, inaccurate data, inconsistent definitions) on
what landed in Initial Staging. Every failure becomes a row of the
bad-transactions log, with the action the rule dictates:

    RECHAZADO    the record cannot continue; layer 4 sends it to stg_rejected
    ADVERTENCIA  the record continues; the anomaly is only logged

    Input   stg_initial_* (layer 2)
    Output  stg_error_log
    Reader  read_failures(run_id), used by layer 4
"""
from collections import defaultdict

import pandas as pd
import sqlalchemy as sa

from common import META, STAGING, insert
from layer2_initial_staging import read_initial

# Rule -> (dq class, category, action). Names match dq_rule.rule_name
# in the metadata repository.
RULES = {
    # --- technical checks ---
    "campos_obligatorios":    ("TECNICA", "CAMPO_FALTANTE",   "RECHAZADO"),
    "tipo_de_dato_valido":    ("TECNICA", "DATO_INVALIDO",    "RECHAZADO"),
    "formato_email":          ("TECNICA", "DATO_INVALIDO",    "ADVERTENCIA"),
    # --- business checks ---
    "integridad_referencial": ("NEGOCIO", "INTEGRIDAD_REFERENCIAL", "RECHAZADO"),
    "valores_positivos":      ("NEGOCIO", "DATO_INEXACTO",    "RECHAZADO"),
    "secuencia_de_fechas":    ("NEGOCIO", "DATO_INEXACTO",    "RECHAZADO"),
    "envio_consistente_con_estado": ("NEGOCIO", "DATO_INEXACTO", "RECHAZADO"),
    "precio_sugerido_coherente":    ("NEGOCIO", "DATO_INEXACTO", "ADVERTENCIA"),
    "cliente_con_vendedor":   ("NEGOCIO", "CAMPO_FALTANTE",   "ADVERTENCIA"),
    "consistencia_entre_fuentes_cliente":
                              ("NEGOCIO", "DEFINICION_INCONSISTENTE", "ADVERTENCIA"),
    "consistencia_entre_fuentes_producto":
                              ("NEGOCIO", "DEFINICION_INCONSISTENTE", "ADVERTENCIA"),
}

# Columns that identify a record in the error log. cs_customer_calls
# has no primary key in its source, so its references plus the date
# are used instead.
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


def technical_checks(data, log):
    """Missing and invalid data."""
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
    # (child table, column, parent table, parent column, description)
    references = [
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
    counted = set()
    for child, col, parent, parent_col, desc in references:
        if child not in data or parent not in data:
            continue
        source, df = data[child]
        valid = keys(parent, parent_col)
        if child not in counted:
            log.check("integridad_referencial", len(df))
            counted.add(child)
        for _, row in df.iterrows():
            v = row.get(col)
            if pd.notna(v) and v not in valid:
                log.fail("integridad_referencial", source, child, row,
                         f"{col}={v}: {desc}")

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


def run(run_id):
    print("\n[Layer 3] Data Quality")
    data = read_initial(run_id)
    log = QualityLog()
    technical_checks(data, log)
    business_checks(data, log)

    insert("stg_error_log", [{"run_id": run_id, **f} for f in log.failures])

    print(f"    {'Rule':<38}{'Class':<9}{'Action':<13}{'Checked':>9}{'Failed':>8}")
    for rule, (dq_class, _, action) in RULES.items():
        print(f"    {rule:<38}{dq_class:<9}{action:<13}"
              f"{log.evaluated[rule]:>9}{log.failed[rule]:>8}")
    print(f"    {len(log.failures)} entries written to stg_error_log")
    return log


def read_failures(run_id):
    """Failures Data Quality logged for a run, as dicts."""
    with STAGING.connect() as con:
        rows = con.execute(sa.text(
            "SELECT tabla_origen, nro_fila, regla, accion "
            "FROM staging_dw.stg_error_log WHERE run_id = :r"),
            {"r": run_id}).mappings().all()
    return [dict(r) for r in rows]
