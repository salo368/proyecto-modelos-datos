"""
Prueba que el backup del almacen restaure de verdad.

Un backup que nadie probo no es un backup. Este script crea una base
desechable en el mismo servidor, restaura dw_backup.sql ahi, compara los
conteos y el monto total contra el almacen real, y borra la base de
prueba al terminar.

Uso (desde la raiz del proyecto):
    python datawarehouse/backup/probar_restauracion.py
"""
import os

import sqlalchemy as sa
from dotenv import load_dotenv

load_dotenv(".env")

BACKUP = "datawarehouse/backup/dw_backup.sql"
BASE_PRUEBA = "dw_restore_test"

TABLAS = [
    "dim_tiempo", "dim_cliente", "dim_producto", "dim_empleado",
    "dim_oficina", "dim_estado_orden",
    "fact_ventas", "fact_llamadas_servicio",
]


def main():
    if not os.path.exists(BACKUP):
        raise SystemExit(
            f"No encuentro {BACKUP}. Genera el backup primero:\n"
            f"    python datawarehouse/backup/generar_backup.py dw"
        )

    admin = sa.create_engine(os.getenv("METADATA_REPO_URL"),
                             isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(sa.text(f"DROP DATABASE IF EXISTS {BASE_PRUEBA}"))
        c.execute(sa.text(f"CREATE DATABASE {BASE_PRUEBA}"))
    print(f"Base de prueba '{BASE_PRUEBA}' creada.")

    url_prueba = os.getenv("DW_URL").rsplit("/", 1)[0] + f"/{BASE_PRUEBA}"
    prueba = sa.create_engine(url_prueba, isolation_level="AUTOCOMMIT")

    with open(BACKUP, encoding="utf-8") as f:
        sql = f.read()
    with prueba.connect() as c:
        c.execute(sa.text(sql))
    print("Backup restaurado sin errores.")

    real = sa.create_engine(os.getenv("DW_URL"))
    print(f"\n{'Tabla':<26}{'Original':>12}{'Restaurado':>12}   Estado")
    print("-" * 64)

    todo_ok = True
    with real.connect() as a, prueba.connect() as b:
        for t in TABLAS:
            n1 = a.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar()
            n2 = b.execute(sa.text(f"SELECT COUNT(*) FROM {t}")).scalar()
            ok = n1 == n2
            todo_ok &= ok
            print(f"{t:<26}{n1:>12}{n2:>12}   {'OK' if ok else 'DIFIERE'}")

        q = "SELECT ROUND(SUM(monto_linea),2) FROM fact_ventas"
        m1 = a.execute(sa.text(q)).scalar()
        m2 = b.execute(sa.text(q)).scalar()
        ok = m1 == m2
        todo_ok &= ok
        print(f"{'monto total vendido':<26}{m1:>12}{m2:>12}   {'OK' if ok else 'DIFIERE'}")

    prueba.dispose()
    with admin.connect() as c:
        c.execute(sa.text(f"DROP DATABASE {BASE_PRUEBA}"))
    print(f"\nBase de prueba eliminada.")

    print("RESTAURACION VERIFICADA." if todo_ok
          else "LA RESTAURACION NO CUADRA. Revisa el generador de backup.")


if __name__ == "__main__":
    main()
