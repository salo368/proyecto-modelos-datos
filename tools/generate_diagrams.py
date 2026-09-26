"""
Generate the physical diagrams in docs/img from the live databases.

    classicmodels_erd          source 1 (MySQL)
    customerservice_erd        source 2 (PostgreSQL)
    metadata_repository_erd    metadata repository, all tables
    metadata_core_erd          metadata repository, core tables only
    dw_star_schema             data warehouse star schema
    etl_pipeline               ETL layers with the row counts of the last load

Each diagram is written as Graphviz source (.dot) and rendered to .png
with the local `dot` binary or, if it is not installed, with the
nshine/dot Docker image.

Usage:
    python tools/generate_diagrams.py
"""
import os
import shutil
import subprocess
from pathlib import Path

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "img"

FACT_COLOR = "#f7ecf1"
CONFORMED_COLOR = "#e9f2f0"
DEFAULT_COLOR = "#eef1f5"
CONFORMED_DIMENSIONS = {"dim_cliente", "dim_producto", "dim_tiempo"}

METADATA_CORE_TABLES = {"data_source", "db_table", "db_column", "business_entity",
                        "business_attribute", "column_business_mapping"}


def introspect(url, schema, only=None):
    """{table: {'cols': [(name, type, is_pk)], 'fks': [(column, referenced table)]}}"""
    insp = sa.inspect(sa.create_engine(url))
    model = {}
    for table in sorted(insp.get_table_names(schema=schema)):
        if only and table not in only:
            continue
        pk = set(insp.get_pk_constraint(table, schema=schema).get("constrained_columns") or [])
        cols = [(c["name"], str(c["type"]), c["name"] in pk)
                for c in insp.get_columns(table, schema=schema)]
        fks = [(fk["constrained_columns"][0], fk["referred_table"])
               for fk in insp.get_foreign_keys(table, schema=schema)
               if fk.get("constrained_columns") and fk.get("referred_table")]
        model[table] = {"cols": cols, "fks": fks}
    return model


def short_type(t):
    t = t.upper()
    for long, short in [("CHARACTER VARYING", "VARCHAR"),
                        ("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP"),
                        ("DOUBLE PRECISION", "FLOAT")]:
        t = t.replace(long, short)
    return t.split("(")[0][:12]


def erd_dot(model, title):
    def color(table):
        if table.startswith("fact_"):
            return FACT_COLOR
        if table in CONFORMED_DIMENSIONS:
            return CONFORMED_COLOR
        return DEFAULT_COLOR

    out = [
        "digraph model {",
        '    graph [rankdir=LR, splines=ortho, nodesep=0.6, ranksep=1.4,'
        f'    label="{title}", labelloc=t, fontname="Helvetica", fontsize=16];',
        '    node  [shape=plaintext, fontname="Helvetica", fontsize=10];',
        '    edge  [color="#5d6b7d", arrowsize=0.7];',
    ]
    for table, d in model.items():
        rows = "".join(
            f'<TR><TD ALIGN="LEFT">{"<B>" if pk else ""}{n}{"</B>" if pk else ""}'
            f'</TD><TD ALIGN="LEFT"><FONT POINT-SIZE="8">{short_type(t)}</FONT></TD></TR>'
            for n, t, pk in d["cols"]
        )
        out.append(
            f'    {table} [label=<<TABLE BORDER="0" CELLBORDER="1" CELLSPACING="0">'
            f'<TR><TD COLSPAN="2" BGCOLOR="{color(table)}"><B>{table}</B></TD></TR>'
            f"{rows}</TABLE>>];"
        )
    for table, d in model.items():
        for _, referenced in d["fks"]:
            if referenced in model:
                out.append(f"    {referenced} -> {table};")
    out.append("}")
    return "\n".join(out)


