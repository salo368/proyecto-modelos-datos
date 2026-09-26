"""Create the PostgreSQL database named in a connection string, if missing.

Usage:
    python tools/create_database.py <ENV_VARIABLE>

A fresh Docker volume already gets its databases from docker/init-dw.sql.
This covers a volume created before a database was added to that script,
so the stack does not have to be wiped to pick it up.
"""
import os
import sys

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

if len(sys.argv) < 2:
    raise SystemExit(__doc__)

variable = sys.argv[1]
url = os.getenv(variable)
if not url:
    raise SystemExit(f"{variable} is not defined in .env")

target = sa.engine.make_url(url)
server = sa.create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
with server.connect() as con:
    exists = con.execute(sa.text("SELECT 1 FROM pg_database WHERE datname = :d"),
                         {"d": target.database}).scalar()
    if exists:
        print(f"Database '{target.database}' already exists")
    else:
        con.execute(sa.text(f'CREATE DATABASE "{target.database}"'))
        print(f"Created database '{target.database}'")
