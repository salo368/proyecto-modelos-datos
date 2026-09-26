"""Crea la base de datos 'dw' en el servidor PostgreSQL de Railway.

El almacen vive como una base separada dentro del mismo servidor que ya
hospeda el repositorio de metadatos. Asi no hace falta un servicio nuevo
en Railway y el costo adicional es cero.

Es idempotente: si la base ya existe, no hace nada.

Uso:
    python datawarehouse/ddl/00_crear_base.py
"""
import os

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

# Nos conectamos a la base 'railway' para poder crear otra base desde ahi.
# AUTOCOMMIT es obligatorio: PostgreSQL rechaza CREATE DATABASE dentro
# de una transaccion.
admin = sa.create_engine(os.getenv("METADATA_REPO_URL"), isolation_level="AUTOCOMMIT")

with admin.connect() as con:
    existe = con.execute(
        sa.text("SELECT 1 FROM pg_database WHERE datname = 'dw'")
    ).scalar()
    if existe:
        print("La base 'dw' ya existe. No se hace nada.")
    else:
        con.execute(sa.text("CREATE DATABASE dw"))
        print("Base 'dw' creada.")
