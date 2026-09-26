"""
Metadatos de Uso - Entrega 2.

Cierra la cuarta categoria de metadatos de la Clase 3
(Negocio | Tecnicos | Procesos | USO).

Hace dos cosas distintas:

  1. DECLARA que herramientas acceden al almacen y que consultas
     conocidas existen, con su frecuencia y cuantos joins hacen.
     Esto responde "Queries vs Tablas" y "Joins" de la diapositiva.

  2. MIDE el acceso real, leyendo pg_stat_user_tables del almacen.
     Esa es la parte que no se puede inventar: son los contadores que
     lleva el propio motor de base de datos. Responde "Monitoreo de
     uso" y "Patrones y frecuencias de acceso".

Correr DESPUES de:
    python metadata_repository/etl/etl_dw_metadata.py

Uso:
    python metadata_repository/etl/etl_uso_metadata.py
"""
import os

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

DW   = sa.create_engine(os.getenv("DW_URL"))
META = sa.create_engine(os.getenv("METADATA_REPO_URL"))


# ------------------------------------------------------------
# Herramientas que acceden al almacen
# ------------------------------------------------------------
HERRAMIENTAS = [
    ("Metabase", "BI",
     "Construye y sirve los seis reportes de la Entrega 2. Es el unico "
     "consumidor de cara al usuario final.", "LECTURA"),
    ("ETL Python (staging, dimensiones y hechos)", "ETL",
     "Carga el almacen desde las capas de staging. Unico proceso con "
     "permiso de escritura sobre las tablas del modelo dimensional.", "ESCRITURA"),
    ("Scripts de validacion y backup", "CLIENTE_SQL",
     "Comparan totales contra las fuentes y generan los respaldos. "
     "Acceso de solo lectura, bajo demanda.", "LECTURA"),
]

# ------------------------------------------------------------
# Consultas conocidas contra el almacen.
#
# nro_joins es metadato de uso real: la diapositiva de la Clase 3
# nombra "Joins" explicitamente, porque saber que una consulta cruza
# cinco tablas es lo que justifica un indice o una tabla agregada.
# ------------------------------------------------------------
CONSULTAS = [
    ("Ventas y margen por mes", "Metabase",
     "Evolucion mensual del monto vendido y el margen, solo ordenes efectivas.",
     "DIARIA", 3, ["fact_ventas", "dim_tiempo", "dim_estado_orden"]),

    ("Intensidad de servicio por producto", "Metabase",
     "Llamadas al centro de servicio por unidad vendida. Es el reporte que "
     "cruza las dos fuentes.",
     "DIARIA", 1, ["vw_interaccion_cliente_producto"]),

    ("Margen por linea de producto", "Metabase",
     "Monto y margen agrupados por familia de producto.",
     "DIARIA", 2, ["fact_ventas", "dim_producto"]),

    ("Clientes: compras frente a llamadas", "Metabase",
     "Dispersion de cada cliente entre lo que compra y lo que consulta.",
     "SEMANAL", 1, ["vw_interaccion_cliente_producto"]),

    ("Ventas por oficina", "Metabase",
     "Monto vendido segun la sede del representante asignado.",
     "SEMANAL", 2, ["fact_ventas", "dim_oficina"]),

    ("Carga del centro de servicio por agente", "Metabase",
     "Llamadas atendidas por agente. Verifica que la llave compuesta de "
     "dim_empleado separa bien las dos poblaciones.",
     "SEMANAL", 2, ["fact_llamadas_servicio", "dim_empleado"]),

    ("Validacion contra fuentes", "Scripts de validacion y backup",
     "Nueve comparaciones de totales entre el almacen y las fuentes.",
     "BAJO_DEMANDA", 8,
     ["fact_ventas", "fact_llamadas_servicio", "dim_cliente", "dim_producto",
      "dim_oficina", "dim_empleado"]),

    ("Carga de dimensiones y hechos", "ETL Python (staging, dimensiones y hechos)",
     "Escritura de las ocho tablas del modelo dimensional desde staging.",
     "BAJO_DEMANDA", 0,
     ["dim_tiempo", "dim_cliente", "dim_producto", "dim_empleado",
      "dim_oficina", "dim_estado_orden", "fact_ventas",
      "fact_llamadas_servicio"]),
]


