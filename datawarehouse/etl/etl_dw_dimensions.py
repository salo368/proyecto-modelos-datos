"""
ETL de dimensiones hacia el almacen de datos - Entrega 2.

Sigue el mismo patron de capas de la Entrega 1 (Anthony Giordano,
Data Integration Blueprint and Modeling): cada dimension pasa por
Extract -> Data Quality -> Transform -> Load, y cada corrida queda
registrada en el repositorio de metadatos.

Orden de carga (importa: los hechos dependen de que esto termine):
    dim_tiempo        generada, no viene de ninguna fuente
    dim_estado_orden  desde orders.status
    dim_oficina       desde offices
    dim_cliente       CONFORMADA: customers + cs_customers
    dim_producto      CONFORMADA: products + productlines + cs_products
    dim_empleado      NO conformada: employees + cs_employees

Uso:
    python datawarehouse/etl/etl_dw_dimensions.py
"""
import os
from datetime import date, datetime, timedelta

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

MYSQL = sa.create_engine(os.getenv("URL_MYSQLDATABASE"))
PG    = sa.create_engine(os.getenv("DATABASE_URL"))
DW    = sa.create_engine(os.getenv("DW_URL"))
META  = sa.create_engine(os.getenv("METADATA_REPO_URL"))

PROCESO = "etl_dw_dimensions"
HERRAMIENTA = "Python 3.11 + SQLAlchemy 2.x + pandas"

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS  = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

# Acumuladores para la bitacora de metadatos.
_leidas = 0
_escritas = 0
_calidad = []   # (nombre_regla, filas_evaluadas, filas_que_fallan, paso)


# ============================================================
# Registro en el repositorio de metadatos
# ============================================================

def abrir_ejecucion():
    """Crea la fila de etl_execution y devuelve (execution_id, run_id)."""
    with META.begin() as con:
        proceso_id = con.execute(sa.text("""
            INSERT INTO etl_process (process_name, tool, source_systems,
                                     target_system, description)
            VALUES (:n, :t, :s, :d, :desc)
            ON CONFLICT (process_name) DO UPDATE SET tool = EXCLUDED.tool
            RETURNING etl_process_id
        """), {
            "n": PROCESO, "t": HERRAMIENTA,
            "s": "classicmodels (MySQL), customerservice (PostgreSQL)",
            "d": "dw (PostgreSQL)",
            "desc": "Carga las seis dimensiones del almacen, incluidas las "
                    "tres conformadas entre las dos fuentes.",
        }).scalar()

        run_id = con.execute(sa.text("""
            SELECT COALESCE(MAX(run_id), 0) + 1
            FROM etl_execution WHERE etl_process_id = :p
        """), {"p": proceso_id}).scalar()

        exec_id = con.execute(sa.text("""
            INSERT INTO etl_execution (etl_process_id, run_id, started_at, status)
            VALUES (:p, :r, :s, 'EN_CURSO')
            RETURNING etl_execution_id
        """), {"p": proceso_id, "r": run_id, "s": datetime.now()}).scalar()

    return exec_id, run_id


def cerrar_ejecucion(exec_id, estado, error=None):
    """Cierra la bitacora y vuelca los resultados de calidad."""
    with META.begin() as con:
        con.execute(sa.text("""
            UPDATE etl_execution
               SET finished_at = :f, status = :s, rows_read = :lr,
                   rows_written = :lw, rows_rejected = 0, error_message = :e
             WHERE etl_execution_id = :id
        """), {"f": datetime.now(), "s": estado, "lr": _leidas,
               "lw": _escritas, "e": error, "id": exec_id})

        for nombre, evaluadas, fallan, paso in _calidad:
            regla_id = con.execute(
                sa.text("SELECT dq_rule_id FROM dq_rule WHERE rule_name = :n"),
                {"n": nombre},
            ).scalar()
            if regla_id:
                con.execute(sa.text("""
                    INSERT INTO dq_result (dq_rule_id, etl_execution_id,
                                           rows_evaluated, rows_failed, passed)
                    VALUES (:r, :e, :ev, :fa, :p)
                """), {"r": regla_id, "e": exec_id, "ev": evaluadas,
                       "fa": fallan, "p": paso})


