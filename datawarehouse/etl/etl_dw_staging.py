"""
ETL de staging - capas 1 a 4 de la arquitectura de Giordano.

Es la mitad frontal del diagrama de la Clase 2 (diapositivas 14 a 19),
la que comparten las cargas de dimensiones y de hechos:

    1 Extract/Publish   un modelo logico de extraccion por fuente   dia. 15
    2 Initial Staging   una tabla por fuente + perfilamiento        dia. 16
    3 Data Quality      Tech DQ + Bus DQ + Error Handling           dia. 17
    4 Clean Staging     pila de limpios y pila de rechazados        dia. 18

Despues de este proceso las fuentes NO se vuelven a leer en la carga.
Dimensiones y hechos consumen solo lo que quedo en Clean Staging.

Principios de la Clase 2 que este proceso implementa:

  Read once, write many (dia. 15)  cada tabla fuente se lee una vez.
  Traer todo (dia. 15)              se extraen las 13 tablas, incluso las
                                    que el modelo actual no usa (payments,
                                    cs_customer_products): el modelo puede
                                    crecer sin volver a tocar la fuente.
  Almacenamiento no volatil (16)    nada se trunca; todo queda por run_id.
  Perfilamiento (16)                cada carga perfila lo que aterrizo.

Uso:
    python datawarehouse/etl/etl_dw_staging.py
"""
from collections import defaultdict

import pandas as pd
import sqlalchemy as sa

from staging_comun import (DW, META, MYSQL, PG, abrir_run, cerrar_run,
                           filas_json, insertar, registrar_ejecucion)

PROCESO = "etl_dw_staging"

# ============================================================
# CAPA 1 - EXTRACT/PUBLISH: modelos logicos de extraccion
#
# El diagrama dibuja un "Logical Extract Model" por cada fuente. Aqui
# cada modelo declara que tablas se leen y con que consulta. "Traer
# todo" (dia. 15): se leen todas las tablas de cada fuente.
# ============================================================
MODELOS_EXTRACCION = {
    "classicmodels": {
        "motor": MYSQL,
        "initial": "stg_initial_classicmodels",
        "tablas": ["customers", "employees", "offices", "products",
                   "productlines", "orders", "orderdetails", "payments"],
    },
    "customerservice": {
        "motor": PG,
        "initial": "stg_initial_customerservice",
        "tablas": ["cs_customers", "cs_products", "cs_employees",
                   "cs_customer_calls", "cs_customer_products"],
    },
}

# Llave con la que cada registro se identifica en el reporte de errores.
# cs_customer_calls no tiene llave primaria en su fuente: se identifica
# por la combinacion de sus referencias y la fecha.
LLAVES = {
    "customers": ["customerNumber"], "employees": ["employeeNumber"],
    "offices": ["officeCode"], "products": ["productCode"],
    "productlines": ["productLine"], "orders": ["orderNumber"],
    "orderdetails": ["orderNumber", "productCode"],
    "payments": ["customerNumber", "checkNumber"],
    "cs_customers": ["customernumber"], "cs_products": ["productcode"],
    "cs_employees": ["employeenumber"],
    "cs_customer_calls": ["customernumber", "productcode", "employeenumber", "date"],
    "cs_customer_products": ["customernumber", "productcode"],
}