def pipeline_dot():
    """ETL layers of the warehouse with the counts of the last successful load."""
    dw = sa.create_engine(os.getenv("DW_URL"))
    with dw.connect() as c:
        def n(sql):
            return c.execute(sa.text(sql)).scalar() or 0

        def last_run(process):
            return n(f"SELECT MAX(run_id) FROM staging_dw.etl_run "
                     f"WHERE proceso='{process}' AND estado='OK'")

        rs, rd, rf = last_run("staging"), last_run("dimensiones"), last_run("hechos")
        ini_cm = n(f"SELECT COUNT(*) FROM staging_dw.stg_initial_classicmodels WHERE run_id={rs}")
        ini_cs = n(f"SELECT COUNT(*) FROM staging_dw.stg_initial_customerservice WHERE run_id={rs}")
        tab_cm = n(f"SELECT COUNT(DISTINCT tabla_origen) FROM staging_dw.stg_initial_classicmodels WHERE run_id={rs}")
        tab_cs = n(f"SELECT COUNT(DISTINCT tabla_origen) FROM staging_dw.stg_initial_customerservice WHERE run_id={rs}")
        profiled = n(f"SELECT COUNT(*) FROM staging_dw.stg_perfil WHERE run_id={rs}")
        errors = n(f"SELECT COUNT(*) FROM staging_dw.stg_error_log WHERE run_id={rs}")
        warnings = n(f"SELECT COUNT(*) FROM staging_dw.stg_error_log WHERE run_id={rs} AND accion='ADVERTENCIA'")
        clean = n(f"SELECT COUNT(*) FROM staging_dw.stg_clean WHERE run_id={rs}")
        rejected = n(f"SELECT COUNT(*) FROM staging_dw.stg_rejected WHERE run_id={rs}")
        tr_d = n(f"SELECT COUNT(*) FROM staging_dw.stg_transform WHERE run_id={rd}")
        tr_f = n(f"SELECT COUNT(*) FROM staging_dw.stg_transform WHERE run_id={rf}")
        lr_d = n(f"SELECT COUNT(*) FROM staging_dw.stg_loadready WHERE run_id={rd}")
        lr_f = n(f"SELECT COUNT(*) FROM staging_dw.stg_loadready WHERE run_id={rf}")
        dims = n("SELECT (SELECT COUNT(*) FROM dim_tiempo)+(SELECT COUNT(*) FROM dim_cliente)"
                 "+(SELECT COUNT(*) FROM dim_producto)+(SELECT COUNT(*) FROM dim_empleado)"
                 "+(SELECT COUNT(*) FROM dim_oficina)+(SELECT COUNT(*) FROM dim_estado_orden)")
        facts = n("SELECT (SELECT COUNT(*) FROM fact_ventas)+(SELECT COUNT(*) FROM fact_llamadas_servicio)")
        dm1 = n("SELECT COUNT(*) FROM dm.vw_interaccion_cliente_producto")
        dm2 = n("SELECT COUNT(*) FROM dm.vw_ventas_mensuales_linea")

    def node(name, title, detail, color, shape="box3d"):
        return (f'  {name} [shape={shape}, style="filled", fillcolor="{color}", '
                f'label=<<B>{title}</B><BR/><FONT POINT-SIZE="9">{detail}</FONT>>];')

    GREY, BLUE, GREEN, RED, AMBER, MAUVE = ("#e8ecf1", "#dbe8f5", "#e2f0e4",
                                            "#f6d4d4", "#fbeccd", "#ece3f3")
    lines = [
        "digraph pipeline {",
        '  graph [rankdir=LR, nodesep=0.35, ranksep=0.55, fontname="Helvetica", '
        'label="Pipeline ETL del almacen (conteos de la ultima carga)", labelloc=t, fontsize=14];',
        '  node [fontname="Helvetica", fontsize=11];',
        '  edge [color="#5d6b7d", arrowsize=0.7];',
        "",
        '  subgraph cluster_1 { label="1  Extract/Publish"; style=dashed; color="#8a96a3";',
        node("ext_cm", "Modelo de extraccion", "classicmodels (MySQL)", GREY, "box"),
        node("ext_cs", "Modelo de extraccion", "customerservice (PostgreSQL)", GREY, "box"),
        "  }",
        '  subgraph cluster_2 { label="2  Initial Staging"; style=dashed; color="#8a96a3";',
        node("ini_cm", "stg_initial_classicmodels", f"{tab_cm} tablas, {ini_cm} filas", BLUE),
        node("ini_cs", "stg_initial_customerservice", f"{tab_cs} tablas, {ini_cs} filas", GREEN),
        node("profile", "stg_perfil", f"{profiled} columnas perfiladas", GREY, "note"),
        "  }",
        '  subgraph cluster_3 { label="3  Data Quality"; style=dashed; color="#8a96a3";',
        node("dq", "Reglas tecnicas y de negocio", "11 reglas por registro", AMBER, "box"),
        node("errlog", "stg_error_log", f"{errors} entradas ({warnings} advertencias)", AMBER, "note"),
        "  }",
        '  subgraph cluster_4 { label="4  Clean Staging"; style=dashed; color="#8a96a3";',
        node("clean", "stg_clean", f"{clean} filas limpias", GREY),
        node("rej", "stg_rejected", f"{rejected} filas rechazadas", RED),
        "  }",
        '  subgraph cluster_5 { label="5  Transformation"; style=dashed; color="#8a96a3";',
        node("tr_d", "Conformar dimensiones", f"6 areas, {tr_d} filas", GREY, "box"),
        node("tr_f", "Conformar hechos", f"Ventas y Servicio, {tr_f} filas", GREY, "box"),
        "  }",
        '  subgraph cluster_6 { label="6  Load-Ready Publish"; style=dashed; color="#8a96a3";',
        node("lr_d", "stg_loadready", f"DIMENSIONES, {lr_d} filas", GREY),
        node("lr_f", "stg_loadready", f"HECHOS, {lr_f} filas", GREY),
        "  }",
        '  subgraph cluster_7 { label="7  Load"; style=dashed; color="#8a96a3";',
        node("dims", "dim_*", f"6 dimensiones, {dims} filas", GREEN, "cylinder"),
        node("facts", "fact_*", f"2 hechos, {facts} filas", BLUE, "cylinder"),
        "  }",
        '  subgraph cluster_8 { label="Data marts (schema dm)"; style=dashed; color="#8a96a3";',
        node("dm1", "dm.vw_interaccion_cliente_producto", f"{dm1} filas", MAUVE, "cylinder"),
        node("dm2", "dm.vw_ventas_mensuales_linea", f"{dm2} filas", MAUVE, "cylinder"),
        "  }",
        "",
        "  ext_cm -> ini_cm; ext_cs -> ini_cs;",
        "  ini_cm -> profile [style=dotted]; ini_cs -> profile [style=dotted];",
        "  ini_cm -> dq; ini_cs -> dq;",
        "  dq -> errlog [style=dotted];",
        "  dq -> clean; dq -> rej [color=\"#c0392b\"];",
        "  clean -> tr_d; clean -> tr_f;",
        "  tr_d -> lr_d; tr_f -> lr_f;",
        "  lr_d -> dims; lr_f -> facts;",
        "  dims -> tr_f [style=dashed, label=\"lookup\", fontsize=9];",
        "  facts -> dm1; dims -> dm1; facts -> dm2; dims -> dm2;",
        "}",
    ]
    return "\n".join(lines)


