"""
Layer 5 - Transformation, facts.

Conforms sales and service from Clean Staging: joins, surrogate-key
lookups against the dimensions already loaded in the EDW, and calculated
measures. It must run after the dimension branch has been loaded.

    Area      Target                  Operations
    Ventas    fact_ventas             join of 5 tables, 5 key lookups, measures
    Servicio  fact_llamadas_servicio  3 key lookups, measures

    Input   stg_clean (layer 4); dim_* (EDW) for the key lookups
    Output  stg_transform; stg_dq_resumen (profiling findings handled here)
"""
import pandas as pd

from common import DW, write_payload, write_quality
from layer4_clean_staging import read_clean

TARGETS = ["fact_ventas", "fact_llamadas_servicio"]

# Special members of dim_empleado and dim_oficina, created by
# datawarehouse/edw/special_members.sql. A sale points to them instead of
# carrying a NULL key.
UNKNOWN = -1        # 'Desconocido': the sales rep did not reach the warehouse
NOT_ASSIGNED = -2   # 'Sin asignar': the customer has no sales rep

_quality_results = []   # (rule, evaluated, failed) -> stg_dq_resumen


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


def time_keys(dates):
    """tiempo_key (YYYYMMDD) of each date, NA when dim_tiempo lacks it.

    The key is computed rather than looked up, so without this check a
    date outside the calendar would only surface as a foreign-key error
    inside Load.
    """
    loaded = set(pd.read_sql("SELECT tiempo_key FROM dim_tiempo", DW)["tiempo_key"])
    keys = pd.to_datetime(dates, errors="coerce").dt.strftime("%Y%m%d").astype("Int64")
    return keys.where(keys.isin(loaded))


def check_special_members(keys, table):
    """Stop if the warehouse lacks the special members the facts point to."""
    missing = {UNKNOWN, NOT_ASSIGNED} - set(keys.values())
    if missing:
        raise RuntimeError(
            f"{table} lacks the special members {sorted(missing)}.\n"
            "Run first: python tools/run_sql.py datawarehouse/edw/special_members.sql")


def check_keys(df, required, target):
    """Stop the load instead of writing a fact with an unresolved key."""
    orphans = int(df[required].isna().any(axis=1).sum())
    if orphans:
        per_key = df[required].isna().sum()
        detail = ", ".join(f"{c}: {int(n)}" for c, n in per_key.items() if n)
        raise RuntimeError(
            f"{orphans} rows of {target} could not resolve a required key "
            f"({detail}). Check that the dimensions are complete.")


def publish_transform(run_id, area, target, df, operations):
    n = write_payload("stg_transform", run_id, df, area_conformada=area,
                      objetivo=target, operaciones=operations)
    print(f"    {area:<10}{target:<24}{n:>6}  {operations}")


# ============================================================
# One function per subject area
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

    df["tiempo_key"] = time_keys(df["orderDate"])
    df["cliente_key"] = df["customerNumber"].map(customer_keys)
    df["producto_key"] = df["productCode"].map(product_keys)
    df["estado_key"] = df["status"].map(status_keys)

    # Sales reps always come from classicmodels, and the office is the
    # rep's. A customer without a rep points to 'Sin asignar'; one whose
    # rep does not exist or was rejected (both warnings in Data Quality),
    # to 'Desconocido'.
    check_special_members(employee_keys, "dim_empleado")
    check_special_members(office_keys, "dim_oficina")
    no_rep = df["salesRepEmployeeNumber"].isna()
    df["empleado_key"] = df["salesRepEmployeeNumber"].map(
        lambda n: employee_keys.get((n, "classicmodels"), UNKNOWN))
    df["oficina_key"] = df["officeCode"].map(office_keys).fillna(UNKNOWN)
    df.loc[no_rep, ["empleado_key", "oficina_key"]] = NOT_ASSIGNED
    special = int((df["empleado_key"] < 0).sum())
    record_quality("venta_vendedor_no_resuelto", len(df), special,
                   f"lines without a resolved sales rep: {special} of {len(df)} "
                   f"-> 'Sin asignar' / 'Desconocido'")

    out = df.rename(columns={
        "orderNumber": "numero_orden", "orderLineNumber": "numero_linea",
        "quantityOrdered": "cantidad_ordenada", "priceEach": "precio_unitario",
        "MSRP": "precio_msrp"})[[
        "tiempo_key", "cliente_key", "producto_key", "empleado_key",
        "oficina_key", "estado_key", "numero_orden", "numero_linea",
        "cantidad_ordenada", "precio_unitario", "monto_linea",
        "costo_linea", "margen_linea", "precio_msrp", "dias_hasta_envio"]].copy()

    check_keys(out, ["tiempo_key", "cliente_key", "producto_key", "empleado_key",
                     "oficina_key", "estado_key"], "fact_ventas")
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

    df["tiempo_key"] = time_keys(df["date"])
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


def run(run_id, staging_run):
    """Transform both facts; returns the rows written. The quality
    findings go to stg_dq_resumen, and from there to dq_result."""
    print("\n[Layer 5] Transformation (facts)")
    _quality_results.clear()
    rows = area_sales(run_id, staging_run) + area_service(run_id, staging_run)
    write_quality(run_id, 5, _quality_results)
    return rows
