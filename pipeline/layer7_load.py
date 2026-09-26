"""
Layer 7 - Load.

The only layer that writes to the data warehouse. Takes what Load-Ready
Publish left and writes every table of the branch in ONE transaction:
either every table ends up with the new rows or none of them change.

    Dimensions  upserted on their business key (type 1): new members are
                inserted and the attributes of existing ones overwritten,
                keeping their surrogate key. Reloading the dimensions
                therefore never invalidates the facts already loaded.
    Facts       replaced: the table is emptied and loaded again.

The same transaction records the load in dim_lote_carga (the audit
dimension) and stamps every row it writes with its lote_carga_key, so
the warehouse itself says which run and which staging run each row came
from. The layer is idempotent: if a resumed run loads again, it writes
the same rows and updates its own dim_lote_carga row.

The history lives in the staging database.

    Input   stg_loadready (layer 6)
    Output  dim_* or fact_*, and dim_lote_carga, in the EDW (database dw,
            datawarehouse/edw/star_schema.sql)
"""
import sqlalchemy as sa

from common import DW, json_rows
from layer6_load_ready import read_load_ready

# Business key of each dimension: its UNIQUE constraint in star_schema.sql
# (dim_tiempo's key is the date itself as YYYYMMDD).
BUSINESS_KEYS = {
    "dim_tiempo": ["tiempo_key"],
    "dim_estado_orden": ["estado"],
    "dim_oficina": ["codigo_oficina"],
    "dim_cliente": ["numero_cliente"],
    "dim_producto": ["codigo_producto"],
    "dim_empleado": ["numero_empleado", "sistema_origen"],
}


def upsert(con, target, df):
    """Insert new members, overwrite existing ones; surrogate keys stay."""
    if df.empty:
        return
    cols = list(df.columns)
    keys = BUSINESS_KEYS[target]
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c not in keys)
    con.execute(sa.text(
        f"INSERT INTO {target} ({', '.join(cols)}) "
        f"VALUES ({', '.join(':' + c for c in cols)}) "
        f"ON CONFLICT ({', '.join(keys)}) "
        f"DO {'UPDATE SET ' + updates if updates else 'NOTHING'}"),
        json_rows(df))


def replace(con, target, df):
    """Empty a fact table and load it again."""
    con.execute(sa.text(f"TRUNCATE TABLE {target} RESTART IDENTITY"))
    df.to_sql(target, con, if_exists="append", index=False)


def record_load(con, batch, rows):
    """Upsert the dim_lote_carga row of this load."""
    run_id, process, staging_run = batch
    con.execute(sa.text("""
        INSERT INTO dim_lote_carga (lote_carga_key, proceso, run_staging, filas)
        VALUES (:k, :p, :s, :f)
        ON CONFLICT (lote_carga_key) DO UPDATE
            SET proceso = EXCLUDED.proceso, run_staging = EXCLUDED.run_staging,
                filas = EXCLUDED.filas, cargado_en = now()"""),
        {"k": run_id, "p": process, "s": staging_run, "f": rows})


def load_atomic(frames, batch=None):
    """Write every target table in ONE transaction.

    batch: (run_id, process, staging run) of the load. When given, the
    load is recorded in dim_lote_carga and every row carries its key,
    inside the same transaction.

    If anything fails halfway (a constraint, a lost connection),
    PostgreSQL rolls back every statement of the batch, TRUNCATE and the
    dim_lote_carga row included, and the warehouse keeps its previous
    content. Without this, a failure after the third table would leave
    some tables new and the rest old.

    pandas reuses the open transaction when it receives a connection
    that is already inside one, instead of committing on its own.
    """
    total = sum(len(df) for df in frames.values())
    with DW.begin() as con:
        if batch:
            record_load(con, batch, total)
        for target, df in frames.items():
            if batch:
                df = df.assign(lote_carga_key=batch[0])
            if target in BUSINESS_KEYS:
                upsert(con, target, df)
            else:
                replace(con, target, df)
    return total


def run(run_id, targets, process, staging_run):
    print("\n[Layer 7] Load (single transaction)")
    frames = read_load_ready(run_id, targets)
    total = load_atomic(frames, batch=(run_id, process, staging_run))
    for target, df in frames.items():
        mode = "upsert" if target in BUSINESS_KEYS else "replace"
        print(f"    {target:<24}{len(df):>6} rows  ({mode})")
    print(f"    dim_lote_carga: load {run_id} (process '{process}', "
          f"staging run {staging_run})")
    return total
