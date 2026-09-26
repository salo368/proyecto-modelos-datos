"""
ETL de dimensiones - capas 5 a 7 de Giordano, rama de dimensiones.

El diagrama de la Clase 2 (diapositivas 14 a 19) termina bifurcandose en
dos modelos de carga: partes involucradas y eventos. Este proceso es la
rama de las dimensiones; etl_dw_facts.py es la de los hechos. Ambos
parten del mismo Clean Staging que dejo etl_dw_staging.py.

    5 Transformation     conformar por area tematica      dia. 19
    6 Load-Ready Publish forma definitiva                 -
    7 Load               tablas dim_* del modelo estrella -

La transformacion se organiza por AREA CONFORMADA, igual que las cajas
"Conform Loan Data" y "Conform Deposit Data" del diagrama:

    Tiempo        dim_tiempo        generacion
    Organizacion  dim_oficina       proyeccion
    Ventas        dim_estado_orden  agregacion (valores distintos)
    Cliente       dim_cliente       join entre fuentes, consolidacion
    Producto      dim_producto      join con productlines, join entre fuentes
    Empleado      dim_empleado      union de fuentes, llave compuesta

Este proceso NO lee las fuentes: solo la pila de limpios de Clean Staging.

Uso:
    python datawarehouse/etl/etl_dw_dimensions.py
"""
from datetime import date, timedelta

import pandas as pd
import sqlalchemy as sa

from staging_comun import (DW, abrir_run, cerrar_run, filas_json, insertar,
                           leer_limpio, leer_payload, registrar_ejecucion,
                           ultimo_staging_ok)

PROCESO = "etl_dw_dimensions"

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS  = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

# Orden de carga: no hay dependencias entre dimensiones, pero se fija
# para que la salida sea siempre la misma.
ORDEN_CARGA = ["dim_tiempo", "dim_estado_orden", "dim_oficina",
               "dim_cliente", "dim_producto", "dim_empleado"]

_calidad = []   # (regla, evaluadas, fallidas) -> dq_result


def calidad(regla, evaluadas, fallidas, mensaje):
    _calidad.append((regla, evaluadas, fallidas))
    print(f"        [calidad] {mensaje}")


def publicar_transform(run_id, area, objetivo, df, operaciones):
    insertar("stg_transform", [
        {"run_id": run_id, "area_conformada": area, "objetivo": objetivo,
         "nro_fila": i, "payload": p, "operaciones": operaciones}
        for i, p in enumerate(filas_json(df), 1)
    ])
    print(f"    {area:<13}{objetivo:<18}{len(df):>6}  {operaciones}")


# ============================================================
# CAPA 5 - TRANSFORMATION: conformar por area tematica
# ============================================================

def area_tiempo(run_id):
    """No viene de ninguna fuente: se genera. Cubre 2003-2005, que es el
    rango de ventas (2003-01-06 a 2005-05-31) y de llamadas."""
    filas, d, fin = [], date(2003, 1, 1), date(2005, 12, 31)
    while d <= fin:
        filas.append({
            "tiempo_key": int(d.strftime("%Y%m%d")), "fecha": d,
            "anio": d.year, "trimestre": (d.month - 1) // 3 + 1, "mes": d.month,
            "nombre_mes": MESES[d.month - 1], "dia": d.day,
            "dia_semana": d.isoweekday(), "nombre_dia": DIAS[d.isoweekday() - 1],
            "es_fin_semana": d.isoweekday() >= 6, "anio_mes": d.strftime("%Y-%m"),
        })
        d += timedelta(days=1)
    publicar_transform(run_id, "Tiempo", "dim_tiempo", pd.DataFrame(filas),
                       "generacion")


def area_organizacion(run_id, rs):
    ofi = leer_limpio(rs, "offices").rename(columns={
        "officeCode": "codigo_oficina", "city": "ciudad", "country": "pais",
        "state": "region", "territory": "territorio"})
    ofi = ofi[["codigo_oficina", "ciudad", "pais", "region", "territorio"]]
    publicar_transform(run_id, "Organizacion", "dim_oficina", ofi, "proyeccion")


