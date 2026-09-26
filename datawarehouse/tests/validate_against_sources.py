"""Compare warehouse totals against the original sources.

Exits with status 1 if any check differs, which means the ETL lost or
duplicated data.

Usage:
    python datawarehouse/tests/validate_against_sources.py
"""
import os
import sys

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

CLASSICMODELS = sa.create_engine(os.getenv("CLASSICMODELS_URL"))
CUSTOMERSERVICE = sa.create_engine(os.getenv("CUSTOMERSERVICE_URL"))
DW = sa.create_engine(os.getenv("DW_URL"))


def scalar(engine, sql):
    return pd.read_sql(sql, engine).iloc[0, 0]


CHECKS = [
    ("Total sales amount",
     scalar(CLASSICMODELS, "SELECT ROUND(SUM(quantityOrdered*priceEach),2) FROM orderdetails"),
     scalar(DW, "SELECT ROUND(SUM(monto_linea),2) FROM fact_ventas")),

    ("Units sold",
     scalar(CLASSICMODELS, "SELECT SUM(quantityOrdered) FROM orderdetails"),
     scalar(DW, "SELECT SUM(cantidad_ordenada) FROM fact_ventas")),

    ("Order lines",
     scalar(CLASSICMODELS, "SELECT COUNT(*) FROM orderdetails"),
     scalar(DW, "SELECT COUNT(*) FROM fact_ventas")),

    ("Distinct orders",
     scalar(CLASSICMODELS, "SELECT COUNT(DISTINCT orderNumber) FROM orderdetails"),
     scalar(DW, "SELECT COUNT(DISTINCT numero_orden) FROM fact_ventas")),

    ("Service calls",
     scalar(CUSTOMERSERVICE, "SELECT COUNT(*) FROM cs_customer_calls"),
     scalar(DW, "SELECT COUNT(*) FROM fact_llamadas_servicio")),

    ("Customers",
     scalar(CLASSICMODELS, "SELECT COUNT(*) FROM customers"),
     scalar(DW, "SELECT COUNT(*) FROM dim_cliente")),

    ("Products",
     scalar(CLASSICMODELS, "SELECT COUNT(*) FROM products"),
     scalar(DW, "SELECT COUNT(*) FROM dim_producto")),

    ("Offices",
     scalar(CLASSICMODELS, "SELECT COUNT(*) FROM offices"),
     scalar(DW, "SELECT COUNT(*) FROM dim_oficina")),

    ("Employees (both sources)",
     scalar(CLASSICMODELS, "SELECT COUNT(*) FROM employees")
     + scalar(CUSTOMERSERVICE, "SELECT COUNT(*) FROM cs_employees"),
     scalar(DW, "SELECT COUNT(*) FROM dim_empleado")),
]

print(f"{'Check':<28}{'Source':>18}{'Warehouse':>18}   Status")
print("-" * 76)
all_ok = True
for name, source, warehouse in CHECKS:
    ok = float(source) == float(warehouse)
    all_ok &= ok
    print(f"{name:<28}{source:>18}{warehouse:>18}   {'OK' if ok else 'DIFFERS'}")

print()
print("All checks passed." if all_ok else "Some checks differ: review the ETL.")
sys.exit(0 if all_ok else 1)
