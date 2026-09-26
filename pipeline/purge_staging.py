"""
Retention of the staging area.

The loads never delete from staging: every run appends its rows under
its run_id. This script bounds that growth. It keeps whole:

    - the last N runs of each process (N = --keep, 3 by default), which
      always includes the latest one, resumable if it failed
    - the latest successful run of each process
    - the dimension and fact loads the warehouse holds now, and the
      staging runs they read (from dim_lote_carga)
    - the staging runs that any kept load read

Every other run loses the rows of the bulky layer tables (stg_initial_*,
stg_clean, stg_transform, stg_loadready) and is stamped with
depurado_en; it can no longer be resumed. Its run control, layer
checkpoints, profile, bad-transactions log, rejected records and quality
summary stay: they are the audit trail, and they are small.

It takes the pipeline lock, so it never purges under a running process.

Usage:
    python pipeline/purge_staging.py [--keep N]
"""
import argparse
from collections import defaultdict

import sqlalchemy as sa

from common import STAGING, pipeline_lock, warehouse_load

PURGED_TABLES = ["stg_initial_classicmodels", "stg_initial_customerservice",
                 "stg_clean", "stg_transform", "stg_loadready"]


def runs_to_purge(keep):
    with STAGING.connect() as con:
        runs = con.execute(sa.text("""
            SELECT run_id, proceso, run_origen, estado FROM staging_dw.etl_run
             WHERE depurado_en IS NULL ORDER BY run_id DESC""")).fetchall()

    kept, by_process = set(), defaultdict(list)
    for r in runs:
        by_process[r.proceso].append(r)
    for process_runs in by_process.values():
        kept |= {r.run_id for r in process_runs[:keep]}
        ok = [r.run_id for r in process_runs if r.estado == "OK"]
        kept |= set(ok[:1])
    for process in ("dimensiones", "hechos"):
        kept |= {x for x in warehouse_load(process) if x}
    kept |= {r.run_origen for r in runs if r.run_id in kept and r.run_origen}
    return sorted(r.run_id for r in runs if r.run_id not in kept), sorted(kept)


def main():
    parser = argparse.ArgumentParser(description="Purge old runs from the staging area.")
    parser.add_argument("--keep", type=int, default=3, metavar="N",
                        help="runs to keep whole per process (default 3, at least 1)")
    args = parser.parse_args()
    if args.keep < 1:
        parser.error("--keep must be at least 1")

    with pipeline_lock():
        purge, kept = runs_to_purge(args.keep)
        deleted = {}
        with STAGING.begin() as con:
            if purge:
                for table in PURGED_TABLES:
                    deleted[table] = con.execute(sa.text(
                        f"DELETE FROM staging_dw.{table} WHERE run_id = ANY(:r)"),
                        {"r": purge}).rowcount
                con.execute(sa.text("""
                    UPDATE staging_dw.etl_run SET depurado_en = now()
                     WHERE run_id = ANY(:r)"""), {"r": purge})

    print(f"Runs kept whole: {kept}")
    if not purge:
        print("Nothing to purge.")
        return
    print(f"Runs purged: {purge}")
    for table, n in deleted.items():
        print(f"    staging_dw.{table:<30}{n:>8} rows deleted")
    print(f"    {'TOTAL':<40}{sum(deleted.values()):>8} rows deleted")


if __name__ == "__main__":
    main()
