"""
Shared infrastructure of the pipeline layers. No layer logic lives here:
only what every layer and process needs.

    Connections        the two sources, the staging area, the warehouse
                       and the metadata repository
    Lock               one pipeline process at a time
    Run control        staging_dw.etl_run, with a checkpoint per layer in
                       staging_dw.etl_run_capa so a failed run resumes
                       where it stopped
    Staging I/O        append to and read from any staging_dw table
    Process logging    etl_process / etl_execution / dq_result in the
                       metadata repository
    Process runner     what run_staging.py, run_dimensions.py and
                       run_facts.py share: resume or open the run, run
                       the layers, close it and log it
"""
import argparse
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

CLASSICMODELS = sa.create_engine(os.getenv("CLASSICMODELS_URL"))
CUSTOMERSERVICE = sa.create_engine(os.getenv("CUSTOMERSERVICE_URL"))
# The staging area is its own database, outside the warehouse: only
# layer 7 (Load), the surrogate-key lookups of layer 5 and the target
# shape check of layer 6 touch DW.
STAGING = sa.create_engine(os.getenv("STAGING_URL"))
DW = sa.create_engine(os.getenv("DW_URL"))
META = sa.create_engine(os.getenv("METADATA_URL"))

TOOL = "Python 3.11 + SQLAlchemy 2.1 + pandas 3.0"

# Key of the PostgreSQL advisory lock the three processes share.
LOCK_KEY = 2026_0309

ABANDONED = "Abandonada: el proceso termino sin cerrar la corrida"


# ============================================================
# Lock
# ============================================================

