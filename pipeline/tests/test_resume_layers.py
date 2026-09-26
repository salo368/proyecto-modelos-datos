"""
Test: a failed run resumes from the layer where it stopped.

Makes the real processes fail on purpose (PIPELINE_FAULT, see
common.injected_fault) and resumes them with --resume, checking after
each step the run history in staging, the execution log in the metadata
repository and the warehouse:

  1. Lock. While another process holds the pipeline lock, a process
     refuses to start and opens no run.
  2. Staging fails after layer 3. The run is ERROR with layers 2 and 3
     checkpointed. Layer 4 is left half written on purpose. --resume
     continues the SAME run: layers 2 and 3 are skipped (the sources are
     not read again), layer 4 starts clean and the result matches the
     previous staging run. The metadata keeps both attempts: the failed
     one and the one that finished, with its real duration and the
     results of the quality rules of layer 3, which that attempt skipped.
  3. Dimensions killed after layer 6 (like kill -9). The run stays
     EN_CURSO. The next process closes it as ERROR (abandoned), and
     --resume continues it at layer 7 without repeating 5 and 6.
  4. Facts. They load from the resumed runs.
  5. The warehouse ends up exactly as it started, and no failure blanked
     the description of a process in the metadata.

It runs against the live databases and leaves the warehouse loaded from
the new staging run, like test_resume.py.

Usage:
    python pipeline/tests/test_resume_layers.py
"""
import os
import subprocess
import sys
from pathlib import Path

import sqlalchemy as sa

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DW, LOCK_KEY, META, STAGING  # noqa: E402
from test_resume import snapshot  # noqa: E402


def run(script, *args, fault=None):
    """Run a pipeline process; (exit code, console output)."""
    env = {k: v for k, v in os.environ.items() if k != "PIPELINE_FAULT"}
    if fault:
        env["PIPELINE_FAULT"] = fault
    r = subprocess.run([sys.executable, str(PIPELINE / script), *args],
                       cwd=PIPELINE.parent, capture_output=True, text=True, env=env)
    return r.returncode, r.stdout + r.stderr


def one(engine, sql, **params):
    with engine.connect() as con:
        return con.execute(sa.text(sql), params).first()


def value(engine, sql, **params):
    with engine.connect() as con:
        return con.execute(sa.text(sql), params).scalar()


def latest_run(process):
    return one(STAGING, """SELECT run_id, estado, reintentos, error FROM staging_dw.etl_run
                           WHERE proceso = :p ORDER BY run_id DESC LIMIT 1""", p=process)


def layers(run_id):
    """{layer: (estado, iniciado_en)} of a run."""
    with STAGING.connect() as con:
        return {r.capa: (r.estado, r.iniciado_en) for r in con.execute(sa.text(
            "SELECT capa, estado, iniciado_en FROM staging_dw.etl_run_capa WHERE run_id = :r"),
            {"r": run_id})}


def executions(run_id, process):
    with META.connect() as con:
        return con.execute(sa.text("""
            SELECT e.etl_execution_id, e.status, e.error_message,
                   e.finished_at > e.started_at AS timed,
                   (SELECT COUNT(*) FROM dq_result d
                     WHERE d.etl_execution_id = e.etl_execution_id) AS rules
              FROM etl_execution e JOIN etl_process p USING (etl_process_id)
             WHERE e.run_id = :r AND p.process_name = :p
             ORDER BY e.etl_execution_id"""), {"r": run_id, "p": process}).fetchall()


def count(table, run_id):
    return value(STAGING, f"SELECT COUNT(*) FROM staging_dw.{table} WHERE run_id = :r", r=run_id)