def calidad(nombre, evaluadas, fallan, paso, mensaje):
    _calidad.append((nombre, evaluadas, fallan, paso))
    print(f"  [calidad] {mensaje}")


# ============================================================
# Utilidades de carga
# ============================================================

def cargar(df, tabla):
    """Reemplaza el contenido de una tabla del almacen."""
    global _escritas
    with DW.begin() as con:
        con.execute(sa.text(f"TRUNCATE TABLE {tabla} RESTART IDENTITY CASCADE"))
    df.to_sql(tabla, DW, if_exists="append", index=False)
    _escritas += len(df)
    print(f"  {tabla}: {len(df)} filas")


def leer(engine, sql):
    global _leidas
    df = pd.read_sql(sql, engine)
    _leidas += len(df)
    return df


# ============================================================
# Dimensiones
# ============================================================

def dim_tiempo():
    """Generada, no extraida. Cubre 2003-2005: el rango de ventas
    (2003-01-06 a 2005-05-31) y de llamadas (2003-02-19 a 2005-05-09)."""
    filas, d, fin = [], date(2003, 1, 1), date(2005, 12, 31)
    while d <= fin:
        filas.append({
            "tiempo_key":    int(d.strftime("%Y%m%d")),
            "fecha":         d,
            "anio":          d.year,
            "trimestre":     (d.month - 1) // 3 + 1,
            "mes":           d.month,
            "nombre_mes":    MESES[d.month - 1],
            "dia":           d.day,
            "dia_semana":    d.isoweekday(),
            "nombre_dia":    DIAS[d.isoweekday() - 1],
            "es_fin_semana": d.isoweekday() >= 6,
            "anio_mes":      d.strftime("%Y-%m"),
        })
        d += timedelta(days=1)
    cargar(pd.DataFrame(filas), "dim_tiempo")


def dim_estado_orden():
    """Hallazgo de calidad #7: hay 13 ordenes Cancelled/Disputed/On Hold
    mezcladas con las despachadas. Se cargan todas, pero es_efectiva
    permite excluirlas en los reportes."""
    df = leer(MYSQL, "SELECT DISTINCT status AS estado FROM orders")
    no_efectivos = {"Cancelled", "Disputed", "On Hold"}
    df["es_efectiva"] = ~df["estado"].isin(no_efectivos)

    n_no_efectivos = int((~df["es_efectiva"]).sum())
    calidad("estado_orden_no_efectivo", len(df), n_no_efectivos, True,
            f"estados no efectivos marcados: {n_no_efectivos} de {len(df)}")
    cargar(df, "dim_estado_orden")


def dim_oficina():
    df = leer(MYSQL, """
        SELECT officeCode AS codigo_oficina, city AS ciudad, country AS pais,
               state AS region, territory AS territorio
        FROM offices
    """)
    cargar(df, "dim_oficina")


def dim_cliente():
    """DIMENSION CONFORMADA.

    classicmodels es la fuente autoritativa porque tiene mas atributos.
    customerservice solo aporta la bandera de presencia.

    Hallazgo de calidad #3: addressLine2 esta vacia en el 81,97% de las
    filas. En vez de arrastrar una columna casi vacia, se consolida con
    addressLine1 en un solo atributo.
    """
    cm = leer(MYSQL, """
        SELECT customerNumber   AS numero_cliente,
               customerName     AS nombre_cliente,
               contactFirstName AS contacto_nombre,
               contactLastName  AS contacto_apellido,
               phone            AS telefono,
               addressLine1, addressLine2,
               city             AS ciudad,
               state            AS estado_region,
               postalCode       AS codigo_postal,
               country          AS pais,
               creditLimit      AS limite_credito
        FROM customers
    """)

    vacias = int(cm["addressLine2"].isna().sum())
    cm["direccion_completa"] = (
        cm["addressLine1"].fillna("")
        + cm["addressLine2"].fillna("").apply(lambda x: f", {x}" if x else "")
    ).str.strip(", ")
    cm = cm.drop(columns=["addressLine1", "addressLine2"])
    calidad("cliente_direccion_linea2_nula", len(cm), vacias, True,
            f"addressLine2 nula en {vacias} de {len(cm)} filas -> consolidada "
            f"en direccion_completa")

    cs = leer(PG, "SELECT customernumber AS numero_cliente FROM cs_customers")
    cm["presente_en_ventas"]   = True
    cm["presente_en_servicio"] = cm["numero_cliente"].isin(cs["numero_cliente"])

    solape = int(cm["presente_en_servicio"].sum())
    calidad("cliente_conformidad_fuentes", len(cm), len(cm) - solape, solape == len(cm),
            f"clientes presentes en ambas fuentes: {solape} de {len(cm)} "
            f"-> dimension conformada")
    cargar(cm, "dim_cliente")


