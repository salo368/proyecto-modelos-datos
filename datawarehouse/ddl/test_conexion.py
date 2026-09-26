"""Verifica que las cadenas de conexion del .env funcionen.

Uso:
    python datawarehouse/ddl/test_conexion.py
"""
import os

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

OBJETIVOS = [
    ("classicmodels (MySQL)",        "URL_MYSQLDATABASE"),
    ("customerservice (PostgreSQL)", "DATABASE_URL"),
    ("repositorio de metadatos",     "METADATA_REPO_URL"),
    ("almacen de datos",             "DW_URL"),
]

for nombre, variable in OBJETIVOS:
    url = os.getenv(variable)
    if not url:
        print(f"FALTA {nombre}: la variable {variable} no esta en el .env")
        continue
    try:
        with sa.create_engine(url).connect() as con:
            con.execute(sa.text("SELECT 1"))
        print(f"OK    {nombre}")
    except Exception as e:
        print(f"FALLA {nombre}: {str(e).splitlines()[0][:110]}")
