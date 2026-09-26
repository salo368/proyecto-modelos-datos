"""
Generate a plain-SQL backup (schema + data) of the data warehouse or the
metadata repository.

The schema comes from the project's own DDL files, so the backup keeps
every constraint, index, comment and view; the data is dumped as INSERT
statements in foreign-key order. The file restores with psql on an
empty PostgreSQL database and needs no pg_dump binary on the host.

Staging schemas (staging_dw, staging) are not included: they hold the
load history and are rebuilt by running the ETL.

Usage:
    python tools/generate_backup.py dw
    python tools/generate_backup.py metadata
"""
import os
import sys
from datetime import date

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

TARGETS = {
    "dw": {
        "url_var": "DW_URL",
        "output":  "datawarehouse/backup/dw_backup.sql",
        "title":   "Almacen de datos (modelo dimensional)",
        "ddl":     ["datawarehouse/ddl/01_star_schema.sql",
                    "datawarehouse/ddl/03_data_marts.sql"],
        # Load order respects foreign keys.
        "tables": [
            "dim_tiempo", "dim_cliente", "dim_producto", "dim_empleado",
            "dim_oficina", "dim_estado_orden",
            "fact_ventas", "fact_llamadas_servicio",
        ],
        "views": ["dm.vw_interaccion_cliente_producto", "dm.vw_ventas_mensuales_linea"],
    },
    "metadata": {
        "url_var": "METADATA_URL",
        "output":  "metadata_repository/backup/metadata_repo_backup.sql",
        "title":   "Repositorio de metadatos",
        "ddl":     ["metadata_repository/ddl/01_core_schema.sql",
                    "metadata_repository/ddl/03_dw_extension.sql",
                    "metadata_repository/ddl/04_usage_extension.sql"],
        "tables": [
            "data_source", "db_table", "db_column",
            "business_entity", "business_attribute", "column_business_mapping",
            "dw_object", "dw_measure", "dw_attribute", "dw_lineage",
            "etl_process", "etl_execution", "dq_rule", "dq_result",
            "usage_herramienta", "usage_consulta", "usage_consulta_objeto",
            "usage_acceso_objeto",
        ],
        "views": ["vw_perfil_uso"],
    },
}


def sql_literal(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def dump_table(con, table):
    result = con.execute(sa.text(f"SELECT * FROM {table}"))
    rows = result.fetchall()
    cols = list(result.keys())
    if not rows:
        return f"-- {table}: 0 filas\n\n"

    out = [f"-- {table}: {len(rows)} filas\n"]
    for i in range(0, len(rows), 200):          # 200 rows per INSERT
        chunk = rows[i:i + 200]
        values = ",\n".join(
            "    (" + ", ".join(sql_literal(v) for v in row) + ")" for row in chunk
        )
        out.append(f"INSERT INTO {table} ({', '.join(cols)}) VALUES\n{values};\n")
    out.append("\n")
    return "".join(out)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in TARGETS:
        raise SystemExit(f"Usage: python {sys.argv[0]} [{' | '.join(TARGETS)}]")

    cfg = TARGETS[sys.argv[1]]
    engine = sa.create_engine(os.getenv(cfg["url_var"]))
    insp = sa.inspect(engine)
    existing = set(insp.get_table_names(schema="public"))
    tables = [t for t in cfg["tables"] if t in existing]

    parts = [
        "-- ============================================================\n",
        f"-- Backup: {cfg['title']}\n",
        f"-- Generated: {date.today().isoformat()} by tools/generate_backup.py\n",
        "-- Engine: PostgreSQL 16\n",
        "--\n",
        "-- Restore on an empty database with:\n",
        f"--   psql \"<connection-url>\" -f {cfg['output']}\n",
        "--\n",
        "-- Contents:\n",
    ]
    with engine.connect() as con:
        for t in tables:
            n = con.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar()
            parts.append(f"--   {t}: {n} filas\n")
    parts.append("-- ============================================================\n\n")

    parts.append("-- Drop previous objects\n")
    for t in reversed(tables):
        parts.append(f"DROP TABLE IF EXISTS {t} CASCADE;\n")
    parts.append("\n")

    for path in cfg["ddl"]:
        with open(path, encoding="utf-8") as f:
            ddl = "\n".join(line for line in f.read().splitlines()
                            if not line.strip().startswith("DROP "))
        parts.append(f"-- ---- {path} ----\n{ddl}\n\n")

    parts.append("-- ============================================================\n")
    parts.append("-- Data\n")
    parts.append("-- ============================================================\n\n")
    with engine.connect() as con:
        for t in tables:
            parts.append(dump_table(con, t))

        parts.append("-- Sync SERIAL sequences with the restored data\n")
        for t in tables:
            for c in insp.get_columns(t, schema="public"):
                if "nextval" in str(c.get("default") or ""):
                    max_id = con.execute(
                        sa.text(f"SELECT COALESCE(MAX({c['name']}), 0) FROM {t}")
                    ).scalar()
                    parts.append(
                        f"SELECT setval(pg_get_serial_sequence('{t}', '{c['name']}'), "
                        f"{max_id}, {'true' if max_id else 'false'});\n"
                    )

    output = cfg["output"]
    os.makedirs(os.path.dirname(output), exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        f.write("".join(parts))

    kb = os.path.getsize(output) / 1024
    print(f"{output}  ({kb:.0f} KB, {len(tables)} tables)")


if __name__ == "__main__":
    main()
