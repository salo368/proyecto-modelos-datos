"""
Test: Load (layer 7) is all-or-nothing.

Forces a failure halfway through a load and checks that the warehouse is
left exactly as it was before the attempt.

The batch has two tables:

  1. dim_oficina with a single valid row. On its own it would succeed:
     TRUNCATE ... CASCADE empties dim_oficina AND, through the foreign
     keys, fact_ventas and fact_llamadas_servicio; then one row is written.
  2. dim_estado_orden with a column that does not exist, so it fails.

With the old per-table load, the warehouse would end up with one office
and both fact tables empty. With load_atomic, PostgreSQL rolls back the
whole batch and every table keeps its previous content.

The test compares row counts and an MD5 of each table's full content, so
it also catches a change that keeps the same number of rows.

It runs against the live warehouse. If load_atomic were not atomic, the
warehouse would be left damaged: rerun `python run_all.py` to rebuild it.

Usage:
    python datawarehouse/tests/test_load_atomic.py
"""
import sys
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "etl"))
from common import DW, load_atomic  # noqa: E402

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
    if before["fact_ventas"][0] == 0:
        sys.exit("The warehouse is empty. Run the pipeline first: python run_all.py")

    one_office = pd.read_sql("SELECT * FROM dim_oficina ORDER BY oficina_key LIMIT 1", DW)
    broken = pd.DataFrame([{"estado": "X", "es_efectiva": True,
                            "columna_que_no_existe": 1}])

    try:
        load_atomic({"dim_oficina": one_office, "dim_estado_orden": broken})
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
