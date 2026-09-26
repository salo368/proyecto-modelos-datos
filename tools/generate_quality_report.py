"""
Data quality report by pipeline stage.

Measures what happened to the data in each layer of the last successful
load and writes it to docs/data_quality_report.md, so that anyone reading
an analysis built on the warehouse knows what share of the data it rests
on and what was left out, fixed or kept as NULL.

Every figure is computed from what the layers left persisted in the
staging database and from the warehouse itself:

    staging_dw.stg_initial_*   rows extracted per source table
    staging_dw.stg_perfil      nulls per source column
    staging_dw.stg_error_log   quality findings per record
    staging_dw.stg_clean       records accepted
    staging_dw.stg_rejected    records rejected
    staging_dw.stg_transform   rows per target after transformation
    staging_dw.stg_loadready   rows ready to load
    dim_* / fact_*             rows actually loaded
    dw_lineage (metadata)      which source column feeds which target

Nothing is typed by hand, so the report cannot drift from the pipeline.
The file carries no dates or run ids: it only changes in git when the
data or the logic change, and that diff shows the change in behaviour.

Usage:
    python tools/generate_quality_report.py
"""
import os
import sys
from pathlib import Path

import sqlalchemy as sa
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
load_dotenv(REPO / ".env")

STAGING = sa.create_engine(os.getenv("STAGING_URL"))
DW = sa.create_engine(os.getenv("DW_URL"))
META = sa.create_engine(os.getenv("METADATA_URL"))
OUT = REPO / "docs" / "data_quality_report.md"

# What a NULL means in the columns where it is expected. Only the wording
# is written here; every count comes from the database.
NULL_MEANING = {
    ("orders", "shippedDate"): "órdenes aún no despachadas; el nulo es un dato válido",
    ("orders", "comments"): "comentario libre opcional",
    ("customers", "addressLine2"): "segunda línea de dirección opcional",
    ("customers", "state"): "muchos países no usan estado o región",
    ("customers", "postalCode"): "algunos países no usan código postal",
    ("customers", "salesRepEmployeeNumber"): "cliente sin representante de ventas asignado",
    ("employees", "reportsTo"): "el presidente no reporta a nadie",
    ("offices", "state"): "oficinas fuera de países con estados",
    ("offices", "addressLine2"): "segunda línea de dirección opcional",
    ("productlines", "htmlDescription"): "columna nunca poblada en la fuente",
    ("productlines", "image"): "columna nunca poblada en la fuente",
    ("cs_customers", "addressline2"): "segunda línea de dirección opcional",
    ("cs_customers", "state"): "muchos países no usan estado o región",
    ("cs_customers", "postalcode"): "algunos países no usan código postal",
}


# ============================================================
# Formatting (Colombian conventions: 9.604.190,61 and 81,9 %)
# ============================================================

def n(x):
    return f"{int(x):,}".replace(",", ".")


def money(x):
    return f"{float(x):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def pct(part, whole):
    if not whole:
        return "—"
    return f"{100 * part / whole:.1f}".replace(".", ",") + " %"


def table(headers, rows, align=None):
    align = align or ["l"] * len(headers)
    sep = ["---:" if a == "r" else "---" for a in align]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(sep) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


# ============================================================
# Queries
# ============================================================

def scalar(engine, sql, **params):
    with engine.connect() as con:
        return con.execute(sa.text(sql), params).scalar()


def rows(engine, sql, **params):
    with engine.connect() as con:
        return con.execute(sa.text(sql), params).fetchall()


def last_runs():
    staging = scalar(STAGING, """SELECT MAX(run_id) FROM staging_dw.etl_run
                            WHERE proceso = 'staging' AND estado = 'OK'""")
    if staging is None:
        sys.exit("There is no successful load yet. Run: python run_all.py")

    def branch(process):
        return scalar(STAGING, """SELECT MAX(run_id) FROM staging_dw.etl_run
                             WHERE proceso = :p AND estado = 'OK' AND run_origen = :s""",
                      p=process, s=staging)

    dims, facts = branch("dimensiones"), branch("hechos")
    if dims is None or facts is None:
        sys.exit("The last staging run has no successful dimensions and facts load.")
    return staging, dims, facts


