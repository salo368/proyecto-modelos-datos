"""
Technical-metadata ETL: loads the data dictionary of both sources into
the metadata repository (data_source, db_table, db_column).

Each stage reads the previous stage's table in schema `staging` of the
repository and writes its own, so every run can be audited by run_id:

    extract()             -> staging.stg_extract    data dictionary via SQLAlchemy inspect()
    data_quality()        -> staging.stg_dq         completeness, contradictions, duplicates
    transform()           -> staging.stg_transform  type normalisation + table descriptions
    load_ready_publish()  -> staging.stg_loadready  final shape
    load()                -> data_source, db_table, db_column (idempotent upsert)

Requires ddl/01_core_schema.sql and ddl/02_etl_staging.sql.

Usage:
    python metadata_repository/etl/etl_source_metadata.py
"""
import os
import re
import time

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text

load_dotenv()

CLASSICMODELS_URL = os.getenv("CLASSICMODELS_URL")
CUSTOMERSERVICE_URL = os.getenv("CUSTOMERSERVICE_URL")
METADATA_URL = os.getenv("METADATA_URL")

for name, val in [("CLASSICMODELS_URL", CLASSICMODELS_URL),
                  ("CUSTOMERSERVICE_URL", CUSTOMERSERVICE_URL),
                  ("METADATA_URL", METADATA_URL)]:
    if not val:
        raise ValueError(f"{name} is not defined in .env")

MYSQL_SCHEMA = "classicmodels"
PG_SCHEMA = "public"

mysql_engine = create_engine(CLASSICMODELS_URL)
pg_engine = create_engine(CUSTOMERSERVICE_URL)
repo_engine = create_engine(METADATA_URL)

SOURCES = [
    {"source_name": "classicmodels", "db_engine": "MySQL", "engine": mysql_engine, "schema": MYSQL_SCHEMA},
    {"source_name": "customerservice", "db_engine": "PostgreSQL", "engine": pg_engine, "schema": PG_SCHEMA},
]


def preflight_check():
    """Fail early with a clear message if the repository schema is missing."""
    inspector = inspect(repo_engine)
    if "staging" not in inspector.get_schema_names():
        raise RuntimeError(
            "Schema 'staging' does not exist in the metadata repository. "
            "Run metadata_repository/ddl/02_etl_staging.sql first."
        )

    staging_tables = set(inspector.get_table_names(schema="staging"))
    missing_staging = {"stg_extract", "stg_dq", "stg_transform", "stg_loadready"} - staging_tables
    if missing_staging:
        raise RuntimeError(
            f"Missing staging tables: {sorted(missing_staging)}. "
            "Run metadata_repository/ddl/02_etl_staging.sql."
        )

    public_tables = set(inspector.get_table_names(schema="public"))
    required = {"data_source", "db_table", "db_column", "business_entity",
                "business_attribute", "column_business_mapping"}
    missing = required - public_tables
    if missing:
        raise RuntimeError(
            f"Missing repository tables: {sorted(missing)}. "
            "Run metadata_repository/ddl/01_core_schema.sql."
        )


# Description of each source, stored in data_source.description.
SOURCE_DESCRIPTIONS = {
    "classicmodels": "Base de datos transaccional de ventas (MySQL): clientes, empleados, oficinas, "
                      "ordenes de compra, pagos junto con el catalogo de productos.",
    "customerservice": "Base de datos del centro de servicio al cliente (PostgreSQL): clientes, "
                        "empleados, catalogo de productos, llamadas de servicio junto con el registro "
                        "de productos de interes de cada cliente.",
}

