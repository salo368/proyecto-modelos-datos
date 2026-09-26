"""
Markdown report of the columns and keys (PK/FK) of every source table,
built from output/metadata_tecnico.csv (see profile_from_dumps.py).

Writes:
    profiling/output/columnas_por_tabla.md

Usage:
    python profiling/columns_report.py
"""
import csv
from collections import OrderedDict
from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
INPUT_CSV = OUTPUT_DIR / "metadata_tecnico.csv"
OUTPUT_MD = OUTPUT_DIR / "columnas_por_tabla.md"


def main():
    tables = OrderedDict()
    with open(INPUT_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            tables.setdefault((row["base_datos"], row["tabla"]), []).append(row)

    lines = []
    current_db = None
    for (db, table), cols in tables.items():
        if db != current_db:
            lines.append(f"\n## Base de datos: {db}\n")
            current_db = db

        lines.append(f"### Tabla: {table}\n")
        lines.append("| Columna | Tipo de dato | Nulo | PK | FK -> referencia |")
        lines.append("|---|---|---|---|---|")
        pk_cols = [c["columna"] for c in cols if c["es_pk"] == "True"]
        for c in cols:
            pk_mark = "PK" if c["es_pk"] == "True" else ""
            fk_mark = f"FK -> {c['referencia']}" if c["es_fk"] == "True" else ""
            lines.append(
                f"| {c['columna']} | {c['tipo_dato']} | {c['permite_nulo']} | {pk_mark} | {fk_mark} |"
            )
        lines.append(f"\n**Llave primaria:** {', '.join(pk_cols) if pk_cols else '(ninguna definida)'}\n")

    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Column report written to {OUTPUT_MD}")


if __name__ == "__main__":
    main()
