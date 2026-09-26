"""
Layer 4 - Clean Staging.

Separates, physically, the records that can continue from those that
cannot. A record goes to stg_rejected if Data Quality logged at least
one RECHAZADO failure for it; records with warnings only are clean.

    Input   stg_initial_* (layer 2) and stg_error_log (layer 3)
    Output  stg_clean, stg_rejected
    Reader  read_clean(staging_run, table), used by layer 5
"""
from collections import defaultdict

from common import insert, json_rows, read_payload
from layer2_initial_staging import read_initial
from layer3_data_quality import read_failures


def rejection_reasons(failures):
    """{(table, row number): [rules]} for records that must be rejected.

    Only RECHAZADO failures remove a record; ADVERTENCIA only logs it.
    """
    reasons = defaultdict(list)
    for f in failures:
        if f["accion"] == "RECHAZADO":
            reasons[(f["tabla_origen"], f["nro_fila"])].append(f["regla"])
    return reasons


def run(run_id):
    """Write accepted rows to stg_clean and rejected rows to stg_rejected."""
    print("\n[Layer 4] Clean Staging")
    data = read_initial(run_id)
    reasons = rejection_reasons(read_failures(run_id))

    total_clean = total_rejected = 0
    for table, (source, df) in data.items():
        clean, rejected = [], []
        body = df.drop(columns=["_nro_fila"])
        for payload, row_number in zip(json_rows(body), df["_nro_fila"]):
            key = (table, int(row_number))
            base = {"run_id": run_id, "fuente": source, "tabla_origen": table,
                    "nro_fila": int(row_number), "payload": payload}
            if key in reasons:
                rejected.append({**base, "motivos": ", ".join(sorted(set(reasons[key])))})
            else:
                clean.append(base)
        insert("stg_clean", clean)
        insert("stg_rejected", rejected)
        total_clean += len(clean)
        total_rejected += len(rejected)
        print(f"      {table:<22} clean {len(clean):>5}   rejected {len(rejected):>3}")
    print(f"    {'TOTAL':<22} clean {total_clean:>5}   rejected {total_rejected:>3}")
    return total_clean, total_rejected


def read_clean(staging_run, source_table):
    """Rows of a source table that Clean Staging accepted."""
    return read_payload("stg_clean", staging_run, tabla_origen=source_table)
