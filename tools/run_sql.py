"""Run a .sql file against one of the project databases.

Usage:
    python tools/run_sql.py <file.sql> [ENV_VARIABLE]

ENV_VARIABLE names the connection string in .env and defaults to DW_URL.
Example against the metadata repository:

    python tools/run_sql.py metadata_repository/ddl/01_core_schema.sql METADATA_URL
"""
import os
import sys

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

if len(sys.argv) < 2:
    raise SystemExit(__doc__)

path = sys.argv[1]
variable = sys.argv[2] if len(sys.argv) > 2 else "DW_URL"

url = os.getenv(variable)
if not url:
    raise SystemExit(f"{variable} is not defined in .env")

with open(path, encoding="utf-8") as f:
    sql = f.read()

# AUTOCOMMIT so DDL and DO blocks are applied statement by statement.
engine = sa.create_engine(url, isolation_level="AUTOCOMMIT")
with engine.connect() as con:
    con.execute(sa.text(sql))

print(f"Executed {path} against {variable}")
