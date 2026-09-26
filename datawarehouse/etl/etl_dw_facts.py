"""
ETL de hechos - capas 5 a 7 de Giordano, rama de hechos.

Es la segunda rama de la bifurcacion final del diagrama de la Clase 2
(el modelo de carga de eventos). Parte del mismo Clean Staging que la
rama de dimensiones y necesita que esa rama haya terminado, porque
resuelve las llaves subrogadas contra las dimensiones ya cargadas.

    5 Transformation     conformar por area tematica      dia. 19
    6 Load-Ready Publish forma definitiva                 -
    7 Load               tablas fact_* del modelo estrella -

Areas conformadas:

    Ventas    fact_ventas             join (5 tablas), lookup (5 dim.), calculo
    Servicio  fact_llamadas_servicio  lookup (3 dimensiones), calculo

Las tres operaciones de la diapositiva 19 aparecen juntas en
fact_ventas: los JOINS reunen cinco tablas limpias, el LOOKUP traduce
cada llave de negocio a su llave subrogada, y las AGREGACIONES producen
las medidas calculadas.

Este proceso NO lee las fuentes: solo la pila de limpios de Clean Staging.

Uso:
    python datawarehouse/etl/etl_dw_facts.py
"""
import pandas as pd
import sqlalchemy as sa

from staging_comun import (DW, abrir_run, cerrar_run, filas_json, insertar,
                           leer_limpio, leer_payload, registrar_ejecucion,
                           ultimo_staging_ok)

PROCESO = "etl_dw_facts"

_calidad = []


def calidad(regla, evaluadas, fallidas, mensaje):
    _calidad.append((regla, evaluadas, fallidas))
    print(f"        [calidad] {mensaje}")


def mapa_subrogadas(tabla, llave_negocio, llave_subrogada, extra=None):
    """LOOKUP de la diapositiva 19: llave de negocio -> llave subrogada.

    Con `extra` la clave es una tupla. Lo necesita dim_empleado, cuya
    llave de negocio es compuesta (numero_empleado, sistema_origen).
    """
    cols = f"{llave_negocio}, {llave_subrogada}" + (f", {extra}" if extra else "")
    df = pd.read_sql(f"SELECT {cols} FROM {tabla}", DW)
    if extra:
        return {(r[llave_negocio], r[extra]): r[llave_subrogada]
                for _, r in df.iterrows()}
    return dict(zip(df[llave_negocio], df[llave_subrogada]))


def verificar_llaves(df, obligatorias, objetivo):
    """Antes de escribir un hecho huerfano, el proceso falla.

    Un hecho que apunta a una dimension inexistente corrompe todos los
    reportes que lo agreguen; es preferible detener la carga.
    """
    huerfanas = int(df[obligatorias].isna().any(axis=1).sum())
    if huerfanas:
        raise RuntimeError(
            f"{huerfanas} filas de {objetivo} no resolvieron alguna llave "
            f"obligatoria. Revisa que las dimensiones esten completas.")


def publicar_transform(run_id, area, objetivo, df, operaciones):
    insertar("stg_transform", [
        {"run_id": run_id, "area_conformada": area, "objetivo": objetivo,
         "nro_fila": i, "payload": p, "operaciones": operaciones}
        for i, p in enumerate(filas_json(df), 1)
    ])
    print(f"    {area:<10}{objetivo:<24}{len(df):>6}  {operaciones}")


# ============================================================
# CAPA 5 - TRANSFORMATION
# ============================================================

def area_ventas(run_id, rs):
    """fact_ventas: grano de una linea de orden."""
    od  = leer_limpio(rs, "orderdetails")
    orq = leer_limpio(rs, "orders")
    pro = leer_limpio(rs, "products")
    cli = leer_limpio(rs, "customers")
    emp = leer_limpio(rs, "employees")

    # --- Joins ---
    df = (od
          .merge(orq, on="orderNumber", how="inner")
          .merge(pro[["productCode", "buyPrice", "MSRP"]], on="productCode", how="left")
          .merge(cli[["customerNumber", "salesRepEmployeeNumber"]],
                 on="customerNumber", how="left")
          .merge(emp[["employeeNumber", "officeCode"]],
                 left_on="salesRepEmployeeNumber", right_on="employeeNumber",
                 how="left"))

    # --- Agregaciones: medidas calculadas ---
    df["monto_linea"]  = (df["quantityOrdered"] * df["priceEach"]).round(2)
    df["costo_linea"]  = (df["quantityOrdered"] * df["buyPrice"]).round(2)
    df["margen_linea"] = (df["monto_linea"] - df["costo_linea"]).round(2)
    pedido = pd.to_datetime(df["orderDate"], errors="coerce")
    envio  = pd.to_datetime(df["shippedDate"], errors="coerce")
    df["dias_hasta_envio"] = (envio - pedido).dt.days

    # Hallazgo de la Entrega 1: shippedDate es nula en las ordenes que no
    # se despacharon. No es un error (Data Quality ya verifico que ninguna
    # orden 'Shipped' carezca de fecha): la medida queda NULL.
    sin_envio = int(df["dias_hasta_envio"].isna().sum())
    calidad("orden_fecha_envio_nula", len(df), sin_envio,
            f"lineas de ordenes aun no despachadas: {sin_envio} de {len(df)} "
            f"-> dias_hasta_envio NULL")

    # --- Lookups: llave de negocio -> llave subrogada ---
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
    # El vendedor siempre proviene de classicmodels. Los 22 clientes sin
    # vendedor asignado (advertencia en Data Quality) quedan con
    # empleado_key y oficina_key nulos, que el modelo admite.
    df["empleado_key"] = df["salesRepEmployeeNumber"].map(
        lambda n: k_emp.get((n, "classicmodels")) if pd.notna(n) else None)

    salida = df.rename(columns={
        "orderNumber": "numero_orden", "orderLineNumber": "numero_linea",
        "quantityOrdered": "cantidad_ordenada", "priceEach": "precio_unitario",
        "MSRP": "precio_msrp"})[[
        "tiempo_key", "cliente_key", "producto_key", "empleado_key",
        "oficina_key", "estado_key", "numero_orden", "numero_linea",
        "cantidad_ordenada", "precio_unitario", "monto_linea",
        "costo_linea", "margen_linea", "precio_msrp", "dias_hasta_envio"]].copy()

    verificar_llaves(salida, ["tiempo_key", "cliente_key", "producto_key",
                              "estado_key"], "fact_ventas")
    for c in ["cliente_key", "producto_key", "empleado_key", "oficina_key",
              "estado_key", "dias_hasta_envio"]:
        salida[c] = salida[c].astype("Int64")

    publicar_transform(run_id, "Ventas", "fact_ventas", salida,
                       "join (5 tablas), lookup (5 dimensiones), calculo de medidas")
    return len(salida)


