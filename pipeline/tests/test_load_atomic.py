"""
Test: Load (layer 7) is all-or-nothing.

Forces a failure halfway through a load and checks that the warehouse is
left exactly as it was before the attempt.

The batch has three tables, one per way Load writes:

  1. dim_oficina, upserted: an existing office with another city. On its
     own it would succeed and overwrite that office.
  2. fact_llamadas_servicio, replaced: a single call. On its own it would
     succeed, emptying the table and leaving that one call.
  3. dim_estado_orden with a column that does not exist, so it fails.

With a per-table load, the warehouse would end up with the office
changed and every call but one gone. With load_atomic, PostgreSQL rolls
back the whole batch and every table keeps its previous content.

The test compares row counts and an MD5 of each table's full content, so
it also catches a change that keeps the same number of rows.

It runs against the live warehouse. If load_atomic were not atomic, the
warehouse would be left damaged: rerun `python run_all.py` to rebuild it.

Usage:
    python pipeline/tests/test_load_atomic.py
"""
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import DW  # noqa: E402
from layer7_load import load_atomic  # noqa: E402

WATCHED = ["dim_oficina", "dim_estado_orden", "fact_ventas", "fact_llamadas_servicio"]


def snapshot():
    """(rows, md5 of the full content) per table."""
    with DW.connect() as con:
        return {
            t: tuple(con.execute(sa.text(
                f"SELECT COUNT(*), md5(COALESCE(string_agg(x::text, '|' ORDER BY x::text), '')) "
                f"FROM {t} x")).one())
            for t in WATCHED
        }


def main():
    before = snapshot()
    if before["fact_llamadas_servicio"][0] < 2:
        sys.exit("The warehouse is empty. Run the pipeline first: python run_all.py")

    # Load-Ready shape: business columns only, no surrogate key.
    office = pd.read_sql("""SELECT codigo_oficina, ciudad, pais, region, territorio
                            FROM dim_oficina ORDER BY oficina_key LIMIT 1""", DW)
    office["ciudad"] = "Ciudad de prueba"
    one_call = pd.read_sql("""SELECT tiempo_key, cliente_key, producto_key, empleado_key,
                                     texto_llamada, cantidad_llamadas, longitud_texto
                              FROM fact_llamadas_servicio ORDER BY llamada_key LIMIT 1""", DW)
    broken = pd.DataFrame([{"estado": "X", "es_efectiva": True,
                            "columna_que_no_existe": 1}])

    try:
        load_atomic({"dim_oficina": office, "fact_llamadas_servicio": one_call,
                     "dim_estado_orden": broken})
        failed = False
    except Exception as e:
        failed = True
        reason = str(e).splitlines()[0][:90]

    after = snapshot()

    print(f"{'Table':<26}{'Rows before':>12}{'Rows after':>12}   Content")
    print("-" * 66)
    ok = failed
    for t in WATCHED:
        same = before[t] == after[t]
        ok &= same
        print(f"{t:<26}{before[t][0]:>12}{after[t][0]:>12}   "
              f"{'unchanged' if same else 'CHANGED'}")

    print()
    if not failed:
        print("The broken batch did not raise: the test could not force the failure.")
    else:
        print(f"The batch failed as intended: {reason}")
    print("Load is all-or-nothing." if ok else
          "Load left the warehouse partially loaded. Rerun: python run_all.py")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
