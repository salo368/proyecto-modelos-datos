"""
Layer 2 - Initial Staging.

Lands each extract, exactly as read, in the initial staging table of
its source (one table per source system, the row as a JSONB payload),
then profiles what landed: nulls, distinct values, min and max of every
column.

    Input   extracts from layer 1
    Output  stg_initial_classicmodels, stg_initial_customerservice, stg_perfil
    Reader  read_initial(run_id), used by layers 3 and 4
"""
from collections import defaultdict

import pandas as pd
import sqlalchemy as sa

from common import STAGING, insert, write_payload
from layer1_extract import EXTRACTION_MODELS


def land(run_id, extracts):
    total = 0
    for source, table, df in extracts:
        target = EXTRACTION_MODELS[source]["initial_table"]
        total += write_payload(target, run_id, df, tabla_origen=table)
    for source, model in EXTRACTION_MODELS.items():
        n = sum(len(df) for s, _, df in extracts if s == source)
        print(f"    staging_dw.{model['initial_table']:<30}{n:>6} rows")
    print(f"    {'TOTAL in Initial Staging':<41}{total:>6} rows")
    return total


def read_initial(run_id):
    """What landed in Initial Staging for a run.

    Returns {table: (source, DataFrame)} with a _nro_fila column.
    """
    data = {}
    for source, model in EXTRACTION_MODELS.items():
        with STAGING.connect() as con:
            rows = con.execute(sa.text(
                f"SELECT tabla_origen, nro_fila, payload "
                f"FROM staging_dw.{model['initial_table']} "
                f"WHERE run_id = :r ORDER BY tabla_origen, nro_fila"),
                {"r": run_id}).fetchall()
        by_table = defaultdict(list)
        for table, row_number, payload in rows:
            by_table[table].append({"_nro_fila": row_number, **payload})
        for table, records in by_table.items():
            data[table] = (source, pd.DataFrame(records))
    return data


def profile(run_id, data):
    """Nulls, distinct values, min and max of every landed column."""
    records = []
    for table, (source, df) in data.items():
        for col in df.columns:
            if col == "_nro_fila":
                continue
            s = df[col]
            non_null = s.dropna()
            try:
                minimum = str(non_null.min()) if len(non_null) else None
                maximum = str(non_null.max()) if len(non_null) else None
            except TypeError:           # mixed-type column
                minimum = maximum = None
            records.append({
                "run_id": run_id, "fuente": source, "tabla_origen": table,
                "columna": col, "filas": len(s), "nulos": int(s.isna().sum()),
                # Native float: psycopg2 cannot adapt numpy.float64.
                "pct_nulos": float(round(100 * s.isna().mean(), 2)) if len(s) else 0.0,
                "distintos": int(s.nunique()),
                "minimo": (minimum or "")[:200] or None,
                "maximo": (maximum or "")[:200] or None,
            })
    insert("stg_perfil", records)
    with_nulls = sum(1 for r in records if r["nulos"] > 0)
    print(f"    Profile: {len(records)} columns in staging_dw.stg_perfil, "
          f"{with_nulls} with nulls")


def run(run_id, extracts):
    print("\n[Layer 2] Initial Staging")
    total = land(run_id, extracts)
    profile(run_id, read_initial(run_id))
    return total
