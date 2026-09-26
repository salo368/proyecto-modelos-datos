"""
Test of the rejection path of the Data Quality layer.

The real source data has no blocking defects, so a normal load leaves
stg_rejected empty. This test builds a synthetic batch with one defect
per rule type and checks that:

  1. each defect is caught by the rule it belongs to;
  2. blocking (RECHAZADO) failures send the record to the rejected set;
  3. warnings (ADVERTENCIA) let the record through;
  4. the children of a rejected record are rejected too, down every
     level (customer -> order -> order line), so nothing that reaches
     Clean Staging points to a record that did not;
  5. no healthy record is flagged.

It calls the same functions as the ETL on in-memory data and writes
nothing; it only reads the NOT NULL columns from the metadata repository.

Usage:
    python pipeline/tests/test_dq_reject_path.py
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from layer3_data_quality import (QualityLog, business_checks,  # noqa: E402
                                 cascade_rejections, technical_checks)
from layer4_clean_staging import rejection_reasons  # noqa: E402


# A date after the load, relative to today so the test never expires.
FUTURE = date.today() + timedelta(days=30)


def batch(source, rows):
    return source, pd.DataFrame([{"_nro_fila": i, **r} for i, r in enumerate(rows, 1)])


# One healthy record per table plus records with a single defect each.
# The comment above each defect names the rule expected to catch it.
DATA = {
    "customers": batch("classicmodels", [
        {"customerNumber": 1, "customerName": "Sano", "contactLastName": "A",
         "contactFirstName": "B", "phone": "1", "addressLine1": "x", "city": "c",
         "country": "p", "postalCode": "1", "salesRepEmployeeNumber": 10,
         "creditLimit": 100.0},
        # cliente_con_vendedor (warning): no sales rep
        {"customerNumber": 2, "customerName": "Sin vendedor", "contactLastName": "A",
         "contactFirstName": "B", "phone": "2", "addressLine1": "x", "city": "c",
         "country": "p", "postalCode": "2", "salesRepEmployeeNumber": None,
         "creditLimit": 100.0},
        # campos_obligatorios (reject): customerName is NOT NULL
        {"customerNumber": 3, "customerName": None, "contactLastName": "A",
         "contactFirstName": "B", "phone": "3", "addressLine1": "x", "city": "c",
         "country": "p", "postalCode": "3", "salesRepEmployeeNumber": 10,
         "creditLimit": 100.0},
    ]),
    "employees": batch("classicmodels", [
        {"employeeNumber": 10, "lastName": "V", "firstName": "W", "extension": "x1",
         "email": "v@empresa.com", "officeCode": "1", "reportsTo": None, "jobTitle": "Sales"},
        # formato_email (warning)
        {"employeeNumber": 11, "lastName": "V", "firstName": "W", "extension": "x2",
         "email": "sin-arroba", "officeCode": "1", "reportsTo": None, "jobTitle": "Sales"},
    ]),
    "offices": batch("classicmodels", [
        {"officeCode": "1", "city": "c", "phone": "1", "addressLine1": "x",
         "country": "p", "postalCode": "1", "territory": "NA"},
    ]),
    "productlines": batch("classicmodels", [{"productLine": "Cars"}]),
    "products": batch("classicmodels", [
        {"productCode": "P1", "productName": "Auto", "productLine": "Cars",
         "productScale": "1:10", "productVendor": "V", "productDescription": "d",
         "quantityInStock": 5, "buyPrice": 10.0, "MSRP": 20.0},
        # precio_sugerido_coherente (warning): MSRP below cost
        {"productCode": "P2", "productName": "Barato", "productLine": "Cars",
         "productScale": "1:10", "productVendor": "V", "productDescription": "d",
         "quantityInStock": 5, "buyPrice": 30.0, "MSRP": 20.0},
    ]),
    "orders": batch("classicmodels", [
        {"orderNumber": 100, "orderDate": "2004-01-10", "requiredDate": "2004-01-20",
         "shippedDate": "2004-01-12", "status": "Shipped", "customerNumber": 1},
        # secuencia_de_fechas (reject): shipped before ordered
        {"orderNumber": 101, "orderDate": "2004-01-10", "requiredDate": "2004-01-20",
         "shippedDate": "2004-01-05", "status": "Shipped", "customerNumber": 1},
        # envio_consistente_con_estado (reject): Shipped without shippedDate
        {"orderNumber": 102, "orderDate": "2004-01-10", "requiredDate": "2004-01-20",
         "shippedDate": None, "status": "Shipped", "customerNumber": 1},
        # tipo_de_dato_valido (reject): unparseable date
        {"orderNumber": 103, "orderDate": "no-es-fecha", "requiredDate": "2004-01-20",
         "shippedDate": None, "status": "In Process", "customerNumber": 1},
        # padre_rechazado (reject): healthy, but its customer #3 was rejected
        {"orderNumber": 104, "orderDate": "2004-01-10", "requiredDate": "2004-01-20",
         "shippedDate": None, "status": "In Process", "customerNumber": 3},
        # fecha_no_futura (reject): ordered after the load
        {"orderNumber": 105, "orderDate": FUTURE.isoformat(),
         "requiredDate": (FUTURE + timedelta(days=10)).isoformat(),
         "shippedDate": None, "status": "In Process", "customerNumber": 1},
    ]),
    "orderdetails": batch("classicmodels", [
        {"orderNumber": 100, "productCode": "P1", "quantityOrdered": 2,
         "priceEach": 15.0, "orderLineNumber": 1},
        # integridad_referencial (reject): unknown product
        {"orderNumber": 100, "productCode": "NO_EXISTE", "quantityOrdered": 2,
         "priceEach": 15.0, "orderLineNumber": 2},
        # valores_positivos (reject): negative quantity
        {"orderNumber": 100, "productCode": "P1", "quantityOrdered": -3,
         "priceEach": 15.0, "orderLineNumber": 3},
        # padre_rechazado (reject): line of order 101, rejected for its dates
        {"orderNumber": 101, "productCode": "P1", "quantityOrdered": 1,
         "priceEach": 15.0, "orderLineNumber": 1},
        # padre_rechazado (reject), second level: line of order 104, whose
        # customer was rejected
        {"orderNumber": 104, "productCode": "P1", "quantityOrdered": 1,
         "priceEach": 15.0, "orderLineNumber": 1},
    ]),
    "cs_customers": batch("customerservice", [
        {"customernumber": 1, "phone": "1", "city": "c", "country": "p", "postalcode": "1"},
        # consistencia_entre_fuentes_cliente (warning): different city
        {"customernumber": 2, "phone": "2", "city": "OTRA", "country": "p", "postalcode": "2"},
        {"customernumber": 3, "phone": "3", "city": "c", "country": "p", "postalcode": "3"},
    ]),
    "cs_products": batch("customerservice", [
        {"productcode": "P1", "productname": "Auto", "productscale": "1:10", "productvendor": "V"},
    ]),
    "cs_employees": batch("customerservice", [
        {"employeenumber": 50, "lastname": "A", "firstname": "B", "email": "a@b.co"},
    ]),
    "cs_customer_calls": batch("customerservice", [
        {"employeenumber": 50, "customernumber": 1, "productcode": "P1",
         "text": "ok", "date": "2004-02-01"},
        # integridad_referencial (reject): customer missing from both sources
        {"employeenumber": 50, "customernumber": 999, "productcode": "P1",
         "text": "huerfana", "date": "2004-02-01"},
        # padre_rechazado (reject), across sources: customer #3 exists in
        # both, but classicmodels rejected it
        {"employeenumber": 50, "customernumber": 3, "productcode": "P1",
         "text": "cliente rechazado", "date": "2004-02-01"},
    ]),
}

# (table, row number) -> (expected rule, must be rejected)
EXPECTED = {
    ("customers", 2):         ("cliente_con_vendedor", False),
    ("customers", 3):         ("campos_obligatorios", True),
    ("employees", 2):         ("formato_email", False),
    ("products", 2):          ("precio_sugerido_coherente", False),
    ("orders", 2):            ("secuencia_de_fechas", True),
    ("orders", 3):            ("envio_consistente_con_estado", True),
    ("orders", 4):            ("tipo_de_dato_valido", True),
    ("orders", 5):            ("padre_rechazado", True),
    ("orders", 6):            ("fecha_no_futura", True),
    ("orderdetails", 2):      ("integridad_referencial", True),
    ("orderdetails", 3):      ("valores_positivos", True),
    ("orderdetails", 4):      ("padre_rechazado", True),
    ("orderdetails", 5):      ("padre_rechazado", True),
    ("cs_customers", 2):      ("consistencia_entre_fuentes_cliente", False),
    ("cs_customer_calls", 2): ("integridad_referencial", True),
    ("cs_customer_calls", 3): ("padre_rechazado", True),
}


def main():
    log = QualityLog()
    technical_checks(DATA, log)
    business_checks(DATA, log)
    cascade_rejections(DATA, log)
    rejected = rejection_reasons(log.failures)

    detected = {}
    for f in log.failures:
        detected.setdefault((f["tabla_origen"], f["nro_fila"]), set()).add(f["regla"])

    print(f"{'Record':<24}{'Expected rule':<38}{'Caught':>8}{'Outcome':>12}   Status")
    print("-" * 92)
    all_ok = True
    for (table, row), (rule, must_reject) in EXPECTED.items():
        caught = rule in detected.get((table, row), set())
        was_rejected = (table, row) in rejected
        ok = caught and was_rejected == must_reject
        all_ok &= ok
        outcome = "rejected" if was_rejected else "clean"
        print(f"{table + ' #' + str(row):<24}{rule:<38}{'yes' if caught else 'NO':>8}"
              f"{outcome:>12}   {'OK' if ok else 'FAIL'}")

    healthy_flagged = [key for key in detected if key not in EXPECTED]
    print()
    if healthy_flagged:
        all_ok = False
        print(f"FAIL: healthy records flagged as defective: {healthy_flagged}")
    else:
        print("No healthy record was flagged.")

    print()
    print("The rejection path works." if all_ok
          else "Some rules do not behave as expected.")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
