"""Check that every connection string in .env reaches its database.

Usage:
    python tools/check_connections.py
"""
import os

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

TARGETS = [
    ("classicmodels (MySQL)",        "CLASSICMODELS_URL"),
    ("customerservice (PostgreSQL)", "CUSTOMERSERVICE_URL"),
    ("metadata repository",          "METADATA_URL"),
    ("data warehouse",               "DW_URL"),
]

for name, variable in TARGETS:
    url = os.getenv(variable)
    if not url:
        print(f"MISSING {name}: {variable} is not defined in .env")
        continue
    try:
        with sa.create_engine(url).connect() as con:
            con.execute(sa.text("SELECT 1"))
        print(f"OK      {name}")
    except Exception as e:
        print(f"FAILED  {name}: {str(e).splitlines()[0][:110]}")
