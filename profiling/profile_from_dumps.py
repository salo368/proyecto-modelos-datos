"""
Discovery and profiling of both sources, parsed directly from the SQL
dumps in sources/ (no database connection needed).

Writes to profiling/output/:
    metadata_tecnico.csv                columns, types, nullability, PK and FK per table
    perfilamiento.csv                   rows, nulls, distinct values, min/max and
                                        text pattern per column
    comparacion_entidades_comunes.csv   row counts of the entities present in both sources

Usage:
    python profiling/profile_from_dumps.py
"""
import csv
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MYSQL_DUMP = ROOT / "sources" / "mysqlsampledatabase.sql"
PG_DUMP = ROOT / "sources" / "customerservice.sql"
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Value parsing helpers
# ---------------------------------------------------------------------------

def split_value_tuples(s):
    """Split "(1,'a'),(2,'b')" into ["1,'a'", "2,'b'"], respecting quotes."""
    tuples = []
    depth = 0
    in_str = False
    start = None
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == "'":
                in_str = False
        else:
            if c == "'":
                in_str = True
            elif c == "(":
                if depth == 0:
                    start = i + 1
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0 and start is not None:
                    tuples.append(s[start:i])
                    start = None
        i += 1
    return tuples


def split_fields(s):
    """Split "a, 'b,c', NULL" into fields, respecting quotes."""
    fields = []
    cur = []
    in_str = False
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if in_str:
            if c == "\\" and i + 1 < n:
                cur.append(c)
                cur.append(s[i + 1])
                i += 2
                continue
            if c == "'":
                in_str = False
                cur.append(c)
                i += 1
                continue
            cur.append(c)
        else:
            if c == "'":
                in_str = True
                cur.append(c)
            elif c == ",":
                fields.append("".join(cur).strip())
                cur = []
            else:
                cur.append(c)
        i += 1
    if cur:
        fields.append("".join(cur).strip())
    return fields


def coerce_value(raw):
    raw = raw.strip()
    if raw == "NULL":
        return None
    if raw.startswith("'") and raw.endswith("'"):
        inner = raw[1:-1]
        inner = inner.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
        return inner
    try:
        if "." in raw:
            return float(raw)
        return int(raw)
    except ValueError:
        return raw


# ---------------------------------------------------------------------------
# MySQL: schema (CREATE TABLE) and data (INSERT)
# ---------------------------------------------------------------------------

def parse_mysql_schema(text):
    tables = {}
    for m in re.finditer(r"CREATE TABLE `(\w+)` \((.*?)\n\) ENGINE", text, re.DOTALL):
        tname, body = m.group(1), m.group(2)
        columns = []
        pk_cols = []
        fks = []
        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            col_m = re.match(r"`(\w+)`\s+([a-zA-Z]+(?:\([^)]*\))?)\s*(.*)", line)
            if line.startswith("PRIMARY KEY"):
                pk_cols = re.findall(r"`(\w+)`", line)
            elif line.startswith("CONSTRAINT") and "FOREIGN KEY" in line:
                fk_m = re.search(r"FOREIGN KEY \(`(\w+)`\) REFERENCES `(\w+)` \(`(\w+)`\)", line)
                if fk_m:
                    fks.append(fk_m.groups())
            elif line.startswith("KEY") or line.startswith("UNIQUE KEY"):
                continue
            elif col_m:
                cname, ctype, rest = col_m.groups()
                nullable = "NO" if "NOT NULL" in rest.upper() else "YES"
                columns.append({"columna": cname, "tipo": ctype, "nulo": nullable})
        for c in columns:
            c["pk"] = c["columna"] in pk_cols
        tables[tname] = {"columns": columns, "pk": pk_cols, "fks": fks}
    return tables


def scan_tuples(text, pos):
    """Scan from `pos` collecting balanced '(...)' tuples up to a top-level ';'
    (outside quotes and parentheses). Product descriptions contain literal ';'
    characters, so a plain regex would cut the statement short."""
    rows = []
    n = len(text)
    i = pos
    in_str = False
    depth = 0
    tuple_start = None
    while i < n:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == "'":
                in_str = False
            i += 1
            continue
        if c == "'":
            in_str = True
        elif c == "(":
            if depth == 0:
                tuple_start = i + 1
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0 and tuple_start is not None:
                rows.append(split_fields(text[tuple_start:i]))
                tuple_start = None
        elif c == ";" and depth == 0:
            return rows, i + 1
        i += 1
    return rows, i


