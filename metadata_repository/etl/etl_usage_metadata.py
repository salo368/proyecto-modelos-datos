"""
Usage metadata of the data warehouse.

1. Declares the tools that access the warehouse and the known queries,
   with their expected frequency, number of joins and the objects they
   read (usage_herramienta, usage_consulta, usage_consulta_objeto).
2. Measures real access by copying the engine counters from
   pg_stat_user_tables into usage_acceso_objeto.

Run after etl_dw_metadata.py (it needs dw_object).

Usage:
    python metadata_repository/etl/etl_usage_metadata.py
"""
import os

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

DW = sa.create_engine(os.getenv("DW_URL"))
META = sa.create_engine(os.getenv("METADATA_URL"))

# (name, type, purpose, access)
TOOLS = [
    ("Metabase", "BI",
     "Construye y sirve los seis reportes del dashboard. Es el unico "
     "consumidor de cara al usuario final.", "LECTURA"),
    ("ETL Python (staging, dimensiones y hechos)", "ETL",
     "Carga el almacen desde las capas de staging. Unico proceso con "
     "permiso de escritura sobre las tablas del modelo dimensional.", "ESCRITURA"),
    ("Scripts de validacion y backup", "CLIENTE_SQL",
     "Comparan totales contra las fuentes y generan los respaldos. "
     "Acceso de solo lectura, bajo demanda.", "LECTURA"),
]

# (name, tool, purpose, frequency, number of joins, objects read)
QUERIES = [
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
     "Conciliacion del almacen con las fuentes: nueve verificaciones de que "
     "cada registro de las fuentes esta cargado o fue rechazado.",
     "BAJO_DEMANDA", 8,
     ["fact_ventas", "fact_llamadas_servicio", "dim_cliente", "dim_producto",
      "dim_oficina", "dim_empleado", "dim_lote_carga"]),

    ("Carga de dimensiones y hechos", "ETL Python (staging, dimensiones y hechos)",
     "Escritura de las ocho tablas del modelo dimensional y del registro de "
     "cada carga en la dimension de auditoria, desde staging.",
     "BAJO_DEMANDA", 0,
     ["dim_tiempo", "dim_cliente", "dim_producto", "dim_empleado",
      "dim_oficina", "dim_estado_orden", "fact_ventas",
      "fact_llamadas_servicio", "dim_lote_carga"]),
]


def dw_object_ids(con):
    return {
        r.object_name: r.dw_object_id
        for r in con.execute(sa.text("SELECT object_name, dw_object_id FROM dw_object"))
    }


def declare(con):
    """Rebuild tools, queries and the query -> object relation."""
    con.execute(sa.text("DELETE FROM usage_consulta_objeto"))
    con.execute(sa.text("DELETE FROM usage_consulta"))
    con.execute(sa.text("DELETE FROM usage_herramienta"))

    tool_ids = {}
    for name, tool_type, purpose, access in TOOLS:
        tool_ids[name] = con.execute(sa.text("""
            INSERT INTO usage_herramienta (nombre, tipo, proposito, acceso)
            VALUES (:n, :t, :p, :a) RETURNING usage_herramienta_id
        """), {"n": name, "t": tool_type, "p": purpose, "a": access}).scalar()

    objects = dw_object_ids(con)
    uncatalogued = []
    for name, tool, purpose, frequency, joins, reads in QUERIES:
        query_id = con.execute(sa.text("""
            INSERT INTO usage_consulta (nombre, usage_herramienta_id, proposito,
                                        frecuencia, nro_joins)
            VALUES (:n, :h, :p, :f, :j) RETURNING usage_consulta_id
        """), {"n": name, "h": tool_ids[tool], "p": purpose,
               "f": frequency, "j": joins}).scalar()

        for obj in reads:
            if obj not in objects:
                uncatalogued.append(obj)
                continue
            con.execute(sa.text("""
                INSERT INTO usage_consulta_objeto (usage_consulta_id, dw_object_id)
                VALUES (:c, :o) ON CONFLICT DO NOTHING
            """), {"c": query_id, "o": objects[obj]})

    return len(tool_ids), len(QUERIES), sorted(set(uncatalogued))


def measure(con):
    """Store the current pg_stat_user_tables counters of the warehouse.

    The counters are cumulative since the last statistics reset.
    """
    with DW.connect() as d:
        stats = d.execute(sa.text("""
            SELECT relname,
                   seq_scan, seq_tup_read, idx_scan,
                   n_tup_ins, n_tup_upd, n_tup_del
            FROM pg_stat_user_tables
            WHERE schemaname = 'public'
        """)).fetchall()

    objects = dw_object_ids(con)
    con.execute(sa.text("DELETE FROM usage_acceso_objeto"))
    measured = 0
    for s in stats:
        if s.relname not in objects:
            continue
        con.execute(sa.text("""
            INSERT INTO usage_acceso_objeto
                (dw_object_id, lecturas_secuenciales, filas_leidas_secuencial,
                 lecturas_por_indice, filas_insertadas, filas_actualizadas,
                 filas_borradas)
            VALUES (:o, :ss, :sr, :is_, :ins, :upd, :del)
        """), {"o": objects[s.relname], "ss": s.seq_scan, "sr": s.seq_tup_read,
               "is_": s.idx_scan, "ins": s.n_tup_ins, "upd": s.n_tup_upd,
               "del": s.n_tup_del})
        measured += 1
    return measured


if __name__ == "__main__":
    with META.begin() as con:
        n_tools, n_queries, missing = declare(con)
        n_measured = measure(con)

    print("Usage metadata registered:")
    print(f"  usage_herramienta   : {n_tools} tools")
    print(f"  usage_consulta      : {n_queries} declared queries")
    print(f"  usage_acceso_objeto : {n_measured} objects with measured access")
    if missing:
        print(f"  WARNING: queries reference objects missing from dw_object: {missing}")
        print("           Run metadata_repository/etl/etl_dw_metadata.py first.")
