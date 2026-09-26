"""
Warehouse ETL, layers 5-7 for the facts.

Reads the same Clean Staging run as the dimension process and resolves
surrogate keys against the dimensions already loaded, so it must run
after etl_dw_dimensions.py.

    Area      Target                  Operations
    Ventas    fact_ventas             join of 5 tables, 5 key lookups, measures
    Servicio  fact_llamadas_servicio  3 key lookups, measures

Usage:
    python datawarehouse/etl/etl_dw_facts.py
"""
import pandas as pd

from common import (DW, close_run, insert, json_rows, last_successful_staging_run,
                    load_atomic, log_execution, open_run, publish_load_ready,
                    read_clean, read_load_ready)

PROCESS = "etl_dw_facts"
LOAD_ORDER = ["fact_ventas", "fact_llamadas_servicio"]

_quality_results = []   # (rule, evaluated, failed) -> dq_result


def record_quality(rule, evaluated, failed, message):
    _quality_results.append((rule, evaluated, failed))
    print(f"        [quality] {message}")


def surrogate_key_map(table, business_key, surrogate_key, extra=None):
    """Lookup table business key -> surrogate key.

    With `extra` the key is a tuple; dim_empleado needs it because its
    business key is (numero_empleado, sistema_origen).
    """
    cols = f"{business_key}, {surrogate_key}" + (f", {extra}" if extra else "")
    df = pd.read_sql(f"SELECT {cols} FROM {table}", DW)
    if extra:
        return {(r[business_key], r[extra]): r[surrogate_key]
                for _, r in df.iterrows()}
    return dict(zip(df[business_key], df[surrogate_key]))


def check_keys(df, required, target):
    """Stop the load instead of writing a fact with an unresolved key."""
    orphans = int(df[required].isna().any(axis=1).sum())
    if orphans:
        raise RuntimeError(
            f"{orphans} rows of {target} could not resolve a required key. "
            f"Check that the dimensions are complete.")


def publish_transform(run_id, area, target, df, operations):
    insert("stg_transform", [
        {"run_id": run_id, "area_conformada": area, "objetivo": target,
         "nro_fila": i, "payload": p, "operaciones": operations}
        for i, p in enumerate(json_rows(df), 1)
    ])
    print(f"    {area:<10}{target:<24}{len(df):>6}  {operations}")


# ============================================================
# Layer 5 - Transformation
# ============================================================

def area_sales(run_id, staging_run):
    """fact_ventas: one row per order line."""
    details = read_clean(staging_run, "orderdetails")
    orders = read_clean(staging_run, "orders")
    products = read_clean(staging_run, "products")
    customers = read_clean(staging_run, "customers")
    employees = read_clean(staging_run, "employees")

    # orders.comments is free text with no analytical use: not modelled.
    no_comments = int(orders["comments"].isna().sum())
    record_quality("orden_comentarios_nulos", len(orders), no_comments,
                   f"orders.comments null in {no_comments} of {len(orders)} "
                   f"-> not modelled")

    # --- Joins ---
    df = (details
          .merge(orders, on="orderNumber", how="inner")
          .merge(products[["productCode", "buyPrice", "MSRP"]], on="productCode", how="left")
          .merge(customers[["customerNumber", "salesRepEmployeeNumber"]],
                 on="customerNumber", how="left")
          .merge(employees[["employeeNumber", "officeCode"]],
                 left_on="salesRepEmployeeNumber", right_on="employeeNumber",
                 how="left"))

    # --- Calculated measures ---
    df["monto_linea"] = (df["quantityOrdered"] * df["priceEach"]).round(2)
    df["costo_linea"] = (df["quantityOrdered"] * df["buyPrice"]).round(2)
    df["margen_linea"] = (df["monto_linea"] - df["costo_linea"]).round(2)
    ordered = pd.to_datetime(df["orderDate"], errors="coerce")
    shipped = pd.to_datetime(df["shippedDate"], errors="coerce")
    df["dias_hasta_envio"] = (shipped - ordered).dt.days

    # Orders not shipped yet have no shippedDate; the measure stays NULL.
    # (Data Quality already guarantees no 'Shipped' order lacks the date.)
    not_shipped = int(df["dias_hasta_envio"].isna().sum())
    record_quality("orden_fecha_envio_nula", len(df), not_shipped,
                   f"lines of orders not shipped yet: {not_shipped} of {len(df)} "
                   f"-> dias_hasta_envio NULL")

    # --- Lookups: business key -> surrogate key ---
    customer_keys = surrogate_key_map("dim_cliente", "numero_cliente", "cliente_key")
    product_keys = surrogate_key_map("dim_producto", "codigo_producto", "producto_key")
    office_keys = surrogate_key_map("dim_oficina", "codigo_oficina", "oficina_key")
    status_keys = surrogate_key_map("dim_estado_orden", "estado", "estado_key")
    employee_keys = surrogate_key_map("dim_empleado", "numero_empleado", "empleado_key",
                                      extra="sistema_origen")

    df["tiempo_key"] = ordered.dt.strftime("%Y%m%d").astype("Int64")
    df["cliente_key"] = df["customerNumber"].map(customer_keys)
    df["producto_key"] = df["productCode"].map(product_keys)
    df["oficina_key"] = df["officeCode"].map(office_keys)
    df["estado_key"] = df["status"].map(status_keys)
    # Sales reps always come from classicmodels. Customers without a rep
    # (logged as a warning in Data Quality) keep empleado_key and
    # oficina_key NULL, which the model allows.
    df["empleado_key"] = df["salesRepEmployeeNumber"].map(
        lambda n: employee_keys.get((n, "classicmodels")) if pd.notna(n) else None)

    out = df.rename(columns={
        "orderNumber": "numero_orden", "orderLineNumber": "numero_linea",
        "quantityOrdered": "cantidad_ordenada", "priceEach": "precio_unitario",
        "MSRP": "precio_msrp"})[[
        "tiempo_key", "cliente_key", "producto_key", "empleado_key",
        "oficina_key", "estado_key", "numero_orden", "numero_linea",
        "cantidad_ordenada", "precio_unitario", "monto_linea",
        "costo_linea", "margen_linea", "precio_msrp", "dias_hasta_envio"]].copy()

    check_keys(out, ["tiempo_key", "cliente_key", "producto_key", "estado_key"],
               "fact_ventas")
    for c in ["cliente_key", "producto_key", "empleado_key", "oficina_key",
              "estado_key", "dias_hasta_envio"]:
        out[c] = out[c].astype("Int64")

    publish_transform(run_id, "Ventas", "fact_ventas", out,
                      "join (5 tablas), lookup (5 dimensiones), calculo de medidas")
    return len(out)