def parse_mysql_inserts(text, schema):
    data = {}
    for m in re.finditer(r"insert\s+into\s+`(\w+)`\(([^)]*)\)\s*values", text, re.IGNORECASE):
        tname = m.group(1)
        cols = [c.strip(" `") for c in m.group(2).split(",")]
        raw_rows, _ = scan_tuples(text, m.end())
        rows = [[coerce_value(f) for f in row] for row in raw_rows]
        data.setdefault(tname, {"columns": cols, "rows": []})
        data[tname]["rows"].extend(rows)
    return data


# ---------------------------------------------------------------------------
# PostgreSQL: schema (CREATE TABLE + ALTER TABLE) and data (COPY)
# ---------------------------------------------------------------------------

def parse_postgres_schema(text):
    tables = {}
    for m in re.finditer(r"CREATE TABLE public\.(\w+) \((.*?)\n\);", text, re.DOTALL):
        tname, body = m.group(1), m.group(2)
        columns = []
        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            if not line:
                continue
            col_m = re.match(r"(\w+)\s+(.*)", line)
            if col_m:
                cname, rest = col_m.groups()
                nullable = "NO" if "NOT NULL" in rest.upper() else "YES"
                ctype = re.split(r"\s+NOT NULL|\s+DEFAULT", rest)[0].strip()
                columns.append({"columna": cname, "tipo": ctype, "nulo": nullable})
        tables[tname] = {"columns": columns, "pk": [], "fks": []}

    for m in re.finditer(
        r"ALTER TABLE ONLY public\.(\w+)\s+ADD CONSTRAINT \w+ PRIMARY KEY \(([^)]*)\);",
        text,
    ):
        tname, cols = m.groups()
        pk_cols = [c.strip() for c in cols.split(",")]
        if tname in tables:
            tables[tname]["pk"] = pk_cols
            for c in tables[tname]["columns"]:
                c["pk"] = c["columna"] in pk_cols

    for m in re.finditer(
        r"ALTER TABLE ONLY public\.(\w+)\s+ADD CONSTRAINT \w+ FOREIGN KEY \((\w+)\) REFERENCES public\.(\w+)\((\w+)\);",
        text,
    ):
        tname, col, ref_table, ref_col = m.groups()
        if tname in tables:
            tables[tname]["fks"].append((col, ref_table, ref_col))

    for t in tables.values():
        for c in t["columns"]:
            c.setdefault("pk", c["columna"] in t["pk"])
    return tables


def parse_postgres_copy(text):
    data = {}
    for m in re.finditer(
        r"COPY public\.(\w+) \(([^)]*)\) FROM stdin;\n(.*?)\n\\\.", text, re.DOTALL
    ):
        tname, cols_raw, block = m.groups()
        cols = [c.strip() for c in cols_raw.split(",")]
        rows = []
        for line in block.split("\n"):
            if not line:
                continue
            fields = line.split("\t")
            rows.append([None if f == "\\N" else f for f in fields])
        data[tname] = {"columns": cols, "rows": rows}
    return data


# ---------------------------------------------------------------------------
# Simple text pattern detection
# ---------------------------------------------------------------------------

