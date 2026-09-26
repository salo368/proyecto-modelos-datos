"""
NIVEL 3 - Profiling relacional (descubrimiento de relaciones no declaradas).

A diferencia de relational_profiling.py (Nivel 2, que solo mide la salud de
las FK YA declaradas en el esquema), este script NO parte de las llaves
foraneas conocidas: compara los valores de TODAS las columnas "tipo
identificador" de las 13 tablas (de las dos bases de datos, cruzando MySQL
con PostgreSQL) contra cada llave candidata (columna unica de alguna tabla),
para detectar relaciones de contencion (inclusion dependencies).

Esto permite:
    - Redescubrir automaticamente las FK que ya conociamos (control de
      calidad del propio algoritmo).
    - Encontrar relaciones IMPLICITAS que el esquema no declara, en
      particular las que cruzan de classicmodels a customerservice (que
      fisicamente no pueden tener una FK real por estar en motores
      distintos), y cualquier otra columna que "por los datos" resulte
      ser un candidato a FK que nadie habia marcado como tal.

Uso:
    python discover_relationships.py

Requiere el mismo .env que relational_profiling.py.
"""
import os
from pathlib import Path
from itertools import product

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect

load_dotenv()

MYSQL_URL = os.getenv("URL_MYSQLDATABASE")
PG_URL = os.getenv("DATABASE_URL")

if not MYSQL_URL:
    raise ValueError("No se encontro URL_MYSQLDATABASE en el archivo .env")
if not PG_URL:
    raise ValueError("No se encontro DATABASE_URL en el archivo .env")

MYSQL_SCHEMA = "classicmodels"
PG_SCHEMA = "public"

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

mysql_engine = create_engine(MYSQL_URL)
pg_engine = create_engine(PG_URL)

# Tipos que se excluyen del analisis: texto libre/binario, sin valor como
# identificador y demasiado costosos de comparar por contencion.
EXCLUDED_TYPE_KEYWORDS = ("text", "blob", "mediumtext", "mediumblob")
MAX_VARCHAR_LEN_AS_ID = 100  # varchar mas largo que esto no se trata como identificador

MIN_CONTAINMENT = 0.90       # % minimo de valores de A contenidos en B para reportar
MIN_KEY_DISTINCT = 5         # una llave candidata con menos valores distintos que esto se ignora (evita falsos positivos con dominios pequenos como 'status')


# ---------------------------------------------------------------------------
# 1. Inventario de columnas "tipo identificador" de ambas bases de datos
# ---------------------------------------------------------------------------

def qualified_table(db_label, schema, table):
    if db_label == "customerservice":
        return f'"{schema}"."{table}"'
    return f"`{schema}`.`{table}`"


def qualified_col(db_label, col):
    if db_label == "customerservice":
        return f'"{col}"'
    return f"`{col}`"


def list_identifier_columns(engine, schema, db_label):
    inspector = inspect(engine)
    columns_info = []
    for table in inspector.get_table_names(schema=schema):
        for col in inspector.get_columns(table, schema=schema):
            type_str = str(col["type"]).lower()
            if any(k in type_str for k in EXCLUDED_TYPE_KEYWORDS):
                continue
            if "varchar" in type_str or "character varying" in type_str:
                length = getattr(col["type"], "length", None)
                if length and length > MAX_VARCHAR_LEN_AS_ID:
                    continue
            columns_info.append({
                "db": db_label, "schema": schema, "table": table,
                "column": col["name"], "type": type_str,
            })
    return columns_info


def load_values(engine, db_label, schema, table, column):
    q = f"SELECT DISTINCT {qualified_col(db_label, column)} FROM {qualified_table(db_label, schema, table)} " \
        f"WHERE {qualified_col(db_label, column)} IS NOT NULL"
    df = pd.read_sql(q, engine)
    return set(str(v).strip().lower() for v in df.iloc[:, 0].tolist())


def load_known_fks(engine, schema):
    inspector = inspect(engine)
    known = set()
    for table in inspector.get_table_names(schema=schema):
        for fk in inspector.get_foreign_keys(table, schema=schema):
            for c, rc in zip(fk["constrained_columns"], fk["referred_columns"]):
                known.add((table, c, fk["referred_table"], rc))
    return known


