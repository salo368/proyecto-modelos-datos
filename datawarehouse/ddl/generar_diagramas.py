"""
Genera los diagramas fisicos del almacen y del repositorio de metadatos
a partir del esquema REAL de las bases, no de un dibujo hecho a mano.

Produce dos salidas por cada base:

  .mmd  fuente Mermaid, que GitHub renderiza nativo dentro de un .md
  .dot  fuente Graphviz, para convertir a PNG con:
            docker run --rm -v "$PWD:/w" -w /w nshine/dot \
                dot -Tpng archivo.dot -o archivo.png

Uso:
    python datawarehouse/ddl/generar_diagramas.py
"""
import os
from pathlib import Path

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

SALIDA = Path("docs/Entrega_2/img")

# Colores por rol de tabla, para que el diagrama se lea de un vistazo.
COLOR_HECHO     = "#f7ecf1"
COLOR_DIM_CONF  = "#e9f2f0"
COLOR_DIM       = "#eef1f5"

CONFORMADAS = {"dim_cliente", "dim_producto", "dim_tiempo"}


def introspeccion(url, schema="public"):
    """Devuelve {tabla: {'cols': [(nombre, tipo, es_pk)], 'fks': [(col, tabla_ref)]}}."""
    insp = sa.inspect(sa.create_engine(url))
    modelo = {}
    for tabla in sorted(insp.get_table_names(schema=schema)):
        pk = set(insp.get_pk_constraint(tabla, schema=schema).get("constrained_columns") or [])
        cols = [
            (c["name"], str(c["type"]), c["name"] in pk)
            for c in insp.get_columns(tabla, schema=schema)
        ]
        fks = [
            (fk["constrained_columns"][0], fk["referred_table"])
            for fk in insp.get_foreign_keys(tabla, schema=schema)
            if fk.get("constrained_columns") and fk.get("referred_table")
        ]
        modelo[tabla] = {"cols": cols, "fks": fks}
    return modelo


def tipo_corto(t):
    """Acorta los tipos para que el diagrama no quede ilegible."""
    t = t.upper()
    for largo, corto in [
        ("CHARACTER VARYING", "VARCHAR"), ("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP"),
        ("DOUBLE PRECISION", "FLOAT"), ("NUMERIC", "NUMERIC"),
    ]:
        t = t.replace(largo, corto)
    return t.split("(")[0][:12]


def a_mermaid(modelo):
    lineas = ["erDiagram"]
    for tabla, d in modelo.items():
        lineas.append(f"    {tabla} {{")
        for nombre, tipo, es_pk in d["cols"]:
            marca = " PK" if es_pk else ""
            lineas.append(f"        {tipo_corto(tipo)} {nombre}{marca}")
        lineas.append("    }")
    for tabla, d in modelo.items():
        for col, ref in d["fks"]:
            lineas.append(f"    {ref} ||--o{{ {tabla} : \"{col}\"")
    return "\n".join(lineas)


def a_dot(modelo, titulo):
    def color(t):
        if t.startswith("fact_"):
            return COLOR_HECHO
        if t in CONFORMADAS:
            return COLOR_DIM_CONF
        return COLOR_DIM

    out = [
        "digraph modelo {",
        '    graph [rankdir=LR, splines=ortho, nodesep=0.6, ranksep=1.4,'
        f'    label="{titulo}", labelloc=t, fontname="Helvetica", fontsize=16];',
        '    node  [shape=plaintext, fontname="Helvetica", fontsize=10];',
        '    edge  [color="#5d6b7d", arrowsize=0.7];',
    ]
    for tabla, d in modelo.items():
        filas = "".join(
            f'<TR><TD ALIGN="LEFT">{"<B>" if pk else ""}{n}{"</B>" if pk else ""}'
            f'</TD><TD ALIGN="LEFT"><FONT POINT-SIZE="8">{tipo_corto(t)}</FONT></TD></TR>'
            for n, t, pk in d["cols"]
        )
        out.append(
            f'    {tabla} [label=<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0">'
            f'<TR><TD COLSPAN="2" BGCOLOR="{color(tabla)}"><B>{tabla}</B></TD></TR>'
            f"{filas}</TABLE>>];"
        )
    for tabla, d in modelo.items():
        for col, ref in d["fks"]:
            out.append(f"    {ref} -> {tabla};")
    out.append("}")
    return "\n".join(out)


def generar(url, nombre, titulo):
    modelo = introspeccion(url)
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / f"{nombre}.mmd").write_text(a_mermaid(modelo), encoding="utf-8")
    (SALIDA / f"{nombre}.dot").write_text(a_dot(modelo, titulo), encoding="utf-8")
    total_cols = sum(len(d["cols"]) for d in modelo.values())
    total_fks  = sum(len(d["fks"])  for d in modelo.values())
    print(f"  {nombre}: {len(modelo)} tablas, {total_cols} columnas, {total_fks} FKs")
    print(f"    -> {SALIDA / f'{nombre}.mmd'}")
    print(f"    -> {SALIDA / f'{nombre}.dot'}")


