"""
ETL de hechos hacia el almacen de datos - Entrega 2.

Requiere que las dimensiones ya esten cargadas:
    python datawarehouse/etl/etl_dw_dimensions.py

Carga:
    fact_ventas             desde classicmodels (orderdetails, orders,
                            products, customers, employees)
    fact_llamadas_servicio  desde customerservice (cs_customer_calls)

Y crea la vista vw_interaccion_cliente_producto, que cruza los dos
hechos al grano cliente x producto x mes.

La parte especifica de un ETL dimensional es la BUSQUEDA DE LLAVES
SUBROGADAS: el hecho no guarda customerNumber = 103, guarda
cliente_key = 7, que es la fila que le toco a ese cliente en
dim_cliente. Hay que traducir cada llave de negocio a su subrogada.

Uso:
    python datawarehouse/etl/etl_dw_facts.py
"""
import os
from datetime import datetime

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

MYSQL = sa.create_engine(os.getenv("URL_MYSQLDATABASE"))
PG    = sa.create_engine(os.getenv("DATABASE_URL"))
DW    = sa.create_engine(os.getenv("DW_URL"))
META  = sa.create_engine(os.getenv("METADATA_REPO_URL"))

PROCESO = "etl_dw_facts"
HERRAMIENTA = "Python 3.11 + SQLAlchemy 2.x + pandas"

_leidas = 0
_escritas = 0
_calidad = []


# ============================================================
# Registro en el repositorio de metadatos
# ============================================================

def abrir_ejecucion():
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
            "desc": "Carga fact_ventas y fact_llamadas_servicio resolviendo "
                    "llaves subrogadas, y crea la vista integrada.",
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


def cerrar_ejecucion(exec_id, estado, rechazadas=0, error=None):
    with META.begin() as con:
        con.execute(sa.text("""
            UPDATE etl_execution
               SET finished_at = :f, status = :s, rows_read = :lr,
                   rows_written = :lw, rows_rejected = :rj, error_message = :e
             WHERE etl_execution_id = :id
        """), {"f": datetime.now(), "s": estado, "lr": _leidas,
               "lw": _escritas, "rj": rechazadas, "e": error, "id": exec_id})

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
# Utilidades
# ============================================================

def leer(engine, sql):
    global _leidas
    df = pd.read_sql(sql, engine)
    _leidas += len(df)
    return df


def cargar(df, tabla):
    global _escritas
    with DW.begin() as con:
        con.execute(sa.text(f"TRUNCATE TABLE {tabla} RESTART IDENTITY CASCADE"))
    df.to_sql(tabla, DW, if_exists="append", index=False)
    _escritas += len(df)
    print(f"  {tabla}: {len(df)} filas")


def mapa(tabla, llave_negocio, llave_subrogada, extra=None):
    """Diccionario {llave_de_negocio: llave_subrogada} para traducir.

    Con `extra`, la clave del diccionario es una tupla. Lo necesita
    dim_empleado, cuya llave de negocio es compuesta
    (numero_empleado, sistema_origen).
    """
    cols = f"{llave_negocio}, {llave_subrogada}" + (f", {extra}" if extra else "")
    df = pd.read_sql(f"SELECT {cols} FROM {tabla}", DW)
    if extra:
        return {(r[llave_negocio], r[extra]): r[llave_subrogada]
                for _, r in df.iterrows()}
    return dict(zip(df[llave_negocio], df[llave_subrogada]))


# ============================================================
# fact_ventas - grano: una linea de una orden
# ============================================================

