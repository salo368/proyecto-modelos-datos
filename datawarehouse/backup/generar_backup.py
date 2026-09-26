"""
Genera un backup SQL (esquema + datos) de una base PostgreSQL.

Por que no se usa pg_dump: la maquina de desarrollo tiene el binario de
PostgreSQL 15 y Railway corre PostgreSQL 18, asi que pg_dump aborta con
"no coincide la version del servidor". Este generador produce un archivo
equivalente y portable, leyendo el esquema por introspeccion.

Uso:
    python datawarehouse/backup/generar_backup.py dw
    python datawarehouse/backup/generar_backup.py metadata
"""
import os
import sys
from datetime import date

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

DESTINOS = {
    "dw": {
        "url_var": "DW_URL",
        "salida":  "datawarehouse/backup/dw_backup.sql",
        "titulo":  "Almacen de Datos (modelo dimensional)",
        "ddl":     "datawarehouse/ddl/01_dw_schema.sql",
        # Orden de carga: respeta las llaves foraneas.
        "orden": [
            "dim_tiempo", "dim_cliente", "dim_producto", "dim_empleado",
            "dim_oficina", "dim_estado_orden",
            "fact_ventas", "fact_llamadas_servicio",
        ],
    },
    "metadata": {
        "url_var": "METADATA_REPO_URL",
        "salida":  "metadata_repository/backup/metadata_repo_backup.sql",
        "titulo":  "Repositorio de Metadatos (Entregas 1 y 2)",
        "ddl":     None,   # se reconstruye por introspeccion
        # Orden de carga: respeta las llaves foraneas. Las cuatro
        # categorias de metadatos de la Clase 3 en secuencia:
        # tecnicos -> negocio -> almacen -> procesos -> calidad -> uso.
        "orden": [
            "data_source", "db_table", "db_column",
            "business_entity", "business_attribute", "column_business_mapping",
            "dw_object", "dw_measure", "dw_attribute", "dw_lineage",
            "etl_process", "etl_execution", "dq_rule", "dq_result",
            "usage_herramienta", "usage_consulta", "usage_consulta_objeto",
            "usage_acceso_objeto",
        ],
    },
}


def literal(v):
    """Convierte un valor de Python a literal SQL."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def ddl_por_introspeccion(insp, tablas):
    """Reconstruye CREATE TABLE leyendo el esquema real."""
    partes = []
    for t in tablas:
        cols = insp.get_columns(t, schema="public")
        pk = set(insp.get_pk_constraint(t, schema="public").get("constrained_columns") or [])
        lineas = []
        for c in cols:
            tipo = str(c["type"])
            # Las columnas SERIAL aparecen como INTEGER con un default nextval().
            default = c.get("default") or ""
            if "nextval" in str(default):
                tipo = "BIGSERIAL" if "BIGINT" in tipo.upper() else "SERIAL"
                default = ""
            linea = f"    {c['name']} {tipo}"
            if c["name"] in pk and len(pk) == 1:
                linea += " PRIMARY KEY"
            if not c.get("nullable", True) and c["name"] not in pk:
                linea += " NOT NULL"
            if default and "nextval" not in str(default):
                linea += f" DEFAULT {default}"
            lineas.append(linea)
        if len(pk) > 1:
            lineas.append(f"    PRIMARY KEY ({', '.join(sorted(pk))})")
        partes.append(f"CREATE TABLE {t} (\n" + ",\n".join(lineas) + "\n);\n")
    return "\n".join(partes)


def volcar_tabla(con, tabla):
    res = con.execute(sa.text(f"SELECT * FROM {tabla}"))
    filas = res.fetchall()
    cols = list(res.keys())
    if not filas:
        return f"-- {tabla}: sin filas\n\n"

    salida = [f"-- {tabla}: {len(filas)} filas\n"]
    # Se vuelca por lotes de 200 para que ningun INSERT quede gigantesco.
    for i in range(0, len(filas), 200):
        lote = filas[i:i + 200]
        valores = ",\n".join(
            "    (" + ", ".join(literal(v) for v in fila) + ")" for fila in lote
        )
        salida.append(
            f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES\n{valores};\n"
        )
    salida.append("\n")
    return "".join(salida)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in DESTINOS:
        raise SystemExit(f"Uso: python {sys.argv[0]} [{' | '.join(DESTINOS)}]")

    cfg = DESTINOS[sys.argv[1]]
    eng = sa.create_engine(os.getenv(cfg["url_var"]))
    insp = sa.inspect(eng)
    existentes = set(insp.get_table_names(schema="public"))
    tablas = [t for t in cfg["orden"] if t in existentes]

    # --- Encabezado ---
    partes = [
        "-- ============================================================\n",
        f"-- Backup: {cfg['titulo']}\n",
        "-- Proyecto: Modelos y Persistencia de Datos - Entrega 2\n",
        f"-- Generado: {date.today().isoformat()}\n",
        "--\n",
        "-- Motor: PostgreSQL 18 (Railway).\n",
        "-- Herramienta: script propio en Python con SQLAlchemy.\n",
        "-- No se uso pg_dump porque el binario local es de PostgreSQL 15 y\n",
        "-- aborta contra un servidor 18 por incompatibilidad de version.\n",
        "--\n",
        "-- Restaurar sobre una base vacia con:\n",
        f"--   psql \"$URL\" -f {cfg['salida']}\n",
        "--\n",
        "-- Contenido:\n",
    ]
    with eng.connect() as con:
        for t in tablas:
            n = con.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar()
            partes.append(f"--   {t}: {n} filas\n")
    partes.append("-- ============================================================\n\n")

    # --- Esquema ---
    partes.append("-- Limpieza previa (idempotente)\n")
    for t in reversed(tablas):
        partes.append(f"DROP TABLE IF EXISTS {t} CASCADE;\n")
    partes.append("\n")

    if cfg["ddl"] and os.path.exists(cfg["ddl"]):
        # Para el almacen se reutiliza el DDL fuente, que lleva los
        # comentarios que explican cada decision de diseno.
        ddl = open(cfg["ddl"], encoding="utf-8").read()
        ddl = "\n".join(
            l for l in ddl.splitlines()
            if not l.strip().startswith("DROP ")
        )
        partes.append(ddl + "\n\n")
    else:
        partes.append(ddl_por_introspeccion(insp, tablas) + "\n")

    # --- Datos ---
    partes.append("-- ============================================================\n")
    partes.append("-- Datos\n")
    partes.append("-- ============================================================\n\n")
    with eng.connect() as con:
        for t in tablas:
            partes.append(volcar_tabla(con, t))

        # --- Secuencias ---
        partes.append("-- Sincronizacion de secuencias SERIAL\n")
        for t in tablas:
            for c in insp.get_columns(t, schema="public"):
                if "nextval" in str(c.get("default") or ""):
                    mx = con.execute(
                        sa.text(f"SELECT COALESCE(MAX({c['name']}), 0) FROM {t}")
                    ).scalar()
                    partes.append(
                        f"SELECT setval('{t}_{c['name']}_seq', {mx}, true);\n"
                    )

    destino = cfg["salida"]
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        f.write("".join(partes))

    kb = os.path.getsize(destino) / 1024
    print(f"{destino}  ({kb:.0f} KB, {len(tablas)} tablas)")


if __name__ == "__main__":
    main()