PATTERNS = [
    ("solo_digitos", re.compile(r"^\d+$")),
    ("email", re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")),
    ("telefono_like", re.compile(r"^[\d\s()+\-.]+$")),
    ("alfabetico", re.compile(r"^[A-Za-zÀ-ÿ\s.]+$")),
    ("alfanumerico", re.compile(r"^[A-Za-z0-9\s.,\-]+$")),
]


def detect_pattern(values):
    non_null = [v for v in values if v is not None and v != ""]
    if not non_null:
        return "sin_datos"
    sample = non_null[:200]
    for name, rx in PATTERNS:
        if all(rx.match(str(v)) for v in sample):
            return name
    return "libre/mixto"


def is_number(v):
    return isinstance(v, (int, float))


def looks_like_date(v):
    if not isinstance(v, str):
        return False
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            datetime.strptime(v, fmt)
            return True
        except ValueError:
            continue
    return False


# ---------------------------------------------------------------------------
# Technical metadata
# ---------------------------------------------------------------------------

def write_metadata_csv(mysql_schema, pg_schema):
    path = OUTPUT_DIR / "metadata_tecnico.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["base_datos", "tabla", "columna", "tipo_dato", "permite_nulo", "es_pk", "es_fk", "referencia"])
        for tname, t in mysql_schema.items():
            fk_map = {fk[0]: (fk[1], fk[2]) for fk in t["fks"]}
            for c in t["columns"]:
                ref = fk_map.get(c["columna"])
                w.writerow([
                    "classicmodels", tname, c["columna"], c["tipo"], c["nulo"],
                    c.get("pk", False), c["columna"] in fk_map,
                    f"{ref[0]}.{ref[1]}" if ref else "",
                ])
        for tname, t in pg_schema.items():
            fk_map = {fk[0]: (fk[1], fk[2]) for fk in t["fks"]}
            for c in t["columns"]:
                ref = fk_map.get(c["columna"])
                w.writerow([
                    "customerservice", tname, c["columna"], c["tipo"], c["nulo"],
                    c.get("pk", False), c["columna"] in fk_map,
                    f"{ref[0]}.{ref[1]}" if ref else "",
                ])
    print(f"Technical metadata written to {path}")


# ---------------------------------------------------------------------------
# Column profiling
# ---------------------------------------------------------------------------

def profile_table(bd, tname, columns_def, data):
    rows = []
    cols = data["columns"]
    values_by_col = {c: [] for c in cols}
    for row in data["rows"]:
        for c, v in zip(cols, row):
            values_by_col[c].append(v)

    type_by_col = {c["columna"]: c["tipo"] for c in columns_def}

    for col, values in values_by_col.items():
        total = len(values)
        nulls = sum(1 for v in values if v is None or v == "")
        pct_null = round(100 * nulls / total, 2) if total else 0
        non_null = [v for v in values if v is not None and v != ""]
        distinct = len(set(non_null))

        min_v = max_v = pattern = ""
        if non_null:
            if all(is_number(v) for v in non_null):
                min_v, max_v = min(non_null), max(non_null)
            elif all(looks_like_date(v) for v in non_null):
                min_v, max_v = min(non_null), max(non_null)
            else:
                lengths = [len(str(v)) for v in non_null]
                min_v, max_v = f"len_min={min(lengths)}", f"len_max={max(lengths)}"
                pattern = detect_pattern(non_null)

        rows.append({
            "base_datos": bd,
            "tabla": tname,
            "columna": col,
            "tipo_dato": type_by_col.get(col, ""),
            "total_filas": total,
            "nulos": nulls,
            "pct_nulos": pct_null,
            "valores_distintos": distinct,
            "min": min_v,
            "max": max_v,
            "patron_texto": pattern,
        })
    return rows


def write_profiling_csv(mysql_schema, mysql_data, pg_schema, pg_data):
    path = OUTPUT_DIR / "perfilamiento.csv"
    all_rows = []
    for tname, data in mysql_data.items():
        cdef = mysql_schema.get(tname, {}).get("columns", [])
        all_rows.extend(profile_table("classicmodels", tname, cdef, data))
    for tname, data in pg_data.items():
        cdef = pg_schema.get(tname, {}).get("columns", [])
        all_rows.extend(profile_table("customerservice", tname, cdef, data))

    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()), lineterminator="\n")
        w.writeheader()
        w.writerows(all_rows)
    print(f"Column profile written to {path}")


# ---------------------------------------------------------------------------
# Entities present in both sources (customers, employees, products)
# ---------------------------------------------------------------------------

def compare_common_entities(mysql_data, pg_data):
    pairs = [("customers", "cs_customers"), ("employees", "cs_employees"), ("products", "cs_products")]
    path = OUTPUT_DIR / "comparacion_entidades_comunes.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["entidad", "tabla_mysql", "filas_mysql", "tabla_postgres", "filas_postgres"])
        for mt, pt in pairs:
            n_mysql = len(mysql_data.get(mt, {}).get("rows", []))
            n_pg = len(pg_data.get(pt, {}).get("rows", []))
            w.writerow([mt, mt, n_mysql, pt, n_pg])
    print(f"Common-entity comparison written to {path}")


# ---------------------------------------------------------------------------
def main():
    mysql_text = MYSQL_DUMP.read_text(encoding="utf-8", errors="ignore")
    pg_text = PG_DUMP.read_text(encoding="utf-8", errors="ignore")

    mysql_schema = parse_mysql_schema(mysql_text)
    pg_schema = parse_postgres_schema(pg_text)
    print("MySQL tables found:", list(mysql_schema.keys()))
    print("PostgreSQL tables found:", list(pg_schema.keys()))

    mysql_data = parse_mysql_inserts(mysql_text, mysql_schema)
    pg_data = parse_postgres_copy(pg_text)

    write_metadata_csv(mysql_schema, pg_schema)
    write_profiling_csv(mysql_schema, mysql_data, pg_schema, pg_data)
    compare_common_entities(mysql_data, pg_data)


if __name__ == "__main__":
    main()
