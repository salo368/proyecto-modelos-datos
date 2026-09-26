"""
Genera reportes HTML de ydata-profiling comparando, lado a lado, las 3
entidades que existen en ambas fuentes (customers, employees, products).

Complementa a relational_profiling.py: ese script da los NUMEROS de
correspondencia/duplicados: este da la vista VISUAL (distribuciones,
%nulos, tipos) para pegar capturas en el documento de perfilamiento.

Uso:
    python compare_common_entities.py

Requiere el mismo .env que relational_profiling.py.
"""
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
from ydata_profiling import ProfileReport

load_dotenv()

MYSQL_URL = os.getenv("URL_MYSQLDATABASE")
PG_URL = os.getenv("DATABASE_URL")

mysql_engine = create_engine(MYSQL_URL)
pg_engine = create_engine(PG_URL)

REPORTS_DIR = Path(__file__).resolve().parent / "reports_comparacion"
REPORTS_DIR.mkdir(exist_ok=True)

PAIRS = [
    ("customers", "classicmodels.customers", "SELECT * FROM `classicmodels`.`customers`",
     "customerservice.cs_customers", 'SELECT * FROM "public"."cs_customers"'),
    ("employees", "classicmodels.employees", "SELECT * FROM `classicmodels`.`employees`",
     "customerservice.cs_employees", 'SELECT * FROM "public"."cs_employees"'),
    ("products", "classicmodels.products", "SELECT * FROM `classicmodels`.`products`",
     "customerservice.cs_products", 'SELECT * FROM "public"."cs_products"'),
]


def main():
    for entidad, title_a, sql_a, title_b, sql_b in PAIRS:
        print(f"Comparando entidad: {entidad}")
        df_a = pd.read_sql(sql_a, mysql_engine)
        df_b = pd.read_sql(sql_b, pg_engine)

        profile_a = ProfileReport(df_a, title=title_a, minimal=True)
        profile_b = ProfileReport(df_b, title=title_b, minimal=True)

        comparison = profile_a.compare(profile_b)
        out_path = REPORTS_DIR / f"comparacion_{entidad}.html"
        comparison.to_file(out_path)
        print(f"  Reporte generado: {out_path}")

    print("\nProceso finalizado.")


if __name__ == "__main__":
    main()
