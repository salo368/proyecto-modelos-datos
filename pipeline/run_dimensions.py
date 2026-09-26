"""
Process 'dimensiones': layers 5 to 7 for the six dimensions.

    5 Transformation      layer5_transform_dimensions.py
    6 Load-Ready Publish  layer6_load_ready.py
    7 Load                layer7_load.py

Reads the Clean Staging of the latest successful staging run; the
sources are not read again. With --resume, a failed run continues from
the first layer that did not finish.

Usage:
    python pipeline/run_dimensions.py [--resume]
"""
import layer5_transform_dimensions as transform
import layer6_load_ready
import layer7_load
from common import (Layer, Process, count_rows, last_successful_staging_run,
                    parse_args, pipeline_lock, run_process)


def summary(run_id):
    return count_rows("stg_transform", run_id), count_rows("stg_loadready", run_id), 0


PROCESS = Process(
    name="dimensiones",
    script="run_dimensions.py",
    title="Integration, dimensions (layers 5-7)",
    metadata_name="etl_dw_dimensions",
    description="Capas 5 a 7 para el modelo de dimensiones: conforma por area "
                "tematica desde Clean Staging y carga las seis dimensiones.",
    sources="staging_dw.stg_clean de la ultima corrida de staging exitosa "
            "(etl_execution.run_origen); las fuentes no se releen",
    target="dw (PostgreSQL)",
    summary=summary,
)


def layers(staging_run):
    return [
        Layer(5, "Transformation (dimensions)", ("stg_transform",),
              lambda r: transform.run(r, staging_run)),
        Layer(6, "Load-Ready Publish", ("stg_loadready",),
              lambda r: layer6_load_ready.run(r, "DIMENSIONES", transform.TARGETS)),
        Layer(7, "Load", (),
              lambda r: layer7_load.run(r, transform.TARGETS, PROCESS.name, staging_run)),
    ]


if __name__ == "__main__":
    args = parse_args("Pipeline layers 5-7 for the dimensions.")
    with pipeline_lock():
        staging_run = last_successful_staging_run()
        run_id = run_process(PROCESS, layers(staging_run), staging_run, args.resume)
    print(f"\nDimensions loaded: {summary(run_id)[1]} rows.")
