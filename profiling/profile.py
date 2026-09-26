import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from ydata_profiling import ProfileReport


# ============================================================
# CONFIGURACIÓN
# ============================================================

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "No se encontró DATABASE_URL en el archivo .env"
    )

REPORTS_DIR = Path("reports")
REPORTS_DIR.mkdir(exist_ok=True)


# ============================================================
# CONEXIÓN
# ============================================================

def create_database_engine():
    return create_engine(DATABASE_URL)


# ============================================================
# DESCUBRIR TABLAS
# ============================================================

def get_tables(engine):
    inspector = inspect(engine)

    tables = inspector.get_table_names()

    print(f"\nTablas encontradas: {len(tables)}")

    for table in tables:
        print(f"  - {table}")

    return tables


# ============================================================
# OBTENER DATOS
# ============================================================

def load_table(engine, table_name):
    print(f"\nLeyendo tabla: {table_name}")

    df = pd.read_sql_table(
        table_name,
        engine
    )

    print(f"  Registros: {len(df)}")
    print(f"  Columnas: {len(df.columns)}")

    return df


# ============================================================
# GENERAR PROFILING
# ============================================================

def generate_profile(df, table_name):

    print(f"Generando profiling: {table_name}")

    profile = ProfileReport(
        df,
        title=f"Data Profiling - {table_name}",
        explorative=True
    )

    output_file = REPORTS_DIR / f"{table_name}_profile.html"

    profile.to_file(output_file)

    print(f"  Reporte generado: {output_file}")


# ============================================================
# PROCESAR TODAS LAS TABLAS
# ============================================================

def profile_all_tables(engine):

    tables = get_tables(engine)

    successful = []
    failed = []

    for table_name in tables:

        try:

            df = load_table(
                engine,
                table_name
            )

            generate_profile(
                df,
                table_name
            )

            successful.append(table_name)

        except Exception as error:

            print(
                f"  ERROR procesando {table_name}: {error}"
            )

            failed.append(table_name)

    return successful, failed


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)
    print("DATA PROFILING")
    print("=" * 60)

    engine = create_database_engine()

    successful, failed = profile_all_tables(engine)

    print("\n" + "=" * 60)
    print("RESUMEN")
    print("=" * 60)

    print(f"\nTablas procesadas correctamente: {len(successful)}")

    for table in successful:
        print(f"  ✓ {table}")

    print(f"\nTablas con errores: {len(failed)}")

    for table in failed:
        print(f"  ✗ {table}")

    print("\nProceso finalizado.")


if __name__ == "__main__":
    main()