# Business description of each table, added in transform().
TABLE_DESCRIPTIONS = {
    ("classicmodels", "customers"): "Clientes de la compania que realizan ordenes de compra.",
    ("classicmodels", "employees"): "Empleados de la compania, incluye representantes de ventas y su jerarquia.",
    ("classicmodels", "offices"): "Oficinas o sedes fisicas de la compania.",
    ("classicmodels", "orders"): "Encabezado de las ordenes de compra realizadas por los clientes.",
    ("classicmodels", "orderdetails"): "Detalle (lineas) de cada orden de compra: producto, cantidad y precio.",
    ("classicmodels", "payments"): "Pagos realizados por los clientes asociados a sus ordenes de compra.",
    ("classicmodels", "products"): "Catalogo de productos que la compania vende.",
    ("classicmodels", "productlines"): "Lineas o categorias de productos.",
    ("customerservice", "cs_customers"): "Clientes registrados en el sistema de call center.",
    ("customerservice", "cs_employees"): "Empleados que atienden llamadas en el call center.",
    ("customerservice", "cs_products"): "Catalogo de productos referenciado en las llamadas de servicio.",
    ("customerservice", "cs_customer_calls"): "Registro de llamadas de servicio al cliente.",
    ("customerservice", "cs_customer_products"): "Relacion entre clientes y productos consultados en servicio.",
}


def qualified_table(source_name, schema, table):
    if source_name == "customerservice":
        return f'"{schema}"."{table}"'
    return f"`{schema}`.`{table}`"


# ---------------------------------------------------------------------------
# Stage 1: EXTRACT - 1:1 copy of the source data dictionaries
# ---------------------------------------------------------------------------

def extract(run_id):
    rows = []
    for src in SOURCES:
        inspector = inspect(src["engine"])
        for table in inspector.get_table_names(schema=src["schema"]):
            count = pd.read_sql(
                f"SELECT COUNT(*) AS n FROM {qualified_table(src['source_name'], src['schema'], table)}",
                src["engine"],
            ).iloc[0]["n"]

            pk_cols = set(inspector.get_pk_constraint(table, schema=src["schema"])["constrained_columns"] or [])
            fk_map = {}
            for fk in inspector.get_foreign_keys(table, schema=src["schema"]):
                for c, rc in zip(fk["constrained_columns"], fk["referred_columns"]):
                    fk_map[c] = (fk["referred_table"], rc)

            for pos, col in enumerate(inspector.get_columns(table, schema=src["schema"]), start=1):
                ref = fk_map.get(col["name"])
                rows.append({
                    "run_id": run_id,
                    "source_name": src["source_name"],
                    "db_engine": src["db_engine"],
                    "schema_name": src["schema"],
                    "table_name": table,
                    "row_count_approx": int(count),
                    "column_name": col["name"],
                    "ordinal_position": pos,
                    "data_type": str(col["type"]),
                    "is_nullable": bool(col["nullable"]),
                    "is_primary_key": col["name"] in pk_cols,
                    "is_foreign_key": col["name"] in fk_map,
                    "fk_ref_table": ref[0] if ref else None,
                    "fk_ref_column": ref[1] if ref else None,
                })

    df = pd.DataFrame(rows)
    df.to_sql("stg_extract", repo_engine, schema="staging", if_exists="append", index=False)
    print(f"[EXTRACT] {len(df)} rows -> staging.stg_extract (run_id={run_id})")
    return df


# ---------------------------------------------------------------------------
# Stage 2: DATA QUALITY - completeness, contradictions, duplicates
# ---------------------------------------------------------------------------

def data_quality(run_id):
    df = pd.read_sql(
        text("SELECT * FROM staging.stg_extract WHERE run_id = :rid"), repo_engine, params={"rid": run_id}
    )

    statuses, notes = [], []
    seen = set()
    for _, row in df.iterrows():
        issues = []
        if not row["table_name"] or not row["column_name"]:
            issues.append("nombre de tabla o columna vacio")
        if row["is_primary_key"] and row["is_nullable"]:
            issues.append("llave primaria marcada como nullable (contradiccion)")
        key = (row["source_name"], row["schema_name"], row["table_name"], row["column_name"])
        if key in seen:
            issues.append("fila duplicada en el extract")
        seen.add(key)

        if issues:
            statuses.append("RECHAZADO")
            notes.append("; ".join(issues))
        else:
            statuses.append("OK")
            notes.append(None)

    df["dq_status"] = statuses
    df["dq_notes"] = notes
    df.to_sql("stg_dq", repo_engine, schema="staging", if_exists="append", index=False)

    rejected = (df["dq_status"] == "RECHAZADO").sum()
    print(f"[DATA QUALITY] {len(df)} rows checked, {rejected} rejected (run_id={run_id})")
    return df


