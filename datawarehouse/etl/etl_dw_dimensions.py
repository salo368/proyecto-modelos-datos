"""
ETL de dimensiones hacia el almacen de datos - Entrega 2.

Implementa la arquitectura de referencia de Anthony Giordano
(Data Integration Blueprint and Modeling, 2011, Cap. 2) tal como se
presento en la Clase 2 del curso. Las capas NO son pasos en memoria:
cada una escribe en una tabla fisica de staging_dw que queda
disponible para auditoria.

    Capa            Tabla                        Diapositiva
    ------------------------------------------------------------
    Extract         staging_dw.stg_extract       15, 16
    Data Quality    staging_dw.stg_dq            17, 18
    Transform       staging_dw.stg_transform     19
    Load-Ready      staging_dw.stg_loadready     -
    Load            dim_* en el schema public    -

Dos principios de Giordano que gobiernan el diseno:

  Read once, write many (dia. 15)
      Cada tabla de las fuentes se lee UNA SOLA VEZ por corrida, hacia
      Extract. Las capas siguientes y el ETL de hechos consumen desde
      staging, nunca de la fuente. Por eso extraer() trae tambien
      orderdetails y cs_customer_calls, que este proceso no necesita
      pero el de hechos si.

  Almacenamiento no volatil (dia. 16)
      Ninguna tabla de staging se trunca. Cada corrida agrega filas
      con su run_id y el historial completo queda disponible.

Requiere haber corrido antes:
    datawarehouse/ddl/01_dw_schema.sql
    datawarehouse/ddl/02_staging_dw.sql

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

PROCESO     = "etl_dw_dimensions"
HERRAMIENTA = "Python 3.11 + SQLAlchemy 2.1 + pandas 3.0"

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
DIAS  = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]

# Las nueve tablas de las dos fuentes. Se extraen TODAS en cada corrida,
# aunque este proceso solo use algunas: el principio "read once, write
# many" exige leer la fuente una vez y que los demas procesos consuman
# la copia. orderdetails y cs_customer_calls los usa el ETL de hechos.
FUENTES = [
    ("classicmodels",   MYSQL, "customers",            "SELECT * FROM customers"),
    ("classicmodels",   MYSQL, "employees",            "SELECT * FROM employees"),
    ("classicmodels",   MYSQL, "offices",              "SELECT * FROM offices"),
    ("classicmodels",   MYSQL, "products",             "SELECT * FROM products"),
    ("classicmodels",   MYSQL, "productlines",         "SELECT productLine, textDescription FROM productlines"),
    ("classicmodels",   MYSQL, "orders",               "SELECT * FROM orders"),
    ("classicmodels",   MYSQL, "orderdetails",         "SELECT * FROM orderdetails"),
    ("customerservice", PG,    "cs_customers",         "SELECT * FROM cs_customers"),
    ("customerservice", PG,    "cs_products",          "SELECT * FROM cs_products"),
    ("customerservice", PG,    "cs_employees",         "SELECT * FROM cs_employees"),
    ("customerservice", PG,    "cs_customer_calls",    "SELECT * FROM cs_customer_calls"),
]

_calidad = []   # (regla, evaluadas, fallidas, paso) -> se vuelca a dq_result


# ============================================================
# Utilidades de staging
# ============================================================

def abrir_run():
    with DW.begin() as con:
        return con.execute(sa.text("""
            INSERT INTO staging_dw.etl_run (proceso) VALUES (:p) RETURNING run_id
        """), {"p": "dimensiones"}).scalar()


def cerrar_run(run_id, estado):
    with DW.begin() as con:
        con.execute(sa.text("""
            UPDATE staging_dw.etl_run
               SET finalizado_en = now(), estado = :e
             WHERE run_id = :r
        """), {"e": estado, "r": run_id})


def _json_seguro(v):
    """Convierte un valor de pandas a algo serializable en JSON."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat()
    if hasattr(v, "item"):          # numpy int64 / float64 / bool_
        return v.item()
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", "replace")
    return v


def _filas_json(df):
    """DataFrame -> lista de dicts listos para JSONB."""
    return [
        {k: _json_seguro(v) for k, v in fila.items()}
        for fila in df.to_dict(orient="records")
    ]