# ============================================================
# Reglas de calidad (capa 3)
#
# clase:     TECNICA o NEGOCIO, como las divide la diapositiva 17.
# categoria: las del reporte de "Bad Transactions" del diagrama.
# accion:    RECHAZADO manda el registro a la pila roja; ADVERTENCIA
#            lo deja pasar pero lo traza.
#
# Los nombres coinciden con dq_rule del repositorio de metadatos.
# ============================================================
REGLAS = {
    # --- Tech DQ Checks ---
    "campos_obligatorios":    ("TECNICA", "CAMPO_FALTANTE",   "RECHAZADO"),
    "tipo_de_dato_valido":    ("TECNICA", "DATO_INVALIDO",    "RECHAZADO"),
    "formato_email":          ("TECNICA", "DATO_INVALIDO",    "ADVERTENCIA"),
    # --- Bus DQ Check ---
    "integridad_referencial": ("NEGOCIO", "INTEGRIDAD_REFERENCIAL", "RECHAZADO"),
    "valores_positivos":      ("NEGOCIO", "DATO_INEXACTO",    "RECHAZADO"),
    "secuencia_de_fechas":    ("NEGOCIO", "DATO_INEXACTO",    "RECHAZADO"),
    "envio_consistente_con_estado": ("NEGOCIO", "DATO_INEXACTO", "RECHAZADO"),
    "precio_sugerido_coherente":    ("NEGOCIO", "DATO_INEXACTO", "ADVERTENCIA"),
    "cliente_con_vendedor":   ("NEGOCIO", "CAMPO_FALTANTE",   "ADVERTENCIA"),
    "consistencia_entre_fuentes_cliente":
                              ("NEGOCIO", "DEFINICION_INCONSISTENTE", "ADVERTENCIA"),
    "consistencia_entre_fuentes_producto":
                              ("NEGOCIO", "DEFINICION_INCONSISTENTE", "ADVERTENCIA"),
}

COLUMNAS_FECHA = {
    "orders": ["orderDate", "requiredDate", "shippedDate"],
    "payments": ["paymentDate"],
    "cs_customer_calls": ["date"],
}
COLUMNAS_NUMERO = {
    "orderdetails": ["quantityOrdered", "priceEach", "orderLineNumber"],
    "products": ["quantityInStock", "buyPrice", "MSRP"],
    "customers": ["creditLimit"],
    "payments": ["amount"],
}


# ============================================================
# CAPAS 1 y 2 - EXTRACT y INITIAL STAGING
# ============================================================

def extraer(run_id):
    print("\n[Capa 1] Extract/Publish            (dia. 15: read once, traer todo)")
    print("[Capa 2] Initial Staging            (dia. 16: una tabla por fuente)")
    total = 0
    for fuente, modelo in MODELOS_EXTRACCION.items():
        print(f"    Modelo de extraccion: {fuente}  ->  staging_dw.{modelo['initial']}")
        for tabla in modelo["tablas"]:
            df = pd.read_sql(f"SELECT * FROM {tabla}", modelo["motor"])
            insertar(modelo["initial"], [
                {"run_id": run_id, "tabla_origen": tabla,
                 "nro_fila": i, "payload": p}
                for i, p in enumerate(filas_json(df), 1)
            ])
            total += len(df)
            print(f"      {tabla:<22}{len(df):>6} filas")
    print(f"    {'TOTAL en Initial Staging':<28}{total:>6} filas")
    return total


def leer_initial(run_id):
    """Relee lo que aterrizo. Las capas siguientes parten de aqui, no de
    la fuente: el limite entre capas es fisico, no una variable en memoria."""
    datos = {}
    for fuente, modelo in MODELOS_EXTRACCION.items():
        with DW.connect() as con:
            filas = con.execute(sa.text(
                f"SELECT tabla_origen, nro_fila, payload "
                f"FROM staging_dw.{modelo['initial']} "
                f"WHERE run_id = :r ORDER BY tabla_origen, nro_fila"),
                {"r": run_id}).fetchall()
        porTabla = defaultdict(list)
        for tabla, nro, payload in filas:
            porTabla[tabla].append({"_nro_fila": nro, **payload})
        for tabla, registros in porTabla.items():
            datos[tabla] = (fuente, pd.DataFrame(registros))
    return datos