def area_servicio(run_id, rs):
    """fact_llamadas_servicio: grano de una llamada."""
    df = leer_limpio(rs, "cs_customer_calls")

    k_cli = mapa_subrogadas("dim_cliente",  "numero_cliente",  "cliente_key")
    k_pro = mapa_subrogadas("dim_producto", "codigo_producto", "producto_key")
    k_emp = mapa_subrogadas("dim_empleado", "numero_empleado", "empleado_key",
                            extra="sistema_origen")

    df["tiempo_key"]   = pd.to_datetime(df["date"]).dt.strftime("%Y%m%d").astype("Int64")
    df["cliente_key"]  = df["customernumber"].map(k_cli)
    df["producto_key"] = df["productcode"].map(k_pro)
    # El agente siempre proviene de customerservice: la llave compuesta
    # garantiza que se resuelva contra esa poblacion y no contra la de
    # vendedores de classicmodels.
    df["empleado_key"] = df["employeenumber"].map(
        lambda n: k_emp.get((n, "customerservice")))
    df["texto_llamada"]     = df["text"]
    df["cantidad_llamadas"] = 1
    df["longitud_texto"]    = df["text"].fillna("").str.len()

    salida = df[["tiempo_key", "cliente_key", "producto_key", "empleado_key",
                 "texto_llamada", "cantidad_llamadas", "longitud_texto"]].copy()
    verificar_llaves(salida, ["tiempo_key", "cliente_key", "producto_key",
                              "empleado_key"], "fact_llamadas_servicio")
    for c in ["cliente_key", "producto_key", "empleado_key"]:
        salida[c] = salida[c].astype("Int64")

    publicar_transform(run_id, "Servicio", "fact_llamadas_servicio", salida,
                       "lookup (3 dimensiones), calculo de medidas")
    return len(salida)


# ============================================================
# CAPAS 6 y 7 - LOAD-READY PUBLISH y LOAD
# ============================================================

def publicar_y_cargar(run_id):
    print("\n[Capa 6] Load-Ready Publish         (modelo de carga: HECHOS)")
    print("[Capa 7] Load")
    total = 0
    for objetivo in ["fact_ventas", "fact_llamadas_servicio"]:
        df = leer_payload("stg_transform", run_id, objetivo=objetivo)
        insertar("stg_loadready", [
            {"run_id": run_id, "modelo_carga": "HECHOS", "objetivo": objetivo,
             "nro_fila": i, "payload": p}
            for i, p in enumerate(filas_json(df), 1)
        ])
        with DW.begin() as con:
            con.execute(sa.text(f"TRUNCATE TABLE {objetivo} RESTART IDENTITY CASCADE"))
        df.to_sql(objetivo, DW, if_exists="append", index=False)
        total += len(df)
        print(f"    {objetivo:<24}{len(df):>6} filas")
    return total


if __name__ == "__main__":
    rs = ultimo_staging_ok()
    run_id = abrir_run("hechos", run_origen=rs)
    print(f"ETL de hechos - run_id={run_id}, lee Clean Staging del run {rs}")
    print("Las fuentes NO se leen aqui (dia. 15: read once, write many)")
    try:
        print("\n[Capa 5] Transformation             (dia. 19: joins, lookups, agregaciones)")
        n = area_ventas(run_id, rs) + area_servicio(run_id, rs)
        escritas = publicar_y_cargar(run_id)
    except Exception as e:
        cerrar_run(run_id, "ERROR")
        registrar_ejecucion(PROCESO, "", "", run_id, 0, 0, 0, "ERROR", str(e)[:500])
        raise
    cerrar_run(run_id, "OK")
    registrar_ejecucion(
        PROCESO,
        "Capas 5 a 7 de Giordano para el modelo de hechos: conforma ventas y "
        "servicio desde Clean Staging, resuelve llaves subrogadas y carga los "
        "dos hechos.",
        f"staging_dw.stg_clean (run {rs}); las fuentes no se releen",
        run_id, n, escritas, 0, "OK", resultados_calidad=_calidad,
    )
    print(f"\nHechos cargados: {escritas} filas.")
