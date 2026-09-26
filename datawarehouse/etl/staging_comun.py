"""
Utilidades compartidas por los tres procesos ETL del almacen.

    etl_dw_staging.py     capas 1 a 4  (Extract .. Clean Staging)
    etl_dw_dimensions.py  capas 5 a 7  para el modelo de dimensiones
    etl_dw_facts.py       capas 5 a 7  para el modelo de hechos

Aqui solo viven las piezas que los tres usan igual: conexiones, control
de corridas en staging_dw.etl_run, lectura y escritura de capas, y el
registro en el repositorio de metadatos.
"""
import os
from datetime import date, datetime

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

MYSQL = sa.create_engine(os.getenv("URL_MYSQLDATABASE"))
PG    = sa.create_engine(os.getenv("DATABASE_URL"))
DW    = sa.create_engine(os.getenv("DW_URL"))
META  = sa.create_engine(os.getenv("METADATA_REPO_URL"))

HERRAMIENTA = "Python 3.11 + SQLAlchemy 2.1 + pandas 3.0"


# ============================================================
# Control de corridas
# ============================================================

def abrir_run(proceso, run_origen=None):
    with DW.begin() as con:
        return con.execute(sa.text("""
            INSERT INTO staging_dw.etl_run (proceso, run_origen)
            VALUES (:p, :o) RETURNING run_id
        """), {"p": proceso, "o": run_origen}).scalar()


def cerrar_run(run_id, estado):
    with DW.begin() as con:
        con.execute(sa.text("""
            UPDATE staging_dw.etl_run
               SET finalizado_en = now(), estado = :e
             WHERE run_id = :r
        """), {"e": estado, "r": run_id})


def ultimo_staging_ok():
    """run_id de la ultima corrida de staging que termino bien.

    Los procesos de dimensiones y hechos leen de aqui y nunca de las
    fuentes: es lo que exige "read once, write many" (dia. 15).
    """
    with DW.connect() as con:
        rid = con.execute(sa.text("""
            SELECT MAX(run_id) FROM staging_dw.etl_run
            WHERE proceso = 'staging' AND estado = 'OK'
        """)).scalar()
    if rid is None:
        raise RuntimeError(
            "No hay ninguna corrida de staging terminada.\n"
            "Corre primero: python datawarehouse/etl/etl_dw_staging.py")
    return rid


# ============================================================
# Serializacion
# ============================================================

def json_seguro(v):
    """Convierte un valor de pandas a algo serializable en JSON."""
    if v is None:
        return None
    if isinstance(v, float) and pd.isna(v):
        return None
    if v is pd.NaT:
        return None
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat()
    if hasattr(v, "item"):              # numpy int64 / float64 / bool_
        v = v.item()
        return None if isinstance(v, float) and pd.isna(v) else v
    if isinstance(v, (bytes, bytearray, memoryview)):
        return None                     # blobs (productlines.image): no aportan
    return v


def filas_json(df):
    return [
        {k: json_seguro(v) for k, v in fila.items()}
        for fila in df.to_dict(orient="records")
    ]


# ============================================================
# Lectura y escritura de capas
# ============================================================

def insertar(tabla, registros):
    """Inserta registros en una tabla de staging. Nunca trunca (dia. 16)."""
    if not registros:
        return
    cols = list(registros[0].keys())
    sql = sa.text(
        f"INSERT INTO staging_dw.{tabla} ({', '.join(cols)}) "
        f"VALUES ({', '.join(':' + c for c in cols)})"
    )
    # El payload se pasa como dict: el bindparam JSON lo serializa. Hacer
    # json.dumps antes lo codificaria dos veces y el JSONB guardaria una
    # cadena en vez de un objeto.
    if "payload" in cols:
        sql = sql.bindparams(sa.bindparam("payload", type_=sa.JSON))
    with DW.begin() as con:
        con.execute(sql, registros)


def leer_payload(tabla, run_id, **filtros):
    """DataFrame con el payload de una capa, en el orden original."""
    cond = "".join(f" AND {k} = :{k}" for k in filtros)
    with DW.connect() as con:
        filas = con.execute(sa.text(
            f"SELECT payload FROM staging_dw.{tabla} "
            f"WHERE run_id = :r{cond} ORDER BY nro_fila"),
            {"r": run_id, **filtros}).fetchall()
    return pd.DataFrame([f[0] for f in filas])


def leer_limpio(run_staging, tabla_origen):
    """Solo lo que Clean Staging dejo en la pila de limpios."""
    return leer_payload("stg_clean", run_staging, tabla_origen=tabla_origen)


# ============================================================
# Registro en el repositorio de metadatos
# ============================================================

def registrar_ejecucion(proceso, descripcion, fuentes, run_id, leidas,
                        escritas, rechazadas, estado, error=None,
                        resultados_calidad=()):
    """Deja la corrida en etl_process / etl_execution / dq_result.

    resultados_calidad: iterable de (regla, evaluadas, fallidas).
    Una regla "pasa" cuando no tuvo ninguna falla.
    """
    with META.begin() as con:
        proceso_id = con.execute(sa.text("""
            INSERT INTO etl_process (process_name, tool, source_systems,
                                     target_system, description)
            VALUES (:n, :t, :s, 'dw (PostgreSQL)', :d)
            ON CONFLICT (process_name) DO UPDATE
                SET tool = EXCLUDED.tool,
                    source_systems = EXCLUDED.source_systems,
                    description = EXCLUDED.description
            RETURNING etl_process_id
        """), {"n": proceso, "t": HERRAMIENTA, "s": fuentes,
               "d": descripcion}).scalar()

        exec_id = con.execute(sa.text("""
            INSERT INTO etl_execution (etl_process_id, run_id, started_at,
                                       finished_at, status, rows_read,
                                       rows_written, rows_rejected, error_message)
            VALUES (:p, :r, now(), now(), :s, :lr, :lw, :rj, :e)
            RETURNING etl_execution_id
        """), {"p": proceso_id, "r": run_id, "s": estado, "lr": leidas,
               "lw": escritas, "rj": rechazadas, "e": error}).scalar()

        for regla, evaluadas, fallidas in resultados_calidad:
            rid = con.execute(sa.text(
                "SELECT dq_rule_id FROM dq_rule WHERE rule_name = :n"),
                {"n": regla}).scalar()
            if rid:
                con.execute(sa.text("""
                    INSERT INTO dq_result (dq_rule_id, etl_execution_id,
                                           rows_evaluated, rows_failed, passed)
                    VALUES (:r, :e, :ev, :fa, :p)
                """), {"r": rid, "e": exec_id, "ev": int(evaluadas),
                       "fa": int(fallidas), "p": int(fallidas) == 0})