def funnel(rs):
    """Per source table: extracted, warning, rejected, clean."""
    extracted = rows(STAGING, """
        SELECT 'classicmodels' AS fuente, tabla_origen, COUNT(*)
          FROM staging_dw.stg_initial_classicmodels WHERE run_id = :r GROUP BY 2
        UNION ALL
        SELECT 'customerservice', tabla_origen, COUNT(*)
          FROM staging_dw.stg_initial_customerservice WHERE run_id = :r GROUP BY 2
        ORDER BY 1, 2""", r=rs)

    def per_table(sql):
        return {t: c for t, c in rows(STAGING, sql, r=rs)}

    clean = per_table("""SELECT tabla_origen, COUNT(*) FROM staging_dw.stg_clean
                         WHERE run_id = :r GROUP BY 1""")
    rejected = per_table("""SELECT tabla_origen, COUNT(*) FROM staging_dw.stg_rejected
                            WHERE run_id = :r GROUP BY 1""")
    # Records that passed but carry at least one warning.
    warned = per_table("""
        SELECT e.tabla_origen, COUNT(DISTINCT e.nro_fila)
          FROM staging_dw.stg_error_log e
         WHERE e.run_id = :r AND e.accion = 'ADVERTENCIA'
           AND NOT EXISTS (SELECT 1 FROM staging_dw.stg_rejected x
                            WHERE x.run_id = e.run_id
                              AND x.tabla_origen = e.tabla_origen
                              AND x.nro_fila = e.nro_fila)
         GROUP BY 1""")

    return [
        {"fuente": f, "tabla": t, "extraidas": c,
         "limpias": clean.get(t, 0), "rechazadas": rejected.get(t, 0),
         "con_advertencia": warned.get(t, 0)}
        for f, t, c in extracted
    ]


def lineage():
    """{source table: {(object, target column, rule), ...}} from the repository."""
    out = {}
    for tbl, col, obj, target, rule in rows(META, """
            SELECT dt.table_name, dc.column_name, o.object_name,
                   COALESCE(m.measure_name, a.attribute_name), l.transformation_rule
              FROM dw_lineage l
              JOIN db_column dc ON l.source_column_id = dc.column_id
              JOIN db_table  dt ON dc.table_id = dt.table_id
              LEFT JOIN dw_measure   m ON l.target_measure_id   = m.dw_measure_id
              LEFT JOIN dw_attribute a ON l.target_attribute_id = a.dw_attribute_id
              JOIN dw_object o ON o.dw_object_id = COALESCE(m.dw_object_id, a.dw_object_id)"""):
        out.setdefault(tbl, {}).setdefault(col, set()).add((obj, target, rule))
    return out


def quality_rules(rs):
    return rows(META, """
        SELECT r.rule_name, r.clase_dq, r.severity, res.rows_evaluated, res.rows_failed
          FROM dq_result res
          JOIN dq_rule r        ON res.dq_rule_id = r.dq_rule_id
          JOIN etl_execution e  ON res.etl_execution_id = e.etl_execution_id
         WHERE e.etl_execution_id = (
                 SELECT MAX(e2.etl_execution_id)
                   FROM etl_execution e2 JOIN etl_process p
                     ON e2.etl_process_id = p.etl_process_id
                  WHERE p.process_name = 'etl_dw_staging' AND e2.run_id = :r
                    AND e2.status = 'OK')
         ORDER BY r.clase_dq DESC, r.severity, r.rule_name""", r=rs)


def per_target(table_name, run_id):
    return rows(STAGING, f"""SELECT objetivo, COUNT(*) FROM staging_dw.{table_name}
                        WHERE run_id = :r GROUP BY 1 ORDER BY 1""", r=run_id)