def area_ventas(run_id, rs):
    """Catalogo de estados de orden. es_efectiva distingue la venta
    cerrada de la cancelada, en disputa o en espera: se cargan todas y el
    reporte decide si las excluye, en vez de borrarlas del almacen."""
    ordenes = leer_limpio(rs, "orders")
    no_efectivos = {"Cancelled", "Disputed", "On Hold"}
    estados = pd.DataFrame([
        {"estado": e, "es_efectiva": e not in no_efectivos}
        for e in sorted(ordenes["status"].unique())
    ])
    n_no = int((~estados["es_efectiva"]).sum())
    calidad("estado_orden_no_efectivo", len(estados), n_no,
            f"estados que no cuentan como venta cerrada: {n_no} de {len(estados)}")
    publicar_transform(run_id, "Ventas", "dim_estado_orden", estados,
                       "agregacion (valores distintos)")


def area_cliente(run_id, rs):
    """Dimension CONFORMADA: classicmodels es la fuente autoritativa (tiene
    todos los atributos); customerservice aporta la bandera de presencia."""
    cm = leer_limpio(rs, "customers").rename(columns={
        "customerNumber": "numero_cliente", "customerName": "nombre_cliente",
        "contactFirstName": "contacto_nombre", "contactLastName": "contacto_apellido",
        "phone": "telefono", "city": "ciudad", "state": "estado_region",
        "postalCode": "codigo_postal", "country": "pais",
        "creditLimit": "limite_credito"})

    # Hallazgo de la Entrega 1: addressLine2 esta vacia en el 81,97% de
    # las filas. Se consolida con addressLine1 en un solo atributo.
    vacias = int(cm["addressLine2"].isna().sum())
    cm["direccion_completa"] = (
        cm["addressLine1"].fillna("")
        + cm["addressLine2"].fillna("").apply(lambda x: f", {x}" if x else "")
    ).str.strip(", ")
    calidad("cliente_direccion_linea2_nula", len(cm), vacias,
            f"addressLine2 nula en {vacias} de {len(cm)} -> consolidada")

    cs = leer_limpio(rs, "cs_customers")
    cm["presente_en_ventas"] = True
    cm["presente_en_servicio"] = cm["numero_cliente"].isin(cs["customernumber"])
    en_ambas = int(cm["presente_en_servicio"].sum())
    calidad("cliente_conformidad_fuentes", len(cm), len(cm) - en_ambas,
            f"clientes presentes en ambas fuentes: {en_ambas} de {len(cm)}")

    cm = cm[["numero_cliente", "nombre_cliente", "contacto_nombre",
             "contacto_apellido", "telefono", "direccion_completa", "ciudad",
             "estado_region", "codigo_postal", "pais", "limite_credito",
             "presente_en_ventas", "presente_en_servicio"]]
    publicar_transform(run_id, "Cliente", "dim_cliente", cm,
                       "join entre fuentes, consolidacion de direccion")


def area_producto(run_id, rs):
    """Dimension CONFORMADA, con la linea de producto desnormalizada."""
    pr = leer_limpio(rs, "products")
    pl = leer_limpio(rs, "productlines")

    # Hallazgo de la Entrega 1: htmlDescription e image estan 100% vacias.
    # Se extrajeron ("traer todo", dia. 15) pero no pasan al modelo.
    calidad("productline_columnas_vacias", 2, 2,
            "htmlDescription e image (100% nulas) no pasan al modelo")
    pl = pl[["productLine", "textDescription"]]

    pr = pr.merge(pl, on="productLine", how="left").rename(columns={
        "productCode": "codigo_producto", "productName": "nombre_producto",
        "productLine": "linea_producto", "textDescription": "descripcion_linea",
        "productScale": "escala", "productVendor": "proveedor",
        "buyPrice": "precio_compra", "MSRP": "precio_msrp"})
    pcs = leer_limpio(rs, "cs_products")
    pr["presente_en_ventas"] = True
    pr["presente_en_servicio"] = pr["codigo_producto"].isin(pcs["productcode"])
    en_ambas = int(pr["presente_en_servicio"].sum())
    calidad("producto_conformidad_fuentes", len(pr), len(pr) - en_ambas,
            f"productos presentes en ambas fuentes: {en_ambas} de {len(pr)}")

    pr = pr[["codigo_producto", "nombre_producto", "linea_producto",
             "descripcion_linea", "escala", "proveedor", "precio_compra",
             "precio_msrp", "presente_en_ventas", "presente_en_servicio"]]
    publicar_transform(run_id, "Producto", "dim_producto", pr,
                       "join con productlines, join entre fuentes")


