#!/usr/bin/env python3
"""
Monta el proyecto completo desde cero, en cualquier maquina.

    python run_all.py

Levanta las cuatro piezas del stack en Docker (las dos fuentes, el
repositorio de metadatos con el almacen, y Metabase), espera a que esten
listas y ejecuta el pipeline entero de las dos entregas. Al terminar deja
el dashboard de reportes abierto en http://localhost:3000.

Funciona igual en Windows, macOS y Linux: lo unico que hace falta es
Docker y Python 3.9 o superior.

Opciones:
    python run_all.py              monta todo y corre el pipeline
    python run_all.py --solo-etl   no toca Docker, solo corre el pipeline
    python run_all.py --reiniciar  borra los datos y empieza de cero
    python run_all.py --apagar     apaga el stack (conserva los datos)
"""
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
PY = sys.executable

# Cada paso es (titulo, comando). El orden importa: las dimensiones
# tienen que existir antes que los hechos, y el metadato tecnico antes
# que el de negocio.
PIPELINE = [
    ("Repositorio de metadatos: esquema base",
     [PY, "datawarehouse/ddl/run_sql.py",
      "metadata_repository/ddl/metadata_repository_ddl.sql", "METADATA_REPO_URL"]),

    ("Repositorio de metadatos: area de staging",
     [PY, "datawarehouse/ddl/run_sql.py",
      "metadata_repository/ddl/metadata_staging_ddl.sql", "METADATA_REPO_URL"]),

    ("Entrega 1 - ETL de metadatos tecnicos",
     [PY, "metadata_repository/etl/etl_metadata_repository.py"]),

    ("Entrega 1 - Metadatos de negocio y linaje semantico",
     [PY, "datawarehouse/ddl/run_sql.py",
      "metadata_repository/etl/business_metadata_seed.sql", "METADATA_REPO_URL"]),

    ("Entrega 2 - Extension del repositorio para el almacen",
     [PY, "datawarehouse/ddl/run_sql.py",
      "metadata_repository/ddl/metadata_dw_extension.sql", "METADATA_REPO_URL"]),

    ("Entrega 2 - Reglas de calidad de datos",
     [PY, "datawarehouse/ddl/run_sql.py",
      "metadata_repository/etl/dq_rules_seed.sql", "METADATA_REPO_URL"]),

    ("Entrega 2 - Metadatos de uso (cuarta categoria, Clase 3)",
     [PY, "datawarehouse/ddl/run_sql.py",
      "metadata_repository/ddl/metadata_uso_extension.sql", "METADATA_REPO_URL"]),

    ("Entrega 2 - Esquema del almacen dimensional",
     [PY, "datawarehouse/ddl/run_sql.py", "datawarehouse/ddl/01_dw_schema.sql"]),

    ("Entrega 2 - Capas de staging del ETL (Giordano, Clase 2)",
     [PY, "datawarehouse/ddl/run_sql.py", "datawarehouse/ddl/02_staging_dw.sql"]),

    ("Entrega 2 - ETL de dimensiones",
     [PY, "datawarehouse/etl/etl_dw_dimensions.py"]),

    ("Entrega 2 - ETL de hechos y vista integrada",
     [PY, "datawarehouse/etl/etl_dw_facts.py"]),

    ("Entrega 2 - Catalogo del almacen en el repositorio",
     [PY, "metadata_repository/etl/etl_dw_metadata.py"]),

    ("Entrega 2 - Medicion de uso del almacen",
     [PY, "metadata_repository/etl/etl_uso_metadata.py"]),

    ("Validacion contra las fuentes",
     [PY, "datawarehouse/queries/validacion.py"]),

    ("Reportes en Metabase",
     [PY, "reports/construir_dashboard.py"]),
]


# ============================================================
# Presentacion
# ============================================================

def titulo(texto):
    print(f"\n{'=' * 66}\n  {texto}\n{'=' * 66}")


def paso(n, total, texto):
    print(f"\n[{n}/{total}] {texto}")
    print("-" * 66)


# ============================================================
# Docker
# ============================================================

def comando_compose():
    """Devuelve el comando de compose disponible, o None si no hay Docker."""
    if shutil.which("docker") is None:
        return None
    # Docker moderno trae 'docker compose'; los instalados hace anos usan
    # el binario aparte 'docker-compose'.
    for cmd in (["docker", "compose"], ["docker-compose"]):
        try:
            r = subprocess.run(cmd + ["version"], capture_output=True, timeout=30)
            if r.returncode == 0:
                return cmd
        except Exception:
            continue
    return None


def docker_vivo():
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=60)
        return r.returncode == 0
    except Exception:
        return False


def levantar_stack(compose, reiniciar=False):
    if reiniciar:
        print("  Borrando datos anteriores...")
        subprocess.run(compose + ["down", "-v"], cwd=RAIZ)

    print("  Levantando contenedores (la primera vez descarga imagenes)...")
    r = subprocess.run(compose + ["up", "-d"], cwd=RAIZ)
    if r.returncode != 0:
        sys.exit("\nNo pude levantar el stack. Revisa que Docker este corriendo.")


