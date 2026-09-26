"""
Genera un reporte legible de columnas y llaves (PK/FK) por tabla,
a partir de output/metadata_tecnico.csv (creado por discover_and_profile.py).

Uso:
    python report_keys.py

Genera:
    output/columnas_por_tabla.md   -> tablas markdown listas para pegar en Word
"""
import csv
from pathlib import Path
from collections import OrderedDict

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_CSV = BASE_DIR / "output" / "metadata_tecnico.csv"
OUTPUT_MD = BASE_DIR / "output" / "columnas_por_tabla.md"


def main():
    tables = OrderedDict()
    with open(INPUT_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["base_datos"], row["tabla"])
            tables.setdefault(key, []).append(row)

    lines = []
    current_bd = None
    for (bd, tabla), cols in tables.items():
        if bd != current_bd:
            lines.append(f"\n## Base de datos: {bd}\n")
            current_bd = bd

        lines.append(f"### Tabla: {tabla}\n")
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
    print(f"Reporte de columnas y llaves escrito en {OUTPUT_MD}")


if __name__ == "__main__":
    main()