def escribir_capa(tabla, run_id, filas, **fijos):
    """Inserta filas en una capa de staging. Nunca trunca (no volatil)."""
    if not filas:
        return
    cols = ["run_id"] + list(fijos.keys()) + ["nro_fila", "payload"]
    # El payload se pasa como dict: el bindparam de tipo JSON se encarga
    # de serializarlo. Hacerle json.dumps antes lo codificaria dos veces
    # y el JSONB guardaria una cadena en vez de un objeto.
    registros = [
        {"run_id": run_id, **fijos, "nro_fila": i, "payload": p}
        for i, p in enumerate(filas, 1)
    ]
    marcadores = ", ".join(f":{c}" for c in cols)
    sql = sa.text(
        f"INSERT INTO staging_dw.{tabla} ({', '.join(cols)}) "
        f"VALUES ({marcadores})"
    ).bindparams(sa.bindparam("payload", type_=sa.JSON))
    with DW.begin() as con:
        con.execute(sql, registros)


def leer_capa(tabla, run_id, **filtros):
    """Devuelve un DataFrame con el payload de una capa."""
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
# CAPA 1 - EXTRACT / LANDING            (Clase 2, diapositivas 15-16)
# ============================================================

def extraer(run_id):
    """Lee cada fuente UNA SOLA VEZ y la deposita tal cual en landing."""
    print("\n[Capa 1/4] Extract - Landing        (dia. 15-16: read once, no volatil)")
    total = 0
    for fuente, engine, tabla, sql in FUENTES:
        df = pd.read_sql(sql, engine)
        escribir_capa("stg_extract", run_id, _filas_json(df),
                      fuente=fuente, tabla_origen=tabla)
        total += len(df)
        print(f"    {fuente:<16} {tabla:<20} {len(df):>5} filas")
    print(f"    {'TOTAL':<37} {total:>5} filas en landing")
    return total


# ============================================================
# CAPA 2 - DATA QUALITY                 (Clase 2, diapositivas 17-18)
# ============================================================

