"""
Layer 6 - Load-Ready Publish.

Checks that each target's rows from stg_transform fit the warehouse
table they are going to, and copies them to stg_loadready in their final
shape. After this step nothing is left to transform or to find out: Load
only has to copy. modelo_carga separates the dimension and fact branches.

The check reads the target's definition from the warehouse catalogue
(information_schema) and reports every problem at once, before Load
opens its transaction:

    - a column the target does not have
    - a required target column (NOT NULL, no default) the rows lack
    - a NULL in a NOT NULL column
    - text longer than its VARCHAR / CHAR
    - a number that does not fit its NUMERIC(p, s), SMALLINT or INTEGER

Without it, any of these would only surface inside Load as a database
error about the first offending row.

    Input   stg_transform (layer 5); the target definitions in dw
    Output  stg_loadready
    Reader  read_load_ready(run_id, targets), used by layer 7
"""
import pandas as pd
import sqlalchemy as sa

from common import DW, read_payload, write_payload

INTEGER_RANGES = {"smallint": 2 ** 15, "integer": 2 ** 31, "bigint": 2 ** 63}

# Filled by Load, not by the transformation.
LOAD_COLUMNS = {"lote_carga_key"}


def target_columns(target):
    """{column: definition} of a warehouse table, from information_schema."""
    with DW.connect() as con:
        return {r.column_name: r for r in con.execute(sa.text("""
            SELECT column_name, data_type, is_nullable, column_default,
                   character_maximum_length, numeric_precision, numeric_scale
              FROM information_schema.columns
             WHERE table_schema = 'public' AND table_name = :t"""), {"t": target})}


def shape_problems(target, df, columns):
    """Every way the rows of `target` do not fit its warehouse table."""
    if not columns:
        return [f"{target}: the table does not exist in the warehouse"]
    problems = []
    for col in df.columns:
        if col not in columns:
            problems.append(f"{target}.{col}: the table has no such column")
    for col, c in columns.items():
        if (c.is_nullable == "NO" and c.column_default is None
                and col not in df.columns and col not in LOAD_COLUMNS):
            problems.append(f"{target}.{col}: required (NOT NULL) but missing")

    for col in df.columns:
        c = columns.get(col)
        if c is None:
            continue
        s = df[col]
        present = s.dropna()
        if c.is_nullable == "NO" and len(present) < len(s):
            problems.append(f"{target}.{col}: {len(s) - len(present)} NULL values "
                            "in a NOT NULL column")
        if c.character_maximum_length:
            too_long = present.astype(str).str.len() > c.character_maximum_length
            if too_long.any():
                problems.append(
                    f"{target}.{col}: {int(too_long.sum())} values longer than "
                    f"{c.character_maximum_length} characters "
                    f"(e.g. {present[too_long].iloc[0]!r})")
        numbers = pd.to_numeric(present, errors="coerce")
        if c.data_type == "numeric" and c.numeric_precision:
            limit = 10 ** (c.numeric_precision - (c.numeric_scale or 0))
            out = numbers.abs().round(c.numeric_scale or 0) >= limit
            if out.any():
                problems.append(f"{target}.{col}: {int(out.sum())} values do not "
                                f"fit NUMERIC({c.numeric_precision},{c.numeric_scale})")
        if c.data_type in INTEGER_RANGES:
            bound = INTEGER_RANGES[c.data_type]
            out = (numbers < -bound) | (numbers >= bound) | (numbers % 1 != 0)
            if out.any():
                problems.append(f"{target}.{col}: {int(out.sum())} values are not "
                                f"a {c.data_type.upper()}")
    return problems


def check_shape(frames):
    """Raise, listing every problem, unless all frames fit their targets."""
    problems = [p for target, df in frames.items()
                for p in shape_problems(target, df, target_columns(target))]
    if problems:
        raise RuntimeError(
            "The rows do not fit the warehouse tables; nothing was loaded:\n  "
            + "\n  ".join(problems))


def run(run_id, model, targets):
    print(f"\n[Layer 6] Load-Ready Publish ({model})")
    frames = {t: read_payload("stg_transform", run_id, objetivo=t) for t in targets}
    check_shape(frames)
    print(f"    Shape checked against the warehouse: {len(frames)} tables fit")
    total = 0
    for target, df in frames.items():
        n = write_payload("stg_loadready", run_id, df,
                          modelo_carga=model, objetivo=target)
        total += n
        print(f"    {target:<24}{n:>6} rows")
    return total


def read_load_ready(run_id, targets):
    """{target: DataFrame} exactly as Load-Ready Publish left them."""
    return {t: read_payload("stg_loadready", run_id, objetivo=t) for t in targets}
