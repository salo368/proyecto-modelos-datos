"""
Relationship profiling of the sources, complementing the per-column
profiles.

For every declared foreign key of each source:
    rows in the child table, % null FKs, orphan rows (value missing in
    the parent) and observed cardinality (1:1 or 1:N).

For the three entities present in both sources (customers, employees,
products):
    keys only in classicmodels, only in customerservice or in both
    (Jaccard overlap), duplicate keys per source, and field-by-field
    match rate for the keys present on both sides.

Writes to profiling/output/:
    relaciones_fk.csv
    correspondencia_entidades.csv

Usage:
    python profiling/referential_profiling.py
"""
import os
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


# ---------------------------------------------------------------------------
# 1. Referential integrity within each source
# ---------------------------------------------------------------------------

def profile_foreign_keys(engine, schema, db_label):
    inspector = inspect(engine)
    tables = inspector.get_table_names(schema=schema)
    rows = []

    for table in tables:
        fks = inspector.get_foreign_keys(table, schema=schema)
        for fk in fks:
            child_cols = fk["constrained_columns"]
            parent_table = fk["referred_table"]
            parent_cols = fk["referred_columns"]

            child_col_sql = ", ".join(f'"{c}"' if schema == PG_SCHEMA else f"`{c}`" for c in child_cols)
            parent_col_sql = ", ".join(f'"{c}"' if schema == PG_SCHEMA else f"`{c}`" for c in parent_cols)

            qualified_child = f'"{schema}"."{table}"' if schema == PG_SCHEMA else f"`{schema}`.`{table}`"
            qualified_parent = f'"{schema}"."{parent_table}"' if schema == PG_SCHEMA else f"`{schema}`.`{parent_table}`"

            df_child = pd.read_sql(f"SELECT {child_col_sql} FROM {qualified_child}", engine)
            df_parent = pd.read_sql(f"SELECT {parent_col_sql} FROM {qualified_parent}", engine)

            total = len(df_child)
            null_mask = df_child[child_cols].isnull().any(axis=1)
            nulls = int(null_mask.sum())

            non_null_child = df_child.loc[~null_mask]
            child_keys = list(non_null_child[child_cols].itertuples(index=False, name=None))
            parent_keys = set(df_parent[parent_cols].itertuples(index=False, name=None))

            orphan_keys = [k for k in child_keys if k not in parent_keys]
            orphans = len(orphan_keys)
            pct_orphans = round(100 * orphans / total, 2) if total else 0.0

            counts_per_parent = pd.Series(child_keys).value_counts() if child_keys else pd.Series(dtype=int)
            max_children = int(counts_per_parent.max()) if not counts_per_parent.empty else 0
            cardinality = "1:1" if max_children <= 1 else "1:N"

            rows.append({
                "base_datos": db_label,
                "tabla_hija": table,
                "columna_fk": ", ".join(child_cols),
                "tabla_padre": parent_table,
                "columna_pk_padre": ", ".join(parent_cols),
                "total_filas_hija": total,
                "fk_nulas": nulls,
                "pct_fk_nulas": round(100 * nulls / total, 2) if total else 0.0,
                "filas_huerfanas": orphans,
                "pct_huerfanas": pct_orphans,
                "max_hijos_por_padre": max_children,
                "cardinalidad_observada": cardinality,
            })
            print(f"  [{db_label}] {table}.{child_cols} -> {parent_table}.{parent_cols}: "
                  f"{orphans} orphans ({pct_orphans}%), cardinality {cardinality}")

    return rows


# ---------------------------------------------------------------------------
# 2. Key correspondence of the entities present in both sources
# ---------------------------------------------------------------------------