def fact_ventas():
    df = leer(MYSQL, """
        SELECT od.orderNumber     AS numero_orden,
               od.orderLineNumber AS numero_linea,
               o.orderDate, o.shippedDate, o.status,
               o.customerNumber,
               od.productCode,
               od.quantityOrdered AS cantidad_ordenada,
               od.priceEach       AS precio_unitario,
               p.buyPrice,
               p.MSRP             AS precio_msrp,
               c.salesRepEmployeeNumber,
               e.officeCode
        FROM orderdetails od
        JOIN orders    o ON od.orderNumber   = o.orderNumber
        JOIN products  p ON od.productCode   = p.productCode
        JOIN customers c ON o.customerNumber = c.customerNumber
        LEFT JOIN employees e ON c.salesRepEmployeeNumber = e.employeeNumber
    """)

    # --- Medidas calculadas ---
    df["monto_linea"]  = (df["cantidad_ordenada"] * df["precio_unitario"]).round(2)
    df["costo_linea"]  = (df["cantidad_ordenada"] * df["buyPrice"]).round(2)
    df["margen_linea"] = (df["monto_linea"] - df["costo_linea"]).round(2)

    # Hallazgo de calidad #5: shippedDate es nula en las ordenes que no se
    # despacharon. Se deja NULL en vez de inventar un valor.
    df["dias_hasta_envio"] = (
        pd.to_datetime(df["shippedDate"]) - pd.to_datetime(df["orderDate"])
    ).dt.days
    sin_envio = int(df["dias_hasta_envio"].isna().sum())
    calidad("orden_fecha_envio_nula", len(df), sin_envio, True,
            f"lineas sin fecha de envio: {sin_envio} de {len(df)} "
            f"-> dias_hasta_envio queda NULL")

    # --- Traduccion a llaves subrogadas ---
    k_cli = mapa("dim_cliente",      "numero_cliente",  "cliente_key")
    k_pro = mapa("dim_producto",     "codigo_producto", "producto_key")
    k_ofi = mapa("dim_oficina",      "codigo_oficina",  "oficina_key")
    k_est = mapa("dim_estado_orden", "estado",          "estado_key")
    k_emp = mapa("dim_empleado",     "numero_empleado", "empleado_key",
                 extra="sistema_origen")

    df["tiempo_key"]   = pd.to_datetime(df["orderDate"]).dt.strftime("%Y%m%d").astype(int)
    df["cliente_key"]  = df["customerNumber"].map(k_cli)
    df["producto_key"] = df["productCode"].map(k_pro)
    df["oficina_key"]  = df["officeCode"].map(k_ofi)
    df["estado_key"]   = df["status"].map(k_est)
    # El vendedor siempre viene de classicmodels, nunca de customerservice.
    df["empleado_key"] = df["salesRepEmployeeNumber"].map(
        lambda n: k_emp.get((n, "classicmodels")) if pd.notna(n) else None
    )

    # Ninguna llave obligatoria puede quedar sin resolver.
    obligatorias = ["tiempo_key", "cliente_key", "producto_key", "estado_key"]
    huerfanas = int(df[obligatorias].isna().any(axis=1).sum())
    if huerfanas:
        raise RuntimeError(
            f"{huerfanas} filas de fact_ventas no resolvieron alguna llave "
            f"obligatoria. Revisa que las dimensiones esten completas."
        )

    salida = df[[
        "tiempo_key", "cliente_key", "producto_key", "empleado_key",
        "oficina_key", "estado_key", "numero_orden", "numero_linea",
        "cantidad_ordenada", "precio_unitario", "monto_linea",
        "costo_linea", "margen_linea", "precio_msrp", "dias_hasta_envio",
    ]].copy()

    # Int64 (con mayuscula) es el entero de pandas que admite nulos.
    for c in ["cliente_key", "producto_key", "empleado_key",
              "oficina_key", "estado_key", "dias_hasta_envio"]:
        salida[c] = salida[c].astype("Int64")

    cargar(salida, "fact_ventas")


# ============================================================
# fact_llamadas_servicio - grano: una llamada
# ============================================================