# ---------------------------------------------------------------------------
# Stage 3: TRANSFORM - cross-engine type normalisation and enrichment
# ---------------------------------------------------------------------------

def normalize_data_type(raw):
    t = raw.upper()
    m = re.search(r"\((\d+)\)", t)
    length = m.group(1) if m else None
    if "VARCHAR" in t or "CHARACTER VARYING" in t:
        return f"VARCHAR({length})" if length else "VARCHAR"
    if "TINYINT" in t or "SMALLINT" in t or "BIGINT" in t or re.search(r"\bINT\b", t) or "INTEGER" in t:
        return "INTEGER"
    if "DECIMAL" in t or "NUMERIC" in t:
        return "DECIMAL"
    if "TIMESTAMP" in t:
        return "TIMESTAMP"
    if t.startswith("DATE"):
        return "DATE"
    if "MEDIUMTEXT" in t or "TEXT" in t:
        return "TEXT"
    if "BLOB" in t:
        return "BINARY"
    if "BOOL" in t:
        return "BOOLEAN"
    return t


def transform(run_id):
    df = pd.read_sql(
        text("SELECT * FROM staging.stg_dq WHERE run_id = :rid AND dq_status = 'OK'"),
        repo_engine, params={"rid": run_id},
    )
    df = df.drop(columns=["dq_status", "dq_notes"])
    df["native_data_type"] = df["data_type"]
    df["data_type"] = df["data_type"].apply(normalize_data_type)
    df["table_description"] = df.apply(
        lambda r: TABLE_DESCRIPTIONS.get((r["source_name"], r["table_name"]), ""), axis=1
    )
    df.to_sql("stg_transform", repo_engine, schema="staging", if_exists="append", index=False)
    print(f"[TRANSFORM] {len(df)} rows normalised and enriched (run_id={run_id})")
    return df


# ---------------------------------------------------------------------------
# Stage 4: LOAD READY PUBLISH - exact shape of the target tables
# ---------------------------------------------------------------------------

def load_ready_publish(run_id):
    df = pd.read_sql(
        text("SELECT * FROM staging.stg_transform WHERE run_id = :rid"), repo_engine, params={"rid": run_id}
    )
    df.to_sql("stg_loadready", repo_engine, schema="staging", if_exists="append", index=False)
    print(f"[LOAD READY PUBLISH] {len(df)} rows ready to load (run_id={run_id})")
    return df


# ---------------------------------------------------------------------------
# Stage 5: TARGET LOAD - idempotent upsert into the repository
# ---------------------------------------------------------------------------

