"""
One ydata-profiling HTML report per source table.

Writes:
    profiling/reports/classicmodels/<table>_profile.html
    profiling/reports/customerservice/<table>_profile.html

Requires the extra dependency in profiling/requirements.txt.

Usage:
    python profiling/ydata_table_profiles.py
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from ydata_profiling import ProfileReport

load_dotenv()

REPORTS_DIR = Path(__file__).resolve().parent / "reports"

# (source name, connection variable, schema, report title prefix)
SOURCES = [
    ("classicmodels", "CLASSICMODELS_URL", "classicmodels", "MySQL Data Profiling"),
    ("customerservice", "CUSTOMERSERVICE_URL", "public", "Data Profiling"),
]


def profile_source(name, url_var, schema, title_prefix):
    url = os.getenv(url_var)
    if not url:
        raise ValueError(f"{url_var} is not defined in .env")
    engine = create_engine(url)
    out_dir = REPORTS_DIR / name
    out_dir.mkdir(parents=True, exist_ok=True)

    failed = []
    for table in inspect(engine).get_table_names(schema=schema):
        try:
            df = pd.read_sql_table(table, engine, schema=schema)
            report = ProfileReport(df, title=f"{title_prefix} - {table}", explorative=True)
            path = out_dir / f"{table}_profile.html"
            report.to_file(path)
            print(f"  {path.relative_to(REPORTS_DIR.parent)}  ({len(df)} rows)")
        except Exception as error:
            print(f"  ERROR in {name}.{table}: {error}")
            failed.append(table)
    return failed


def main():
    failed = []
    for source in SOURCES:
        print(f"Profiling {source[0]}...")
        failed += profile_source(*source)
    print("\nDone." if not failed else f"\nTables with errors: {failed}")


if __name__ == "__main__":
    main()