def perfilar(run_id, datos):
    """Perfilamiento de lo que aterrizo (dia. 16)."""
    print("\n    Perfilamiento de Initial Staging  (dia. 16)")
    registros = []
    for tabla, (fuente, df) in datos.items():
        for col in df.columns:
            if col == "_nro_fila":
                continue
            s = df[col]
            no_nulos = s.dropna()
            try:
                minimo = str(no_nulos.min()) if len(no_nulos) else None
                maximo = str(no_nulos.max()) if len(no_nulos) else None
            except TypeError:           # columnas con tipos mezclados
                minimo = maximo = None
            registros.append({
                "run_id": run_id, "fuente": fuente, "tabla_origen": tabla,
                "columna": col, "filas": len(s), "nulos": int(s.isna().sum()),
                # float() nativo: con numpy 2, psycopg2 recibiria la
                # representacion "np.float64(0.0)" y la base la rechaza.
                "pct_nulos": float(round(100 * s.isna().mean(), 2)) if len(s) else 0.0,
                "distintos": int(s.nunique()),
                "minimo": (minimo or "")[:200] or None,
                "maximo": (maximo or "")[:200] or None,
            })
    insertar("stg_perfil", registros)
    con_nulos = sum(1 for r in registros if r["nulos"] > 0)
    print(f"      {len(registros)} columnas perfiladas, {con_nulos} con nulos")


# ============================================================
# CAPA 3 - DATA QUALITY
# ============================================================

def campos_obligatorios():
    """Columnas NOT NULL de cada tabla, leidas del REPOSITORIO DE METADATOS.

    Es metadato tecnico de la Entrega 1 (db_column.is_nullable) usado
    para gobernar el proceso: la regla no esta escrita a mano en el ETL,
    la dicta el diccionario de la fuente catalogado en el repositorio.
    """
    with META.connect() as con:
        filas = con.execute(sa.text("""
            SELECT dt.table_name, dc.column_name
            FROM db_column dc JOIN db_table dt ON dc.table_id = dt.table_id
            WHERE dc.is_nullable = FALSE
        """)).fetchall()
    req = defaultdict(list)
    for tabla, col in filas:
        req[tabla].append(col)
    return req


class Evaluador:
    """Acumula las fallas que producen los chequeos de calidad."""

    def __init__(self):
        self.fallas = []                          # filas para stg_error_log
        self.evaluadas = defaultdict(int)         # regla -> filas revisadas
        self.fallidas = defaultdict(int)          # regla -> filas que fallaron

    def revisar(self, regla, n):
        self.evaluadas[regla] += n

    def fallar(self, regla, fuente, tabla, fila, detalle):
        clase, categoria, accion = REGLAS[regla]
        llave = "|".join(str(fila.get(k)) for k in LLAVES.get(tabla, []))
        self.fallas.append({
            "fuente": fuente, "tabla_origen": tabla,
            "nro_fila": int(fila["_nro_fila"]), "llave_registro": llave,
            "clase_dq": clase, "categoria": categoria, "regla": regla,
            "accion": accion, "detalle": detalle,
        })
        self.fallidas[regla] += 1


def tech_dq_checks(datos, ev):
    """Calidad TECNICA: datos faltantes y datos invalidos (dia. 17)."""
    obligatorios = campos_obligatorios()
    for tabla, (fuente, df) in datos.items():
        # Datos faltantes: columnas NOT NULL segun el repositorio.
        cols = [c for c in obligatorios.get(tabla, []) if c in df.columns]
        if cols:
            ev.revisar("campos_obligatorios", len(df))
            for _, fila in df.iterrows():
                faltan = [c for c in cols if pd.isna(fila[c])]
                if faltan:
                    ev.fallar("campos_obligatorios", fuente, tabla, fila,
                              f"Faltan campos obligatorios: {', '.join(faltan)}")

        # Datos invalidos: fechas y numeros que no se pueden interpretar.
        fechas = [c for c in COLUMNAS_FECHA.get(tabla, []) if c in df.columns]
        numeros = [c for c in COLUMNAS_NUMERO.get(tabla, []) if c in df.columns]
        if fechas or numeros:
            ev.revisar("tipo_de_dato_valido", len(df))
            invalido = pd.Series(False, index=df.index)
            motivo = pd.Series("", index=df.index)
            for c in fechas:
                conv = pd.to_datetime(df[c], errors="coerce")
                malo = df[c].notna() & conv.isna()
                invalido |= malo
                motivo[malo] += f"{c} no es una fecha; "
            for c in numeros:
                conv = pd.to_numeric(df[c], errors="coerce")
                malo = df[c].notna() & conv.isna()
                invalido |= malo
                motivo[malo] += f"{c} no es un numero; "
            for i in df.index[invalido]:
                ev.fallar("tipo_de_dato_valido", fuente, tabla, df.loc[i],
                          motivo[i].strip())

    # Formato de correo en los dos catalogos de empleados.
    for tabla in ("employees", "cs_employees"):
        if tabla in datos:
            fuente, df = datos[tabla]
            ev.revisar("formato_email", len(df))
            for _, fila in df.iterrows():
                e = fila.get("email")
                if isinstance(e, str) and ("@" not in e or "." not in e.split("@")[-1]):
                    ev.fallar("formato_email", fuente, tabla, fila,
                              f"Correo con formato invalido: {e}")


