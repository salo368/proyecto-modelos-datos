"""
ETL de hechos hacia el almacen de datos - Entrega 2.

Implementa las mismas cuatro capas de Giordano que el ETL de
dimensiones, con una diferencia que es el punto central del principio
"read once, write many" (Clase 2, diapositiva 15):

    ESTE PROCESO NO TOCA LAS FUENTES.

Las once tablas de classicmodels y customerservice ya fueron leidas
una sola vez por el ETL de dimensiones, que las deposito en
staging_dw.stg_extract. Este proceso consume esa copia. Si volviera a
consultar MySQL y PostgreSQL estaria leyendo las fuentes por segunda
vez en la misma carga, que es justo lo que la diapositiva 15 prohibe.

    Capa            Tabla                        Diapositiva
    ------------------------------------------------------------
    Extract         (reusa el landing existente)  15, 16
    Data Quality    staging_dw.stg_dq             17, 18
    Transform       staging_dw.stg_transform      19
    Load-Ready      staging_dw.stg_loadready      -
    Load            fact_* en el schema public    -

La capa Transform es donde ocurre el LOOKUP de la diapositiva 19: la
traduccion de llave de negocio a llave subrogada (customerNumber 103
se convierte en cliente_key 7). En un ETL dimensional esa es la
operacion caracteristica, y aqui queda persistida y auditable en vez
de vivir en un diccionario en memoria.

Requiere haber corrido antes:
    python datawarehouse/etl/etl_dw_dimensions.py

Uso:
    python datawarehouse/etl/etl_dw_facts.py
"""
import os
from datetime import date, datetime

import pandas as pd
import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

DW   = sa.create_engine(os.getenv("DW_URL"))
META = sa.create_engine(os.getenv("METADATA_REPO_URL"))

PROCESO     = "etl_dw_facts"
HERRAMIENTA = "Python 3.11 + SQLAlchemy 2.1 + pandas 3.0"

_calidad = []


# ============================================================
# Utilidades de staging (mismas que en el ETL de dimensiones)
# ============================================================

def abrir_run():
    with DW.begin() as con:
        return con.execute(sa.text("""
            INSERT INTO staging_dw.etl_run (proceso) VALUES (:p) RETURNING run_id
        """), {"p": "hechos"}).scalar()


def cerrar_run(run_id, estado):
    with DW.begin() as con:
        con.execute(sa.text("""
            UPDATE staging_dw.etl_run
               SET finalizado_en = now(), estado = :e
             WHERE run_id = :r
        """), {"e": estado, "r": run_id})


