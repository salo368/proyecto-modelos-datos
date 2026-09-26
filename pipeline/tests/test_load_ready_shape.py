"""
Test: Load-Ready Publish (layer 6) catches rows that do not fit the
warehouse before Load runs.

Builds one frame per kind of problem, starting from rows that fit, and
checks each against the live warehouse definition:

  1. rows copied from the warehouse itself fit (no false alarms);
  2. a column the table does not have;
  3. a required column (NOT NULL, no default) left out;
  4. a NULL in a NOT NULL column;
  5. text longer than its VARCHAR;
  6. a number too large for its NUMERIC(p, s);
  7. a number out of the SMALLINT range;
  8. a fraction in an INTEGER column.

It also checks that check_shape stops the batch listing every problem.
It only reads the warehouse catalogue and a few rows; it writes nothing.

Usage:
    python pipeline/tests/test_load_ready_shape.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DW  # noqa: E402
from layer6_load_ready import check_shape, shape_problems, target_columns  # noqa: E402

OFFICE = ["codigo_oficina", "ciudad", "pais", "region", "territorio"]
SALE = ["tiempo_key", "cliente_key", "producto_key", "empleado_key", "oficina_key",
        "estado_key", "numero_orden", "numero_linea", "cantidad_ordenada",
        "precio_unitario", "monto_linea", "costo_linea", "margen_linea",
        "precio_msrp", "dias_hasta_envio"]


def rows(table, cols):
    return pd.read_sql(f"SELECT {', '.join(cols)} FROM {table} "
                       f"ORDER BY 1 DESC LIMIT 3", DW)


def main():
    office, sale = rows("dim_oficina", OFFICE), rows("fact_ventas", SALE)
    customer = rows("dim_cliente", ["numero_cliente", "limite_credito"])
    if len(sale) == 0:
        sys.exit("The warehouse is empty. Run the pipeline first: python run_all.py")

    cases = [
        ("Rows taken from the warehouse", "dim_oficina", office, None),
        ("Rows taken from the warehouse", "fact_ventas", sale, None),
        ("Column the table does not have", "dim_oficina",
         office.assign(columna_inventada=1), "columna_inventada"),
        ("Required column left out", "dim_oficina",
         office.drop(columns=["codigo_oficina"]), "codigo_oficina"),
        ("NULL in a NOT NULL column", "fact_ventas",
         sale.assign(monto_linea=None), "monto_linea"),
        ("Text longer than its VARCHAR", "dim_oficina",
         office.assign(territorio="X" * 25), "territorio"),
        ("Number too large for NUMERIC", "dim_cliente",
         customer.assign(limite_credito=1e12), "limite_credito"),
        ("Out of the SMALLINT range", "fact_ventas",
         sale.assign(numero_linea=40000), "numero_linea"),
        ("Fraction in an INTEGER", "fact_ventas",
         sale.assign(cantidad_ordenada=1.5), "cantidad_ordenada"),
    ]

    print(f"{'Case':<34}{'Table':<14}{'Expected':<30}Status")
    print("-" * 86)
    all_ok = True
    for name, table, df, column in cases:
        problems = shape_problems(table, df, target_columns(table))
        ok = (not problems) if column is None else any(f".{column}:" in p for p in problems)
        all_ok &= ok
        expected = "fits" if column is None else f"flags {column}"
        print(f"{name:<34}{table:<14}{expected:<30}{'OK' if ok else 'FAIL'}")
        if not ok:
            print(f"    problems: {problems}")

    try:
        check_shape({"dim_oficina": office.assign(territorio="X" * 25),
                     "fact_ventas": sale.assign(numero_linea=40000)})
        stopped = False
    except RuntimeError as e:
        stopped = "territorio" in str(e) and "numero_linea" in str(e)
    all_ok &= stopped
    print(f"{'Batch with two problems':<34}{'both':<14}{'stops, lists both':<30}"
          f"{'OK' if stopped else 'FAIL'}")

    print()
    print("Load-Ready Publish stops rows that do not fit the warehouse." if all_ok
          else "The load-ready shape check does not behave as expected.")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