@contextmanager
def pipeline_lock():
    """Hold the pipeline lock while the block runs.

    The three processes write the same staging tables and the same
    warehouse, and the facts depend on the dimensions, so only one may
    run at a time. The lock is a session-level advisory lock in the
    staging database: PostgreSQL releases it when the connection closes,
    so a killed process never leaves it taken.

    With the lock held no other process can be running, so any run still
    EN_CURSO was abandoned by a process that died: it is closed as ERROR
    here, and can be resumed like any failed run.
    """
    con = STAGING.connect()
    acquired = False
    try:
        acquired = con.execute(sa.text("SELECT pg_try_advisory_lock(:k)"),
                               {"k": LOCK_KEY}).scalar()
        con.commit()        # the session lock outlives the transaction
        if not acquired:
            raise SystemExit(
                "Another pipeline process is running (the pipeline lock is "
                "taken). Wait for it to finish and run this again.")
        close_abandoned_runs()
        yield
    finally:
        if acquired:        # the connection goes back to the pool, still open
            con.execute(sa.text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
            con.commit()
        con.close()


def close_abandoned_runs():
    """Close as ERROR the runs, layers and executions left EN_CURSO.

    Only call it with the pipeline lock held.
    """
    with STAGING.begin() as con:
        runs = con.execute(sa.text("""
            UPDATE staging_dw.etl_run
               SET estado = 'ERROR', finalizado_en = now(), error = :e
             WHERE estado = 'EN_CURSO'
            RETURNING run_id"""), {"e": ABANDONED}).scalars().all()
        if runs:
            con.execute(sa.text("""
                UPDATE staging_dw.etl_run_capa
                   SET estado = 'ERROR', finalizado_en = now()
                 WHERE estado = 'EN_CURSO' AND run_id = ANY(:r)"""), {"r": runs})
    if runs:
        with META.begin() as con:
            con.execute(sa.text("""
                UPDATE etl_execution
                   SET status = 'ERROR', finished_at = now(), error_message = :e
                 WHERE status = 'EN_CURSO' AND run_id = ANY(:r)"""),
                {"e": ABANDONED, "r": runs})
        print(f"Runs left EN_CURSO by a process that died, closed as ERROR: {runs}")


# ============================================================
# Run control
# ============================================================

def open_run(process, source_run=None):
    with STAGING.begin() as con:
        return con.execute(sa.text("""
            INSERT INTO staging_dw.etl_run (proceso, run_origen)
            VALUES (:p, :o) RETURNING run_id
        """), {"p": process, "o": source_run}).scalar()


def reopen_run(run_id):
    with STAGING.begin() as con:
        con.execute(sa.text("""
            UPDATE staging_dw.etl_run
               SET estado = 'EN_CURSO', finalizado_en = NULL, error = NULL,
                   reintentos = reintentos + 1
             WHERE run_id = :r"""), {"r": run_id})


def close_run(run_id, status, error=None):
    with STAGING.begin() as con:
        con.execute(sa.text("""
            UPDATE staging_dw.etl_run
               SET finalizado_en = now(), estado = :e, error = :m
             WHERE run_id = :r
        """), {"e": status, "m": error, "r": run_id})


def last_successful_run(process):
    """(run_id, run_origen) of the latest run of a process that finished
    OK, or (None, None) if there is none."""
    with STAGING.connect() as con:
        row = con.execute(sa.text("""
            SELECT run_id, run_origen FROM staging_dw.etl_run
            WHERE proceso = :p AND estado = 'OK'
            ORDER BY run_id DESC LIMIT 1
        """), {"p": process}).first()
    return tuple(row) if row else (None, None)


def last_successful_staging_run():
    """run_id of the latest staging run that finished OK.

    The dimension and fact processes read Clean Staging from this run
    and never query the sources directly.
    """
    run_id, _ = last_successful_run("staging")
    if run_id is None:
        raise RuntimeError(
            "No finished staging run found.\n"
            "Run first: python pipeline/run_staging.py")
    return run_id


def run_to_resume(process, source_run=None):
    """run_id of the latest run of `process` if it did not finish, else None.

    Only the latest run can be resumed: an older failed run was already
    superseded by a newer one. A dimension or fact run is resumed only if
    it read the staging run the process would read now; otherwise it
    would load data older than the latest successful staging run.
    """
    with STAGING.connect() as con:
        row = con.execute(sa.text("""
            SELECT run_id, estado, run_origen, depurado_en
              FROM staging_dw.etl_run
             WHERE proceso = :p
             ORDER BY run_id DESC LIMIT 1"""), {"p": process}).first()
    if row is None or row.estado == "OK":
        return None
    if row.depurado_en is not None:
        print(f"Run {row.run_id} failed, but its layer data was purged: it "
              "cannot be resumed.")
        return None
    if row.run_origen != source_run:
        print(f"Run {row.run_id} failed, but it read staging run "
              f"{row.run_origen} and the latest successful one is "
              f"{source_run}: it is not resumed.")
        return None
    return row.run_id


def warehouse_load(process):
    """(lote_carga_key, run_staging) of the last load of `process` that
    reached the warehouse, read from the warehouse itself
    (dim_lote_carga), or (None, None)."""
    with DW.connect() as con:
        row = con.execute(sa.text("""
            SELECT lote_carga_key, run_staging FROM dim_lote_carga
             WHERE proceso = :p
             ORDER BY cargado_en DESC, lote_carga_key DESC LIMIT 1
        """), {"p": process}).first()
    return tuple(row) if row else (None, None)


def check_dimensions_loaded_from(staging_run):
    """Stop unless the dimensions in the warehouse came from staging_run.

    Facts resolve their surrogate keys against the loaded dimensions, so
    both must be built from the same Clean Staging. After a new staging
    run, the dimensions have to be reloaded before the facts.

    The answer comes from the warehouse (dim_lote_carga), not from the
    run history in staging: if the warehouse is rebuilt empty or restored
    from a backup, the check sees what it really holds.
    """
    load, origin = warehouse_load("dimensiones")
    if origin != staging_run:
        loaded = (f"were loaded from staging run {origin} (load {load})"
                  if load else "have never been loaded")
        raise RuntimeError(
            f"The dimensions in the warehouse {loaded}, but the latest "
            f"successful staging run is {staging_run}.\n"
            "Run first: python pipeline/run_dimensions.py")


# ============================================================
# Layer checkpoints
# ============================================================

@dataclass
class Layer:
    """A layer as a process runs it.

    tables  staging_dw tables the layer writes. Before the layer starts,
            its rows for the run are deleted, so a layer that failed
            halfway starts clean when the run is resumed.
    run     run(run_id) -> rows written.
    """
    number: int
    name: str
    tables: tuple
    run: Callable[[int], int]


def completed_layers(run_id):
    with STAGING.connect() as con:
        return set(con.execute(sa.text("""
            SELECT capa FROM staging_dw.etl_run_capa
             WHERE run_id = :r AND estado = 'OK'"""), {"r": run_id}).scalars())


def start_layer(run_id, layer):
    with STAGING.begin() as con:
        for table in layer.tables:
            con.execute(sa.text(f"DELETE FROM staging_dw.{table} WHERE run_id = :r"),
                        {"r": run_id})
        con.execute(sa.text("""
            DELETE FROM staging_dw.stg_dq_resumen WHERE run_id = :r AND capa = :c"""),
            {"r": run_id, "c": layer.number})
        con.execute(sa.text("""
            INSERT INTO staging_dw.etl_run_capa (run_id, capa, nombre, estado)
            VALUES (:r, :c, :n, 'EN_CURSO')
            ON CONFLICT (run_id, capa) DO UPDATE
                SET estado = 'EN_CURSO', filas = NULL,
                    iniciado_en = now(), finalizado_en = NULL"""),
            {"r": run_id, "c": layer.number, "n": layer.name})


def end_layer(run_id, layer, status, rows=None):
    with STAGING.begin() as con:
        con.execute(sa.text("""
            UPDATE staging_dw.etl_run_capa
               SET estado = :e, filas = :f, finalizado_en = now()
             WHERE run_id = :r AND capa = :c"""),
            {"e": status, "f": rows, "r": run_id, "c": layer.number})


def injected_fault(layer_number):
    """Test hook to reproduce a failure between two layers.

    PIPELINE_FAULT=error@N raises right after layer N is checkpointed;
    PIPELINE_FAULT=kill@N ends the process there without any cleanup, as
    kill -9 would. Used by pipeline/tests/test_resume_layers.py.
    """
    mode, _, at = os.getenv("PIPELINE_FAULT", "").partition("@")
    if at and int(at) == layer_number:
        if mode == "kill":
            os._exit(137)
        raise RuntimeError(f"Fault injected after layer {layer_number} "
                           f"(PIPELINE_FAULT={mode}@{at})")


# ============================================================
# Serialisation
# ============================================================

def json_safe(v):
    """Convert a pandas/numpy value into something JSON can store."""
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if v is pd.NaT:
        return None
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat()
    if hasattr(v, "item"):              # numpy int64 / float64 / bool_
        v = v.item()
        return None if isinstance(v, float) and pd.isna(v) else v
    if isinstance(v, (bytes, bytearray, memoryview)):
        return None                     # blobs (productlines.image) are not staged
    return v


def json_rows(df):
    return [
        {k: json_safe(v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


# ============================================================
# Staging I/O
# ============================================================

def insert(table, records):
    """Append records to a staging_dw table."""
    if not records:
        return
    cols = list(records[0].keys())
    sql = sa.text(
        f"INSERT INTO staging_dw.{table} ({', '.join(cols)}) "
        f"VALUES ({', '.join(':' + c for c in cols)})"
    )
    # Pass the payload as a dict and let the JSON bind parameter serialise
    # it; calling json.dumps first would store a JSON string, not an object.
    if "payload" in cols:
        sql = sql.bindparams(sa.bindparam("payload", type_=sa.JSON))
    with STAGING.begin() as con:
        con.execute(sql, records)


def write_payload(table, run_id, df, **fields):
    """Append a DataFrame to a staging_dw layer, one JSONB payload per row,
    numbered in order. `fields` are the layer's own columns. Returns the
    number of rows written."""
    insert(table, [
        {"run_id": run_id, **fields, "nro_fila": i, "payload": p}
        for i, p in enumerate(json_rows(df), 1)
    ])
    return len(df)


def read_payload(table, run_id, **filters):
    """DataFrame built from the payload column of a layer, in original order."""
    where = "".join(f" AND {k} = :{k}" for k in filters)
    with STAGING.connect() as con:
        rows = con.execute(sa.text(
            f"SELECT payload FROM staging_dw.{table} "
            f"WHERE run_id = :r{where} ORDER BY nro_fila"),
            {"r": run_id, **filters}).fetchall()
    return pd.DataFrame([r[0] for r in rows])


def count_rows(table, run_id):
    with STAGING.connect() as con:
        return con.execute(sa.text(
            f"SELECT COUNT(*) FROM staging_dw.{table} WHERE run_id = :r"),
            {"r": run_id}).scalar()


def write_quality(run_id, layer, results):
    """Persist (rule, evaluated, failed) per rule in stg_dq_resumen."""
    insert("stg_dq_resumen", [
        {"run_id": run_id, "capa": layer, "regla": rule,
         "evaluados": int(evaluated), "fallidos": int(failed)}
        for rule, evaluated, failed in results
    ])


def read_quality(run_id):
    """[(rule, evaluated, failed)] of every layer of a run."""
    with STAGING.connect() as con:
        return [tuple(r) for r in con.execute(sa.text("""
            SELECT regla, SUM(evaluados), SUM(fallidos)
              FROM staging_dw.stg_dq_resumen WHERE run_id = :r
             GROUP BY regla ORDER BY regla"""), {"r": run_id})]


# ============================================================
# Process logging in the metadata repository
# ============================================================

@dataclass
class Process:
    """A pipeline process as the run history and the metadata see it.

    summary(run_id) -> (rows read, rows written, rows rejected), counted
    from what the layers left in staging, so a resumed run reports the
    layers it skipped too.
    """
    name: str               # staging_dw.etl_run.proceso
    script: str             # file in pipeline/, to tell how to resume it
    title: str              # console header
    metadata_name: str      # etl_process.process_name
    description: str
    sources: str
    target: str
    summary: Callable[[int], tuple]


def start_execution(process, run_id, source_run=None):
    """Record in the repository that an execution started; returns its id.

    Every attempt is its own etl_execution row, EN_CURSO until it ends:
    a resumed run adds a new one under the same run_id. The process row
    of etl_process only carries what does not change between runs.
    """
    with META.begin() as con:
        process_id = con.execute(sa.text("""
            INSERT INTO etl_process (process_name, tool, source_systems,
                                     target_system, description)
            VALUES (:n, :t, :s, :g, :d)
            ON CONFLICT (process_name) DO UPDATE
                SET tool = EXCLUDED.tool,
                    source_systems = EXCLUDED.source_systems,
                    target_system = EXCLUDED.target_system,
                    description = EXCLUDED.description
            RETURNING etl_process_id
        """), {"n": process.metadata_name, "t": TOOL, "s": process.sources,
               "g": process.target, "d": process.description}).scalar()

        return con.execute(sa.text("""
            INSERT INTO etl_execution (etl_process_id, run_id, run_origen,
                                       started_at, status)
            VALUES (:p, :r, :o, now(), 'EN_CURSO')
            RETURNING etl_execution_id
        """), {"p": process_id, "r": run_id, "o": source_run}).scalar()


def finish_execution(execution_id, status, rows=(None, None, None),
                     error=None, quality_results=()):
    """Close an execution and store how each quality rule did.

    quality_results: iterable of (rule_name, rows_evaluated, rows_failed).
    A rule passes when it had no failures.
    """
    rows_read, rows_written, rows_rejected = rows
    with META.begin() as con:
        con.execute(sa.text("""
            UPDATE etl_execution
               SET finished_at = now(), status = :s, rows_read = :lr,
                   rows_written = :lw, rows_rejected = :rj, error_message = :e
             WHERE etl_execution_id = :x
        """), {"s": status, "lr": rows_read, "lw": rows_written,
               "rj": rows_rejected, "e": error, "x": execution_id})

        for rule, evaluated, failed in quality_results:
            rule_id = con.execute(sa.text(
                "SELECT dq_rule_id FROM dq_rule WHERE rule_name = :n"),
                {"n": rule}).scalar()
            if rule_id:
                con.execute(sa.text("""
                    INSERT INTO dq_result (dq_rule_id, etl_execution_id,
                                           rows_evaluated, rows_failed, passed)
                    VALUES (:r, :e, :ev, :fa, :p)
                """), {"r": rule_id, "e": execution_id, "ev": int(evaluated),
                       "fa": int(failed), "p": int(failed) == 0})


# ============================================================
# Process runner
# ============================================================

def parse_args(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--resume", action="store_true",
        help="resume the latest run of this process if it failed, skipping "
             "the layers it finished; start a new run if there is none")
    return parser.parse_args()


def run_process(process, layers, source_run=None, resume=False):
    """Run the layers of a process as one run; returns its run_id.

    With resume=True, the latest run of the process, if it failed, is
    resumed: it keeps its run_id, the layers that finished are skipped
    and the first one that did not is redone from a clean slate. Without
    it, or if there is nothing to resume, a new run is opened.

    Call it with the pipeline lock held.
    """
    run_id = run_to_resume(process.name, source_run) if resume else None
    if run_id:
        reopen_run(run_id)
        done = completed_layers(run_id)
        verb = "resuming "
    else:
        if resume:
            print(f"No failed '{process.name}' run to resume: starting a new one.")
        run_id = open_run(process.name, source_run)
        done = set()
        verb = ""
    origin = f", reading Clean Staging of run {source_run}" if source_run else ""
    print(f"{process.title} - {verb}run_id={run_id}{origin}")

    execution = current = None
    try:
        execution = start_execution(process, run_id, source_run)
        for layer in layers:
            if layer.number in done:
                print(f"\n[Layer {layer.number}] {layer.name}: finished in an "
                      f"earlier attempt of run {run_id}, skipped")
                continue
            current = layer
            start_layer(run_id, layer)
            rows = layer.run(run_id)
            end_layer(run_id, layer, "OK", rows)
            current = None
            injected_fault(layer.number)
    except BaseException as e:          # KeyboardInterrupt included
        error = f"{type(e).__name__}: {e}"[:500]
        if current:
            end_layer(run_id, current, "ERROR")
        close_run(run_id, "ERROR", error)
        if execution:
            finish_execution(execution, "ERROR", error=error)
        print(f"\nRun {run_id} failed. Resume it with: "
              f"python pipeline/{process.script} --resume")
        raise

    close_run(run_id, "OK")
    finish_execution(execution, "OK", process.summary(run_id),
                     quality_results=read_quality(run_id))
    return run_id
