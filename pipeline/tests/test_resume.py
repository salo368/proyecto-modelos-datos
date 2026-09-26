"""
Test: a load can be resumed without damaging the warehouse.

Replays how a load is resumed after a new staging run and checks the
warehouse after each step against a snapshot taken before:

  1. The facts alone. The loaded dimensions come from the previous
     staging run, so run_facts.py must refuse to start instead of
     resolving keys against dimensions built from other data.
  2. The dimensions. They are upserted on their business key, so their
     surrogate keys do not change and the facts already loaded stay
     untouched (a full reload with TRUNCATE ... CASCADE emptied them).
  3. The facts again, now allowed. With the same source data the
     warehouse ends up identical to the snapshot.

It runs the real processes against the live databases and leaves the
warehouse loaded from the new staging run. The extra runs stay in the
staging history, like any other load.

Usage:
    python pipeline/tests/test_resume.py
"""
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
from common import DW, last_successful_run  # noqa: E402

DIMENSIONS = ["dim_tiempo", "dim_estado_orden", "dim_oficina",
              "dim_cliente", "dim_producto", "dim_empleado"]
# Facts are compared without their own surrogate key, which Load
# renumbers on every reload; the dimension keys they carry are compared.
FACT_KEYS = {"fact_ventas": "venta_key", "fact_llamadas_servicio": "llamada_key"}


def snapshot():
    """(rows, md5 of the full content) per table."""
    out = {}
    with DW.connect() as con:
        for t in DIMENSIONS + list(FACT_KEYS):
            row = f"(to_jsonb(x) - '{FACT_KEYS[t]}')" if t in FACT_KEYS else "to_jsonb(x)"
            out[t] = tuple(con.execute(sa.text(
                f"SELECT COUNT(*), md5(COALESCE(string_agg({row}::text, '|' "
                f"ORDER BY {row}::text), '')) FROM {t} x")).one())
    return out


def run(script):
    """Run a pipeline process; (exit code, console output)."""
    r = subprocess.run([sys.executable, str(PIPELINE / script)],
                       cwd=PIPELINE.parent, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def changed(before, after):
    return [t for t in before if before[t] != after[t]]


def main():
    before = snapshot()
    if before["fact_ventas"][0] == 0:
        sys.exit("The warehouse is empty. Run the pipeline first: python run_all.py")

    code, out = run("run_staging.py")
    if code:
        sys.exit(f"The staging run failed; the test cannot continue:\n{out[-1500:]}")
    staging_run, _ = last_successful_run("staging")
    results = []

    # 1. Facts before the dimensions of the new staging run: refused.
    code, out = run("run_facts.py")
    facts_before, _ = last_successful_run("hechos")
    diff = changed(before, snapshot())
    results.append((
        "Facts before the dimensions",
        "refuses to run",
        code != 0 and "run_dimensions.py" in out and not diff,
        "refused, warehouse unchanged" if code and not diff
        else f"exit {code}, changed: {diff or 'nothing'}"))

    # 2. Dimensions: same keys, facts untouched.
    code, out = run("run_dimensions.py")
    diff = changed(before, snapshot())
    results.append((
        "Dimensions reloaded",
        "stable keys, facts untouched",
        code == 0 and not diff,
        "warehouse unchanged" if code == 0 and not diff
        else f"exit {code}, changed: {diff or 'nothing'}"))

    # 3. Facts, now from the same staging run as the dimensions.
    code, out = run("run_facts.py")
    facts_run, facts_origin = last_successful_run("hechos")
    diff = changed(before, snapshot())
    results.append((
        "Facts after the dimensions",
        f"load from staging run {staging_run}",
        code == 0 and facts_origin == staging_run and facts_run != facts_before and not diff,
        f"run {facts_run} from staging run {facts_origin}, warehouse unchanged"
        if code == 0 and not diff
        else f"exit {code}, changed: {diff or 'nothing'}"))

    print(f"New staging run: {staging_run}\n")
    print(f"{'Step':<34}{'Expected':<36}{'Status':<7}Observed")
    print("-" * 110)
    for step, expected, ok, observed in results:
        print(f"{step:<34}{expected:<36}{'OK' if ok else 'FAIL':<7}{observed}")

    ok = all(r[2] for r in results)
    print()
    print("A load can be resumed step by step without damaging the warehouse." if ok
          else "Resuming the load did not behave as expected.")
    if not ok:
        print(out[-1500:])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
