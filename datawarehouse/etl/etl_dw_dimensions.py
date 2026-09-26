"""
Warehouse ETL, layers 5-7 for the dimensions.

Reads the latest successful Clean Staging run (never the sources),
conforms each subject area, publishes the load-ready rows and reloads
the dimension tables:

    Area          Target             Operations
    Tiempo        dim_tiempo         generated
    Organizacion  dim_oficina        projection
    Ventas        dim_estado_orden   distinct values
    Cliente       dim_cliente        cross-source join, address merge
    Producto      dim_producto       join with productlines, cross-source join
    Empleado      dim_empleado       union of both sources, composite key

Usage:
    python datawarehouse/etl/etl_dw_dimensions.py
"""
from datetime import date, timedelta

import pandas as pd

from common import (close_run, insert, json_rows, last_successful_staging_run,
                    load_atomic, log_execution, open_run, publish_load_ready,
                    read_clean, read_load_ready)

PROCESS = "etl_dw_dimensions"

MONTH_NAMES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
               "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DAY_NAMES = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

# Fixed load order so the output is always the same.
LOAD_ORDER = ["dim_tiempo", "dim_estado_orden", "dim_oficina",
              "dim_cliente", "dim_producto", "dim_empleado"]

# Order statuses that do not count as a closed sale.
NON_EFFECTIVE_STATUSES = {"Cancelled", "Disputed", "On Hold"}

_quality_results = []   # (rule, evaluated, failed) -> dq_result


def record_quality(rule, evaluated, failed, message):
    _quality_results.append((rule, evaluated, failed))
    print(f"        [quality] {message}")


def publish_transform(run_id, area, target, df, operations):
    insert("stg_transform", [
        {"run_id": run_id, "area_conformada": area, "objetivo": target,
         "nro_fila": i, "payload": p, "operaciones": operations}
        for i, p in enumerate(json_rows(df), 1)
    ])
    print(f"    {area:<13}{target:<18}{len(df):>6}  {operations}")


# ============================================================
# Layer 5 - Transformation, one function per subject area
# ============================================================

def area_time(run_id):
    """Generated calendar covering 2003-2005, the span of sales and calls."""
    rows, d, end = [], date(2003, 1, 1), date(2005, 12, 31)
    while d <= end:
        rows.append({
            "tiempo_key": int(d.strftime("%Y%m%d")), "fecha": d,
            "anio": d.year, "trimestre": (d.month - 1) // 3 + 1, "mes": d.month,
            "nombre_mes": MONTH_NAMES[d.month - 1], "dia": d.day,
            "dia_semana": d.isoweekday(), "nombre_dia": DAY_NAMES[d.isoweekday() - 1],
            "es_fin_semana": d.isoweekday() >= 6, "anio_mes": d.strftime("%Y-%m"),
        })
        d += timedelta(days=1)
    publish_transform(run_id, "Tiempo", "dim_tiempo", pd.DataFrame(rows),
                      "generacion")


def area_organization(run_id, staging_run):
    offices = read_clean(staging_run, "offices").rename(columns={
        "officeCode": "codigo_oficina", "city": "ciudad", "country": "pais",
        "state": "region", "territory": "territorio"})
    offices = offices[["codigo_oficina", "ciudad", "pais", "region", "territorio"]]
    publish_transform(run_id, "Organizacion", "dim_oficina", offices, "proyeccion")


def area_sales(run_id, staging_run):
    """Order status catalogue. es_efectiva flags closed sales; every order
    is loaded and reports decide whether to exclude the rest."""
    orders = read_clean(staging_run, "orders")
    statuses = pd.DataFrame([
        {"estado": s, "es_efectiva": s not in NON_EFFECTIVE_STATUSES}
        for s in sorted(orders["status"].unique())
    ])
    n_non_effective = int((~statuses["es_efectiva"]).sum())
    record_quality("estado_orden_no_efectivo", len(statuses), n_non_effective,
                   f"statuses that are not a closed sale: {n_non_effective} of {len(statuses)}")
    publish_transform(run_id, "Ventas", "dim_estado_orden", statuses,
                      "agregacion (valores distintos)")


def area_customer(run_id, staging_run):
    """Conformed customer: classicmodels is authoritative (it has every
    attribute); customerservice only contributes a presence flag."""
    cm = read_clean(staging_run, "customers").rename(columns={
        "customerNumber": "numero_cliente", "customerName": "nombre_cliente",
        "contactFirstName": "contacto_nombre", "contactLastName": "contacto_apellido",
        "phone": "telefono", "city": "ciudad", "state": "estado_region",
        "postalCode": "codigo_postal", "country": "pais",
        "creditLimit": "limite_credito"})

    # addressLine2 is mostly null, so both lines are merged into one field.
    empty_line2 = int(cm["addressLine2"].isna().sum())
    cm["direccion_completa"] = (
        cm["addressLine1"].fillna("")
        + cm["addressLine2"].fillna("").apply(lambda x: f", {x}" if x else "")
    ).str.strip(", ")
    record_quality("cliente_direccion_linea2_nula", len(cm), empty_line2,
                   f"addressLine2 null in {empty_line2} of {len(cm)} -> merged")

    cs = read_clean(staging_run, "cs_customers")
    cm["presente_en_ventas"] = True
    cm["presente_en_servicio"] = cm["numero_cliente"].isin(cs["customernumber"])
    in_both = int(cm["presente_en_servicio"].sum())
    record_quality("cliente_conformidad_fuentes", len(cm), len(cm) - in_both,
                   f"customers present in both sources: {in_both} of {len(cm)}")

    cm = cm[["numero_cliente", "nombre_cliente", "contacto_nombre",
             "contacto_apellido", "telefono", "direccion_completa", "ciudad",
             "estado_region", "codigo_postal", "pais", "limite_credito",
             "presente_en_ventas", "presente_en_servicio"]]
    publish_transform(run_id, "Cliente", "dim_cliente", cm,
                      "join entre fuentes, consolidacion de direccion")