def render_png(dot_source, png_path):
    """Render with the local dot binary, or with Docker if it is missing."""
    if shutil.which("dot"):
        cmd = ["dot", "-Tpng"]
    elif shutil.which("docker"):
        cmd = ["docker", "run", "-i", "--rm", "nshine/dot", "dot", "-Tpng"]
    else:
        print("    (no Graphviz or Docker found: .dot written, .png skipped)")
        return
    result = subprocess.run(cmd, input=dot_source.encode(), capture_output=True)
    if result.returncode != 0:
        print(f"    (rendering failed, .png not updated: {result.stderr.decode()[:200]})")
        return
    png_path.write_bytes(result.stdout)


def write(name, dot_source):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    dot_path = OUTPUT / f"{name}.dot"
    dot_path.write_text(dot_source, encoding="utf-8")
    render_png(dot_source, OUTPUT / f"{name}.png")
    print(f"  {dot_path.relative_to(ROOT)} (+ .png)")


def main():
    print("Generating diagrams from the live schemas...")
    write("classicmodels_erd", erd_dot(
        introspect(os.getenv("CLASSICMODELS_URL"), "classicmodels"),
        "classicmodels (MySQL)"))
    write("customerservice_erd", erd_dot(
        introspect(os.getenv("CUSTOMERSERVICE_URL"), "public"),
        "customerservice (PostgreSQL)"))
    write("metadata_repository_erd", erd_dot(
        introspect(os.getenv("METADATA_URL"), "public"),
        "Repositorio de metadatos"))
    write("metadata_core_erd", erd_dot(
        introspect(os.getenv("METADATA_URL"), "public", only=METADATA_CORE_TABLES),
        "Repositorio de metadatos - nucleo (fuentes, negocio y linaje)"))
    write("dw_star_schema", erd_dot(
        introspect(os.getenv("DW_URL"), "public"),
        "Almacen de datos - modelo dimensional"))
    write("etl_pipeline", pipeline_dot())


if __name__ == "__main__":
    main()
