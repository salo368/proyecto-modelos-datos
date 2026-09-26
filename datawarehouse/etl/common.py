"""
Shared helpers for the three warehouse ETL processes:

    etl_dw_staging.py     layers 1-4  (Extract .. Clean Staging)
    etl_dw_dimensions.py  layers 5-7  for the dimensions
    etl_dw_facts.py       layers 5-7  for the facts

Connections, run control in staging_dw.etl_run, reading and writing
staging layers, and logging each run in the metadata repository.
"""
import os
from datetime import date, datetime

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

CLASSICMODELS = sa.create_engine(os.getenv("CLASSICMODELS_URL"))
CUSTOMERSERVICE = sa.create_engine(os.getenv("CUSTOMERSERVICE_URL"))
DW = sa.create_engine(os.getenv("DW_URL"))
META = sa.create_engine(os.getenv("METADATA_URL"))

TOOL = "Python 3.11 + SQLAlchemy 2.1 + pandas 3.0"


# ============================================================
# Run control
# ============================================================

def open_run(process, source_run=None):
    with DW.begin() as con:
        return con.execute(sa.text("""
            INSERT INTO staging_dw.etl_run (proceso, run_origen)
            VALUES (:p, :o) RETURNING run_id
        """), {"p": process, "o": source_run}).scalar()


def close_run(run_id, status):
    with DW.begin() as con:
        con.execute(sa.text("""
            UPDATE staging_dw.etl_run
               SET finalizado_en = now(), estado = :e
             WHERE run_id = :r
        """), {"e": status, "r": run_id})


def last_successful_staging_run():
    """run_id of the latest staging run that finished OK.

    The dimension and fact processes read Clean Staging from this run
    and never query the sources directly.
    """
    with DW.connect() as con:
        run_id = con.execute(sa.text("""
            SELECT MAX(run_id) FROM staging_dw.etl_run
            WHERE proceso = 'staging' AND estado = 'OK'
        """)).scalar()
    if run_id is None:
        raise RuntimeError(
            "No finished staging run found.\n"
            "Run first: python datawarehouse/etl/etl_dw_staging.py")
    return run_id


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
# Staging layer I/O
# ============================================================

def insert(table, records):
    """Append records to a staging_dw table (staging is never truncated)."""
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
    with DW.begin() as con:
        con.execute(sql, records)


def read_payload(table, run_id, **filters):
    """DataFrame built from the payload column of a layer, in original order."""
    where = "".join(f" AND {k} = :{k}" for k in filters)
    with DW.connect() as con:
        rows = con.execute(sa.text(
            f"SELECT payload FROM staging_dw.{table} "
            f"WHERE run_id = :r{where} ORDER BY nro_fila"),
            {"r": run_id, **filters}).fetchall()
    return pd.DataFrame([r[0] for r in rows])


def read_clean(staging_run, source_table):
    """Rows of a source table that Clean Staging accepted."""
    return read_payload("stg_clean", staging_run, tabla_origen=source_table)


# ============================================================
# Metadata repository logging
# ============================================================

def log_execution(process, description, sources, run_id, rows_read,
                  rows_written, rows_rejected, status, error=None,
                  quality_results=()):
    """Record the run in etl_process / etl_execution / dq_result.

    quality_results: iterable of (rule_name, rows_evaluated, rows_failed).
    A rule passes when it had no failures.
    """
    with META.begin() as con:
        process_id = con.execute(sa.text("""
            INSERT INTO etl_process (process_name, tool, source_systems,
                                     target_system, description)
            VALUES (:n, :t, :s, 'dw (PostgreSQL)', :d)
            ON CONFLICT (process_name) DO UPDATE
                SET tool = EXCLUDED.tool,
                    source_systems = EXCLUDED.source_systems,
                    description = EXCLUDED.description
            RETURNING etl_process_id
        """), {"n": process, "t": TOOL, "s": sources,
               "d": description}).scalar()

        execution_id = con.execute(sa.text("""
            INSERT INTO etl_execution (etl_process_id, run_id, started_at,
                                       finished_at, status, rows_read,
                                       rows_written, rows_rejected, error_message)
            VALUES (:p, :r, now(), now(), :s, :lr, :lw, :rj, :e)
            RETURNING etl_execution_id
        """), {"p": process_id, "r": run_id, "s": status, "lr": rows_read,
               "lw": rows_written, "rj": rows_rejected, "e": error}).scalar()

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