def area_product(run_id, staging_run):
    """Conformed product with its product line denormalised."""
    products = read_clean(staging_run, "products")
    lines = read_clean(staging_run, "productlines")

    # htmlDescription and image are 100% null: staged, but not modelled.
    record_quality("productline_columnas_vacias", 2, 2,
                   "htmlDescription and image (100% null) are not modelled")
    lines = lines[["productLine", "textDescription"]]

    products = products.merge(lines, on="productLine", how="left").rename(columns={
        "productCode": "codigo_producto", "productName": "nombre_producto",
        "productLine": "linea_producto", "textDescription": "descripcion_linea",
        "productScale": "escala", "productVendor": "proveedor",
        "buyPrice": "precio_compra", "MSRP": "precio_msrp"})
    cs = read_clean(staging_run, "cs_products")
    products["presente_en_ventas"] = True
    products["presente_en_servicio"] = products["codigo_producto"].isin(cs["productcode"])
    in_both = int(products["presente_en_servicio"].sum())
    record_quality("producto_conformidad_fuentes", len(products), len(products) - in_both,
                   f"products present in both sources: {in_both} of {len(products)}")

    products = products[["codigo_producto", "nombre_producto", "linea_producto",
                         "descripcion_linea", "escala", "proveedor", "precio_compra",
                         "precio_msrp", "presente_en_ventas", "presente_en_servicio"]]
    publish_transform(run_id, "Producto", "dim_producto", products,
                      "join con productlines, join entre fuentes")


def area_employee(run_id, staging_run):
    """Non-conformed employee dimension.

    Sales reps (classicmodels) and call-center agents (customerservice)
    are different people with independent numbering. The composite
    business key (numero_empleado, sistema_origen) keeps them apart even
    if the two numberings ever overlap.
    """
    reps = read_clean(staging_run, "employees").rename(columns={
        "employeeNumber": "numero_empleado", "firstName": "nombre",
        "lastName": "apellido", "jobTitle": "cargo", "officeCode": "numero_oficina"})
    reps["sistema_origen"] = "classicmodels"
    agents = read_clean(staging_run, "cs_employees").rename(columns={
        "employeenumber": "numero_empleado", "firstname": "nombre",
        "lastname": "apellido"})
    agents["sistema_origen"] = "customerservice"
    agents["cargo"] = "Agente de Servicio al Cliente"
    agents["numero_oficina"] = None

    shared = set(reps["numero_empleado"]) & set(agents["numero_empleado"])
    record_quality("empleado_conformidad_fuentes", len(reps) + len(agents), len(shared),
                   f"employee numbers shared by both sources: {len(shared)} "
                   f"-> composite key (numero_empleado, sistema_origen)")

    cols = ["numero_empleado", "sistema_origen", "nombre", "apellido",
            "email", "cargo", "numero_oficina"]
    employees = pd.concat([reps[cols], agents[cols]], ignore_index=True)
    publish_transform(run_id, "Empleado", "dim_empleado", employees,
                      "union de fuentes, llave compuesta")


# ============================================================
# Layers 6 and 7 - Load-Ready Publish and Load
# ============================================================

def publish_and_load(run_id):
    print("\n[Layer 6] Load-Ready Publish (DIMENSIONES)")
    for target, n in publish_load_ready(run_id, "DIMENSIONES", LOAD_ORDER).items():
        print(f"    {target:<18}{n:>6} rows")

    # Load reads what Load-Ready left, and replaces the six dimensions in a
    # single transaction: all or nothing. The model tables are fully
    # reloaded each time; the history lives in staging, which is never
    # truncated.
    print("[Layer 7] Load (una sola transaccion)")
    frames = read_load_ready(run_id, LOAD_ORDER)
    total = load_atomic(frames)
    for target, df in frames.items():
        print(f"    {target:<18}{len(df):>6} rows")
    return total


if __name__ == "__main__":
    staging_run = last_successful_staging_run()
    run_id = open_run("dimensiones", source_run=staging_run)
    print(f"Warehouse ETL, dimensions (layers 5-7) - run_id={run_id}, "
          f"reading Clean Staging of run {staging_run}")
    try:
        print("\n[Layer 5] Transformation")
        area_time(run_id)
        area_organization(run_id, staging_run)
        area_sales(run_id, staging_run)
        area_customer(run_id, staging_run)
        area_product(run_id, staging_run)
        area_employee(run_id, staging_run)
        written = publish_and_load(run_id)
    except Exception as e:
        close_run(run_id, "ERROR")
        log_execution(PROCESS, "", "", run_id, 0, 0, 0, "ERROR", str(e)[:500])
        raise
    close_run(run_id, "OK")
    log_execution(
        PROCESS,
        "Capas 5 a 7 para el modelo de dimensiones: conforma por area "
        "tematica desde Clean Staging y carga las seis dimensiones.",
        f"staging_dw.stg_clean (run {staging_run}); las fuentes no se releen",
        run_id, written, written, 0, "OK", quality_results=_quality_results,
    )
    print(f"\nDimensions loaded: {written} rows.")
