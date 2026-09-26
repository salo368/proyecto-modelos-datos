"""
Side-by-side ydata-profiling comparison of the three entities present
in both sources (customers, employees, products).

Writes:
    profiling/reports/common_entities/comparacion_<entity>.html

Requires the extra dependency in profiling/requirements.txt.

Usage:
    python profiling/ydata_compare_common_entities.py
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
from ydata_profiling import ProfileReport

load_dotenv()

mysql_engine = create_engine(os.getenv("CLASSICMODELS_URL"))
pg_engine = create_engine(os.getenv("CUSTOMERSERVICE_URL"))

REPORTS_DIR = Path(__file__).resolve().parent / "reports" / "common_entities"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# (entity, title A, query A, title B, query B)
PAIRS = [
    ("customers", "classicmodels.customers", "SELECT * FROM `classicmodels`.`customers`",
     "customerservice.cs_customers", 'SELECT * FROM "public"."cs_customers"'),
    ("employees", "classicmodels.employees", "SELECT * FROM `classicmodels`.`employees`",
     "customerservice.cs_employees", 'SELECT * FROM "public"."cs_employees"'),
    ("products", "classicmodels.products", "SELECT * FROM `classicmodels`.`products`",
     "customerservice.cs_products", 'SELECT * FROM "public"."cs_products"'),
]


def main():
    for entity, title_a, sql_a, title_b, sql_b in PAIRS:
        print(f"Comparing {entity}...")
        report_a = ProfileReport(pd.read_sql(sql_a, mysql_engine), title=title_a, minimal=True)
        report_b = ProfileReport(pd.read_sql(sql_b, pg_engine), title=title_b, minimal=True)
        path = REPORTS_DIR / f"comparacion_{entity}.html"
        report_a.compare(report_b).to_file(path)
        print(f"  {path}")
    print("\nDone.")


if __name__ == "__main__":
    main()
