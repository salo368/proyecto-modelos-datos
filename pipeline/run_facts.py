"""
Process 'hechos': layers 5 to 7 for the two facts.

    5 Transformation      layer5_transform_facts.py
    6 Load-Ready Publish  layer6_load_ready.py
    7 Load                layer7_load.py

Reads the same Clean Staging run as the dimension process and resolves
surrogate keys against the dimensions already loaded, so it must run
after run_dimensions.py. It refuses to start if the dimensions in the
warehouse came from another staging run. With --resume, a failed run
continues from the first layer that did not finish.

Usage:
    python pipeline/run_facts.py [--resume]
"""
import layer5_transform_facts as transform
import layer6_load_ready
import layer7_load
from common import (Layer, Process, check_dimensions_loaded_from, count_rows,
                    last_successful_staging_run, parse_args, pipeline_lock,
                    run_process)


def summary(run_id):
    return count_rows("stg_transform", run_id), count_rows("stg_loadready", run_id), 0


PROCESS = Process(
    name="hechos",
    script="run_facts.py",
    title="Integration, facts (layers 5-7)",
    metadata_name="etl_dw_facts",
    description="Capas 5 a 7 para el modelo de hechos: conforma ventas y "
                "servicio desde Clean Staging, resuelve llaves subrogadas y "
                "carga los dos hechos.",
    sources="staging_dw.stg_clean de la ultima corrida de staging exitosa "
            "(etl_execution.run_origen); las fuentes no se releen",
    target="dw (PostgreSQL)",
    summary=summary,
)


def layers(staging_run):
    return [
        Layer(5, "Transformation (facts)", ("stg_transform",),
              lambda r: transform.run(r, staging_run)),
        Layer(6, "Load-Ready Publish", ("stg_loadready",),
              lambda r: layer6_load_ready.run(r, "HECHOS", transform.TARGETS)),
        Layer(7, "Load", (),
              lambda r: layer7_load.run(r, transform.TARGETS, PROCESS.name, staging_run)),
    ]


if __name__ == "__main__":
    args = parse_args("Pipeline layers 5-7 for the facts.")
    with pipeline_lock():
        staging_run = last_successful_staging_run()
        check_dimensions_loaded_from(staging_run)
        run_id = run_process(PROCESS, layers(staging_run), staging_run, args.resume)
    print(f"\nFacts loaded: {summary(run_id)[1]} rows.")