def bus_dq_check(datos, ev):
    """Calidad de NEGOCIO: definiciones inconsistentes, datos inexactos e
    integridad referencial (dia. 17 y reporte de 'Bad Transactions')."""

    def llaves(tabla, col):
        return set(datos[tabla][1][col].dropna()) if tabla in datos else set()

    # --- Integridad referencial: dentro de cada fuente y entre fuentes ---
    # (tabla hija, columna, tabla padre, columna padre, descripcion)
    referencias = [
        ("orderdetails", "orderNumber", "orders", "orderNumber", "orden inexistente"),
        ("orderdetails", "productCode", "products", "productCode", "producto inexistente"),
        ("orders", "customerNumber", "customers", "customerNumber", "cliente inexistente"),
        ("payments", "customerNumber", "customers", "customerNumber", "cliente inexistente"),
        ("customers", "salesRepEmployeeNumber", "employees", "employeeNumber", "vendedor inexistente"),
        ("employees", "officeCode", "offices", "officeCode", "oficina inexistente"),
        ("employees", "reportsTo", "employees", "employeeNumber", "jefe inexistente"),
        ("products", "productLine", "productlines", "productLine", "linea inexistente"),
        ("cs_customer_calls", "customernumber", "cs_customers", "customernumber", "cliente inexistente en customerservice"),
        ("cs_customer_calls", "productcode", "cs_products", "productcode", "producto inexistente en customerservice"),
        ("cs_customer_calls", "employeenumber", "cs_employees", "employeenumber", "agente inexistente"),
        ("cs_customer_products", "customernumber", "cs_customers", "customernumber", "cliente inexistente"),
        ("cs_customer_products", "productcode", "cs_products", "productcode", "producto inexistente"),
        # Entre fuentes: la dimension conformada se construye desde
        # classicmodels, asi que una llamada cuyo cliente o producto no
        # exista alli quedaria huerfana en fact_llamadas_servicio.
        ("cs_customer_calls", "customernumber", "customers", "customerNumber",
         "cliente sin equivalente en classicmodels (dimension conformada)"),
        ("cs_customer_calls", "productcode", "products", "productCode",
         "producto sin equivalente en classicmodels (dimension conformada)"),
    ]
    revisadas = set()
    for hija, col, padre, col_padre, desc in referencias:
        if hija not in datos or padre not in datos:
            continue
        fuente, df = datos[hija]
        validas = llaves(padre, col_padre)
        if hija not in revisadas:
            ev.revisar("integridad_referencial", len(df))
            revisadas.add(hija)
        for _, fila in df.iterrows():
            v = fila.get(col)
            if pd.notna(v) and v not in validas:
                ev.fallar("integridad_referencial", fuente, hija, fila,
                          f"{col}={v}: {desc}")

    # --- Datos inexactos: valores que deben ser positivos ---
    positivos = [("orderdetails", ["quantityOrdered", "priceEach"]),
                 ("products", ["buyPrice", "MSRP"]),
                 ("payments", ["amount"]),
                 ("customers", ["creditLimit"])]
    for tabla, cols in positivos:
        if tabla not in datos:
            continue
        fuente, df = datos[tabla]
        ev.revisar("valores_positivos", len(df))
        for _, fila in df.iterrows():
            malos = [c for c in cols
                     if pd.notna(fila.get(c)) and float(fila[c]) < (0 if c == "creditLimit" else 0.000001)]
            if malos:
                ev.fallar("valores_positivos", fuente, tabla, fila,
                          f"Valores no positivos: {', '.join(malos)}")

    # --- Datos inexactos: coherencia de fechas y estado en las ordenes ---
    if "orders" in datos:
        fuente, df = datos["orders"]
        pedido = pd.to_datetime(df["orderDate"], errors="coerce")
        requerida = pd.to_datetime(df["requiredDate"], errors="coerce")
        envio = pd.to_datetime(df["shippedDate"], errors="coerce")
        ev.revisar("secuencia_de_fechas", len(df))
        ev.revisar("envio_consistente_con_estado", len(df))
        for i in df.index:
            if pd.notna(envio[i]) and envio[i] < pedido[i]:
                ev.fallar("secuencia_de_fechas", fuente, "orders", df.loc[i],
                          "La fecha de envio es anterior a la del pedido")
            elif pd.notna(requerida[i]) and requerida[i] < pedido[i]:
                ev.fallar("secuencia_de_fechas", fuente, "orders", df.loc[i],
                          "La fecha requerida es anterior a la del pedido")
            if df.at[i, "status"] == "Shipped" and pd.isna(envio[i]):
                ev.fallar("envio_consistente_con_estado", fuente, "orders", df.loc[i],
                          "Orden marcada Shipped sin fecha de envio")

    # --- Datos inexactos: precio sugerido por debajo del costo ---
    if "products" in datos:
        fuente, df = datos["products"]
        ev.revisar("precio_sugerido_coherente", len(df))
        for _, fila in df.iterrows():
            if pd.notna(fila["MSRP"]) and pd.notna(fila["buyPrice"]) \
                    and float(fila["MSRP"]) < float(fila["buyPrice"]):
                ev.fallar("precio_sugerido_coherente", fuente, "products", fila,
                          f"MSRP {fila['MSRP']} menor al costo {fila['buyPrice']}")

    # --- Cliente sin representante de ventas asignado ---
    # El esquema de la fuente permite el nulo (tecnicamente valido), pero
    # la definicion de negocio espera que todo cliente tenga vendedor.
    # Es el ejemplo exacto de la diferencia entre calidad tecnica y de
    # negocio de la diapositiva 17.
    if "customers" in datos:
        fuente, df = datos["customers"]
        ev.revisar("cliente_con_vendedor", len(df))
        for _, fila in df.iterrows():
            if pd.isna(fila.get("salesRepEmployeeNumber")):
                ev.fallar("cliente_con_vendedor", fuente, "customers", fila,
                          "Cliente sin representante de ventas asignado")

    # --- Definiciones inconsistentes entre las dos fuentes ---
    def comparar(tabla_cs, tabla_cm, llave_cs, llave_cm, pares, regla):
        if tabla_cs not in datos or tabla_cm not in datos:
            return
        fuente, cs = datos[tabla_cs]
        cm = datos[tabla_cm][1].set_index(llave_cm)
        ev.revisar(regla, len(cs))
        norm = lambda v: None if pd.isna(v) else str(v).strip()
        for _, fila in cs.iterrows():
            k = fila[llave_cs]
            if k not in cm.index:
                continue                      # ya lo reporta integridad referencial
            ref = cm.loc[k]
            difieren = [c_cs for c_cs, c_cm in pares
                        if norm(fila.get(c_cs)) != norm(ref.get(c_cm))]
            if difieren:
                ev.fallar(regla, fuente, tabla_cs, fila,
                          f"Difiere de classicmodels en: {', '.join(difieren)}")

    comparar("cs_customers", "customers", "customernumber", "customerNumber",
             [("phone", "phone"), ("city", "city"), ("country", "country"),
              ("postalcode", "postalCode")],
             "consistencia_entre_fuentes_cliente")
    comparar("cs_products", "products", "productcode", "productCode",
             [("productname", "productName"), ("productscale", "productScale"),
              ("productvendor", "productVendor")],
             "consistencia_entre_fuentes_producto")


