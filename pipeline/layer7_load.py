"""
Layer 7 - Load.

The only layer that writes to the data warehouse. Replaces the model
tables of the EDW with what Load-Ready Publish left,
all of them in ONE transaction: either every table ends up with the new
rows or none of them change. The model tables are fully reloaded each
time; the history lives in the staging database, which is never
truncated.

    Input   stg_loadready (layer 6)
    Output  dim_* or fact_* in the EDW (database dw,
            datawarehouse/edw/star_schema.sql)
"""
import sqlalchemy as sa

from common import DW
from layer6_load_ready import read_load_ready


def load_atomic(frames):
    """Replace every target table in ONE transaction.

    If anything fails halfway (a constraint, a lost connection),
    PostgreSQL rolls back every TRUNCATE and INSERT of the batch, and the
    warehouse keeps the previous complete load. Without this, a failure
    after the third table would leave some tables new, one emptied and
    the rest old.

    TRUNCATE is transactional in PostgreSQL, so it is undone on rollback
    like any other statement. pandas reuses the open transaction when it
    receives a connection that is already inside one, instead of
    committing on its own.
    """
    with DW.begin() as con:
        for target, df in frames.items():
            con.execute(sa.text(f"TRUNCATE TABLE {target} RESTART IDENTITY CASCADE"))
            df.to_sql(target, con, if_exists="append", index=False)
    return sum(len(df) for df in frames.values())


def run(run_id, targets):
    print("\n[Layer 7] Load (single transaction)")
    frames = read_load_ready(run_id, targets)
    total = load_atomic(frames)
    for target, df in frames.items():
        print(f"    {target:<24}{len(df):>6} rows")
    return total