def declarar(con):
    """Puebla herramientas, consultas y su relacion con los objetos."""
    con.execute(sa.text("DELETE FROM usage_consulta_objeto"))
    con.execute(sa.text("DELETE FROM usage_consulta"))
    con.execute(sa.text("DELETE FROM usage_herramienta"))

    ids_herr = {}
    for nombre, tipo, proposito, acceso in HERRAMIENTAS:
        ids_herr[nombre] = con.execute(sa.text("""
            INSERT INTO usage_herramienta (nombre, tipo, proposito, acceso)
            VALUES (:n, :t, :p, :a) RETURNING usage_herramienta_id
        """), {"n": nombre, "t": tipo, "p": proposito, "a": acceso}).scalar()

    objetos = {
        r.object_name: r.dw_object_id
        for r in con.execute(sa.text("SELECT object_name, dw_object_id FROM dw_object"))
    }

    sin_catalogar = []
    for nombre, herr, proposito, frecuencia, joins, toca in CONSULTAS:
        cid = con.execute(sa.text("""
            INSERT INTO usage_consulta (nombre, usage_herramienta_id, proposito,
                                        frecuencia, nro_joins)
            VALUES (:n, :h, :p, :f, :j) RETURNING usage_consulta_id
        """), {"n": nombre, "h": ids_herr[herr], "p": proposito,
               "f": frecuencia, "j": joins}).scalar()

        for obj in toca:
            if obj not in objetos:
                sin_catalogar.append(obj)
                continue
            con.execute(sa.text("""
                INSERT INTO usage_consulta_objeto (usage_consulta_id, dw_object_id)
                VALUES (:c, :o) ON CONFLICT DO NOTHING
            """), {"c": cid, "o": objetos[obj]})

    return len(ids_herr), len(CONSULTAS), sorted(set(sin_catalogar))


def medir(con):
    """Lee los contadores reales del motor y los guarda como medicion.

    pg_stat_user_tables acumula desde el ultimo reinicio de estadisticas.
    No es una estimacion: es lo que el motor efectivamente conto.
    """
    with DW.connect() as d:
        stats = d.execute(sa.text("""
            SELECT relname,
                   seq_scan, seq_tup_read, idx_scan,
                   n_tup_ins, n_tup_upd, n_tup_del
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
        """)).fetchall()

    objetos = {
        r.object_name: r.dw_object_id
        for r in con.execute(sa.text("SELECT object_name, dw_object_id FROM dw_object"))
    }

    con.execute(sa.text("DELETE FROM usage_acceso_objeto"))
    medidos = 0
    for s in stats:
        if s.relname not in objetos:
            continue
        con.execute(sa.text("""
            INSERT INTO usage_acceso_objeto
                (dw_object_id, lecturas_secuenciales, filas_leidas_secuencial,
                 lecturas_por_indice, filas_insertadas, filas_actualizadas,
                 filas_borradas)
            VALUES (:o, :ss, :sr, :is_, :ins, :upd, :del)
        """), {"o": objetos[s.relname], "ss": s.seq_scan, "sr": s.seq_tup_read,
               "is_": s.idx_scan, "ins": s.n_tup_ins, "upd": s.n_tup_upd,
               "del": s.n_tup_del})
        medidos += 1
    return medidos


if __name__ == "__main__":
    with META.begin() as con:
        n_herr, n_cons, huerfanos = declarar(con)
        n_med = medir(con)

    print("Metadatos de uso registrados (Clase 3, cuarta categoria):")
    print(f"  usage_herramienta     : {n_herr} herramientas")
    print(f"  usage_consulta        : {n_cons} consultas declaradas")
    print(f"  usage_acceso_objeto   : {n_med} objetos con acceso medido")
    if huerfanos:
        print(f"  AVISO: estas consultas referencian objetos que no estan en "
              f"dw_object: {huerfanos}")
        print(f"         Corre antes metadata_repository/etl/etl_dw_metadata.py")
