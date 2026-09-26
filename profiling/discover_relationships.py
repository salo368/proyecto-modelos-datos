"""
Discovery of undeclared relationships (inclusion dependencies).

Instead of starting from the declared foreign keys, compares the
distinct values of every identifier-like column of the 13 source tables
(across MySQL and PostgreSQL) against every candidate key, and reports
pairs where at least MIN_CONTAINMENT of the values are contained. This
rediscovers the declared FKs and finds implicit ones, notably the
cross-database links that cannot be declared as real FKs.

Writes:
    profiling/output/relaciones_inferidas.csv

Usage:
    python profiling/discover_relationships.py
"""
import os
from itertools import product
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

load_dotenv()

CLASSICMODELS_URL = os.getenv("CLASSICMODELS_URL")
CUSTOMERSERVICE_URL = os.getenv("CUSTOMERSERVICE_URL")
if not CLASSICMODELS_URL or not CUSTOMERSERVICE_URL:
    raise ValueError("CLASSICMODELS_URL and CUSTOMERSERVICE_URL must be defined in .env")

MYSQL_SCHEMA = "classicmodels"
PG_SCHEMA = "public"

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

mysql_engine = create_engine(CLASSICMODELS_URL)
pg_engine = create_engine(CUSTOMERSERVICE_URL)

# Free text and binary columns are never identifiers.
EXCLUDED_TYPE_KEYWORDS = ("text", "blob", "mediumtext", "mediumblob")
MAX_VARCHAR_LEN_AS_ID = 100  # longer varchars are not treated as identifiers

MIN_CONTAINMENT = 0.90       # min share of A's values contained in B to report
MIN_KEY_DISTINCT = 5         # ignore candidate keys with tiny domains (e.g. 'status')


# ---------------------------------------------------------------------------
# 1. Identifier-like columns of both sources
# ---------------------------------------------------------------------------

def qualified_table(db_label, schema, table):
    if db_label == "customerservice":
        return f'"{schema}"."{table}"'
    return f"`{schema}`.`{table}`"


def qualified_col(db_label, col):
    if db_label == "customerservice":
        return f'"{col}"'
    return f"`{col}`"


def list_identifier_columns(engine, schema, db_label):
    inspector = inspect(engine)
    columns_info = []
    for table in inspector.get_table_names(schema=schema):
        for col in inspector.get_columns(table, schema=schema):
            type_str = str(col["type"]).lower()
            if any(k in type_str for k in EXCLUDED_TYPE_KEYWORDS):
                continue
            if "varchar" in type_str or "character varying" in type_str:
                length = getattr(col["type"], "length", None)
                if length and length > MAX_VARCHAR_LEN_AS_ID:
                    continue
            columns_info.append({
                "db": db_label, "schema": schema, "table": table,
                "column": col["name"], "type": type_str,
            })
    return columns_info


def load_values(engine, db_label, schema, table, column):
    q = f"SELECT DISTINCT {qualified_col(db_label, column)} FROM {qualified_table(db_label, schema, table)} " \
        f"WHERE {qualified_col(db_label, column)} IS NOT NULL"
    df = pd.read_sql(q, engine)
    return set(str(v).strip().lower() for v in df.iloc[:, 0].tolist())


def load_known_fks(engine, schema):
    inspector = inspect(engine)
    known = set()
    for table in inspector.get_table_names(schema=schema):
        for fk in inspector.get_foreign_keys(table, schema=schema):
            for c, rc in zip(fk["constrained_columns"], fk["referred_columns"]):
                known.add((table, c, fk["referred_table"], rc))
    return known


# ---------------------------------------------------------------------------
# 2. Inclusion-dependency discovery
# ---------------------------------------------------------------------------

def main():
    print("Listing candidate columns...")
    cols_mysql = list_identifier_columns(mysql_engine, MYSQL_SCHEMA, "classicmodels")
    cols_pg = list_identifier_columns(pg_engine, PG_SCHEMA, "customerservice")
    all_cols = cols_mysql + cols_pg
    print(f"  {len(cols_mysql)} candidate columns in classicmodels, "
          f"{len(cols_pg)} in customerservice")

    engines = {"classicmodels": mysql_engine, "customerservice": pg_engine}

    print("\nLoading distinct values of each candidate column...")
    values_cache = {}
    for c in all_cols:
        key = (c["db"], c["table"], c["column"])
        values_cache[key] = load_values(engines[c["db"]], c["db"], c["schema"], c["table"], c["column"])
        print(f"  {c['db']}.{c['table']}.{c['column']}: {len(values_cache[key])} distinct values")

    # Candidate keys: columns with a non-trivial number of distinct values.
    candidate_keys = [c for c in all_cols if len(values_cache[(c["db"], c["table"], c["column"])]) >= MIN_KEY_DISTINCT]

    known_fks = {
        "classicmodels": load_known_fks(mysql_engine, MYSQL_SCHEMA),
        "customerservice": load_known_fks(pg_engine, PG_SCHEMA),
    }

    print("\nSearching inclusion dependencies...")
    results = []
    for src, dst in product(all_cols, candidate_keys):
        if src["db"] == dst["db"] and src["table"] == dst["table"] and src["column"] == dst["column"]:
            continue

        src_values = values_cache[(src["db"], src["table"], src["column"])]
        dst_values = values_cache[(dst["db"], dst["table"], dst["column"])]
        if not src_values or not dst_values:
            continue

        contained = src_values & dst_values
        containment = len(contained) / len(src_values)
        if containment < MIN_CONTAINMENT:
            continue

        # The target must look like a key: at least half as many distinct
        # values as the source (filters coincidental overlaps like 'country').
        if len(dst_values) < len(src_values) * 0.5:
            continue

        is_cross_db = src["db"] != dst["db"]
        declared = (src["table"], src["column"], dst["table"], dst["column"]) in known_fks.get(src["db"], set())

        results.append({
            "tabla_columna_origen": f"{src['db']}.{src['table']}.{src['column']}",
            "tabla_columna_destino_llave": f"{dst['db']}.{dst['table']}.{dst['column']}",
            "pct_contencion": round(100 * containment, 2),
            "valores_origen": len(src_values),
            "valores_destino": len(dst_values),
            "cruza_bases_de_datos": is_cross_db,
            "ya_declarada_como_fk": declared,
        })
        scope = "cross-DB" if is_cross_db else "same DB"
        tag = "declared" if declared else "NEW/implicit"
        print(f"  [{scope}] [{tag}] {src['db']}.{src['table']}.{src['column']} -> "
              f"{dst['db']}.{dst['table']}.{dst['column']} ({round(100*containment,2)}%)")

    df_out = pd.DataFrame(results).sort_values(
        ["cruza_bases_de_datos", "ya_declarada_como_fk", "pct_contencion"],
        ascending=[False, True, False],
    )
    out_path = OUTPUT_DIR / "relaciones_inferidas.csv"
    df_out.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\nWritten: {out_path} ({len(df_out)} relationships found)")


if __name__ == "__main__":
    main()
