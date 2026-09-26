"""
Process 'staging': layers 1 to 4.

    1 Extract/Publish   layer1_extract.py
    2 Initial Staging   layer2_initial_staging.py
    3 Data Quality      layer3_data_quality.py
    4 Clean Staging     layer4_clean_staging.py

Opens a run in staging_dw.etl_run; the dimension and fact processes read
the Clean Staging of the latest run that finished OK. If this process
fails, its run is marked ERROR and never read. With --resume it continues
that run from the first layer that did not finish, over the same Initial
Staging, without reading the sources again (unless layer 2 itself failed:
layer 1 keeps its extracts in memory, so both are redone together).

Usage:
    python pipeline/run_staging.py [--resume]
"""
import layer1_extract
import layer2_initial_staging
import layer3_data_quality
import layer4_clean_staging
from common import (Layer, Process, count_rows, parse_args, pipeline_lock,
                    run_process)


def summary(run_id):
    read = (count_rows("stg_initial_classicmodels", run_id)
            + count_rows("stg_initial_customerservice", run_id))
    return read, count_rows("stg_clean", run_id), count_rows("stg_rejected", run_id)


PROCESS = Process(
    name="staging",
    script="run_staging.py",
    title="Integration, staging (layers 1-4)",
    metadata_name="etl_dw_staging",
    description="Capas 1 a 4: extrae las 13 tablas de las dos fuentes una sola "
                "vez, las perfila, evalua calidad tecnica y de negocio, y separa "
                "fisicamente limpios de rechazados.",
    sources="classicmodels (MySQL), customerservice (PostgreSQL)",
    target="staging (PostgreSQL)",
    summary=summary,
)

LAYERS = [
    Layer(2, "Extract/Publish + Initial Staging",
          ("stg_initial_classicmodels", "stg_initial_customerservice", "stg_perfil"),
          lambda r: layer2_initial_staging.run(r, layer1_extract.run())),
    Layer(3, "Data Quality", ("stg_error_log",), layer3_data_quality.run),
    Layer(4, "Clean Staging", ("stg_clean", "stg_rejected"),
          lambda r: sum(layer4_clean_staging.run(r))),
]


if __name__ == "__main__":
    args = parse_args("Pipeline layers 1-4: extract, quality, clean staging.")
    with pipeline_lock():
        run_id = run_process(PROCESS, LAYERS, resume=args.resume)
    read, clean, rejected = summary(run_id)
    print(f"\nStaging done. Read {read}, clean {clean}, rejected {rejected}.")
