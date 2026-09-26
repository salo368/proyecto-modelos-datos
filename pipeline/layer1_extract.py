"""
Layer 1 - Extract/Publish.

One extraction model per source system. Every table of both sources is
read exactly once per load, including those the current model does not
use (payments, cs_customer_products): "bring everything, thinking of
future needs". Nothing is written here; layer 2 lands the extracts.

    Input   classicmodels (MySQL), customerservice (PostgreSQL)
    Output  list of extracts, handed to layer 2
"""
import pandas as pd

from common import CLASSICMODELS, CUSTOMERSERVICE

EXTRACTION_MODELS = {
    "classicmodels": {
        "engine": CLASSICMODELS,
        "initial_table": "stg_initial_classicmodels",
        "tables": ["customers", "employees", "offices", "products",
                   "productlines", "orders", "orderdetails", "payments"],
    },
    "customerservice": {
        "engine": CUSTOMERSERVICE,
        "initial_table": "stg_initial_customerservice",
        "tables": ["cs_customers", "cs_products", "cs_employees",
                   "cs_customer_calls", "cs_customer_products"],
    },
}


def run():
    """[(source, source table, DataFrame)] for every table of every model."""
    print("\n[Layer 1] Extract/Publish")
    extracts = []
    for source, model in EXTRACTION_MODELS.items():
        print(f"    Extraction model: {source}")
        for table in model["tables"]:
            df = pd.read_sql(f"SELECT * FROM {table}", model["engine"])
            extracts.append((source, table, df))
            print(f"      {table:<22}{len(df):>6} rows")
    return extracts