def main():
    before = snapshot()
    if before["fact_ventas"][0] == 0:
        sys.exit("The warehouse is empty. Run the pipeline first: python run_all.py")
    previous_staging = latest_run("staging").run_id
    results = []

    def check(step, expected, ok, observed):
        results.append((step, expected, ok, observed))

    # 1. Lock taken by someone else: refused, no run opened.
    runs_before = value(STAGING, "SELECT COUNT(*) FROM staging_dw.etl_run")
    with STAGING.connect() as holder:
        holder.execute(sa.text("SELECT pg_advisory_lock(:k)"), {"k": LOCK_KEY})
        code, out = run("run_staging.py")
        holder.execute(sa.text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
    runs_after = value(STAGING, "SELECT COUNT(*) FROM staging_dw.etl_run")
    check("Lock taken by another process", "refuses, opens no run",
          code != 0 and "lock is taken" in out and runs_after == runs_before,
          f"exit {code}, runs {runs_before} -> {runs_after}")

    # 2. Staging fails after layer 3, then resumes.
    code, out = run("run_staging.py", fault="error@3")
    failed = latest_run("staging")
    marks = layers(failed.run_id)
    ok = (code != 0 and failed.estado == "ERROR"
          and {c for c, (e, _) in marks.items() if e == "OK"} == {2, 3} and 4 not in marks)
    check("Staging fails after layer 3", "ERROR, layers 2-3 kept", ok,
          f"run {failed.run_id} {failed.estado}, layers OK: "
          f"{sorted(c for c, (e, _) in marks.items() if e == 'OK')}")

    landed = count("stg_initial_classicmodels", failed.run_id) \
        + count("stg_initial_customerservice", failed.run_id)
    with STAGING.begin() as con:            # layer 4 left half written
        con.execute(sa.text("""
            INSERT INTO staging_dw.stg_clean (run_id, fuente, tabla_origen, nro_fila, payload)
            VALUES (:r, 'prueba', 'fila_a_medio_escribir', 1, '{}')"""), {"r": failed.run_id})

    code, out = run("run_staging.py", "--resume")
    resumed = latest_run("staging")
    after = layers(resumed.run_id)
    landed_after = count("stg_initial_classicmodels", resumed.run_id) \
        + count("stg_initial_customerservice", resumed.run_id)
    leftovers = value(STAGING, """SELECT COUNT(*) FROM staging_dw.stg_clean
                                   WHERE run_id = :r AND fuente = 'prueba'""", r=resumed.run_id)
    same_result = all(count(t, resumed.run_id) == count(t, previous_staging)
                      for t in ("stg_clean", "stg_rejected", "stg_error_log"))
    ok = (code == 0 and resumed.run_id == failed.run_id and resumed.estado == "OK"
          and resumed.reintentos == 1 and after[2][1] == marks[2][1] and after[3][1] == marks[3][1]
          and landed_after == landed and leftovers == 0 and same_result)
    check("Staging --resume", "same run, from layer 4", ok,
          f"run {resumed.run_id} {resumed.estado}, retries {resumed.reintentos}, "
          f"layers 2-3 {'not redone' if after[2][1] == marks[2][1] else 'REDONE'}, "
          f"half-written rows left: {leftovers}")

    attempts = executions(failed.run_id, "etl_dw_staging")
    dq_rules = value(META, "SELECT COUNT(*) FROM dq_rule WHERE capa = 'DATA_QUALITY'")
    ok = ([a.status for a in attempts] == ["ERROR", "OK"]
          and attempts[-1].timed and attempts[-1].rules == dq_rules)
    check("Staging attempts in metadata", "ERROR then OK, timed", ok,
          f"{[a.status for a in attempts]}, last lasted > 0: {attempts[-1].timed if attempts else '-'}, "
          f"rule results {attempts[-1].rules if attempts else 0} of {dq_rules}")

    # 3. Dimensions killed after layer 6, then resumed at layer 7.
    code, out = run("run_dimensions.py", fault="kill@6")
    killed = latest_run("dimensiones")
    marks = layers(killed.run_id)
    killed_attempt = executions(killed.run_id, "etl_dw_dimensions")
    ok = (code != 0 and killed.estado == "EN_CURSO" and not changed(before)
          and [a.status for a in killed_attempt] == ["EN_CURSO"])
    check("Dimensions killed after layer 6", "EN_CURSO, warehouse intact", ok,
          f"exit {code}, run {killed.run_id} {killed.estado}, changed: {changed(before) or 'nothing'}")

    code, out = run("run_dimensions.py", "--resume")
    resumed = latest_run("dimensiones")
    after = layers(resumed.run_id)
    attempts = executions(killed.run_id, "etl_dw_dimensions")
    load = one(DW, """SELECT lote_carga_key, run_staging FROM dim_lote_carga
                      WHERE proceso = 'dimensiones' ORDER BY cargado_en DESC LIMIT 1""")
    ok = (code == 0 and "closed as ERROR" in out and resumed.run_id == killed.run_id
          and resumed.estado == "OK" and after[5][1] == marks[5][1] and after[6][1] == marks[6][1]
          and after[7][0] == "OK" and [a.status for a in attempts] == ["ERROR", "OK"]
          and "Abandonada" in (attempts[0].error_message or "")
          and tuple(load) == (killed.run_id, failed.run_id) and not changed(before))
    check("Dimensions --resume", "abandoned run closed, from 7", ok,
          f"run {resumed.run_id} {resumed.estado}, layers 5-6 "
          f"{'not redone' if after[5][1] == marks[5][1] else 'REDONE'}, "
          f"attempts {[a.status for a in attempts]}, load {tuple(load)}")

    # 4. Facts from the resumed runs.
    code, out = run("run_facts.py")
    facts = latest_run("hechos")
    load = one(DW, """SELECT lote_carga_key, run_staging FROM dim_lote_carga
                      WHERE proceso = 'hechos' ORDER BY cargado_en DESC LIMIT 1""")
    ok = code == 0 and facts.estado == "OK" and tuple(load) == (facts.run_id, failed.run_id)
    check("Facts", f"load from staging run {failed.run_id}", ok,
          f"exit {code}, load {tuple(load) if load else None}")

    # 5. Same warehouse; no process lost its description.
    blank = value(META, """SELECT COUNT(*) FROM etl_process
                            WHERE process_name LIKE 'etl_dw_%'
                              AND (COALESCE(description, '') = '' OR source_systems = '')""")
    diff = changed(before)
    check("Warehouse and process catalogue", "unchanged, described", not diff and blank == 0,
          f"changed: {diff or 'nothing'}, processes without description: {blank}")

    print(f"{'Step':<34}{'Expected':<32}{'Status':<7}Observed")
    print("-" * 120)
    for step, expected, ok, observed in results:
        print(f"{step:<34}{expected:<32}{'OK' if ok else 'FAIL':<7}{observed}")

    ok = all(r[2] for r in results)
    print()
    print("A failed run resumes from the layer where it stopped." if ok
          else "Resuming by layer did not behave as expected.")
    if not ok:
        print(out[-2000:])
    sys.exit(0 if ok else 1)


def changed(before):
    after = snapshot()
    return [t for t in before if before[t] != after[t]]


if __name__ == "__main__":
    main()
