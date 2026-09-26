"""Reconcile the warehouse with the original sources.

Every record of the sources must be accounted for: either it is in the
warehouse or Data Quality rejected it. The rejected records are those of
the staging run the warehouse's facts were loaded from, which the
warehouse itself records in dim_lote_carga.

    Facts        source = warehouse + rejected, in rows and in the sums
                 of their measures. Facts are replaced on every load, so
                 a rejected line is not in the warehouse.
    Dimensions   every source member is in the warehouse or was rejected.
                 A member rejected now may still be in the warehouse from
                 an earlier load (dimensions keep their members), so it
                 counts once, as loaded.

Exits with status 1 if any check does not reconcile, which means the ETL
lost or duplicated data.

Usage:
    python datawarehouse/tests/validate_against_sources.py
"""
import os
import sys
from decimal import Decimal

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

CLASSICMODELS = sa.create_engine(os.getenv("CLASSICMODELS_URL"))
CUSTOMERSERVICE = sa.create_engine(os.getenv("CUSTOMERSERVICE_URL"))
STAGING = sa.create_engine(os.getenv("STAGING_URL"))
DW = sa.create_engine(os.getenv("DW_URL"))


def scalar(engine, sql):
    with engine.connect() as con:
        return con.execute(sa.text(sql)).scalar()


def keys(engine, sql):
    return set(pd.read_sql(sql, engine).itertuples(index=False, name=None))


def facts_staging_run():
    run = scalar(DW, """SELECT run_staging FROM dim_lote_carga WHERE proceso = 'hechos'
                        ORDER BY cargado_en DESC, lote_carga_key DESC LIMIT 1""")
    if run is None:
        sys.exit("The warehouse has no fact load. Run the pipeline first: python run_all.py")
    return run


def rejected(run):
    """{source table: DataFrame of the records Data Quality rejected}."""
    with STAGING.connect() as con:
        rows = con.execute(sa.text("""
            SELECT tabla_origen, payload FROM staging_dw.stg_rejected
             WHERE run_id = :r"""), {"r": run}).fetchall()
    by_table = {}
    for table, payload in rows:
        by_table.setdefault(table, []).append(payload)
    return {t: pd.DataFrame(p) for t, p in by_table.items()}


def rejected_keys(frames, table, *cols):
    df = frames.get(table)
    if df is None:
        return set()
    return set(df[list(cols)].itertuples(index=False, name=None))


def main():
    run = facts_staging_run()
    rej = rejected(run)
    lines = rej.get("orderdetails", pd.DataFrame(columns=["orderNumber", "quantityOrdered", "priceEach"]))
    rej_amount = sum((Decimal(str(q)) * Decimal(str(p))
                      for q, p in zip(lines["quantityOrdered"], lines["priceEach"])),
                     Decimal(0))

    # (check, source, warehouse, rejected) for the facts: source = warehouse + rejected.
    facts = [
        ("Total sales amount",
         scalar(CLASSICMODELS, "SELECT ROUND(SUM(quantityOrdered*priceEach),2) FROM orderdetails"),
         scalar(DW, "SELECT ROUND(SUM(monto_linea),2) FROM fact_ventas"),
         round(rej_amount, 2)),
        ("Units sold",
         scalar(CLASSICMODELS, "SELECT SUM(quantityOrdered) FROM orderdetails"),
         scalar(DW, "SELECT SUM(cantidad_ordenada) FROM fact_ventas"),
         int(lines["quantityOrdered"].sum())),
        ("Order lines",
         scalar(CLASSICMODELS, "SELECT COUNT(*) FROM orderdetails"),
         scalar(DW, "SELECT COUNT(*) FROM fact_ventas"),
         len(lines)),
        ("Service calls",
         scalar(CUSTOMERSERVICE, "SELECT COUNT(*) FROM cs_customer_calls"),
         scalar(DW, "SELECT COUNT(*) FROM fact_llamadas_servicio"),
         len(rej.get("cs_customer_calls", []))),
    ]

    # (check, source keys, warehouse keys, rejected keys) for members:
    # every source key is loaded or rejected. Special members (negative
    # keys, special_members.sql) do not come from the sources.
    members = [
        ("Distinct orders",
         keys(CLASSICMODELS, "SELECT DISTINCT orderNumber FROM orderdetails"),
         keys(DW, "SELECT DISTINCT numero_orden FROM fact_ventas"),
         rejected_keys(rej, "orderdetails", "orderNumber")),
        ("Customers",
         keys(CLASSICMODELS, "SELECT customerNumber FROM customers"),
         keys(DW, "SELECT numero_cliente FROM dim_cliente"),
         rejected_keys(rej, "customers", "customerNumber")),
        ("Products",
         keys(CLASSICMODELS, "SELECT productCode FROM products"),
         keys(DW, "SELECT codigo_producto FROM dim_producto"),
         rejected_keys(rej, "products", "productCode")),
        ("Offices",
         keys(CLASSICMODELS, "SELECT officeCode FROM offices"),
         keys(DW, "SELECT codigo_oficina FROM dim_oficina WHERE oficina_key > 0"),
         rejected_keys(rej, "offices", "officeCode")),
        ("Employees (both sources)",
         keys(CLASSICMODELS, "SELECT employeeNumber, 'classicmodels' FROM employees")
         | keys(CUSTOMERSERVICE, "SELECT employeenumber, 'customerservice' FROM cs_employees"),
         keys(DW, "SELECT numero_empleado, sistema_origen FROM dim_empleado WHERE empleado_key > 0"),
         {(k, "classicmodels") for (k,) in rejected_keys(rej, "employees", "employeeNumber")}
         | {(k, "customerservice") for (k,) in rejected_keys(rej, "cs_employees", "employeenumber")}),
    ]

    print(f"Rejected records come from staging run {run}, the one the facts were loaded from.\n")
    print(f"{'Check':<28}{'Source':>14}{'Warehouse':>14}{'Rejected':>12}   Status")
    print("-" * 82)
    all_ok = True
    for name, source, warehouse, rejected_n in facts:
        ok = abs(Decimal(str(source)) - Decimal(str(warehouse)) - Decimal(str(rejected_n))) < Decimal("0.005")
        all_ok &= ok
        print(f"{name:<28}{source:>14}{warehouse:>14}{rejected_n:>12}   {'OK' if ok else 'DIFFERS'}")
    for name, source, warehouse, rejected_k in members:
        loaded = source & warehouse
        only_rejected = (source & rejected_k) - warehouse
        missing = source - warehouse - rejected_k
        ok = not missing
        all_ok &= ok
        print(f"{name:<28}{len(source):>14}{len(loaded):>14}{len(only_rejected):>12}   "
              f"{'OK' if ok else 'DIFFERS'}")
        if missing:
            print(f"    neither loaded nor rejected: {sorted(missing)[:10]}")

    n_rejected = sum(len(df) for df in rej.values())
    print()
    print(f"All checks passed: every source record is loaded or rejected "
          f"({n_rejected} rejected in staging run {run})." if all_ok
          else "Some checks do not reconcile: review the ETL.")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
