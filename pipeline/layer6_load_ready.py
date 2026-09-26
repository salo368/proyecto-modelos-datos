"""
Layer 6 - Load-Ready Publish.

Copies each target's rows from stg_transform to stg_loadready in their
final shape. After this step nothing is left to transform: Load only
has to copy. modelo_carga separates the dimension and fact branches.

    Input   stg_transform (layer 5)
    Output  stg_loadready
    Reader  read_load_ready(run_id, targets), used by layer 7
"""
from common import read_payload, write_payload


def run(run_id, model, targets):
    print(f"\n[Layer 6] Load-Ready Publish ({model})")
    for target in targets:
        df = read_payload("stg_transform", run_id, objetivo=target)
        n = write_payload("stg_loadready", run_id, df,
                          modelo_carga=model, objetivo=target)
        print(f"    {target:<24}{n:>6} rows")


def read_load_ready(run_id, targets):
    """{target: DataFrame} exactly as Load-Ready Publish left them."""
    return {t: read_payload("stg_loadready", run_id, objetivo=t) for t in targets}
