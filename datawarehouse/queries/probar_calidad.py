"""
Prueba del camino de rechazo de la capa de Data Quality.

Los datos reales de classicmodels y customerservice no tienen defectos
graves: en una carga normal la pila de rechazados queda vacia. Eso deja
sin ejercitar justo la parte del pipeline que existe para cuando algo
sale mal.

Esta prueba arma un lote SINTETICO con un defecto por cada tipo de regla
y verifica tres cosas:

  1. Que cada defecto lo detecte la regla que le corresponde.
  2. Que las fallas BLOQUEANTES manden el registro a la pila roja.
  3. Que las ADVERTENCIAS dejen pasar el registro, trazado.

No escribe nada en el almacen ni en staging: usa las mismas funciones del
ETL (tech_dq_checks, bus_dq_check, motivos_de_rechazo) sobre datos en
memoria. Solo lee del repositorio de metadatos las columnas obligatorias,
igual que en una carga real.

Uso:
    python datawarehouse/queries/probar_calidad.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "etl"))
from etl_dw_staging import (Evaluador, bus_dq_check, motivos_de_rechazo,  # noqa: E402
                            tech_dq_checks)


def lote(fuente, filas):
    return fuente, pd.DataFrame([{"_nro_fila": i, **f} for i, f in enumerate(filas, 1)])


# Un registro sano por tabla y, al lado, uno con un defecto concreto.
# El comentario de cada defecto dice que regla deberia atraparlo.
DATOS = {
    "customers": lote("classicmodels", [
        {"customerNumber": 1, "customerName": "Sano", "contactLastName": "A",
         "contactFirstName": "B", "phone": "1", "addressLine1": "x", "city": "c",
         "country": "p", "postalCode": "1", "salesRepEmployeeNumber": 10,
         "creditLimit": 100.0},
        # cliente_con_vendedor (ADVERTENCIA): sin vendedor asignado
        {"customerNumber": 2, "customerName": "Sin vendedor", "contactLastName": "A",
         "contactFirstName": "B", "phone": "2", "addressLine1": "x", "city": "c",
         "country": "p", "postalCode": "2", "salesRepEmployeeNumber": None,
         "creditLimit": 100.0},
        # campos_obligatorios (RECHAZO): falta customerName, que es NOT NULL
        {"customerNumber": 3, "customerName": None, "contactLastName": "A",
         "contactFirstName": "B", "phone": "3", "addressLine1": "x", "city": "c",
         "country": "p", "postalCode": "3", "salesRepEmployeeNumber": 10,
         "creditLimit": 100.0},
    ]),
    "employees": lote("classicmodels", [
        {"employeeNumber": 10, "lastName": "V", "firstName": "W", "extension": "x1",
         "email": "v@empresa.com", "officeCode": "1", "reportsTo": None, "jobTitle": "Sales"},
        # formato_email (ADVERTENCIA)
        {"employeeNumber": 11, "lastName": "V", "firstName": "W", "extension": "x2",
         "email": "sin-arroba", "officeCode": "1", "reportsTo": None, "jobTitle": "Sales"},
    ]),
    "offices": lote("classicmodels", [
        {"officeCode": "1", "city": "c", "phone": "1", "addressLine1": "x",
         "country": "p", "postalCode": "1", "territory": "NA"},
    ]),
    "productlines": lote("classicmodels", [{"productLine": "Cars"}]),
    "products": lote("classicmodels", [
        {"productCode": "P1", "productName": "Auto", "productLine": "Cars",
         "productScale": "1:10", "productVendor": "V", "productDescription": "d",
         "quantityInStock": 5, "buyPrice": 10.0, "MSRP": 20.0},
        # precio_sugerido_coherente (ADVERTENCIA): MSRP por debajo del costo
        {"productCode": "P2", "productName": "Barato", "productLine": "Cars",
         "productScale": "1:10", "productVendor": "V", "productDescription": "d",
         "quantityInStock": 5, "buyPrice": 30.0, "MSRP": 20.0},
    ]),
    "orders": lote("classicmodels", [
        {"orderNumber": 100, "orderDate": "2004-01-10", "requiredDate": "2004-01-20",
         "shippedDate": "2004-01-12", "status": "Shipped", "customerNumber": 1},
        # secuencia_de_fechas (RECHAZO): enviada antes de pedida
        {"orderNumber": 101, "orderDate": "2004-01-10", "requiredDate": "2004-01-20",
         "shippedDate": "2004-01-05", "status": "Shipped", "customerNumber": 1},
        # envio_consistente_con_estado (RECHAZO): Shipped sin fecha de envio
        {"orderNumber": 102, "orderDate": "2004-01-10", "requiredDate": "2004-01-20",
         "shippedDate": None, "status": "Shipped", "customerNumber": 1},
        # tipo_de_dato_valido (RECHAZO): fecha que no es fecha
        {"orderNumber": 103, "orderDate": "no-es-fecha", "requiredDate": "2004-01-20",
         "shippedDate": None, "status": "In Process", "customerNumber": 1},
    ]),
    "orderdetails": lote("classicmodels", [
        {"orderNumber": 100, "productCode": "P1", "quantityOrdered": 2,
         "priceEach": 15.0, "orderLineNumber": 1},
        # integridad_referencial (RECHAZO): producto que no existe
        {"orderNumber": 100, "productCode": "NO_EXISTE", "quantityOrdered": 2,
         "priceEach": 15.0, "orderLineNumber": 2},
        # valores_positivos (RECHAZO): cantidad negativa
        {"orderNumber": 100, "productCode": "P1", "quantityOrdered": -3,
         "priceEach": 15.0, "orderLineNumber": 3},
    ]),
    "cs_customers": lote("customerservice", [
        {"customernumber": 1, "phone": "1", "city": "c", "country": "p", "postalcode": "1"},
        # consistencia_entre_fuentes_cliente (ADVERTENCIA): otra ciudad
        {"customernumber": 2, "phone": "2", "city": "OTRA", "country": "p", "postalcode": "2"},
    ]),
    "cs_products": lote("customerservice", [
        {"productcode": "P1", "productname": "Auto", "productscale": "1:10", "productvendor": "V"},
    ]),
    "cs_employees": lote("customerservice", [
        {"employeenumber": 50, "lastname": "A", "firstname": "B", "email": "a@b.co"},
    ]),
    "cs_customer_calls": lote("customerservice", [
        {"employeenumber": 50, "customernumber": 1, "productcode": "P1",
         "text": "ok", "date": "2004-02-01"},
        # integridad_referencial (RECHAZO): cliente que no existe en ninguna
        # fuente, asi que tampoco podria conformarse en dim_cliente
        {"employeenumber": 50, "customernumber": 999, "productcode": "P1",
         "text": "huerfana", "date": "2004-02-01"},
    ]),
}

# (tabla, nro_fila) -> (regla esperada, debe ser rechazado)
ESPERADO = {
    ("customers", 2):         ("cliente_con_vendedor", False),
    ("customers", 3):         ("campos_obligatorios", True),
    ("employees", 2):         ("formato_email", False),
    ("products", 2):          ("precio_sugerido_coherente", False),
    ("orders", 2):            ("secuencia_de_fechas", True),
    ("orders", 3):            ("envio_consistente_con_estado", True),
    ("orders", 4):            ("tipo_de_dato_valido", True),
    ("orderdetails", 2):      ("integridad_referencial", True),
    ("orderdetails", 3):      ("valores_positivos", True),
    ("cs_customers", 2):      ("consistencia_entre_fuentes_cliente", False),
    ("cs_customer_calls", 2): ("integridad_referencial", True),
}


def main():
    ev = Evaluador()
    tech_dq_checks(DATOS, ev)
    bus_dq_check(DATOS, ev)
    rechazados = motivos_de_rechazo(ev)

    detectadas = {}
    for f in ev.fallas:
        detectadas.setdefault((f["tabla_origen"], f["nro_fila"]), set()).add(f["regla"])

    print(f"{'Registro':<24}{'Regla esperada':<38}{'Detecto':>8}{'Destino':>12}   Estado")
    print("-" * 92)
    ok_total = True
    for (tabla, nro), (regla, debe_rechazarse) in ESPERADO.items():
        detecto = regla in detectadas.get((tabla, nro), set())
        rechazado = (tabla, nro) in rechazados
        ok = detecto and rechazado == debe_rechazarse
        ok_total &= ok
        destino = "rechazado" if rechazado else "limpio"
        print(f"{tabla + ' #' + str(nro):<24}{regla:<38}{'si' if detecto else 'NO':>8}"
              f"{destino:>12}   {'OK' if ok else 'FALLA'}")

    # Los registros sanos no deben aparecer ni en el reporte ni rechazados.
    sanos_con_falla = [
        (t, n) for (t, n) in detectadas
        if (t, n) not in ESPERADO
    ]
    print()
    if sanos_con_falla:
        ok_total = False
        print(f"FALLA: registros sanos marcados como defectuosos: {sanos_con_falla}")
    else:
        print("Ningun registro sano fue marcado como defectuoso.")

    print()
    print("El camino de rechazo funciona." if ok_total
          else "Hay reglas que no se comportan como se espera.")
    sys.exit(0 if ok_total else 1)


if __name__ == "__main__":
    main()