def esperar_bases(compose, limite=420):
    """Espera a que los tres motores reporten 'healthy'."""
    servicios = ["mysql", "postgres-cs", "postgres-dw"]
    print("  Esperando a que las bases esten listas...")
    print("  (la primera vez tarda: MySQL restaura classicmodels al arrancar)")

    inicio = time.time()
    listos = set()
    while time.time() - inicio < limite:
        for s in servicios:
            if s in listos:
                continue
            r = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}",
                 f"mpd-{s}"],
                capture_output=True, text=True,
            )
            if r.stdout.strip() == "healthy":
                listos.add(s)
                print(f"    {s}: listo  ({int(time.time() - inicio)}s)")
        if len(listos) == len(servicios):
            return True
        time.sleep(5)

    faltan = set(servicios) - listos
    sys.exit(f"\nEstas bases no quedaron listas a tiempo: {', '.join(faltan)}\n"
             f"Mira que paso con:  docker compose logs {' '.join(faltan)}")


def esperar_metabase(limite=300):
    url = os.getenv("METABASE_URL", "http://localhost:3000") + "/api/health"
    print("  Esperando a Metabase...")
    inicio = time.time()
    while time.time() - inicio < limite:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if b'"ok"' in r.read():
                    print(f"    metabase: listo  ({int(time.time() - inicio)}s)")
                    return True
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(6)
    print("    Aviso: Metabase tardo mas de lo esperado. El resto del "
          "pipeline igual corrio bien.")
    return False


# ============================================================
# Entorno
# ============================================================

def preparar_env():
    env = RAIZ / ".env"
    ejemplo = RAIZ / ".env.example"
    if not env.exists():
        if not ejemplo.exists():
            sys.exit("Falta .env.example en el repositorio.")
        shutil.copy(ejemplo, env)
        print("  .env creado a partir de .env.example (apunta al stack local).")
    else:
        print("  .env ya existe, se respeta como esta.")


def instalar_dependencias():
    print("  Instalando dependencias de Python...")
    r = subprocess.run(
        [PY, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
        cwd=RAIZ,
    )
    if r.returncode != 0:
        sys.exit("Fallo la instalacion de dependencias. Revisa requirements.txt")

    # pandas 3.x necesita SQLAlchemy >= 2.0.36. Si no se cumple, pandas no
    # falla: deja de reconocer los engines y el error aparece mucho despues,
    # sin mencionar la causa. Mejor detectarlo aca.
    try:
        import pandas
        import sqlalchemy
        print(f"    pandas {pandas.__version__} + SQLAlchemy {sqlalchemy.__version__}")
    except ImportError as e:
        sys.exit(f"No pude importar una dependencia: {e}")


# ============================================================
# Pipeline
# ============================================================

def correr_pipeline():
    total = len(PIPELINE)
    for i, (nombre, cmd) in enumerate(PIPELINE, 1):
        paso(i, total, nombre)
        r = subprocess.run(cmd, cwd=RAIZ)
        if r.returncode != 0:
            print(f"\nFallo el paso {i}: {nombre}")
            print("Los pasos son acumulativos, asi que corrige esto y vuelve "
                  "a lanzar 'python run_all.py --solo-etl'.")
            sys.exit(1)


def main():
    args = set(sys.argv[1:])
    compose = comando_compose()

    if "--apagar" in args:
        if not compose:
            sys.exit("No encontre Docker en este equipo.")
        subprocess.run(compose + ["down"], cwd=RAIZ)
        print("\nStack apagado. Los datos se conservan.")
        print("Para borrarlos tambien:  python run_all.py --reiniciar")
        return

    titulo("Proyecto Final - Modelos y Persistencia de Datos")
    print("  Entregas 1 y 2, montaje completo en local.")

    if "--solo-etl" not in args:
        if not compose:
            sys.exit(
                "\nNo encontre Docker en este equipo.\n"
                "Instalalo desde https://www.docker.com/products/docker-desktop/\n"
                "y volve a intentar. Si ya lo tenes y las bases corren en otro\n"
                "lado, edita el .env y corre:  python run_all.py --solo-etl"
            )
        if not docker_vivo():
            sys.exit(
                "\nDocker esta instalado pero el demonio no responde.\n"
                "Abri Docker Desktop, espera a que arranque y volve a intentar."
            )

        titulo("1. Infraestructura")
        levantar_stack(compose, reiniciar="--reiniciar" in args)
        esperar_bases(compose)
    else:
        titulo("1. Infraestructura")
        print("  Omitida (--solo-etl).")

    titulo("2. Entorno de Python")
    preparar_env()
    instalar_dependencias()

    titulo("3. Pipeline de datos")
    if "--solo-etl" not in args:
        esperar_metabase()
    correr_pipeline()

    titulo("Listo")
    print("""
  El proyecto quedo montado y cargado.

    Reportes            http://localhost:3000
        usuario         grupo@javeriana.edu.co
        clave           Javeriana2026!

    Almacen de datos    localhost:5434 / base 'dw'
    Repo de metadatos   localhost:5434 / base 'metadata'
    classicmodels       localhost:3307
    customerservice     localhost:5433

    (usuario 'postgres' o 'root', clave 'javeriana')

  Documentos:
    docs/Entrega_1/Documento_Entrega_1.md
    docs/Entrega_2/Documento_Entrega_2.md

  Para apagar sin perder nada:   python run_all.py --apagar
""")


if __name__ == "__main__":
    main()