def area_empleado(run_id, rs):
    """Dimension NO conformada.

    Los 23 empleados de classicmodels y los 30 de customerservice son
    personas distintas y no comparten ninguna llave (solape 0%, medido en
    la Entrega 1). Hoy sus numeros ni siquiera coinciden, pero son
    secuencias independientes de dos sistemas distintos y nada garantiza
    que no choquen manana. La llave de negocio compuesta
    (numero_empleado, sistema_origen) hace que la dimension no dependa
    de esa casualidad y deja registrada la procedencia de cada fila.
    """
    ecm = leer_limpio(rs, "employees").rename(columns={
        "employeeNumber": "numero_empleado", "firstName": "nombre",
        "lastName": "apellido", "jobTitle": "cargo", "officeCode": "numero_oficina"})
    ecm["sistema_origen"] = "classicmodels"
    ecs = leer_limpio(rs, "cs_employees").rename(columns={
        "employeenumber": "numero_empleado", "firstname": "nombre",
        "lastname": "apellido"})
    ecs["sistema_origen"] = "customerservice"
    ecs["cargo"] = "Agente de Servicio al Cliente"
    ecs["numero_oficina"] = None

    compartidos = set(ecm["numero_empleado"]) & set(ecs["numero_empleado"])
    calidad("empleado_conformidad_fuentes", len(ecm) + len(ecs), len(compartidos),
            f"numeros de empleado compartidos entre fuentes: {len(compartidos)} "
            f"-> llave compuesta (numero_empleado, sistema_origen)")

    cols = ["numero_empleado", "sistema_origen", "nombre", "apellido",
            "email", "cargo", "numero_oficina"]
    emp = pd.concat([ecm[cols], ecs[cols]], ignore_index=True)
    publicar_transform(run_id, "Empleado", "dim_empleado", emp,
                       "union de fuentes, llave compuesta")


# ============================================================
# CAPAS 6 y 7 - LOAD-READY PUBLISH y LOAD
# ============================================================

def publicar_y_cargar(run_id):
    print("\n[Capa 6] Load-Ready Publish         (modelo de carga: DIMENSIONES)")
    print("[Capa 7] Load")
    total = 0
    for objetivo in ORDEN_CARGA:
        df = leer_payload("stg_transform", run_id, objetivo=objetivo)
        insertar("stg_loadready", [
            {"run_id": run_id, "modelo_carga": "DIMENSIONES", "objetivo": objetivo,
             "nro_fila": i, "payload": p}
            for i, p in enumerate(filas_json(df), 1)
        ])
        # Las tablas del modelo si se reemplazan en cada carga: el
        # historial vive en staging, que es no volatil.
        with DW.begin() as con:
            con.execute(sa.text(f"TRUNCATE TABLE {objetivo} RESTART IDENTITY CASCADE"))
        df.to_sql(objetivo, DW, if_exists="append", index=False)
        total += len(df)
        print(f"    {objetivo:<18}{len(df):>6} filas")
    return total


if __name__ == "__main__":
    rs = ultimo_staging_ok()
    run_id = abrir_run("dimensiones", run_origen=rs)
    print(f"ETL de dimensiones - run_id={run_id}, lee Clean Staging del run {rs}")
    print("Las fuentes NO se leen aqui (dia. 15: read once, write many)")
    try:
        print("\n[Capa 5] Transformation             (dia. 19: conformar por area)")
        area_tiempo(run_id)
        area_organizacion(run_id, rs)
        area_ventas(run_id, rs)
        area_cliente(run_id, rs)
        area_producto(run_id, rs)
        area_empleado(run_id, rs)
        escritas = publicar_y_cargar(run_id)
    except Exception as e:
        cerrar_run(run_id, "ERROR")
        registrar_ejecucion(PROCESO, "", "", run_id, 0, 0, 0, "ERROR", str(e)[:500])
        raise
    cerrar_run(run_id, "OK")
    registrar_ejecucion(
        PROCESO,
        "Capas 5 a 7 de Giordano para el modelo de dimensiones: conforma por "
        "area tematica desde Clean Staging y carga las seis dimensiones.",
        f"staging_dw.stg_clean (run {rs}); las fuentes no se releen",
        run_id, escritas, escritas, 0, "OK", resultados_calidad=_calidad,
    )
    print(f"\nDimensiones cargadas: {escritas} filas.")