def load(run_id):
    df = pd.read_sql(
        text("SELECT * FROM staging.stg_loadready WHERE run_id = :rid"), repo_engine, params={"rid": run_id}
    )

    with repo_engine.begin() as conn:
        # 1. data_source
        for (source_name, db_engine_), _ in df.groupby(["source_name", "db_engine"]):
            conn.execute(text("""
                INSERT INTO data_source (source_name, db_engine, description)
                VALUES (:s, :e, :d)
                ON CONFLICT (source_name) DO UPDATE
                    SET db_engine = EXCLUDED.db_engine,
                        description = EXCLUDED.description
            """), {"s": source_name, "e": db_engine_, "d": SOURCE_DESCRIPTIONS.get(source_name, "")})

        # 2. db_table
        tables_df = df[["source_name", "schema_name", "table_name", "table_description", "row_count_approx"]].drop_duplicates()
        for _, t in tables_df.iterrows():
            source_id = conn.execute(
                text("SELECT source_id FROM data_source WHERE source_name = :s"), {"s": t["source_name"]}
            ).scalar()
            conn.execute(text("""
                INSERT INTO db_table (source_id, schema_name, table_name, table_description, row_count_approx, loaded_at)
                VALUES (:sid, :sch, :tbl, :desc, :rc, now())
                ON CONFLICT (source_id, schema_name, table_name) DO UPDATE
                    SET table_description = EXCLUDED.table_description,
                        row_count_approx = EXCLUDED.row_count_approx,
                        loaded_at = now()
            """), {"sid": source_id, "sch": t["schema_name"], "tbl": t["table_name"],
                    "desc": t["table_description"], "rc": int(t["row_count_approx"])})

        # 3. db_column (first pass, fk_ref_column_id still unresolved)
        for _, c in df.iterrows():
            table_id = conn.execute(text("""
                SELECT dt.table_id FROM db_table dt
                JOIN data_source ds ON dt.source_id = ds.source_id
                WHERE ds.source_name = :s AND dt.schema_name = :sch AND dt.table_name = :tbl
            """), {"s": c["source_name"], "sch": c["schema_name"], "tbl": c["table_name"]}).scalar()

            conn.execute(text("""
                INSERT INTO db_column (table_id, column_name, ordinal_position, data_type, native_data_type,
                                       is_nullable, is_primary_key, is_foreign_key, loaded_at)
                VALUES (:tid, :col, :pos, :dt, :ndt, :nul, :pk, :fk, now())
                ON CONFLICT (table_id, column_name) DO UPDATE
                    SET ordinal_position = EXCLUDED.ordinal_position,
                        data_type = EXCLUDED.data_type,
                        native_data_type = EXCLUDED.native_data_type,
                        is_nullable = EXCLUDED.is_nullable,
                        is_primary_key = EXCLUDED.is_primary_key,
                        is_foreign_key = EXCLUDED.is_foreign_key,
                        loaded_at = now()
            """), {"tid": table_id, "col": c["column_name"], "pos": int(c["ordinal_position"]),
                    "dt": c["data_type"], "ndt": c["native_data_type"], "nul": bool(c["is_nullable"]),
                    "pk": bool(c["is_primary_key"]), "fk": bool(c["is_foreign_key"])})

        # 4. second pass: resolve fk_ref_column_id (self-reference)
        fk_rows = df[df["is_foreign_key"] == True]  # noqa: E712
        for _, c in fk_rows.iterrows():
            col_id = conn.execute(text("""
                SELECT dc.column_id FROM db_column dc
                JOIN db_table dt ON dc.table_id = dt.table_id
                JOIN data_source ds ON dt.source_id = ds.source_id
                WHERE ds.source_name = :s AND dt.schema_name = :sch
                  AND dt.table_name = :tbl AND dc.column_name = :col
            """), {"s": c["source_name"], "sch": c["schema_name"], "tbl": c["table_name"], "col": c["column_name"]}).scalar()

            ref_col_id = conn.execute(text("""
                SELECT dc.column_id FROM db_column dc
                JOIN db_table dt ON dc.table_id = dt.table_id
                JOIN data_source ds ON dt.source_id = ds.source_id
                WHERE ds.source_name = :s AND dt.schema_name = :sch
                  AND dt.table_name = :reftbl AND dc.column_name = :refcol
            """), {"s": c["source_name"], "sch": c["schema_name"],
                    "reftbl": c["fk_ref_table"], "refcol": c["fk_ref_column"]}).scalar()

            if col_id and ref_col_id:
                conn.execute(
                    text("UPDATE db_column SET fk_ref_column_id = :r WHERE column_id = :c"),
                    {"r": ref_col_id, "c": col_id},
                )

    print(f"[TARGET LOAD] repository updated (run_id={run_id})")


# ---------------------------------------------------------------------------
def main():
    run_id = int(time.time())
    print(f"=== Source technical metadata ETL - run_id {run_id} ===")
    preflight_check()
    extract(run_id)
    data_quality(run_id)
    transform(run_id)
    load_ready_publish(run_id)
    load(run_id)
    print("Done.")


if __name__ == "__main__":
    main()
