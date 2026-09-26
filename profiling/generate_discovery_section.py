"""
Genera la seccion 1 (Descubrimiento de Metadatos) dentro de PROYECTO FINAL.docx,
a partir de output/metadata_tecnico.csv y output/perfilamiento.csv.

Uso:
    python generate_discovery_section.py

Anade contenido al final del documento existente (respeta la portada).
Requiere: pip install python-docx
"""
import csv
from pathlib import Path
from collections import OrderedDict, defaultdict

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from docx.enum.table import WD_TABLE_ALIGNMENT

BASE_DIR = Path(__file__).resolve().parent.parent
DOCX_PATH = BASE_DIR / "PROYECTO FINAL.docx"
METADATA_CSV = BASE_DIR / "output" / "metadata_tecnico.csv"
PROFILING_CSV = BASE_DIR / "output" / "perfilamiento.csv"

# ---------------------------------------------------------------------------
# Descripciones de negocio de cada tabla (metadato de negocio a nivel tabla)
# ---------------------------------------------------------------------------
TABLE_DESCRIPTIONS = {
    ("classicmodels", "customers"): "Clientes de la compania que realizan ordenes de compra.",
    ("classicmodels", "employees"): "Empleados de la companias, incluye representantes de ventas y su jerarquia.",
    ("classicmodels", "offices"): "Oficinas o sedes fisicas de la compania.",
    ("classicmodels", "orders"): "Encabezado de las ordenes de compra realizadas por los clientes.",
    ("classicmodels", "orderdetails"): "Detalle (lineas) de cada orden de compra: producto, cantidad y precio.",
    ("classicmodels", "payments"): "Pagos realizados por los clientes asociados a sus ordenes de compra.",
    ("classicmodels", "products"): "Catalogo de productos que la compania vende.",
    ("classicmodels", "productlines"): "Lineas o categorias de productos.",
    ("customerservice", "cs_customers"): "Clientes registrados en el sistema de call center.",
    ("customerservice", "cs_employees"): "Empleados que atienden llamadas en el call center.",
    ("customerservice", "cs_products"): "Catalogo de productos referenciado en las llamadas de servicio.",
    ("customerservice", "cs_customer_calls"): "Registro de llamadas de servicio al cliente (empleado, cliente y producto involucrados).",
    ("customerservice", "cs_customer_products"): "Relacion entre clientes y productos sobre los que se han generado llamadas o consultas.",
}

DB_ENGINE = {
    "classicmodels": "MySQL",
    "customerservice": "PostgreSQL",
}

DB_DESCRIPTIONS = {
    "classicmodels": (
        "Base de datos transaccional (MySQL) que soporta el proceso de ventas: clientes, "
        "empleados/representantes de ventas, oficinas, catalogo de productos, ordenes de "
        "compra, su detalle y los pagos asociados."
    ),
    "customerservice": (
        "Base de datos de atencion al cliente (PostgreSQL) que registra las llamadas del "
        "call center, relacionando cada llamada con el empleado que la atendio, el cliente "
        "que llama y el producto sobre el cual se consulta."
    ),
}


FIELDNAMES = ["base_datos", "tabla", "columna", "tipo_dato", "permite_nulo", "es_pk", "es_fk", "referencia"]


def load_metadata():
    tables = OrderedDict()
    with open(METADATA_CSV, encoding="utf-8") as f:
        first_line = f.readline()
        delimiter = ";" if first_line.count(";") > first_line.count(",") else ","
        f.seek(0)
        raw_reader = csv.reader(f, delimiter=delimiter)
        next(raw_reader)  # descartar encabezado (puede venir resalvado desde Excel)
        for values in raw_reader:
            if not values:
                continue
            row = dict(zip(FIELDNAMES, values))
            key = (row["base_datos"], row["tabla"])
            tables.setdefault(key, []).append(row)
    return tables