def calidad_datos(run_id):
    """Evalua calidad tecnica y de negocio sobre lo que hay en landing.

    La diapositiva 17 separa la calidad en dos clases y aqui se marcan
    con clase_dq:

      TECNICA   datos faltantes o invalidos, detectables sin conocer
                la regla de negocio (una llave primaria nula).
      NEGOCIO   definiciones inconsistentes o datos inexactos, que
                requieren conocer la semantica (un cliente que existe
                en ventas pero no en servicio).
    """
    print("\n[Capa 2/4] Data Quality             (dia. 17-18: tecnica / negocio)")

    # Llaves primarias por tabla: si vienen nulas la fila es inservible.
    LLAVES = {
        "customers": "customerNumber", "employees": "employeeNumber",
        "offices": "officeCode", "products": "productCode",
        "productlines": "productLine", "orders": "orderNumber",
        "cs_customers": "customernumber", "cs_products": "productcode",
        "cs_employees": "employeenumber",
    }

    total_ok = total_rech = 0
    with DW.connect() as con:
        tablas = [r[0] for r in con.execute(sa.text(
            "SELECT DISTINCT tabla_origen FROM staging_dw.stg_extract "
            "WHERE run_id = :r ORDER BY 1"), {"r": run_id})]

    for tabla in tablas:
        with DW.connect() as con:
            filas = con.execute(sa.text(
                "SELECT fuente, nro_fila, payload FROM staging_dw.stg_extract "
                "WHERE run_id = :r AND tabla_origen = :t ORDER BY nro_fila"),
                {"r": run_id, "t": tabla}).fetchall()

        llave = LLAVES.get(tabla)
        registros = []
        rechazadas = 0
        for fuente, nro, payload in filas:
            estado, clase, regla, notas = "OK", "NINGUNA", None, None

            # --- Calidad TECNICA: llave primaria presente ---
            if llave and payload.get(llave) is None:
                estado, clase = "RECHAZADO", "TECNICA"
                regla = f"{tabla}_llave_primaria_no_nula"
                notas = f"La llave {llave} vino nula; la fila no es referenciable."
                rechazadas += 1

            registros.append({
                "run_id": run_id, "fuente": fuente, "tabla_origen": tabla,
                "nro_fila": nro, "payload": payload,
                "clase_dq": clase, "dq_status": estado,
                "dq_regla": regla, "dq_notas": notas,
            })

        if registros:
            sql = sa.text("""
                INSERT INTO staging_dw.stg_dq
                    (run_id, fuente, tabla_origen, nro_fila, payload,
                     clase_dq, dq_status, dq_regla, dq_notas)
                VALUES (:run_id, :fuente, :tabla_origen, :nro_fila, :payload,
                        :clase_dq, :dq_status, :dq_regla, :dq_notas)
            """).bindparams(sa.bindparam("payload", type_=sa.JSON))
            with DW.begin() as con:
                con.execute(sql, registros)

        total_ok   += len(registros) - rechazadas
        total_rech += rechazadas

    print(f"    aceptadas  {total_ok:>5}")
    print(f"    rechazadas {total_rech:>5}")

    # --- Calidad de NEGOCIO: conformidad entre las dos fuentes ---
    cli_cm = leer_capa("stg_dq", run_id, tabla_origen="customers")
    cli_cs = leer_capa("stg_dq", run_id, tabla_origen="cs_customers")
    comunes = set(cli_cm["customerNumber"]) & set(cli_cs["customernumber"])
    calidad("cliente_conformidad_fuentes", len(cli_cm), len(cli_cm) - len(comunes),
            len(comunes) == len(cli_cm),
            f"clientes en ambas fuentes: {len(comunes)} de {len(cli_cm)} "
            f"-> dimension conformada")

    pro_cm = leer_capa("stg_dq", run_id, tabla_origen="products")
    pro_cs = leer_capa("stg_dq", run_id, tabla_origen="cs_products")
    comunes_p = set(pro_cm["productCode"]) & set(pro_cs["productcode"])
    calidad("producto_conformidad_fuentes", len(pro_cm), len(pro_cm) - len(comunes_p),
            len(comunes_p) == len(pro_cm),
            f"productos en ambas fuentes: {len(comunes_p)} de {len(pro_cm)} "
            f"-> dimension conformada")

    emp_cm = leer_capa("stg_dq", run_id, tabla_origen="employees")
    emp_cs = leer_capa("stg_dq", run_id, tabla_origen="cs_employees")
    colision = set(emp_cm["employeeNumber"]) & set(emp_cs["employeenumber"])
    calidad("empleado_conformidad_fuentes", len(emp_cm) + len(emp_cs),
            len(colision), True,
            f"empleados con llave compartida: {len(colision)} "
            f"-> llave compuesta (numero_empleado, sistema_origen)")

    return total_ok, total_rech


# ============================================================
# CAPA 3 - TRANSFORM                       (Clase 2, diapositiva 19)
# ============================================================

