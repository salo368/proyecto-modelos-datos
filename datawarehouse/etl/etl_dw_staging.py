"""
Warehouse ETL, layers 1-4: Extract, Initial Staging, Data Quality and
Clean Staging.

    1 Extract/Publish   one extraction model per source (EXTRACTION_MODELS)
    2 Initial Staging   one table per source + column profile (stg_perfil)
    3 Data Quality      technical and business rules -> stg_error_log
    4 Clean Staging     stg_clean (accepted) / stg_rejected (rejected)

All 13 source tables are read exactly once per load, including those
the current model does not use (payments, cs_customer_products). The
dimension and fact processes read only from stg_clean.

Usage:
    python datawarehouse/etl/etl_dw_staging.py
"""
from collections import defaultdict

import pandas as pd
import sqlalchemy as sa

from common import (CLASSICMODELS, CUSTOMERSERVICE, DW, META, close_run,
                    insert, json_rows, log_execution, open_run)

PROCESS = "etl_dw_staging"

# ============================================================
# Layer 1 - Extract/Publish: one logical extraction model per source
# ============================================================
EXTRACTION_MODELS = {
    "classicmodels": {
        "engine": CLASSICMODELS,
        "initial_table": "stg_initial_classicmodels",
        "tables": ["customers", "employees", "offices", "products",
                   "productlines", "orders", "orderdetails", "payments"],
    },
    "customerservice": {
        "engine": CUSTOMERSERVICE,
        "initial_table": "stg_initial_customerservice",
        "tables": ["cs_customers", "cs_products", "cs_employees",
                   "cs_customer_calls", "cs_customer_products"],
    },
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

# ============================================================
# Layer 3 quality rules: rule -> (dq class, category, action).
#
# RECHAZADO sends the record to stg_rejected; ADVERTENCIA lets it
# through and only logs it. Names match dq_rule.rule_name.
# ============================================================
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


# ============================================================
# Layers 1 and 2 - Extract and Initial Staging
# ============================================================

def extract(run_id):
    print("\n[Layer 1] Extract/Publish")
    print("[Layer 2] Initial Staging")
    total = 0
    for source, model in EXTRACTION_MODELS.items():
        print(f"    Extraction model: {source}  ->  staging_dw.{model['initial_table']}")
        for table in model["tables"]:
            df = pd.read_sql(f"SELECT * FROM {table}", model["engine"])
            insert(model["initial_table"], [
                {"run_id": run_id, "tabla_origen": table,
                 "nro_fila": i, "payload": p}
                for i, p in enumerate(json_rows(df), 1)
            ])
            total += len(df)
            print(f"      {table:<22}{len(df):>6} rows")
    print(f"    {'TOTAL in Initial Staging':<28}{total:>6} rows")
    return total


def read_initial(run_id):
    """Re-read what landed; later layers start from here, not from the sources.

    Returns {table: (source, DataFrame)} with a _nro_fila column.
    """
    data = {}
    for source, model in EXTRACTION_MODELS.items():
        with DW.connect() as con:
            rows = con.execute(sa.text(
                f"SELECT tabla_origen, nro_fila, payload "
                f"FROM staging_dw.{model['initial_table']} "
                f"WHERE run_id = :r ORDER BY tabla_origen, nro_fila"),
                {"r": run_id}).fetchall()
        by_table = defaultdict(list)
        for table, row_number, payload in rows:
            by_table[table].append({"_nro_fila": row_number, **payload})
        for table, records in by_table.items():
            data[table] = (source, pd.DataFrame(records))
    return data


def profile(run_id, data):
    """Nulls, distinct values, min and max of every landed column."""
    print("\n    Profiling Initial Staging")
    records = []
    for table, (source, df) in data.items():
        for col in df.columns:
            if col == "_nro_fila":
                continue
            s = df[col]
            non_null = s.dropna()
            try:
                minimum = str(non_null.min()) if len(non_null) else None
                maximum = str(non_null.max()) if len(non_null) else None
            except TypeError:           # mixed-type column
                minimum = maximum = None
            records.append({
                "run_id": run_id, "fuente": source, "tabla_origen": table,
                "columna": col, "filas": len(s), "nulos": int(s.isna().sum()),
                # Native float: psycopg2 cannot adapt numpy.float64.
                "pct_nulos": float(round(100 * s.isna().mean(), 2)) if len(s) else 0.0,
                "distintos": int(s.nunique()),
                "minimo": (minimum or "")[:200] or None,
                "maximo": (maximum or "")[:200] or None,
            })
    insert("stg_perfil", records)
    with_nulls = sum(1 for r in records if r["nulos"] > 0)
    print(f"      {len(records)} columns profiled, {with_nulls} with nulls")


# ============================================================
# Layer 3 - Data Quality
# ============================================================

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


def data_quality(run_id, data):
    print("\n[Layer 3] Data Quality")
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


# ============================================================
# Layer 4 - Clean Staging
# ============================================================

def rejection_reasons(log):
    """{(table, row number): [rules]} for records that must be rejected.

    Only RECHAZADO failures remove a record; ADVERTENCIA only logs it.
    """
    reasons = defaultdict(list)
    for f in log.failures:
        if f["accion"] == "RECHAZADO":
            reasons[(f["tabla_origen"], f["nro_fila"])].append(f["regla"])
    return reasons


def split_clean_rejected(run_id, data, log):
    """Write accepted rows to stg_clean and rejected rows to stg_rejected."""
    print("\n[Layer 4] Clean Staging")
    reasons = rejection_reasons(log)

    total_clean = total_rejected = 0
    for table, (source, df) in data.items():
        clean, rejected = [], []
        body = df.drop(columns=["_nro_fila"])
        for payload, row_number in zip(json_rows(body), df["_nro_fila"]):
            key = (table, int(row_number))
            base = {"run_id": run_id, "fuente": source, "tabla_origen": table,
                    "nro_fila": int(row_number), "payload": payload}
            if key in reasons:
                rejected.append({**base, "motivos": ", ".join(sorted(set(reasons[key])))})
            else:
                clean.append(base)
        insert("stg_clean", clean)
        insert("stg_rejected", rejected)
        total_clean += len(clean)
        total_rejected += len(rejected)
        print(f"      {table:<22} clean {len(clean):>5}   rejected {len(rejected):>3}")
    print(f"    {'TOTAL':<22} clean {total_clean:>5}   rejected {total_rejected:>3}")
    return total_clean, total_rejected


if __name__ == "__main__":
    run_id = open_run("staging")
    print(f"Warehouse ETL, staging (layers 1-4) - run_id={run_id}")
    try:
        rows_read = extract(run_id)
        data = read_initial(run_id)
        profile(run_id, data)
        log = data_quality(run_id, data)
        n_clean, n_rejected = split_clean_rejected(run_id, data, log)
    except Exception as e:
        close_run(run_id, "ERROR")
        log_execution(PROCESS, "", "", run_id, 0, 0, 0, "ERROR", str(e)[:500])
        raise
    close_run(run_id, "OK")
    log_execution(
        PROCESS,
        "Capas 1 a 4: extrae las 13 tablas de las dos fuentes una sola vez, "
        "las perfila, evalua calidad tecnica y de negocio, y separa "
        "fisicamente limpios de rechazados.",
        "classicmodels (MySQL), customerservice (PostgreSQL)",
        run_id, rows_read, n_clean, n_rejected, "OK",
        quality_results=[(r, log.evaluated[r], log.failed[r]) for r in RULES],
    )
    print(f"\nStaging done. Read {rows_read}, clean {n_clean}, rejected {n_rejected}.")