def load_row_counts():
    counts = {}
    with open(PROFILING_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = (row["base_datos"], row["tabla"])
            counts[key] = row["total_filas"]
    return counts


def set_table_borders(table):
    """Dibuja bordes simples por XML: el documento base no trae el estilo
    con nombre 'Table Grid', asi que se agregan directamente al tblPr."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

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
    """El documento base no define estilos Heading 1/2/3, asi que se simula
    el encabezado con tamano y negrita segun el nivel."""
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


def add_column_table(doc, cols):
    table = doc.add_table(rows=1, cols=5)
    hdr = table.rows[0].cells
    headers = ["Columna", "Tipo de dato", "Permite nulo", "PK", "FK -> referencia"]
    for i, htext in enumerate(headers):
        hdr[i].text = htext
    for c in cols:
        cells = table.add_row().cells
        cells[0].text = c["columna"]
        cells[1].text = c["tipo_dato"]
        cells[2].text = c["permite_nulo"]
        cells[3].text = "PK" if c["es_pk"] == "True" else ""
        cells[4].text = f"FK -> {c['referencia']}" if c["es_fk"] == "True" else ""
    style_table(table)
    bold_header_row(table)
    doc.add_paragraph()


def add_simple_table(doc, headers, rows):
    table = doc.add_table(rows=1, cols=len(headers))
    hdr = table.rows[0].cells
    for i, htext in enumerate(headers):
        hdr[i].text = htext
    for row in rows:
        cells = table.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = str(val)
    style_table(table)
    bold_header_row(table)
    doc.add_paragraph()


def add_document_intro(doc):
    doc.add_page_break()

    add_heading(doc, "Introduccion", level=1)
    doc.add_paragraph(
        "Este documento presenta el desarrollo del proyecto final del curso Modelos y "
        "Persistencia de Datos, cuyo proposito es integrar dos fuentes de datos de una "
        "organizacion -classicmodels (MySQL), que soporta el proceso transaccional de "
        "ventas, y customerservice (PostgreSQL), que registra la atencion al cliente en "
        "el call center- e implementar la capa de persistencia de un repositorio de "
        "metadatos que consolide sus metadatos tecnicos y de negocio, permitiendo "
        "trazar el linaje semantico entre ambos."
    )

    add_heading(doc, "Objetivos", level=1)

    doc.add_paragraph().add_run("Objetivo general").bold = True
    doc.add_paragraph(
        "Documentar el descubrimiento y perfilamiento de los metadatos de las fuentes "
        "classicmodels y customerservice, y disenar e implementar un repositorio de "
        "metadatos que integre sus metadatos tecnicos y de negocio con trazabilidad de "
        "linaje semantico."
    )

    doc.add_paragraph().add_run("Objetivos especificos").bold = True
    for obj in [
        "Identificar y documentar los metadatos tecnicos (tablas, columnas, tipos de "
        "dato, llaves primarias y foraneas) de las dos fuentes de datos, asi como las "
        "reglas de negocio implicitas en su estructura.",
        "Realizar el perfilamiento de los datos de ambas fuentes, evaluando rangos, "
        "patrones de texto, porcentaje de nulos, y la correspondencia o duplicidad de "
        "datos entre las estructuras que tienen en comun.",
        "Disenar e implementar el modelo fisico de un repositorio de metadatos que "
        "integre, mediante procesos automaticos (ETL), los metadatos tecnicos de las "
        "dos fuentes, junto con metadatos de negocio registrados manualmente.",
        "Habilitar el analisis de linaje semantico en el repositorio, conectando los "
        "metadatos tecnicos con los metadatos de negocio correspondientes.",
        "Formular y ejecutar consultas sobre el repositorio de metadatos que permitan "
        "resolver las preguntas de negocio planteadas en el enunciado del proyecto.",
    ]:
        add_bullet(doc, obj)


def main():
    doc = Document(DOCX_PATH)
    tables = load_metadata()
    row_counts = load_row_counts()

    add_document_intro(doc)

    doc.add_page_break()
    add_heading(doc, "1. Descubrimiento de Metadatos", level=1)

    # 1.1 Introduccion
    add_heading(doc, "1.1 Alcance de la seccion", level=2)
    doc.add_paragraph(
        "Esta seccion documenta los metadatos tecnicos y de negocio identificados en las "
        "dos fuentes de datos del ejercicio: classicmodels (MySQL) y customerservice "
        "(PostgreSQL). El objetivo es entender la estructura fisica de cada fuente, las "
        "reglas de negocio implicitas en sus llaves y relaciones, y las estructuras que "
        "ambas fuentes tienen en comun frente a las que son exclusivas de cada una."
    )

    # 1.2 Metadatos tecnicos por fuente
    add_heading(doc, "1.2 Metadatos tecnicos por fuente", level=2)

    by_db = defaultdict(list)
    for (bd, tabla) in tables.keys():
        by_db[bd].append(tabla)

    for bd in ["classicmodels", "customerservice"]:
        add_heading(doc, f"1.2.{1 if bd=='classicmodels' else 2} Base de datos {bd} ({DB_ENGINE[bd]})", level=3)
        doc.add_paragraph(DB_DESCRIPTIONS[bd])

        # Tabla resumen de tablas de la BD
        summary_rows = []
        for tabla in by_db[bd]:
            cols = tables[(bd, tabla)]
            pk_cols = [c["columna"] for c in cols if c["es_pk"] == "True"]
            summary_rows.append([
                tabla,
                TABLE_DESCRIPTIONS.get((bd, tabla), ""),
                row_counts.get((bd, tabla), ""),
                ", ".join(pk_cols) if pk_cols else "(ninguna definida)",
            ])
        add_simple_table(
            doc,
            ["Tabla", "Descripcion de negocio", "# filas (aprox.)", "Llave primaria"],
            summary_rows,
        )

        for tabla in by_db[bd]:
            doc.add_paragraph().add_run(f"Tabla: {tabla}").bold = True
            add_column_table(doc, tables[(bd, tabla)])

    # 1.3 Reglas de negocio identificadas en los metadatos
    add_heading(doc, "1.3 Reglas de negocio identificadas en los metadatos", level=2)

    add_heading(doc, "classicmodels (MySQL)", level=3)
    for rule in [
        "Un cliente (customers) puede ser atendido por, a lo sumo, un representante de "
        "ventas (employees), relacion N:1 opcional (salesRepEmployeeNumber permite nulo).",
        "Un empleado puede reportar a otro empleado (reportsTo), lo que define una "
        "jerarquia recursiva dentro de employees.",
        "Todo empleado pertenece a una oficina (officeCode), relacion N:1 obligatoria.",
        "Toda orden (orders) pertenece a un unico cliente, relacion N:1 obligatoria.",
        "Una orden tiene una o mas lineas de detalle (orderdetails); la llave primaria "
        "compuesta (orderNumber, productCode) garantiza que un producto no se repita en "
        "la misma orden.",
        "Todo producto (products) pertenece a una linea de producto (productlines), "
        "relacion N:1 obligatoria.",
        "Un pago (payments) se identifica por la combinacion (customerNumber, "
        "checkNumber); un mismo cliente puede tener multiples pagos, cada uno con un "
        "numero de cheque distinto.",
        "El campo status de orders tiene un dominio cerrado de valores (6 valores "
        "distintos segun el perfilamiento, p. ej. Shipped, Cancelled, In Process).",
    ]:
        add_bullet(doc, rule)

    add_heading(doc, "customerservice (PostgreSQL)", level=3)
    for rule in [
        "Cada llamada (cs_customer_calls) relaciona exactamente un empleado, un cliente "
        "y un producto; la tabla no tiene llave primaria propia, lo que sugiere un diseno "
        "tipo registro de evento/transaccion sin necesidad de identificador unico expuesto.",
        "cs_customer_products es una relacion N:M entre clientes y productos (llave "
        "primaria compuesta customernumber, productcode), que registra que productos "
        "estan asociados a que clientes en el contexto de servicio (no necesariamente "
        "de compra).",
        "Los catalogos de cliente, empleado y producto (cs_customers, cs_employees, "
        "cs_products) son replicas simplificadas de los maestros del dominio "
        "transaccional, usadas unicamente como referencia para las llamadas.",
    ]:
        add_bullet(doc, rule)

    # 1.4 Estructuras comunes entre las dos fuentes
    add_heading(doc, "1.4 Estructuras en comun entre las dos fuentes", level=2)
    doc.add_paragraph(
        "Las siguientes entidades existen en ambas fuentes de datos, aunque con "
        "diferencias en el conjunto de atributos disponibles:"
    )
    add_simple_table(
        doc,
        ["Entidad", "Tabla classicmodels", "Tabla customerservice", "Diferencias principales"],
        [
            [
                "Cliente",
                "customers",
                "cs_customers",
                "classicmodels agrega creditLimit y salesRepEmployeeNumber "
                "(atributos comerciales/financieros no necesarios para el call center).",
            ],
            [
                "Empleado",
                "employees",
                "cs_employees",
                "cs_employees es un subconjunto minimo (numero, nombre, apellido, "
                "email); classicmodels agrega extension, officeCode, reportsTo y "
                "jobTitle (estructura organizacional).",
            ],
            [
                "Producto",
                "products",
                "cs_products",
                "Estructura casi identica en datos descriptivos (nombre, escala, "
                "vendedor, descripcion); classicmodels agrega productLine, "
                "quantityInStock, buyPrice y MSRP (atributos de inventario/precio).",
            ],
        ],
    )

    # 1.5 Estructuras exclusivas
    add_heading(doc, "1.5 Estructuras exclusivas de cada fuente", level=2)
    doc.add_paragraph(
        "Solo en classicmodels: offices, orders, orderdetails, payments y productlines "
        "— es decir, todo el dominio transaccional de ventas (ordenes, pagos, oficinas y "
        "categorizacion de productos), que no tiene equivalente en customerservice."
    )
    doc.add_paragraph(
        "Solo en customerservice: cs_customer_calls (registro de interacciones de "
        "servicio) y cs_customer_products (relacion cliente-producto de interes o "
        "consulta), sin equivalente directo en classicmodels."
    )

    # 1.6 Metadatos de negocio
    add_heading(doc, "1.6 Metadatos de negocio", level=2)
    doc.add_paragraph(
        "Los metadatos de negocio identifican las entidades relevantes para la "
        "organizacion, independientemente de en que base de datos o tabla fisica se "
        "almacenen. Se registran manualmente en el repositorio de metadatos (ver seccion "
        "3) y se muestran aqui como referencia:"
    )
    add_simple_table(
        doc,
        ["Entidad de negocio", "Descripcion", "Dominio de datos"],
        [
            ["Cliente", "Persona o empresa que adquiere productos de la compania o que es atendida por el call center.", "Ventas / Servicio al cliente"],
            ["Empleado", "Persona que trabaja en la organizacion, ya sea en ventas o en el call center.", "Recursos humanos"],
            ["Producto", "Articulo del catalogo que la compania vende y sobre el cual se generan ordenes o llamadas.", "Catalogo de productos"],
            ["Orden de compra", "Transaccion de venta realizada por un cliente, compuesta por uno o mas productos.", "Ventas"],
            ["Pago", "Registro de un pago realizado por un cliente asociado a sus compras.", "Finanzas / Cartera"],
            ["Llamada de servicio", "Interaccion de un cliente con el call center relacionada con un producto y atendida por un empleado.", "Servicio al cliente"],
        ],
    )

    # 1.7 Linaje semantico (vista preliminar)
    add_heading(doc, "1.7 Linaje semantico (vista preliminar)", level=2)
    doc.add_paragraph(
        "El linaje semantico conecta cada columna tecnica con el atributo de negocio que "
        "representa. A modo de ejemplo (el detalle completo, generado desde el "
        "repositorio de metadatos, se presenta en la seccion de Consultas), para la "
        "tabla cs_customers:"
    )
    add_simple_table(
        doc,
        ["Columna", "Tipo de dato", "Atributo de negocio", "Definicion del atributo", "Entidad de negocio"],
        [
            ["customernumber", "integer", "Identificador de cliente", "Codigo unico que identifica a un cliente.", "Cliente"],
            ["contactfirstname", "character varying(50)", "Nombre de contacto", "Primer nombre de la persona de contacto del cliente.", "Cliente"],
            ["contactlastname", "character varying(50)", "Apellido de contacto", "Apellido de la persona de contacto del cliente.", "Cliente"],
            ["phone", "character varying(50)", "Telefono de contacto", "Numero telefonico para comunicarse con el cliente.", "Cliente"],
            ["city", "character varying(50)", "Ciudad", "Ciudad de ubicacion del cliente.", "Cliente"],
            ["country", "character varying(50)", "Pais", "Pais de ubicacion del cliente.", "Cliente"],
        ],
    )

    try:
        doc.save(DOCX_PATH)
        print(f"Seccion de Descubrimiento anadida a {DOCX_PATH}")
    except PermissionError:
        fallback = DOCX_PATH.with_name("PROYECTO FINAL (actualizado).docx")
        doc.save(fallback)
        print(
            f"'{DOCX_PATH.name}' esta abierto (permiso denegado). "
            f"Se guardo el resultado en: {fallback}"
        )


if __name__ == "__main__":
    main()