def transformar(run_id):
    """Joins, lookups y agregaciones sobre los datos que pasaron calidad."""
    print("\n[Capa 3/4] Transform                (dia. 19: joins, lookups, agregaciones)")

    def limpio(tabla):
        """Solo las filas que la capa de calidad acepto."""
        with DW.connect() as con:
            filas = con.execute(sa.text(
                "SELECT payload FROM staging_dw.stg_dq "
                "WHERE run_id = :r AND tabla_origen = :t AND dq_status = 'OK' "
                "ORDER BY nro_fila"), {"r": run_id, "t": tabla}).fetchall()
        return pd.DataFrame([f[0] for f in filas])

    # ---------- dim_tiempo: generada, no extraida ----------
    filas, d, fin = [], date(2003, 1, 1), date(2005, 12, 31)
    while d <= fin:
        filas.append({
            "tiempo_key": int(d.strftime("%Y%m%d")), "fecha": d.isoformat(),
            "anio": d.year, "trimestre": (d.month - 1) // 3 + 1, "mes": d.month,
            "nombre_mes": MESES[d.month - 1], "dia": d.day,
            "dia_semana": d.isoweekday(), "nombre_dia": DIAS[d.isoweekday() - 1],
            "es_fin_semana": d.isoweekday() >= 6, "anio_mes": d.strftime("%Y-%m"),
        })
        d += timedelta(days=1)
    escribir_capa("stg_transform", run_id, filas,
                  objetivo="dim_tiempo", operaciones="generacion")
    print(f"    dim_tiempo        {len(filas):>5}  generacion")

    # ---------- dim_estado_orden: agregacion ----------
    ordenes = limpio("orders")
    no_efectivos = {"Cancelled", "Disputed", "On Hold"}
    estados = [
        {"estado": e, "es_efectiva": e not in no_efectivos}
        for e in sorted(ordenes["status"].unique())
    ]
    escribir_capa("stg_transform", run_id, estados,
                  objetivo="dim_estado_orden", operaciones="agregacion (distinct)")
    calidad("estado_orden_no_efectivo", len(estados),
            sum(1 for e in estados if not e["es_efectiva"]), True,
            f"estados no efectivos: {sum(1 for e in estados if not e['es_efectiva'])} "
            f"de {len(estados)}")
    print(f"    dim_estado_orden  {len(estados):>5}  agregacion")

    # ---------- dim_oficina ----------
    ofi = limpio("offices").rename(columns={
        "officeCode": "codigo_oficina", "city": "ciudad", "country": "pais",
        "state": "region", "territory": "territorio"})
    ofi = ofi[["codigo_oficina", "ciudad", "pais", "region", "territorio"]]
    escribir_capa("stg_transform", run_id, _filas_json(ofi),
                  objetivo="dim_oficina", operaciones="proyeccion")
    print(f"    dim_oficina       {len(ofi):>5}  proyeccion")

    # ---------- dim_cliente: conformada (join entre fuentes) ----------
    cm = limpio("customers").rename(columns={
        "customerNumber": "numero_cliente", "customerName": "nombre_cliente",
        "contactFirstName": "contacto_nombre", "contactLastName": "contacto_apellido",
        "phone": "telefono", "city": "ciudad", "state": "estado_region",
        "postalCode": "codigo_postal", "country": "pais",
        "creditLimit": "limite_credito"})
    # addressLine2 esta vacia en el 81,97% de las filas: se consolida en
    # un solo atributo en vez de arrastrar una columna casi vacia.
    vacias = int(cm["addressLine2"].isna().sum())
    cm["direccion_completa"] = (
        cm["addressLine1"].fillna("")
        + cm["addressLine2"].fillna("").apply(lambda x: f", {x}" if x else "")
    ).str.strip(", ")
    calidad("cliente_direccion_linea2_nula", len(cm), vacias, True,
            f"addressLine2 nula en {vacias} de {len(cm)} -> consolidada")

    cs = limpio("cs_customers")
    cm["presente_en_ventas"]   = True
    cm["presente_en_servicio"] = cm["numero_cliente"].isin(cs["customernumber"])
    cm = cm[["numero_cliente", "nombre_cliente", "contacto_nombre",
             "contacto_apellido", "telefono", "direccion_completa", "ciudad",
             "estado_region", "codigo_postal", "pais", "limite_credito",
             "presente_en_ventas", "presente_en_servicio"]]
    escribir_capa("stg_transform", run_id, _filas_json(cm),
                  objetivo="dim_cliente", operaciones="join entre fuentes, consolidacion")
    print(f"    dim_cliente       {len(cm):>5}  join entre fuentes")

    # ---------- dim_producto: conformada (join con productlines) ----------
    pr = limpio("products")
    pl = limpio("productlines")
    # htmlDescription e image estan 100% vacias: no se traen.
    calidad("productline_columnas_vacias", 2, 2, True,
            "htmlDescription e image (100% nulas) excluidas")
    pr = pr.merge(pl, on="productLine", how="left").rename(columns={
        "productCode": "codigo_producto", "productName": "nombre_producto",
        "productLine": "linea_producto", "textDescription": "descripcion_linea",
        "productScale": "escala", "productVendor": "proveedor",
        "buyPrice": "precio_compra", "MSRP": "precio_msrp"})
    pcs = limpio("cs_products")
    pr["presente_en_ventas"]   = True
    pr["presente_en_servicio"] = pr["codigo_producto"].isin(pcs["productcode"])
    pr = pr[["codigo_producto", "nombre_producto", "linea_producto",
             "descripcion_linea", "escala", "proveedor", "precio_compra",
             "precio_msrp", "presente_en_ventas", "presente_en_servicio"]]
    escribir_capa("stg_transform", run_id, _filas_json(pr),
                  objetivo="dim_producto", operaciones="join con productlines, join entre fuentes")
    print(f"    dim_producto      {len(pr):>5}  join con productlines")

    # ---------- dim_empleado: no conformada (union) ----------
    ecm = limpio("employees").rename(columns={
        "employeeNumber": "numero_empleado", "firstName": "nombre",
        "lastName": "apellido", "jobTitle": "cargo", "officeCode": "numero_oficina"})
    ecm["sistema_origen"] = "classicmodels"
    ecm = ecm[["numero_empleado", "sistema_origen", "nombre", "apellido",
               "email", "cargo", "numero_oficina"]]

    ecs = limpio("cs_employees").rename(columns={
        "employeenumber": "numero_empleado", "firstname": "nombre",
        "lastname": "apellido"})
    ecs["sistema_origen"] = "customerservice"
    ecs["cargo"] = "Agente de Servicio al Cliente"
    ecs["numero_oficina"] = None
    ecs = ecs[["numero_empleado", "sistema_origen", "nombre", "apellido",
               "email", "cargo", "numero_oficina"]]

    emp = pd.concat([ecm, ecs], ignore_index=True)
    escribir_capa("stg_transform", run_id, _filas_json(emp),
                  objetivo="dim_empleado", operaciones="union de fuentes, llave compuesta")
    print(f"    dim_empleado      {len(emp):>5}  union de fuentes")


