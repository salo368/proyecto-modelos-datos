"""Compara los totales del almacen contra las fuentes originales.

Si alguna prueba dice DIFIERE, el ETL perdio o duplico datos y hay que
arreglarlo antes de entregar.

Uso:
    python datawarehouse/queries/validacion.py
"""
import os

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

MYSQL = sa.create_engine(os.getenv("URL_MYSQLDATABASE"))
PG    = sa.create_engine(os.getenv("DATABASE_URL"))
DW    = sa.create_engine(os.getenv("DW_URL"))


def uno(engine, sql):
    return pd.read_sql(sql, engine).iloc[0, 0]


PRUEBAS = [
    ("Monto total vendido",
     uno(MYSQL, "SELECT ROUND(SUM(quantityOrdered*priceEach),2) FROM orderdetails"),
     uno(DW,    "SELECT ROUND(SUM(monto_linea),2) FROM fact_ventas")),

    ("Unidades vendidas",
     uno(MYSQL, "SELECT SUM(quantityOrdered) FROM orderdetails"),
     uno(DW,    "SELECT SUM(cantidad_ordenada) FROM fact_ventas")),

    ("Lineas de orden",
     uno(MYSQL, "SELECT COUNT(*) FROM orderdetails"),
     uno(DW,    "SELECT COUNT(*) FROM fact_ventas")),

    ("Ordenes distintas",
     uno(MYSQL, "SELECT COUNT(DISTINCT orderNumber) FROM orderdetails"),
     uno(DW,    "SELECT COUNT(DISTINCT numero_orden) FROM fact_ventas")),

    ("Llamadas de servicio",
     uno(PG,    "SELECT COUNT(*) FROM cs_customer_calls"),
     uno(DW,    "SELECT COUNT(*) FROM fact_llamadas_servicio")),

    ("Clientes",
     uno(MYSQL, "SELECT COUNT(*) FROM customers"),
     uno(DW,    "SELECT COUNT(*) FROM dim_cliente")),

    ("Productos",
     uno(MYSQL, "SELECT COUNT(*) FROM products"),
     uno(DW,    "SELECT COUNT(*) FROM dim_producto")),

    ("Oficinas",
     uno(MYSQL, "SELECT COUNT(*) FROM offices"),
     uno(DW,    "SELECT COUNT(*) FROM dim_oficina")),

    ("Empleados (ambas fuentes)",
     uno(MYSQL, "SELECT COUNT(*) FROM employees")
     + uno(PG,  "SELECT COUNT(*) FROM cs_employees"),
     uno(DW,    "SELECT COUNT(*) FROM dim_empleado")),
]

print(f"{'Prueba':<28}{'Fuente':>18}{'Almacen':>18}   Estado")
print("-" * 76)
todo_ok = True
for nombre, fuente, almacen in PRUEBAS:
    ok = float(fuente) == float(almacen)
    todo_ok &= ok
    print(f"{nombre:<28}{fuente:>18}{almacen:>18}   {'OK' if ok else 'DIFIERE'}")

print()
print("Todas las validaciones pasaron."
      if todo_ok else
      "Hay diferencias. Revisa el ETL antes de seguir.")
