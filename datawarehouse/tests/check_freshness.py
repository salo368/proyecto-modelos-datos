"""Evaluate the almacen_frescura_de_carga rule (MONITOREO layer).

The rule is catalogued in dq_rule but, until this script, no process
evaluated it: dq_result never had a row for it. This closes that gap by
comparing now() against the last successful load in etl_execution and
recording the result the same way every other rule does.

The rule is ADVERTENCIA, not BLOQUEANTE (staleness does not corrupt
data, it just means the reports are showing an old snapshot), so this
script always exits 0: it reports, it does not gate the build.

Usage:
    python datawarehouse/tests/check_freshness.py
"""
import os
import sys
from datetime import timedelta

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

META = sa.create_engine(os.getenv("METADATA_URL"))
THRESHOLD = timedelta(hours=24)

with META.begin() as con:
    last = con.execute(sa.text("""
        SELECT etl_execution_id, finished_at
        FROM etl_execution
        WHERE status = 'OK' AND finished_at IS NOT NULL
        ORDER BY finished_at DESC
        LIMIT 1
    """)).one_or_none()

    if last is None:
        print("No successful load found in etl_execution yet; nothing to evaluate.")
        sys.exit(0)

    execution_id, finished_at = last
    age = con.execute(sa.text("SELECT now() - :f"), {"f": finished_at}).scalar()
    passed = age < THRESHOLD

    rule_id = con.execute(sa.text(
        "SELECT dq_rule_id FROM dq_rule WHERE rule_name = 'almacen_frescura_de_carga'"
    )).scalar()
    if rule_id is None:
        sys.exit("dq_rule has no 'almacen_frescura_de_carga' row; run seeds/dq_rules.sql first.")

    con.execute(sa.text("""
        INSERT INTO dq_result (dq_rule_id, etl_execution_id, rows_evaluated, rows_failed, passed)
        VALUES (:r, :e, 1, :fa, :p)
    """), {"r": rule_id, "e": int(execution_id), "fa": 0 if passed else 1, "p": passed})

status = "OK (fresh)" if passed else "ADVERTENCIA (datos vencidos)"
print(f"Last successful load: {finished_at}  (age: {age})  ->  {status}")
sys.exit(0)
