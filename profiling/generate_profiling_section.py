"""
Genera la seccion 2 (Perfilamiento de Datos) dentro de PROYECTO FINAL.docx,
a partir de output/perfilamiento.csv, output/relaciones_fk.csv,
output/correspondencia_entidades.csv y output/relaciones_inferidas.csv.

Uso:
    python generate_profiling_section.py

Anade contenido al final del documento existente (despues de la seccion 1).
Requiere: pip install python-docx
"""
import csv
from pathlib import Path
from collections import OrderedDict, defaultdict

from docx import Document
from docx.shared import Pt
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

BASE_DIR = Path(__file__).resolve().parent.parent
DOCX_PATH = BASE_DIR / "PROYECTO FINAL.docx"
PROFILING_CSV = BASE_DIR / "output" / "perfilamiento.csv"
FK_CSV = BASE_DIR / "output" / "relaciones_fk.csv"
CORRESP_CSV = BASE_DIR / "output" / "correspondencia_entidades.csv"
INFERRED_CSV = BASE_DIR / "output" / "relaciones_inferidas.csv"


# ---------------------------------------------------------------------------
# Helpers de formato (el documento base no trae estilos con nombre como
# "Heading 1" o "Table Grid", asi que se aplican manualmente)
# ---------------------------------------------------------------------------

def set_table_borders(table):
    tbl = table._tbl
    tblPr = tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:space"), "0")
        el.set(qn("w:color"), "999999")
        borders.append(el)
    tblPr.append(borders)


def style_table(table):
    set_table_borders(table)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for row in table.rows:
        for cell in row.cells:
            for p in cell.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(9)


def bold_header_row(table):
    for cell in table.rows[0].cells:
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True


def add_heading(doc, text, level):
    sizes = {1: 16, 2: 13, 3: 11}
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(sizes.get(level, 11))
    p.paragraph_format.space_before = Pt(12 if level == 1 else 8)
    p.paragraph_format.space_after = Pt(6)
    return p