def dim_producto():
    """DIMENSION CONFORMADA.

    Hallazgo de calidad #1: productlines.htmlDescription e image estan
    100% vacias. Solo se trae textDescription.
    """
    cm = leer(MYSQL, """
        SELECT p.productCode      AS codigo_producto,
               p.productName      AS nombre_producto,
               p.productLine      AS linea_producto,
               pl.textDescription AS descripcion_linea,
               p.productScale     AS escala,
               p.productVendor    AS proveedor,
               p.buyPrice         AS precio_compra,
               p.MSRP             AS precio_msrp
        FROM products p
        JOIN productlines pl ON p.productLine = pl.productLine
    """)
    calidad("productline_columnas_vacias", 2, 2, True,
            "htmlDescription e image (100% nulas) excluidas del almacen")

    cs = leer(PG, "SELECT productcode AS codigo_producto FROM cs_products")
    cm["presente_en_ventas"]   = True
    cm["presente_en_servicio"] = cm["codigo_producto"].isin(cs["codigo_producto"])

    solape = int(cm["presente_en_servicio"].sum())
    calidad("producto_conformidad_fuentes", len(cm), len(cm) - solape, solape == len(cm),
            f"productos presentes en ambas fuentes: {solape} de {len(cm)} "
            f"-> dimension conformada")
    cargar(cm, "dim_producto")


def dim_empleado():
    """DIMENSION NO CONFORMADA.

    Hallazgo de calidad #2, el mas importante de la Entrega 1: los
    empleados de las dos fuentes tienen solape del 0%. No se pueden
    fusionar sin inventar equivalencias que no existen.

    La solucion es una llave de negocio compuesta
    (numero_empleado, sistema_origen) con llave subrogada encima, de
    modo que las dos poblaciones convivan sin colisionar.
    """
    cm = leer(MYSQL, """
        SELECT employeeNumber AS numero_empleado,
               firstName      AS nombre,
               lastName       AS apellido,
               email,
               jobTitle       AS cargo,
               officeCode     AS numero_oficina
        FROM employees
    """)
    cm["sistema_origen"] = "classicmodels"

    cs = leer(PG, """
        SELECT employeenumber AS numero_empleado,
               firstname      AS nombre,
               lastname       AS apellido,
               email
        FROM cs_employees
    """)
    cs["sistema_origen"] = "customerservice"
    cs["cargo"] = "Agente de Servicio al Cliente"
    cs["numero_oficina"] = None

    colisiones = set(cm["numero_empleado"]) & set(cs["numero_empleado"])
    total = len(cm) + len(cs)
    calidad("empleado_conformidad_fuentes", total, len(colisiones), True,
            f"empleados con llave compartida entre fuentes: {len(colisiones)} "
            f"-> se usa llave compuesta (numero_empleado, sistema_origen)")

    cargar(pd.concat([cm, cs], ignore_index=True), "dim_empleado")


if __name__ == "__main__":
    exec_id, run_id = abrir_ejecucion()
    print(f"Cargando dimensiones... (run_id={run_id})")
    try:
        dim_tiempo()
        dim_estado_orden()
        dim_oficina()
        dim_cliente()
        dim_producto()
        dim_empleado()
    except Exception as e:
        cerrar_ejecucion(exec_id, "ERROR", str(e)[:500])
        raise
    cerrar_ejecucion(exec_id, "OK")
    print(f"Dimensiones cargadas. Leidas {_leidas}, escritas {_escritas}.")