def calidad(run_id, datos):
    print("\n[Capa 3] Data Quality               (dia. 17: tecnica y de negocio)")
    ev = Evaluador()
    tech_dq_checks(datos, ev)
    bus_dq_check(datos, ev)

    # Error Handling: el reporte de "Bad Transactions" del diagrama.
    insertar("stg_error_log", [{"run_id": run_id, **f} for f in ev.fallas])

    print(f"    {'Regla':<38}{'Clase':<9}{'Accion':<13}{'Revisadas':>9}{'Fallas':>8}")
    for regla, (clase, _, accion) in REGLAS.items():
        print(f"    {regla:<38}{clase:<9}{accion:<13}"
              f"{ev.evaluadas[regla]:>9}{ev.fallidas[regla]:>8}")
    print(f"    Error Handling -> {len(ev.fallas)} entradas en el reporte "
          f"de transacciones malas")
    return ev


# ============================================================
# CAPA 4 - CLEAN STAGING
# ============================================================

def motivos_de_rechazo(ev):
    """{(tabla, nro_fila): [reglas]} de los registros que van a la pila roja.

    Solo las fallas con accion RECHAZADO sacan un registro del flujo; las
    ADVERTENCIAS quedan en el reporte pero el registro sigue como limpio.
    """
    motivos = defaultdict(list)
    for f in ev.fallas:
        if f["accion"] == "RECHAZADO":
            motivos[(f["tabla_origen"], f["nro_fila"])].append(f["regla"])
    return motivos