def _json_seguro(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat()
    if hasattr(v, "item"):
        return v.item()
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", "replace")
    return v


def _filas_json(df):
    return [
        {k: _json_seguro(v) for k, v in fila.items()}
        for fila in df.to_dict(orient="records")
    ]


def escribir_capa(tabla, run_id, filas, **fijos):
    if not filas:
        return
    cols = ["run_id"] + list(fijos.keys()) + ["nro_fila", "payload"]
    registros = [
        {"run_id": run_id, **fijos, "nro_fila": i, "payload": p}
        for i, p in enumerate(filas, 1)
    ]
    sql = sa.text(
        f"INSERT INTO staging_dw.{tabla} ({', '.join(cols)}) "
        f"VALUES ({', '.join(f':{c}' for c in cols)})"
    ).bindparams(sa.bindparam("payload", type_=sa.JSON))
    with DW.begin() as con:
        con.execute(sql, registros)


def leer_capa(tabla, run_id, **filtros):
    cond = " AND ".join([f"{k} = :{k}" for k in filtros])
    where = f" AND {cond}" if cond else ""
    with DW.connect() as con:
        filas = con.execute(
            sa.text(f"SELECT payload FROM staging_dw.{tabla} "
                    f"WHERE run_id = :r{where} ORDER BY nro_fila"),
            {"r": run_id, **filtros},
        ).fetchall()
    return pd.DataFrame([f[0] for f in filas])


def calidad(regla, evaluadas, fallidas, paso, mensaje):
    _calidad.append((regla, evaluadas, fallidas, paso))
    print(f"    [calidad] {mensaje}")


# ============================================================
# CAPA 1 - EXTRACT: se reusa el landing, no se relee la fuente
# ============================================================

def ultimo_run_con_landing():
    """run_id de la ultima extraccion disponible en landing.

    No se vuelve a leer MySQL ni PostgreSQL: el principio
    "read once, write many" exige que la fuente se lea una vez por
    carga, y eso ya lo hizo el ETL de dimensiones.
    """
    with DW.connect() as con:
        rid = con.execute(sa.text("""
            SELECT MAX(r.run_id)
            FROM staging_dw.etl_run r
            WHERE r.proceso = 'dimensiones' AND r.estado = 'OK'
              AND EXISTS (SELECT 1 FROM staging_dw.stg_extract e
                           WHERE e.run_id = r.run_id)
        """)).scalar()
    if rid is None:
        raise RuntimeError(
            "No hay ninguna extraccion en staging_dw.stg_extract.\n"
            "Corre primero: python datawarehouse/etl/etl_dw_dimensions.py"
        )
    return rid


def desde_landing(run_landing, tabla):
    """Lee una tabla de origen desde el landing, ya filtrada por calidad."""
    with DW.connect() as con:
        filas = con.execute(sa.text("""
            SELECT payload FROM staging_dw.stg_dq
            WHERE run_id = :r AND tabla_origen = :t AND dq_status = 'OK'
            ORDER BY nro_fila
        """), {"r": run_landing, "t": tabla}).fetchall()
    return pd.DataFrame([f[0] for f in filas])


# ============================================================
# CAPA 3 - TRANSFORM: joins, lookups y agregaciones (dia. 19)
# ============================================================

def mapa_subrogadas(tabla, llave_negocio, llave_subrogada, extra=None):
    """Diccionario {llave de negocio -> llave subrogada}.

    Este es el LOOKUP de la diapositiva 19. Con `extra` la clave es una
    tupla, que es lo que necesita dim_empleado: su llave de negocio es
    compuesta (numero_empleado, sistema_origen) porque las dos fuentes
    reutilizan los mismos numeros para personas distintas.
    """
    cols = f"{llave_negocio}, {llave_subrogada}" + (f", {extra}" if extra else "")
    df = pd.read_sql(f"SELECT {cols} FROM {tabla}", DW)
    if extra:
        return {(r[llave_negocio], r[extra]): r[llave_subrogada]
                for _, r in df.iterrows()}
    return dict(zip(df[llave_negocio], df[llave_subrogada]))


def transformar_ventas(run_id, run_landing):
    """fact_ventas: grano de una linea de orden."""
    od  = desde_landing(run_landing, "orderdetails")
    orq = desde_landing(run_landing, "orders")
    pro = desde_landing(run_landing, "products")
    cli = desde_landing(run_landing, "customers")
    emp = desde_landing(run_landing, "employees")

    # --- Joins (dia. 19) ---
    df = (od
          .merge(orq, on="orderNumber", how="inner")
          .merge(pro[["productCode", "buyPrice", "MSRP"]],
                 on="productCode", how="left")
          .merge(cli[["customerNumber", "salesRepEmployeeNumber"]],
                 on="customerNumber", how="left")
          .merge(emp[["employeeNumber", "officeCode"]],
                 left_on="salesRepEmployeeNumber", right_on="employeeNumber",
                 how="left"))

    # --- Agregaciones / medidas calculadas (dia. 19) ---
    df["monto_linea"]  = (df["quantityOrdered"] * df["priceEach"]).round(2)
    df["costo_linea"]  = (df["quantityOrdered"] * df["buyPrice"]).round(2)
    df["margen_linea"] = (df["monto_linea"] - df["costo_linea"]).round(2)

    envio = pd.to_datetime(df["shippedDate"], errors="coerce")
    pedido = pd.to_datetime(df["orderDate"], errors="coerce")
    df["dias_hasta_envio"] = (envio - pedido).dt.days
    sin_envio = int(df["dias_hasta_envio"].isna().sum())
    calidad("orden_fecha_envio_nula", len(df), sin_envio, True,
            f"lineas sin fecha de envio: {sin_envio} de {len(df)} "
            f"-> dias_hasta_envio queda NULL")

    # --- Lookups: llave de negocio -> llave subrogada (dia. 19) ---
    k_cli = mapa_subrogadas("dim_cliente",      "numero_cliente",  "cliente_key")
    k_pro = mapa_subrogadas("dim_producto",     "codigo_producto", "producto_key")
    k_ofi = mapa_subrogadas("dim_oficina",      "codigo_oficina",  "oficina_key")
    k_est = mapa_subrogadas("dim_estado_orden", "estado",          "estado_key")
    k_emp = mapa_subrogadas("dim_empleado",     "numero_empleado", "empleado_key",
                            extra="sistema_origen")

    df["tiempo_key"]   = pedido.dt.strftime("%Y%m%d").astype("Int64")
    df["cliente_key"]  = df["customerNumber"].map(k_cli)
    df["producto_key"] = df["productCode"].map(k_pro)
    df["oficina_key"]  = df["officeCode"].map(k_ofi)
    df["estado_key"]   = df["status"].map(k_est)
    # El vendedor siempre proviene de classicmodels; un agente de
    # servicio nunca aparece como representante de ventas.
    df["empleado_key"] = df["salesRepEmployeeNumber"].map(
        lambda n: k_emp.get((n, "classicmodels")) if pd.notna(n) else None)

    df = df.rename(columns={
        "orderNumber": "numero_orden", "orderLineNumber": "numero_linea",
        "quantityOrdered": "cantidad_ordenada", "priceEach": "precio_unitario",
        "MSRP": "precio_msrp"})

    salida = df[["tiempo_key", "cliente_key", "producto_key", "empleado_key",
                 "oficina_key", "estado_key", "numero_orden", "numero_linea",
                 "cantidad_ordenada", "precio_unitario", "monto_linea",
                 "costo_linea", "margen_linea", "precio_msrp",
                 "dias_hasta_envio"]].copy()

    # Ninguna llave obligatoria puede quedar sin resolver: antes de
    # escribir un hecho huerfano, el proceso falla.
    obligatorias = ["tiempo_key", "cliente_key", "producto_key", "estado_key"]
    huerfanas = int(salida[obligatorias].isna().any(axis=1).sum())
    if huerfanas:
        raise RuntimeError(
            f"{huerfanas} filas de fact_ventas no resolvieron alguna llave "
            f"obligatoria. Revisa que las dimensiones esten completas.")

    for c in ["cliente_key", "producto_key", "empleado_key", "oficina_key",
              "estado_key", "dias_hasta_envio"]:
        salida[c] = salida[c].astype("Int64")

    escribir_capa("stg_transform", run_id, _filas_json(salida),
                  objetivo="fact_ventas",
                  operaciones="join (5 tablas), lookup (5 dimensiones), calculo de medidas")
    print(f"    fact_ventas            {len(salida):>5}  join + lookup + calculo")
    return len(salida)


def transformar_llamadas(run_id, run_landing):
    """fact_llamadas_servicio: grano de una llamada."""
    df = desde_landing(run_landing, "cs_customer_calls")

    k_cli = mapa_subrogadas("dim_cliente",  "numero_cliente",  "cliente_key")
    k_pro = mapa_subrogadas("dim_producto", "codigo_producto", "producto_key")
    k_emp = mapa_subrogadas("dim_empleado", "numero_empleado", "empleado_key",
                            extra="sistema_origen")

    df["tiempo_key"]   = pd.to_datetime(df["date"]).dt.strftime("%Y%m%d").astype("Int64")
    df["cliente_key"]  = df["customernumber"].map(k_cli)
    df["producto_key"] = df["productcode"].map(k_pro)
    # El agente siempre proviene de customerservice. Esta es la razon de
    # ser de la llave compuesta: el numero 26 existe en las dos fuentes
    # y corresponde a dos personas distintas.
    df["empleado_key"] = df["employeenumber"].map(
        lambda n: k_emp.get((n, "customerservice")))

    df["texto_llamada"]     = df["text"]
    df["cantidad_llamadas"] = 1
    df["longitud_texto"]    = df["text"].fillna("").str.len()

    salida = df[["tiempo_key", "cliente_key", "producto_key", "empleado_key",
                 "texto_llamada", "cantidad_llamadas", "longitud_texto"]].copy()

    obligatorias = ["tiempo_key", "cliente_key", "producto_key", "empleado_key"]
    huerfanas = int(salida[obligatorias].isna().any(axis=1).sum())
    if huerfanas:
        raise RuntimeError(
            f"{huerfanas} llamadas no resolvieron alguna llave obligatoria.")

    for c in ["cliente_key", "producto_key", "empleado_key"]:
        salida[c] = salida[c].astype("Int64")

    escribir_capa("stg_transform", run_id, _filas_json(salida),
                  objetivo="fact_llamadas_servicio",
                  operaciones="lookup (3 dimensiones), calculo de medidas")
    print(f"    fact_llamadas_servicio {len(salida):>5}  lookup + calculo")
    return len(salida)


# ============================================================
# CAPA 4 - LOAD-READY PUBLISH y LOAD
# ============================================================

def publicar_y_cargar(run_id):
    print("\n[Capa 4/4] Load-Ready Publish y Load")
    total = 0
    for objetivo in ["fact_ventas", "fact_llamadas_servicio"]:
        df = leer_capa("stg_transform", run_id, objetivo=objetivo)
        if df.empty:
            continue
        escribir_capa("stg_loadready", run_id, _filas_json(df), objetivo=objetivo)
        with DW.begin() as con:
            con.execute(sa.text(f"TRUNCATE TABLE {objetivo} RESTART IDENTITY CASCADE"))
        df.to_sql(objetivo, DW, if_exists="append", index=False)
        total += len(df)
        print(f"    {objetivo:<24}{len(df):>5} filas")
    return total


def vista_integrada():
    """Vista que cruza los dos hechos al grano cliente x producto x mes.

    Es el artefacto que justifica haber integrado las dos fuentes:
    responde que productos generan mas llamadas por unidad vendida,
    pregunta que ninguna fuente contesta por si sola.
    """
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
        c.numero_cliente, c.nombre_cliente, c.pais,
        p.codigo_producto, p.nombre_producto, p.linea_producto,
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
    print(f"    vw_interaccion_cliente_producto {int(n['n'].iloc[0]):>5} filas")


# ============================================================
# Registro en el repositorio de metadatos
# ============================================================

def registrar_en_metadatos(run_id, leidas, escritas, estado, error=None):
    with META.begin() as con:
        proceso_id = con.execute(sa.text("""
            INSERT INTO etl_process (process_name, tool, source_systems,
                                     target_system, description)
            VALUES (:n, :t, :s, :d, :desc)
            ON CONFLICT (process_name) DO UPDATE SET tool = EXCLUDED.tool
            RETURNING etl_process_id
        """), {
            "n": PROCESO, "t": HERRAMIENTA,
            "s": "staging_dw.stg_extract (landing; las fuentes no se releen)",
            "d": "dw (PostgreSQL)",
            "desc": "Carga los dos hechos resolviendo llaves subrogadas en la "
                    "capa Transform, y crea la vista integrada.",
        }).scalar()

        exec_id = con.execute(sa.text("""
            INSERT INTO etl_execution (etl_process_id, run_id, started_at,
                                       finished_at, status, rows_read,
                                       rows_written, rows_rejected, error_message)
            VALUES (:p, :r, now(), now(), :s, :lr, :lw, 0, :e)
            RETURNING etl_execution_id
        """), {"p": proceso_id, "r": run_id, "s": estado,
               "lr": leidas, "lw": escritas, "e": error}).scalar()

        for regla, evaluadas, fallidas, paso in _calidad:
            rid = con.execute(sa.text(
                "SELECT dq_rule_id FROM dq_rule WHERE rule_name = :n"),
                {"n": regla}).scalar()
            if rid:
                con.execute(sa.text("""
                    INSERT INTO dq_result (dq_rule_id, etl_execution_id,
                                           rows_evaluated, rows_failed, passed)
                    VALUES (:r, :e, :ev, :fa, :p)
                """), {"r": rid, "e": exec_id, "ev": evaluadas,
                       "fa": fallidas, "p": paso})


if __name__ == "__main__":
    run_id = abrir_run()
    run_landing = ultimo_run_con_landing()
    print(f"ETL de hechos - run_id={run_id}")
    print("Arquitectura de referencia: Giordano (2011), Cap. 2 - Clase 2")
    print(f"\n[Capa 1/4] Extract - se reusa el landing del run {run_landing}")
    print("    Las fuentes NO se vuelven a leer (dia. 15: read once, write many)")
    try:
        print("\n[Capa 2/4] Data Quality - heredada del landing filtrado")
        print("\n[Capa 3/4] Transform                (dia. 19: joins, lookups, agregaciones)")
        n1 = transformar_ventas(run_id, run_landing)
        n2 = transformar_llamadas(run_id, run_landing)
        escritas = publicar_y_cargar(run_id)
        vista_integrada()
    except Exception as e:
        cerrar_run(run_id, "ERROR")
        registrar_en_metadatos(run_id, 0, 0, "ERROR", str(e)[:500])
        raise
    cerrar_run(run_id, "OK")
    registrar_en_metadatos(run_id, n1 + n2, escritas, "OK")
    print(f"\nHechos cargados. Transformadas {n1 + n2}, escritas {escritas}.")