def add_bullet(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Pt(18)
    p.add_run(f"• {text}")
    return p


def add_simple_table(doc, headers, rows):
    table = doc.add_table(rows=1, cols=len(headers))
    hdr = table.rows[0].cells
    for i, htext in enumerate(headers):
        hdr[i].text = htext
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = "" if val in (None, "") else str(val)
    style_table(table)
    bold_header_row(table)
    doc.add_paragraph()
    return table


# ---------------------------------------------------------------------------
# Carga de datos
# ---------------------------------------------------------------------------

def load_profiling():
    tables = OrderedDict()
    with open(PROFILING_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["base_datos"], row["tabla"])
            tables.setdefault(key, []).append(row)
    return tables


def load_fk_health():
    with open(FK_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_correspondence():
    with open(CORRESP_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_inferred():
    with open(INFERRED_CSV, encoding="utf-8") as f:
        return list(csv.DictReader(f))


TABLE_LABELS = {
    ("classicmodels", "customers"): "customers",
    ("classicmodels", "employees"): "employees",
    ("classicmodels", "offices"): "offices",
    ("classicmodels", "orderdetails"): "orderdetails",
    ("classicmodels", "orders"): "orders",
    ("classicmodels", "payments"): "payments",
    ("classicmodels", "productlines"): "productlines",
    ("classicmodels", "products"): "products",
    ("customerservice", "cs_customer_calls"): "cs_customer_calls",
    ("customerservice", "cs_customer_products"): "cs_customer_products",
    ("customerservice", "cs_customers"): "cs_customers",
    ("customerservice", "cs_employees"): "cs_employees",
    ("customerservice", "cs_products"): "cs_products",
}


def main():
    doc = Document(DOCX_PATH)
    profiling = load_profiling()
    fk_health = load_fk_health()
    correspondence = load_correspondence()
    inferred = load_inferred()

    doc.add_page_break()
    add_heading(doc, "2. Perfilamiento de Datos", level=1)

    # ---------------------------------------------------------------
    # 2.1 Metodologia
    # ---------------------------------------------------------------
    add_heading(doc, "2.1 Metodologia y alcance", level=2)
    doc.add_paragraph(
        "El perfilamiento se realizo en tres niveles de profundidad creciente. "
        "Nivel 1 (perfil por columna): rangos, patrones de texto y % de nulos "
        "de cada columna de las 13 tablas, usando ydata-profiling sobre cada "
        "tabla y un script propio (Python, pandas) para consolidar los "
        "resultados. Nivel 2 (integridad referencial): validacion de cada "
        "llave foranea declarada en el esquema (filas huerfanas, % de FK "
        "nulas, cardinalidad observada), calculada con SQLAlchemy y pandas "
        "directamente contra las bases de datos restauradas. Nivel 3 "
        "(descubrimiento de relaciones implicitas): busqueda automatica de "
        "relaciones de contencion de valores (inclusion dependencies) entre "
        "columnas de ambas bases de datos, sin partir de las llaves "
        "foraneas conocidas, para identificar correspondencia real de datos "
        "entre las dos fuentes y relaciones no declaradas en el esquema. Los "
        "scripts usados se encuentran en la carpeta data_profiling/ del "
        "repositorio del proyecto."
    )

    # ---------------------------------------------------------------
    # 2.2 Perfilamiento por columna (Nivel 1)
    # ---------------------------------------------------------------
    add_heading(doc, "2.2 Perfilamiento por columna (Nivel 1)", level=2)
    doc.add_paragraph(
        "Para cada columna de las 13 tablas se calculo el % de valores "
        "nulos, la cantidad de valores distintos, el rango (minimo/maximo "
        "para numericos y fechas, o longitud minima/maxima para texto) y el "
        "patron de texto detectado."
    )

    by_db = defaultdict(list)
    for (bd, tabla) in profiling.keys():
        by_db[bd].append(tabla)

    for bd in ["classicmodels", "customerservice"]:
        add_heading(doc, f"Base de datos {bd}", level=3)
        for tabla in by_db[bd]:
            doc.add_paragraph().add_run(f"Tabla: {tabla}").bold = True
            rows = [
                [
                    c["columna"], f"{c['pct_nulos']}%", c["valores_distintos"],
                    c["min"] or "-", c["max"] or "-", c["patron_texto"] or "-",
                ]
                for c in profiling[(bd, tabla)]
            ]
            add_simple_table(
                doc,
                ["Columna", "% Nulos", "Distintos", "Min", "Max", "Patron"],
                rows,
            )

    add_heading(doc, "Hallazgos relevantes de calidad (Nivel 1)", level=3)
    for finding in [
        "addressLine2 tiene 81.97% de nulos en customers y en cs_customers "
        "(la mayoria de clientes no reporta una segunda linea de direccion, "
        "es un campo opcional legitimo, no un error de carga).",
        "state tiene 59.84% de nulos en customers/cs_customers y 42.86% en "
        "offices (aplica solo a paises con divisiones tipo estado/provincia, "
        "p. ej. USA; el resto del mundo no lo diligencia).",
        "orders.comments tiene 75.46% de nulos: la mayoria de ordenes no "
        "tiene comentarios asociados.",
        "productlines.htmlDescription y productlines.image estan 100% "
        "nulas en las 7 lineas de producto: son columnas sin uso, candidatas "
        "a excluir del repositorio de metadatos de negocio o a documentar "
        "como obsoletas.",
        "El rango de fechas de orders (2003-01-06 a 2005-06-11) y de "
        "cs_customer_calls (2003-02-19 a 2005-05-09) cubre practicamente el "
        "mismo periodo, lo que es consistente con que ambas fuentes "
        "describen la misma operacion del negocio en paralelo.",
        "email en employees y cs_employees fue clasificado con patron "
        "'email' en el 100% de los valores en ambas fuentes: formato "
        "consistente entre las dos bases de datos.",
    ]:
        add_bullet(doc, finding)

    # ---------------------------------------------------------------
    # 2.3 Integridad referencial (Nivel 2)
    # ---------------------------------------------------------------
    add_heading(doc, "2.3 Integridad referencial de las relaciones declaradas (Nivel 2)", level=2)
    doc.add_paragraph(
        "Para cada llave foranea declarada en el esquema de las dos bases de "
        "datos se calculo el numero de filas huerfanas (valor de FK que no "
        "existe en la tabla padre), el % de FK nulas y la cardinalidad "
        "observada (cuantos hijos tiene, como maximo, un mismo padre)."
    )
    add_simple_table(
        doc,
        ["BD", "Tabla hija", "Columna FK", "Tabla padre", "% FK nulas",
         "Huerfanas", "% Huerfanas", "Cardinalidad"],
        [
            [r["base_datos"], r["tabla_hija"], r["columna_fk"], r["tabla_padre"],
             f"{r['pct_fk_nulas']}%", r["filas_huerfanas"], f"{r['pct_huerfanas']}%",
             r["cardinalidad_observada"]]
            for r in fk_health
        ],
    )
    for finding in [
        "Las 13 relaciones declaradas (8 en classicmodels, 5 en "
        "customerservice) tienen 0% de filas huerfanas: no hay valores de "
        "llave foranea que apunten a un registro inexistente en ninguna de "
        "las dos bases de datos.",
        "Los unicos porcentajes de nulos relevantes en columnas FK son de "
        "origen de negocio, no de calidad: 18.03% en "
        "customers.salesRepEmployeeNumber (clientes sin representante de "
        "ventas asignado) y 4.35% en employees.reportsTo (el cargo mas alto "
        "de la jerarquia no reporta a nadie).",
        "Todas las relaciones son de cardinalidad 1:N; no se encontraron "
        "relaciones 1:1 en ninguna de las dos bases de datos.",
    ]:
        add_bullet(doc, finding)

    # ---------------------------------------------------------------
    # 2.4 Correspondencia entre entidades comunes
    # ---------------------------------------------------------------
    add_heading(doc, "2.4 Correspondencia y duplicados entre entidades comunes", level=2)
    doc.add_paragraph(
        "Para las tres entidades que existen en ambas fuentes (customers, "
        "employees, products) se comparo el conjunto de llaves de cada lado "
        "(cuantas estan solo en una fuente, solo en la otra, o en ambas), "
        "los duplicados dentro de cada fuente, y el % de coincidencia campo "
        "a campo para las llaves presentes en ambos lados."
    )
    add_simple_table(
        doc,
        ["Entidad", "Solo classicmodels", "Solo customerservice", "En ambas",
         "% Solapamiento", "Duplicados classicmodels", "Duplicados customerservice"],
        [
            [r["entidad"], r["llaves_solo_classicmodels"], r["llaves_solo_customerservice"],
             r["llaves_en_ambas"], f"{r['pct_solapamiento_jaccard']}%",
             r["duplicados_en_classicmodels"], r["duplicados_en_customerservice"]]
            for r in correspondence
        ],
    )

    doc.add_paragraph().add_run("% de coincidencia campo a campo (para llaves presentes en ambas fuentes)").bold = True
    field_cols = [k for k in correspondence[0].keys() if k.startswith("pct_coincidencia_")]
    add_simple_table(
        doc,
        ["Entidad"] + [c.replace("pct_coincidencia_", "") for c in field_cols],
        [
            [r["entidad"]] + [f"{r[c]}%" if r[c] else "-" for c in field_cols]
            for r in correspondence
        ],
    )

    for finding in [
        "customers <-> cs_customers: solapamiento del 100% (los 122 clientes "
        "de classicmodels estan tambien en customerservice, sin duplicados "
        "en ninguna fuente) y 100% de coincidencia en telefono, ciudad, "
        "estado, pais y codigo postal. Es una replica exacta de los datos "
        "de contacto del cliente.",
        "products <-> cs_products: mismo comportamiento, 100% de "
        "solapamiento y 100% de coincidencia en nombre, escala y proveedor "
        "del producto. Tambien es una replica exacta.",
        "employees <-> cs_employees: 0% de solapamiento (los 23 numeros de "
        "empleado de classicmodels y los 30 de customerservice no "
        "coinciden en ningun valor) y 0% de coincidencia en apellido, "
        "nombre y correo. Esto indica que NO son la misma poblacion de "
        "personas replicada entre las dos fuentes, sino dos plantillas de "
        "empleados distintas (fuerza de ventas vs. agentes de call center). "
        "Esta es una regla de negocio importante: employeeNumber no debe "
        "tratarse como comparable entre las dos bases de datos.",
    ]:
        add_bullet(doc, finding)

    # ---------------------------------------------------------------
    # 2.5 Descubrimiento de relaciones implicitas (Nivel 3)
    # ---------------------------------------------------------------
    add_heading(doc, "2.5 Descubrimiento de relaciones implicitas (Nivel 3)", level=2)
    doc.add_paragraph(
        "Se ejecuto un algoritmo de descubrimiento de dependencias de "
        "inclusion: para cada columna tipo identificador de las 13 tablas "
        "(de ambas bases de datos), se calculo que porcentaje de sus "
        "valores esta contenido en cada llave candidata de cualquier otra "
        "tabla (umbral >= 90%), sin partir de las llaves foraneas "
        "declaradas en el esquema."
    )

    declared_rediscovered = [r for r in inferred if r["ya_declarada_como_fk"] == "True"]
    add_heading(doc, "Validacion del metodo", level=3)
    doc.add_paragraph(
        f"El algoritmo redescubrio automaticamente las {len(declared_rediscovered)} "
        "relaciones de llave foranea que ya estaban declaradas en el esquema "
        "(100% de recall sobre las 13 relaciones de la seccion 2.3), lo que "
        "valida el metodo antes de confiar en las relaciones nuevas que "
        "encontro."
    )

    add_heading(doc, "Relaciones nuevas encontradas (no declaradas en el esquema)", level=3)
    doc.add_paragraph(
        "Las mas relevantes son las que cruzan de una base de datos a la "
        "otra (imposibles de declarar como FK real porque son motores "
        "distintos, pero validas como relacion de negocio):"
    )
    cross_new = [
        r for r in inferred
        if r["cruza_bases_de_datos"] == "True" and r["ya_declarada_como_fk"] == "False"
    ]
    # Curaduria: nos quedamos con relaciones semanticamente interesantes
    # (excluye repeticiones exactas en sentido inverso de la misma pareja).
    seen_pairs = set()
    curated = []
    for r in cross_new:
        a, b = r["tabla_columna_origen"], r["tabla_columna_destino_llave"]
        pair_key = tuple(sorted([a.rsplit(".", 1)[0], b.rsplit(".", 1)[0]]))
        col_key = tuple(sorted([a, b]))
        if col_key in seen_pairs:
            continue
        seen_pairs.add(col_key)
        curated.append(r)

    add_simple_table(
        doc,
        ["Columna origen", "Contenida en (llave)", "% Contencion"],
        [[r["tabla_columna_origen"], r["tabla_columna_destino_llave"], f"{r['pct_contencion']}%"]
         for r in curated],
    )
    for finding in [
        "customers.customerNumber y todos sus campos de contacto/direccion "
        "corresponden 1 a 1 con cs_customers: confirma numericamente lo "
        "encontrado en la seccion 2.4.",
        "products.productCode y sus atributos descriptivos corresponden 1 a "
        "1 con cs_products, y a su vez con orderdetails.productCode: el "
        "catalogo de producto es consistente en toda la organizacion.",
        "cs_customer_calls.customernumber y cs_customer_products.customernumber "
        "son subconjuntos de customers.customerNumber (54 de 122 y 75 de 122 "
        "clientes respectivamente): no todos los clientes han llamado o "
        "tienen productos de interes registrados, lo cual es coherente con "
        "el negocio (el call center no interactua con el 100% de la base "
        "de clientes).",
        "cs_customer_calls.productcode y cs_customer_products.productcode "
        "son subconjuntos de products.productCode (47 y 64 de "
        "aproximadamente 110 productos): solo una parte del catalogo ha "
        "generado llamadas o interes registrado.",
    ]:
        add_bullet(doc, finding)

    add_heading(doc, "Limitaciones: falsos positivos por dominios pequenos", level=3)
    doc.add_paragraph(
        "El algoritmo tambien senalo relaciones sin significado de negocio, "
        "producto de columnas con rangos numericos pequenos que por "
        "coincidencia caben dentro de otro rango mas amplio (por ejemplo, "
        "offices.officeCode toma valores 1 a 7, que estan contenidos en "
        "cs_employees.employeenumber, cuyo rango es 1 a 30, sin que exista "
        "ninguna relacion real entre una oficina y un numero de empleado). "
        "Este tipo de coincidencias se descartaron manualmente revisando el "
        "significado de negocio de cada columna; se documentan aqui como "
        "limitacion del metodo automatico: la deteccion por contencion de "
        "valores no reemplaza el juicio experto sobre el significado "
        "semantico de cada columna, especialmente en dominios numericos "
        "pequenos (codigos de 1 a 2 digitos)."
    )
    false_positive_pairs = [
        ("employees.officeCode", "cs_employees.employeenumber / cs_customer_calls.employeenumber"),
        ("offices.officeCode", "cs_employees.employeenumber / cs_customer_calls.employeenumber"),
        ("orderdetails.orderLineNumber", "cs_employees.employeenumber / cs_customer_calls.employeenumber"),
        ("employees.officeCode", "orderdetails.orderLineNumber"),
        ("offices.officeCode", "orderdetails.orderLineNumber"),
    ]
    add_simple_table(
        doc,
        ["Columna origen", "Coincide por casualidad con", "Motivo de descarte"],
        [[a, b, "Dominios numericos pequenos que se solapan sin relacion de negocio real"]
         for a, b in false_positive_pairs],
    )

    # ---------------------------------------------------------------
    # 2.6 Conclusiones
    # ---------------------------------------------------------------
    add_heading(doc, "2.6 Conclusiones del perfilamiento", level=2)
    for c in [
        "La calidad de los datos es alta en ambas fuentes: no se "
        "encontraron filas huerfanas en ninguna de las 13 relaciones "
        "declaradas, y los porcentajes de nulos encontrados corresponden a "
        "reglas de negocio legitimas, no a errores de captura.",
        "customers/cs_customers y products/cs_products son candidatos "
        "directos a unificarse como una unica entidad de negocio en el "
        "repositorio de metadatos, dado que son replicas exactas.",
        "employees/cs_employees NO deben tratarse como la misma entidad de "
        "negocio replicada: representan dos poblaciones de personas "
        "distintas y deben documentarse como entidades de negocio "
        "separadas (o como la misma entidad con dos poblaciones "
        "disjuntas, segun se defina en el glosario de negocio).",
        "productlines.htmlDescription y productlines.image no tienen "
        "ningun dato cargado; se recomienda excluirlas del alcance del "
        "repositorio de metadatos de negocio o marcarlas explicitamente "
        "como no utilizadas.",
        "El descubrimiento automatico de relaciones (Nivel 3) es util para "
        "encontrar candidatos de correspondencia entre fuentes que no "
        "comparten un motor de base de datos, pero requiere validacion "
        "experta para descartar coincidencias numericas sin significado de "
        "negocio.",
    ]:
        add_bullet(doc, c)

    try:
        doc.save(DOCX_PATH)
        print(f"Seccion de Perfilamiento anadida a {DOCX_PATH}")
    except PermissionError:
        fallback = DOCX_PATH.with_name("PROYECTO FINAL (actualizado).docx")
        doc.save(fallback)
        print(
            f"'{DOCX_PATH.name}' esta abierto (permiso denegado). "
            f"Se guardo el resultado en: {fallback}"
        )


if __name__ == "__main__":
    main()
