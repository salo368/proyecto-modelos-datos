"""Ejecuta un archivo .sql contra la base que se indique.

Uso:
    python datawarehouse/ddl/run_sql.py <archivo.sql> [VARIABLE_DEL_ENV]

La variable por defecto es DW_URL (el almacen). Para correr algo contra
el repositorio de metadatos:

    python datawarehouse/ddl/run_sql.py archivo.sql METADATA_REPO_URL
"""
import os
import sys

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

if len(sys.argv) < 2:
    raise SystemExit(__doc__)

ruta = sys.argv[1]
variable = sys.argv[2] if len(sys.argv) > 2 else "DW_URL"

url = os.getenv(variable)
if not url:
    raise SystemExit(f"No encontre la variable {variable} en el .env")

with open(ruta, encoding="utf-8") as f:
    sql = f.read()

# AUTOCOMMIT para que el DDL se aplique sentencia por sentencia.
eng = sa.create_engine(url, isolation_level="AUTOCOMMIT")
with eng.connect() as con:
    con.execute(sa.text(sql))

print(f"Ejecutado {ruta} contra {variable}")