COMMON_ENTITIES = [
    {
        "entidad": "customers",
        "tabla_mysql": "customers", "pk_mysql": "customerNumber",
        "tabla_pg": "cs_customers", "pk_pg": "customernumber",
        "campos_comparables": [
            ("phone", "phone"), ("city", "city"), ("state", "state"),
            ("country", "country"), ("postalCode", "postalcode"),
        ],
    },
    {
        "entidad": "employees",
        "tabla_mysql": "employees", "pk_mysql": "employeeNumber",
        "tabla_pg": "cs_employees", "pk_pg": "employeenumber",
        "campos_comparables": [("lastName", "lastname"), ("firstName", "firstname"), ("email", "email")],
    },
    {
        "entidad": "products",
        "tabla_mysql": "products", "pk_mysql": "productCode",
        "tabla_pg": "cs_products", "pk_pg": "productcode",
        "campos_comparables": [
            ("productName", "productname"), ("productScale", "productscale"),
            ("productVendor", "productvendor"),
        ],
    },
]


def normalize(v):
    if v is None:
        return None
    return str(v).strip().lower()


def profile_common_entities():
    rows = []
    for spec in COMMON_ENTITIES:
        df_my = pd.read_sql(
            f"SELECT * FROM `{MYSQL_SCHEMA}`.`{spec['tabla_mysql']}`", mysql_engine
        )
        df_pg = pd.read_sql(
            f'SELECT * FROM "{PG_SCHEMA}"."{spec["tabla_pg"]}"', pg_engine
        )

        my_keys = df_my[spec["pk_mysql"]].tolist()
        pg_keys = df_pg[spec["pk_pg"]].astype(type(my_keys[0]) if my_keys else int).tolist()

        set_my, set_pg = set(my_keys), set(pg_keys)
        only_my = set_my - set_pg
        only_pg = set_pg - set_my
        both = set_my & set_pg

        dup_my = len(my_keys) - len(set_my)
        dup_pg = len(pg_keys) - len(set_pg)

        jaccard = round(100 * len(both) / len(set_my | set_pg), 2) if (set_my | set_pg) else 0.0

        # Field-by-field match for keys present on both sides
        df_my_idx = df_my.set_index(spec["pk_mysql"])
        df_pg_idx = df_pg.set_index(spec["pk_pg"])

        field_matches = {}
        for col_my, col_pg in spec["campos_comparables"]:
            matches = 0
            for k in both:
                v_my = normalize(df_my_idx.loc[k, col_my]) if col_my in df_my_idx.columns else None
                v_pg = normalize(df_pg_idx.loc[k, col_pg]) if col_pg in df_pg_idx.columns else None
                if v_my == v_pg:
                    matches += 1
            pct = round(100 * matches / len(both), 2) if both else 0.0
            field_matches[col_my] = pct

        rows.append({
            "entidad": spec["entidad"],
            "llaves_solo_classicmodels": len(only_my),
            "llaves_solo_customerservice": len(only_pg),
            "llaves_en_ambas": len(both),
            "pct_solapamiento_jaccard": jaccard,
            "duplicados_en_classicmodels": dup_my,
            "duplicados_en_customerservice": dup_pg,
            **{f"pct_coincidencia_{c}": v for c, v in field_matches.items()},
        })
        print(f"  {spec['entidad']}: {len(both)} shared, "
              f"{len(only_my)} only in classicmodels, {len(only_pg)} only in customerservice "
              f"(overlap {jaccard}%)")

    return rows


# ---------------------------------------------------------------------------
def main():
    print("=" * 70)
    print("REFERENTIAL INTEGRITY")
    print("=" * 70)

    fk_rows = []
    print("\n-- classicmodels (MySQL) --")
    fk_rows += profile_foreign_keys(mysql_engine, MYSQL_SCHEMA, "classicmodels")
    print("\n-- customerservice (PostgreSQL) --")
    fk_rows += profile_foreign_keys(pg_engine, PG_SCHEMA, "customerservice")

    fk_path = OUTPUT_DIR / "relaciones_fk.csv"
    pd.DataFrame(fk_rows).to_csv(fk_path, index=False, encoding="utf-8")
    print(f"\nWritten: {fk_path}")

    print("\n" + "=" * 70)
    print("COMMON ENTITIES ACROSS SOURCES")
    print("=" * 70)
    common_rows = profile_common_entities()

    common_path = OUTPUT_DIR / "correspondencia_entidades.csv"
    pd.DataFrame(common_rows).to_csv(common_path, index=False, encoding="utf-8")
    print(f"\nWritten: {common_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
