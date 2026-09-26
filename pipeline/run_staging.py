"""
Process 'staging': layers 1 to 4.

    1 Extract/Publish   layer1_extract.py
    2 Initial Staging   layer2_initial_staging.py
    3 Data Quality      layer3_data_quality.py
    4 Clean Staging     layer4_clean_staging.py

Opens a run in staging_dw.etl_run; the dimension and fact processes read
the Clean Staging of the latest run that finished OK. If this process
fails, its run is marked ERROR and never read.

Usage:
    python pipeline/run_staging.py
"""
import layer1_extract
import layer2_initial_staging
import layer3_data_quality
import layer4_clean_staging
from common import close_run, log_execution, open_run

PROCESS = "etl_dw_staging"      # name in the metadata repository
TARGET = "staging (PostgreSQL)"


if __name__ == "__main__":
    run_id = open_run("staging")
    print(f"Integration, staging (layers 1-4) - run_id={run_id}")
    try:
        extracts = layer1_extract.run()
        rows_read = layer2_initial_staging.run(run_id, extracts)
        log = layer3_data_quality.run(run_id)
        n_clean, n_rejected = layer4_clean_staging.run(run_id)
    except Exception as e:
        close_run(run_id, "ERROR")
        log_execution(PROCESS, "", "", TARGET, run_id, 0, 0, 0, "ERROR", str(e)[:500])
        raise
    close_run(run_id, "OK")
    log_execution(
        PROCESS,
        "Capas 1 a 4: extrae las 13 tablas de las dos fuentes una sola vez, "
        "las perfila, evalua calidad tecnica y de negocio, y separa "
        "fisicamente limpios de rechazados.",
        "classicmodels (MySQL), customerservice (PostgreSQL)",
        TARGET, run_id, rows_read, n_clean, n_rejected, "OK",
        quality_results=[(r, log.evaluated[r], log.failed[r])
                         for r in layer3_data_quality.RULES],
    )
    print(f"\nStaging done. Read {rows_read}, clean {n_clean}, rejected {n_rejected}.")