def area_service(run_id, staging_run):
    """fact_llamadas_servicio: one row per call."""
    df = read_clean(staging_run, "cs_customer_calls")

    customer_keys = surrogate_key_map("dim_cliente", "numero_cliente", "cliente_key")
    product_keys = surrogate_key_map("dim_producto", "codigo_producto", "producto_key")
    employee_keys = surrogate_key_map("dim_empleado", "numero_empleado", "empleado_key",
                                      extra="sistema_origen")

    df["tiempo_key"] = pd.to_datetime(df["date"]).dt.strftime("%Y%m%d").astype("Int64")
    df["cliente_key"] = df["customernumber"].map(customer_keys)
    df["producto_key"] = df["productcode"].map(product_keys)
    # Agents always come from customerservice, never from the sales reps.
    df["empleado_key"] = df["employeenumber"].map(
        lambda n: employee_keys.get((n, "customerservice")))
    df["texto_llamada"] = df["text"]
    df["cantidad_llamadas"] = 1
    df["longitud_texto"] = df["text"].fillna("").str.len()

    out = df[["tiempo_key", "cliente_key", "producto_key", "empleado_key",
              "texto_llamada", "cantidad_llamadas", "longitud_texto"]].copy()
    check_keys(out, ["tiempo_key", "cliente_key", "producto_key", "empleado_key"],
               "fact_llamadas_servicio")
    for c in ["cliente_key", "producto_key", "empleado_key"]:
        out[c] = out[c].astype("Int64")

    publish_transform(run_id, "Servicio", "fact_llamadas_servicio", out,
                      "lookup (3 dimensiones), calculo de medidas")
    return len(out)


# ============================================================
# Layers 6 and 7 - Load-Ready Publish and Load
# ============================================================

def publish_and_load(run_id):
    print("\n[Layer 6] Load-Ready Publish (HECHOS)")
    for target, n in publish_load_ready(run_id, "HECHOS", LOAD_ORDER).items():
        print(f"    {target:<24}{n:>6} rows")

    # Load reads what Load-Ready left, and replaces both fact tables in a
    # single transaction: all or nothing.
    print("[Layer 7] Load (una sola transaccion)")
    frames = read_load_ready(run_id, LOAD_ORDER)
    total = load_atomic(frames)
    for target, df in frames.items():
        print(f"    {target:<24}{len(df):>6} rows")
    return total


if __name__ == "__main__":
    staging_run = last_successful_staging_run()
    run_id = open_run("hechos", source_run=staging_run)
    print(f"Warehouse ETL, facts (layers 5-7) - run_id={run_id}, "
          f"reading Clean Staging of run {staging_run}")
    try:
        print("\n[Layer 5] Transformation")
        rows_read = area_sales(run_id, staging_run) + area_service(run_id, staging_run)
        written = publish_and_load(run_id)
    except Exception as e:
        close_run(run_id, "ERROR")
        log_execution(PROCESS, "", "", run_id, 0, 0, 0, "ERROR", str(e)[:500])
        raise
    close_run(run_id, "OK")
    log_execution(
        PROCESS,
        "Capas 5 a 7 para el modelo de hechos: conforma ventas y servicio "
        "desde Clean Staging, resuelve llaves subrogadas y carga los dos "
        "hechos.",
        f"staging_dw.stg_clean (run {staging_run}); las fuentes no se releen",
        run_id, rows_read, written, 0, "OK", quality_results=_quality_results,
    )
    print(f"\nFacts loaded: {written} rows.")
