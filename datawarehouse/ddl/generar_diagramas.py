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


if __name__ == "__main__":
    print("Generando diagramas desde el esquema real...")
    generar(os.getenv("DW_URL"), "dw_modelo_dimensional",
            "Almacen de Datos - Modelo Dimensional (Entrega 2)")
    generar(os.getenv("METADATA_REPO_URL"), "repositorio_metadatos",
            "Repositorio de Metadatos - Entregas 1 y 2")
    print()
    print("Para convertir a PNG con Docker (no requiere instalar Graphviz):")
    print('  docker run --rm -v "$PWD/docs/Entrega_2/img:/w" -w /w nshine/dot \\')
    print("      dot -Tpng dw_modelo_dimensional.dot -o dw_modelo_dimensional.png")