def fact_llamadas():
    df = leer(PG, """
        SELECT employeenumber, customernumber, productcode, text, date
        FROM cs_customer_calls
    """)

    k_cli = mapa("dim_cliente",  "numero_cliente",  "cliente_key")
    k_pro = mapa("dim_producto", "codigo_producto", "producto_key")
    k_emp = mapa("dim_empleado", "numero_empleado", "empleado_key",
                 extra="sistema_origen")

    df["tiempo_key"]   = pd.to_datetime(df["date"]).dt.strftime("%Y%m%d").astype(int)
    df["cliente_key"]  = df["customernumber"].map(k_cli)
    df["producto_key"] = df["productcode"].map(k_pro)
    # El agente siempre viene de customerservice. Esta es la razon de ser
    # de la llave compuesta: el numero 26 existe en las dos fuentes y son
    # personas distintas.
    df["empleado_key"] = df["employeenumber"].map(
        lambda n: k_emp.get((n, "customerservice"))
    )

    df["texto_llamada"]     = df["text"]
    df["cantidad_llamadas"] = 1
    df["longitud_texto"]    = df["text"].fillna("").str.len()

    obligatorias = ["tiempo_key", "cliente_key", "producto_key", "empleado_key"]
    huerfanas = int(df[obligatorias].isna().any(axis=1).sum())
    if huerfanas:
        raise RuntimeError(
            f"{huerfanas} llamadas no resolvieron alguna llave obligatoria."
        )

    salida = df[[
        "tiempo_key", "cliente_key", "producto_key", "empleado_key",
        "texto_llamada", "cantidad_llamadas", "longitud_texto",
    ]].copy()
    for c in ["cliente_key", "producto_key", "empleado_key"]:
        salida[c] = salida[c].astype("Int64")

    cargar(salida, "fact_llamadas_servicio")


# ============================================================
# Vista integrada: el entregable que justifica la integracion
# ============================================================

def vista_integrada():
    sql = """
    DROP VIEW IF EXISTS vw_interaccion_cliente_producto;
    CREATE VIEW vw_interaccion_cliente_producto AS
    WITH ventas AS (
        SELECT f.cliente_key, f.producto_key, t.anio_mes,
               SUM(f.cantidad_ordenada) AS unidades_vendidas,
               SUM(f.monto_linea)       AS monto_vendido,
               SUM(f.margen_linea)      AS margen_total,
               COUNT(*)                 AS lineas_orden
        FROM fact_ventas f
        JOIN dim_tiempo t ON f.tiempo_key = t.tiempo_key
        GROUP BY 1, 2, 3
    ),
    llamadas AS (
        SELECT l.cliente_key, l.producto_key, t.anio_mes,
               SUM(l.cantidad_llamadas) AS num_llamadas
        FROM fact_llamadas_servicio l
        JOIN dim_tiempo t ON l.tiempo_key = t.tiempo_key
        GROUP BY 1, 2, 3
    )
    SELECT
        COALESCE(v.anio_mes, ll.anio_mes) AS anio_mes,
        c.numero_cliente,
        c.nombre_cliente,
        c.pais,
        p.codigo_producto,
        p.nombre_producto,
        p.linea_producto,
        COALESCE(v.unidades_vendidas, 0) AS unidades_vendidas,
        COALESCE(v.monto_vendido,     0) AS monto_vendido,
        COALESCE(v.margen_total,      0) AS margen_total,
        COALESCE(v.lineas_orden,      0) AS lineas_orden,
        COALESCE(ll.num_llamadas,     0) AS num_llamadas,
        CASE WHEN COALESCE(v.unidades_vendidas, 0) > 0
             THEN ROUND(COALESCE(ll.num_llamadas, 0)::numeric
                        / v.unidades_vendidas, 4)
        END AS llamadas_por_unidad
    FROM ventas v
    FULL OUTER JOIN llamadas ll
         ON v.cliente_key  = ll.cliente_key
        AND v.producto_key = ll.producto_key
        AND v.anio_mes     = ll.anio_mes
    JOIN dim_cliente  c ON c.cliente_key  = COALESCE(v.cliente_key,  ll.cliente_key)
    JOIN dim_producto p ON p.producto_key = COALESCE(v.producto_key, ll.producto_key);
    """
    with DW.begin() as con:
        con.execute(sa.text(sql))
    n = pd.read_sql("SELECT COUNT(*) AS n FROM vw_interaccion_cliente_producto", DW)
    print(f"  vw_interaccion_cliente_producto: {int(n['n'].iloc[0])} filas")


if __name__ == "__main__":
    exec_id, run_id = abrir_ejecucion()
    print(f"Cargando hechos... (run_id={run_id})")
    try:
        fact_ventas()
        fact_llamadas()
        vista_integrada()
    except Exception as e:
        cerrar_ejecucion(exec_id, "ERROR", error=str(e)[:500])
        raise
    cerrar_ejecucion(exec_id, "OK")
    print(f"Hechos cargados. Leidas {_leidas}, escritas {_escritas}.")
