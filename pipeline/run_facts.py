"""
Process 'hechos': layers 5 to 7 for the two facts.

    5 Transformation      layer5_transform_facts.py
    6 Load-Ready Publish  layer6_load_ready.py
    7 Load                layer7_load.py

Reads the same Clean Staging run as the dimension process and resolves
surrogate keys against the dimensions already loaded, so it must run
after run_dimensions.py.

Usage:
    python pipeline/run_facts.py
"""
import layer5_transform_facts as transform
import layer6_load_ready
import layer7_load
from common import close_run, last_successful_staging_run, log_execution, open_run

PROCESS = "etl_dw_facts"        # name in the metadata repository
TARGET = "dw (PostgreSQL)"


if __name__ == "__main__":
    staging_run = last_successful_staging_run()
    run_id = open_run("hechos", source_run=staging_run)
    print(f"Integration, facts (layers 5-7) - run_id={run_id}, "
          f"reading Clean Staging of run {staging_run}")
    try:
        rows_read, quality = transform.run(run_id, staging_run)
        layer6_load_ready.run(run_id, "HECHOS", transform.TARGETS)
        written = layer7_load.run(run_id, transform.TARGETS)
    except Exception as e:
        close_run(run_id, "ERROR")
        log_execution(PROCESS, "", "", TARGET, run_id, 0, 0, 0, "ERROR", str(e)[:500])
        raise
    close_run(run_id, "OK")
    log_execution(
        PROCESS,
        "Capas 5 a 7 para el modelo de hechos: conforma ventas y servicio "
        "desde Clean Staging, resuelve llaves subrogadas y carga los dos "
        "hechos.",
        f"staging_dw.stg_clean (run {staging_run}); las fuentes no se releen",
        TARGET, run_id, rows_read, written, 0, "OK", quality_results=quality,
    )
    print(f"\nFacts loaded: {written} rows.")