# Dimensions with special members (negative keys: -1 Desconocido, -2 Sin
# asignar), created by datawarehouse/edw/special_members.sql rather than
# loaded by the pipeline. A fact key pointing to -2 stands for a NULL.
SPECIAL_MEMBERS = {"dim_empleado": "empleado_key", "dim_oficina": "oficina_key"}


def loaded_count(target):
    """Rows the pipeline loaded into a target, special members aside."""
    where = f" WHERE {SPECIAL_MEMBERS[target]} > 0" if target in SPECIAL_MEMBERS else ""
    return scalar(DW, f"SELECT COUNT(*) FROM {target}{where}")


def null_as_member(obj, column):
    return obj.startswith("fact_") and column in SPECIAL_MEMBERS.values()


def nulls_in_target(obj, column):
    """NULLs in a target column; for a fact key with special members, the
    rows pointing to -2 Sin asignar, which stands in for the NULL."""
    cond = f"{column} = -2" if null_as_member(obj, column) else f"{column} IS NULL"
    return scalar(DW, f"SELECT COUNT(*) FILTER (WHERE {cond}) FROM {obj}")


# ============================================================
# Report
# ============================================================

def build():
    rs, rd, rh = last_runs()
    fun = funnel(rs)
    lin = lineage()

    total = sum(f["extraidas"] for f in fun)
    rejected = sum(f["rechazadas"] for f in fun)
    warned = sum(f["con_advertencia"] for f in fun)
    clean = sum(f["limpias"] for f in fun)
    spotless = clean - warned
    unused_tables = [f for f in fun if f["tabla"] not in lin]
    unused_rows = sum(f["extraidas"] for f in unused_tables)

    # --- impact of the modelling decisions on the measures ---
    lines = loaded_count("fact_ventas")
    amount = scalar(DW, "SELECT COALESCE(SUM(monto_linea), 0) FROM fact_ventas")

    def share(where, join=""):
        r = rows(DW, f"""SELECT COUNT(*), COALESCE(SUM(f.monto_linea), 0)
                         FROM fact_ventas f {join} WHERE {where}""")[0]
        return r[0], r[1]

    noneff_n, noneff_amt = share(
        "NOT e.es_efectiva", "JOIN dim_estado_orden e ON f.estado_key = e.estado_key")
    unshipped_n, unshipped_amt = share("f.dias_hasta_envio IS NULL")
    norep_n, norep_amt = share("f.empleado_key < 0")
    both_n, _ = share(
        "NOT e.es_efectiva AND f.dias_hasta_envio IS NULL",
        "JOIN dim_estado_orden e ON f.estado_key = e.estado_key")
    customers = loaded_count("dim_cliente")
    no_orders = scalar(DW, """SELECT COUNT(*) FROM dim_cliente c WHERE NOT EXISTS
                              (SELECT 1 FROM fact_ventas f WHERE f.cliente_key = c.cliente_key)""")
    calls = loaded_count("fact_llamadas_servicio")
    products = loaded_count("dim_producto")
    unsold = scalar(DW, """SELECT COUNT(*) FROM dim_producto p WHERE NOT EXISTS
                           (SELECT 1 FROM fact_ventas f WHERE f.producto_key = p.producto_key)""")
    unused_names = ", ".join(f"`{f['tabla']}`" for f in unused_tables)

    md = []
    w = md.append

    w("# Calidad de datos por etapa")
    w("")
    w("Qué le pasó a los datos en cada capa de la última carga completa: cuántos "
      "registros entraron, cuántos se descartaron, qué nulos se resolvieron y "
      "cuáles se conservaron, y sobre qué porcentaje de los datos se apoya cada "
      "análisis del almacén.")
    w("")
    w("> Generado por `tools/generate_quality_report.py` a partir de lo que cada "
      "capa del pipeline dejó persistido en la base `staging`, de lo que quedó "
      "cargado en el almacén (`dw`) y del linaje del repositorio de "
      "metadatos. Ninguna cifra está escrita a mano: se regenera con cada "
      "`python run_all.py`.")
    w("")

    # ---------------- summary ----------------
    w("## Resumen")
    w("")
    w(table(
        ["Estado del registro", "Registros", "% del total extraído"],
        [["Limpio y sin ninguna anomalía", n(spotless), pct(spotless, total)],
         ["Limpio, con advertencia trazada", n(warned), pct(warned, total)],
         ["Rechazado", n(rejected), pct(rejected, total)],
         ["**Total extraído**", f"**{n(total)}**", "**100 %**"]],
        ["l", "r", "r"]))
    w("")
    w(f"- **{pct(spotless, total)}** de los registros pasaron las reglas de "
      "calidad sin ninguna observación.")
    if warned:
        w(f"- **{pct(warned, total)}** pasaron con una advertencia: se usan, pero "
          "la anomalía queda registrada en `staging_dw.vw_reporte_transacciones_malas` "
          "(base `staging`).")
    w(f"- **{pct(rejected, total)}** fueron rechazados"
      + (": ningún registro incumplió una regla bloqueante." if rejected == 0 else "."))
    if unused_tables:
        w(f"- {n(unused_rows)} registros ({pct(unused_rows, total)}) pertenecen a "
          f"tablas que se extraen pero que el modelo actual no usa ({unused_names}). "
          "Se traen por el principio «traer todo pensando en necesidades futuras».")
    w("")

    # ---------------- by layer ----------------
    w("## Recorrido por capa")
    w("")
    tr_d, tr_h = per_target("stg_transform", rd), per_target("stg_transform", rh)
    lr_d, lr_h = per_target("stg_loadready", rd), per_target("stg_loadready", rh)
    profiled = scalar(STAGING, "SELECT COUNT(*) FROM staging_dw.stg_perfil WHERE run_id = :r", r=rs)
    with_nulls = scalar(STAGING, "SELECT COUNT(*) FROM staging_dw.stg_perfil WHERE run_id = :r AND nulos > 0", r=rs)
    findings = scalar(STAGING, "SELECT COUNT(*) FROM staging_dw.stg_error_log WHERE run_id = :r", r=rs)
    loaded = {t: loaded_count(t) for t, _ in tr_d + tr_h}
    specials = sum(scalar(DW, f"SELECT COUNT(*) FROM {t} WHERE {k} < 0")
                   for t, k in SPECIAL_MEMBERS.items())

    w(table(
        ["Capa", "Entra", "Sale", "Qué pasó"],
        [["1-2 · Extract + Initial Staging", n(total), n(total),
          f"{len(fun)} tablas leídas una vez; {n(profiled)} columnas perfiladas, "
          f"{n(with_nulls)} con nulos"],
         ["3 · Data Quality", n(total), n(total),
          f"{n(findings)} hallazgos registrados en el reporte de transacciones malas"],
         ["4 · Clean Staging", n(total), n(clean),
          f"{n(clean)} limpios, {n(rejected)} rechazados"],
         ["5 · Transformation", n(clean), n(sum(c for _, c in tr_d + tr_h)),
          f"{len(tr_d)} dimensiones y {len(tr_h)} hechos conformados"],
         ["6 · Load-Ready Publish", n(sum(c for _, c in tr_d + tr_h)),
          n(sum(c for _, c in lr_d + lr_h)), "forma definitiva, verificada contra las tablas destino"],
         ["7 · Load", n(sum(c for _, c in lr_d + lr_h)), n(sum(loaded.values())),
          "dimensiones por llave de negocio y hechos reemplazados, cada rama "
          "en una sola transacción. Aparte, el almacén tiene "
          f"{n(specials)} miembros especiales (Desconocido y Sin asignar)"]],
        ["l", "r", "r", "l"]))
    w("")
    w("Entre las capas 4 y 5 el número de filas cambia porque la transformación "
      "cambia el grano: varias tablas fuente se consolidan en una dimensión, "
      "`dim_tiempo` se genera sin fuente y las tablas no usadas por el modelo no "
      "continúan.")
    w("")

    # ---------------- funnel ----------------
    w("## Embudo por tabla fuente")
    w("")
    fr = []
    for f in fun:
        used = sorted({o for targets in lin.get(f["tabla"], {}).values() for o, _, _ in targets})
        fr.append([f["fuente"], f"`{f['tabla']}`", n(f["extraidas"]),
                   n(f["con_advertencia"]) if f["con_advertencia"] else "—",
                   n(f["rechazadas"]) if f["rechazadas"] else "—",
                   n(f["limpias"]),
                   ", ".join(f"`{u}`" for u in used) if used else "*no la usa el modelo*"])
    w(table(["Fuente", "Tabla", "Extraídas", "Con advertencia", "Rechazadas",
             "Limpias", "Alimenta a"], fr, ["l", "l", "r", "r", "r", "r", "l"]))
    w("")

    # ---------------- quality rules ----------------
    w("## Reglas de calidad (capa 3)")
    w("")
    clase_label = {"TECNICA": "Técnica", "NEGOCIO": "Negocio"}
    rr = [[f"`{name}`", clase_label.get(clase, clase or "—"),
           "Rechaza" if sev == "BLOQUEANTE" else "Advierte",
           n(ev), n(fa), pct(fa, ev)]
          for name, clase, sev, ev, fa in quality_rules(rs)]
    w(table(["Regla", "Clase", "Si falla", "Revisados", "Fallas", "% fallas"],
            rr, ["l", "l", "l", "r", "r", "r"]))
    w("")

    # ---------------- nulls ----------------
    w("## Nulos: de la fuente al almacén")
    w("")
    w("Para cada columna fuente con nulos, qué pasó con ellos. Las cifras del "
      "destino están en filas del destino, que pueden tener otro grano (por "
      "ejemplo, una orden tiene varias líneas).")
    w("")
    nr = []
    for tbl, col, nulos, filas in rows(STAGING, """
            SELECT tabla_origen, columna, nulos, filas FROM staging_dw.stg_perfil
             WHERE run_id = :r AND nulos > 0 ORDER BY tabla_origen, columna""", r=rs):
        targets = sorted(lin.get(tbl, {}).get(col, set()))
        meaning = NULL_MEANING.get((tbl, col), "")
        if not targets:
            destino, nulos_dest = "—", "—"
            trato = ("No pasa al modelo: la tabla no la usa el almacén"
                     if tbl not in lin else "No pasa al modelo")
        else:
            destino = ", ".join(f"`{o}.{c}`" for o, c, _ in targets)
            dest_nulls = [nulls_in_target(o, c) for o, c, _ in targets]
            nulos_dest = ", ".join(n(x) for x in dest_nulls)
            if sum(dest_nulls) > 0:
                trato = ("Se reemplaza por el miembro especial «Sin asignar»"
                         if all(null_as_member(o, c) for o, c, _ in targets)
                         else "Se conserva como NULL")
            elif all(o.startswith("dim_") for o, _, _ in targets):
                # Same grain as the source: the transformation removed the NULL.
                trato = "Resuelto en la transformación: el destino no tiene nulos"
            else:
                # A fact has another grain: zero NULLs there does not mean
                # anything was fixed, only that no fact row comes from the
                # source rows that had the NULL.
                trato = ("Sin efecto en el destino: ninguna fila del destino "
                         "proviene de los registros con nulo")
        nr.append([f"`{tbl}.{col}`", n(nulos), pct(nulos, filas), destino,
                   nulos_dest, trato, meaning])
    w(table(["Columna fuente", "Nulos", "%", "Destino", "Nulos en destino",
             "Tratamiento", "Qué significa"], nr,
            ["l", "r", "r", "l", "r", "l", "l"]))
    w("")

    # ---------------- decisions ----------------
    w("## Sobre qué datos se apoyan los análisis")
    w("")
    w(f"`fact_ventas` tiene {n(lines)} líneas por {money(amount)} en total. "
      "Estas son las decisiones que recortan la base de cada tipo de análisis:")
    w("")
    w(table(
        ["Situación", "Líneas", "% líneas", "Monto", "% monto"],
        [["Órdenes no efectivas (canceladas, en disputa o en espera)",
          n(noneff_n), pct(noneff_n, lines), money(noneff_amt), pct(noneff_amt, amount)],
         ["Órdenes aún no despachadas (sin días hasta el envío)",
          n(unshipped_n), pct(unshipped_n, lines), money(unshipped_amt), pct(unshipped_amt, amount)],
         ["Ventas sin vendedor resuelto («Sin asignar» o «Desconocido»)",
          n(norep_n), pct(norep_n, lines), money(norep_amt), pct(norep_amt, amount)]],
        ["l", "r", "r", "r", "r"]))
    w("")
    w(f"Las situaciones se solapan y no deben sumarse: {n(both_n)} de las líneas "
      "no despachadas pertenecen también a órdenes no efectivas (una orden "
      "cancelada tampoco sale de la bodega).")
    w("")
    w("En la práctica:")
    w("")
    w(f"- Los análisis de ventas y margen que usan solo **ventas efectivas** "
      f"se apoyan en el **{pct(amount - noneff_amt, amount)}** del monto. El resto "
      "existe en el almacén y se puede incluir filtrando por `dim_estado_orden.es_efectiva`.")
    w(f"- El **promedio de días hasta el envío** se calcula sobre el "
      f"**{pct(lines - unshipped_n, lines)}** de las líneas; las demás son órdenes "
      "que todavía no salieron y no tienen fecha de envío.")
    if norep_n == 0:
        w("- Los análisis **por vendedor u oficina** cubren el **100 %** del monto: "
          "los clientes sin vendedor asignado no tienen compras.")
    else:
        w(f"- Los análisis **por vendedor u oficina** cubren el "
          f"**{pct(amount - norep_amt, amount)}** del monto; el resto aparece bajo "
          "los miembros «Sin asignar» (cliente sin vendedor) o «Desconocido» "
          "(vendedor que no llegó al almacén).")
    w(f"- {n(no_orders)} de {n(customers)} clientes ({pct(no_orders, customers)}) "
      "no tienen ninguna compra. Cuentan en `dim_cliente` pero no pesan en ninguna "
      "medida de ventas.")
    w(f"- {n(unsold)} de {n(products)} productos ({pct(unsold, products)}) "
      + ("no se vendió nunca." if unsold == 1 else "no se vendieron nunca."))
    w(f"- Las {n(calls)} llamadas de servicio quedaron todas asociadas a un "
      "cliente, un producto y un agente: ninguna quedó huérfana.")
    w("")

    # ---------------- limits ----------------
    w("## Lo que el pipeline no verifica")
    w("")
    w("Para no sobrestimar lo que dicen los datos:")
    w("")
    w("- **El contenido de las notas de llamada** (`texto_llamada`) se carga como "
      "texto libre. Se mide su longitud, pero no se valida qué dice.")
    w("- **La consistencia entre fuentes** se compara solo en teléfono, ciudad, "
      "país y código postal para clientes, y en nombre, escala y proveedor para "
      "productos. Las direcciones y el resto de atributos no se contrastan; "
      "`classicmodels` se toma como fuente autoritativa.")
    w("- **La frescura del dato en origen.** Las fuentes son copias estáticas: la "
      "regla de oportunidad mide cuándo se cargó el almacén, no qué tan reciente "
      "es la información de las fuentes.")
    if unused_tables:
        w(f"- **Las tablas que el modelo no usa** ({unused_names}) pasan por "
          "las reglas de calidad pero no por las decisiones de modelado.")
    w("")
    return "\n".join(md) + "\n", {
        "total": total, "spotless": spotless, "warned": warned,
        "rejected": rejected, "unused": unused_rows}


if __name__ == "__main__":
    text, s = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text, encoding="utf-8")
    print(f"Report written to {OUT.relative_to(REPO)}")
    print(f"  extracted {s['total']}: {s['spotless']} clean without findings, "
          f"{s['warned']} with a warning, {s['rejected']} rejected, "
          f"{s['unused']} in tables the model does not use")