# ============================================================
# CAPA 4 - LOAD-READY PUBLISH y LOAD
# ============================================================

ORDEN_CARGA = ["dim_tiempo", "dim_estado_orden", "dim_oficina",
               "dim_cliente", "dim_producto", "dim_empleado"]


def publicar_y_cargar(run_id):
    """Copia Transform -> Load-Ready y de ahi a las tablas del almacen."""
    print("\n[Capa 4/4] Load-Ready Publish y Load")
    total = 0
    for objetivo in ORDEN_CARGA:
        df = leer_capa("stg_transform", run_id, objetivo=objetivo)
        if df.empty:
            continue

        # Load-Ready: forma definitiva, sin transformaciones pendientes.
        escribir_capa("stg_loadready", run_id, _filas_json(df), objetivo=objetivo)

        # Load: las tablas del almacen si se reemplazan; el historial
        # vive en staging, no en el destino.
        with DW.begin() as con:
            con.execute(sa.text(f"TRUNCATE TABLE {objetivo} RESTART IDENTITY CASCADE"))
        df.to_sql(objetivo, DW, if_exists="append", index=False)
        total += len(df)
        print(f"    {objetivo:<18}{len(df):>5} filas")
    return total


# ============================================================
# Registro en el repositorio de metadatos
# ============================================================

def registrar_en_metadatos(run_id, leidas, escritas, rechazadas, estado, error=None):
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
            "desc": "Carga las seis dimensiones aplicando las cuatro capas de "
                    "Giordano sobre tablas fisicas en staging_dw.",
        }).scalar()

        exec_id = con.execute(sa.text("""
            INSERT INTO etl_execution (etl_process_id, run_id, started_at,
                                       finished_at, status, rows_read,
                                       rows_written, rows_rejected, error_message)
            VALUES (:p, :r, now(), now(), :s, :lr, :lw, :rj, :e)
            RETURNING etl_execution_id
        """), {"p": proceso_id, "r": run_id, "s": estado, "lr": leidas,
               "lw": escritas, "rj": rechazadas, "e": error}).scalar()

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
    print(f"ETL de dimensiones - run_id={run_id}")
    print("Arquitectura de referencia: Giordano (2011), Cap. 2 - Clase 2")
    try:
        leidas = extraer(run_id)
        ok, rechazadas = calidad_datos(run_id)
        transformar(run_id)
        escritas = publicar_y_cargar(run_id)
    except Exception as e:
        cerrar_run(run_id, "ERROR")
        registrar_en_metadatos(run_id, 0, 0, 0, "ERROR", str(e)[:500])
        raise
    cerrar_run(run_id, "OK")
    registrar_en_metadatos(run_id, leidas, escritas, rechazadas, "OK")
    print(f"\nDimensiones cargadas. Leidas {leidas}, rechazadas {rechazadas}, "
          f"escritas {escritas}.")