def diagrama_pipeline():
    """Diagrama del pipeline con los conteos REALES de la ultima carga.

    Reproduce la forma del diagrama de Giordano de la Clase 2 (dia. 14):
    siete columnas, una pila por fuente en Initial Staging, dos pilas
    (limpios y rechazados) en Clean Staging, y la bifurcacion final en
    dimensiones y hechos. Cada caja lleva el numero de filas que paso por
    ella, leido de staging_dw, asi que el dibujo no puede contradecir lo
    que el pipeline hizo.
    """
    dw = sa.create_engine(os.getenv("DW_URL"))
    with dw.connect() as c:
        def n(sql):
            return c.execute(sa.text(sql)).scalar() or 0

        rs = n("SELECT MAX(run_id) FROM staging_dw.etl_run "
               "WHERE proceso='staging' AND estado='OK'")
        rd = n("SELECT MAX(run_id) FROM staging_dw.etl_run "
               "WHERE proceso='dimensiones' AND estado='OK'")
        rh = n("SELECT MAX(run_id) FROM staging_dw.etl_run "
               "WHERE proceso='hechos' AND estado='OK'")
        ini_cm = n(f"SELECT COUNT(*) FROM staging_dw.stg_initial_classicmodels WHERE run_id={rs}")
        ini_cs = n(f"SELECT COUNT(*) FROM staging_dw.stg_initial_customerservice WHERE run_id={rs}")
        tab_cm = n(f"SELECT COUNT(DISTINCT tabla_origen) FROM staging_dw.stg_initial_classicmodels WHERE run_id={rs}")
        tab_cs = n(f"SELECT COUNT(DISTINCT tabla_origen) FROM staging_dw.stg_initial_customerservice WHERE run_id={rs}")
        perfil = n(f"SELECT COUNT(*) FROM staging_dw.stg_perfil WHERE run_id={rs}")
        err    = n(f"SELECT COUNT(*) FROM staging_dw.stg_error_log WHERE run_id={rs}")
        adv    = n(f"SELECT COUNT(*) FROM staging_dw.stg_error_log WHERE run_id={rs} AND accion='ADVERTENCIA'")
        limp   = n(f"SELECT COUNT(*) FROM staging_dw.stg_clean WHERE run_id={rs}")
        rech   = n(f"SELECT COUNT(*) FROM staging_dw.stg_rejected WHERE run_id={rs}")
        tr_d   = n(f"SELECT COUNT(*) FROM staging_dw.stg_transform WHERE run_id={rd}")
        tr_h   = n(f"SELECT COUNT(*) FROM staging_dw.stg_transform WHERE run_id={rh}")
        lr_d   = n(f"SELECT COUNT(*) FROM staging_dw.stg_loadready WHERE run_id={rd}")
        lr_h   = n(f"SELECT COUNT(*) FROM staging_dw.stg_loadready WHERE run_id={rh}")
        dims   = n("SELECT (SELECT COUNT(*) FROM dim_tiempo)+(SELECT COUNT(*) FROM dim_cliente)"
                   "+(SELECT COUNT(*) FROM dim_producto)+(SELECT COUNT(*) FROM dim_empleado)"
                   "+(SELECT COUNT(*) FROM dim_oficina)+(SELECT COUNT(*) FROM dim_estado_orden)")
        hechos = n("SELECT (SELECT COUNT(*) FROM fact_ventas)+(SELECT COUNT(*) FROM fact_llamadas_servicio)")
        dm1    = n("SELECT COUNT(*) FROM dm.vw_interaccion_cliente_producto")
        dm2    = n("SELECT COUNT(*) FROM dm.vw_ventas_mensuales_linea")

    def nodo(nombre, titulo, detalle, color, forma="box3d"):
        return (f'  {nombre} [shape={forma}, style="filled", fillcolor="{color}", '
                f'label=<<B>{titulo}</B><BR/><FONT POINT-SIZE="9">{detalle}</FONT>>];')

    G, AZ, VE, RO, AM, MO = "#e8ecf1", "#dbe8f5", "#e2f0e4", "#f6d4d4", "#fbeccd", "#ece3f3"
    lineas = [
        "digraph pipeline {",
        '  graph [rankdir=LR, nodesep=0.35, ranksep=0.55, fontname="Helvetica", '
        'label="Pipeline ETL - arquitectura de Giordano (Clase 2, dia. 14) con los '
        f'conteos reales de la ultima carga (staging run {rs})", labelloc=t, fontsize=14];',
        '  node [fontname="Helvetica", fontsize=11];',
        '  edge [color="#5d6b7d", arrowsize=0.7];',
        "",
        '  subgraph cluster_1 { label="1  Extract/Publish"; style=dashed; color="#8a96a3";',
        nodo("ext_cm", "Modelo extraccion", "classicmodels (MySQL)", G, "box"),
        nodo("ext_cs", "Modelo extraccion", "customerservice (PostgreSQL)", G, "box"),
        "  }",
        '  subgraph cluster_2 { label="2  Initial Staging"; style=dashed; color="#8a96a3";',
        nodo("ini_cm", "stg_initial_classicmodels", f"{tab_cm} tablas, {ini_cm} filas", AZ),
        nodo("ini_cs", "stg_initial_customerservice", f"{tab_cs} tablas, {ini_cs} filas", VE),
        nodo("perfil", "stg_perfil", f"{perfil} columnas perfiladas", G, "note"),
        "  }",
        '  subgraph cluster_3 { label="3  Data Quality"; style=dashed; color="#8a96a3";',
        nodo("dq", "Tech DQ + Bus DQ", "11 reglas por registro", AM, "box"),
        nodo("errlog", "stg_error_log", f"{err} entradas ({adv} advertencias)", AM, "note"),
        "  }",
        '  subgraph cluster_4 { label="4  Clean Staging"; style=dashed; color="#8a96a3";',
        nodo("clean", "stg_clean", f"{limp} filas limpias", G),
        nodo("rej", "stg_rejected", f"{rech} filas rechazadas", RO),
        "  }",
        '  subgraph cluster_5 { label="5  Transformation"; style=dashed; color="#8a96a3";',
        nodo("tr_d", "Conformar dimensiones", f"6 areas, {tr_d} filas", G, "box"),
        nodo("tr_h", "Conformar hechos", f"Ventas y Servicio, {tr_h} filas", G, "box"),
        "  }",
        '  subgraph cluster_6 { label="6  Load-Ready Publish"; style=dashed; color="#8a96a3";',
        nodo("lr_d", "stg_loadready", f"DIMENSIONES, {lr_d} filas", G),
        nodo("lr_h", "stg_loadready", f"HECHOS, {lr_h} filas", G),
        "  }",
        '  subgraph cluster_7 { label="7  Load (EDW)"; style=dashed; color="#8a96a3";',
        nodo("dims", "dim_*", f"6 dimensiones, {dims} filas", VE, "cylinder"),
        nodo("facts", "fact_*", f"2 hechos, {hechos} filas", AZ, "cylinder"),
        "  }",
        '  subgraph cluster_8 { label="Data Marts (Clase 4-5)"; style=dashed; color="#8a96a3";',
        nodo("dm1", "dm.vw_interaccion_cliente_producto", f"{dm1} filas", MO, "cylinder"),
        nodo("dm2", "dm.vw_ventas_mensuales_linea", f"{dm2} filas", MO, "cylinder"),
        "  }",
        "",
        "  ext_cm -> ini_cm; ext_cs -> ini_cs;",
        "  ini_cm -> perfil [style=dotted]; ini_cs -> perfil [style=dotted];",
        "  ini_cm -> dq; ini_cs -> dq;",
        "  dq -> errlog [style=dotted];",
        "  dq -> clean; dq -> rej [color=\"#c0392b\"];",
        "  clean -> tr_d; clean -> tr_h;",
        "  tr_d -> lr_d; tr_h -> lr_h;",
        "  lr_d -> dims; lr_h -> facts;",
        "  dims -> tr_h [style=dashed, label=\"lookup\", fontsize=9];",
        "  facts -> dm1; dims -> dm1; facts -> dm2; dims -> dm2;",
        "}",
    ]
    SALIDA.mkdir(parents=True, exist_ok=True)
    ruta = SALIDA / "pipeline_capas.dot"
    ruta.write_text("\n".join(lineas), encoding="utf-8")
    print(f"  pipeline_capas: staging run {rs}, {limp} limpias, {rech} rechazadas")
    print(f"    -> {ruta}")


if __name__ == "__main__":
    print("Generando diagramas desde el esquema real...")
    generar(os.getenv("DW_URL"), "dw_modelo_dimensional",
            "Almacen de Datos - Modelo Dimensional (Entrega 2)")
    generar(os.getenv("METADATA_REPO_URL"), "repositorio_metadatos",
            "Repositorio de Metadatos - Entregas 1 y 2")
    diagrama_pipeline()
    print()
    print("Para convertir a PNG con Docker (no requiere instalar Graphviz):")
    print('  docker run --rm -v "$PWD/docs/Entrega_2/img:/w" -w /w nshine/dot \\')
    print("      dot -Tpng pipeline_capas.dot -o pipeline_capas.png")