def separar(run_id, datos, ev):
    """Separa fisicamente limpios (pila gris) y rechazados (pila roja)."""
    print("\n[Capa 4] Clean Staging              (dia. 18: separar limpios y rechazados)")
    motivos = motivos_de_rechazo(ev)

    total_ok = total_rech = 0
    for tabla, (fuente, df) in datos.items():
        limpios, rechazados = [], []
        cuerpo = df.drop(columns=["_nro_fila"])
        for payload, nro in zip(filas_json(cuerpo), df["_nro_fila"]):
            clave = (tabla, int(nro))
            base = {"run_id": run_id, "fuente": fuente, "tabla_origen": tabla,
                    "nro_fila": int(nro), "payload": payload}
            if clave in motivos:
                rechazados.append({**base, "motivos": ", ".join(sorted(set(motivos[clave])))})
            else:
                limpios.append(base)
        insertar("stg_clean", limpios)
        insertar("stg_rejected", rechazados)
        total_ok += len(limpios)
        total_rech += len(rechazados)
        print(f"      {tabla:<22} limpios {len(limpios):>5}   rechazados {len(rechazados):>3}")
    print(f"    {'TOTAL':<22} limpios {total_ok:>5}   rechazados {total_rech:>3}")
    return total_ok, total_rech


if __name__ == "__main__":
    run_id = abrir_run("staging")
    print(f"ETL de staging - run_id={run_id}")
    print("Arquitectura de referencia: Giordano (2011), Cap. 2 - Clase 2, dia. 14-19")
    try:
        leidas = extraer(run_id)
        datos = leer_initial(run_id)
        perfilar(run_id, datos)
        ev = calidad(run_id, datos)
        limpios, rechazados = separar(run_id, datos, ev)
    except Exception as e:
        cerrar_run(run_id, "ERROR")
        registrar_ejecucion(PROCESO, "", "", run_id, 0, 0, 0, "ERROR", str(e)[:500])
        raise
    cerrar_run(run_id, "OK")
    registrar_ejecucion(
        PROCESO,
        "Capas 1 a 4 de Giordano: extrae las 13 tablas de las dos fuentes una "
        "sola vez, las perfila, evalua calidad tecnica y de negocio, y separa "
        "fisicamente limpios de rechazados.",
        "classicmodels (MySQL), customerservice (PostgreSQL)",
        run_id, leidas, limpios, rechazados, "OK",
        resultados_calidad=[(r, ev.evaluadas[r], ev.fallidas[r]) for r in REGLAS],
    )
    print(f"\nStaging listo. Leidas {leidas}, limpias {limpios}, rechazadas {rechazados}.")