# ---------------------------------------------------------------------------
# 2. Descubrimiento de inclusion dependencies
# ---------------------------------------------------------------------------

def main():
    print("Inventariando columnas candidatas...")
    cols_mysql = list_identifier_columns(mysql_engine, MYSQL_SCHEMA, "classicmodels")
    cols_pg = list_identifier_columns(pg_engine, PG_SCHEMA, "customerservice")
    all_cols = cols_mysql + cols_pg
    print(f"  {len(cols_mysql)} columnas candidatas en classicmodels, "
          f"{len(cols_pg)} en customerservice")

    engines = {"classicmodels": mysql_engine, "customerservice": pg_engine}
    schemas = {"classicmodels": MYSQL_SCHEMA, "customerservice": PG_SCHEMA}

    print("\nCargando valores distintos de cada columna candidata (puede tardar un poco)...")
    values_cache = {}
    for c in all_cols:
        key = (c["db"], c["table"], c["column"])
        values_cache[key] = load_values(engines[c["db"]], c["db"], c["schema"], c["table"], c["column"])
        print(f"  {c['db']}.{c['table']}.{c['column']}: {len(values_cache[key])} valores distintos")

    # Llaves candidatas: columnas cuyo conjunto de valores distintos tiene
    # tamano razonable (heuristica simple de unicidad aproximada: se valida
    # comparando contra el total de filas no nulas mas abajo via containment).
    candidate_keys = [c for c in all_cols if len(values_cache[(c["db"], c["table"], c["column"])]) >= MIN_KEY_DISTINCT]

    known_fks = {
        "classicmodels": load_known_fks(mysql_engine, MYSQL_SCHEMA),
        "customerservice": load_known_fks(pg_engine, PG_SCHEMA),
    }

    print("\nBuscando relaciones de contencion (inclusion dependencies)...")
    results = []
    for src, dst in product(all_cols, candidate_keys):
        if src["db"] == dst["db"] and src["table"] == dst["table"] and src["column"] == dst["column"]:
            continue

        src_values = values_cache[(src["db"], src["table"], src["column"])]
        dst_values = values_cache[(dst["db"], dst["table"], dst["column"])]
        if not src_values or not dst_values:
            continue

        contained = src_values & dst_values
        containment = len(contained) / len(src_values)
        if containment < MIN_CONTAINMENT:
            continue

        # Solo tiene sentido como "candidata a FK" si el destino es
        # razonablemente unico (aprox. llave), es decir domina en tamano
        # frente al origen o es igual (evita marcar cosas como 'country'
        # que por casualidad se solapan entre si).
        if len(dst_values) < len(src_values) * 0.5:
            continue

        is_cross_db = src["db"] != dst["db"]
        declared = (src["table"], src["column"], dst["table"], dst["column"]) in known_fks.get(src["db"], set())

        results.append({
            "tabla_columna_origen": f"{src['db']}.{src['table']}.{src['column']}",
            "tabla_columna_destino_llave": f"{dst['db']}.{dst['table']}.{dst['column']}",
            "pct_contencion": round(100 * containment, 2),
            "valores_origen": len(src_values),
            "valores_destino": len(dst_values),
            "cruza_bases_de_datos": is_cross_db,
            "ya_declarada_como_fk": declared,
        })
        marca = "cross-DB" if is_cross_db else "misma BD"
        tag = "ya declarada" if declared else "NUEVA/implicita"
        print(f"  [{marca}] [{tag}] {src['db']}.{src['table']}.{src['column']} -> "
              f"{dst['db']}.{dst['table']}.{dst['column']} ({round(100*containment,2)}%)")

    df_out = pd.DataFrame(results).sort_values(
        ["cruza_bases_de_datos", "ya_declarada_como_fk", "pct_contencion"],
        ascending=[False, True, False],
    )
    out_path = OUTPUT_DIR / "relaciones_inferidas.csv"
    df_out.to_csv(out_path, index=False, encoding="utf-8")
    print(f"\nEscrito: {out_path} ({len(df_out)} relaciones encontradas)")


if __name__ == "__main__":
    main()
