#!/usr/bin/env python3
"""
Build the whole project from scratch.

    python run_all.py

Starts the Docker stack (both sources, the PostgreSQL instance that holds
the metadata repository, the pipeline staging area and the data
warehouse, and Metabase), waits for
it to be ready and runs every step of the pipeline in order. Needs only
Docker and Python 3.9+.

Options:
    python run_all.py                  start the stack and run the pipeline
    python run_all.py --etl-only       skip Docker, run the pipeline against .env
    python run_all.py --from-step N    resume at step N, skipping the ones before
    python run_all.py --reset          wipe the Docker volumes and start over
    python run_all.py --down           stop the stack (data is kept)
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
RUN_SQL = "tools/run_sql.py"

# (title, command). Order matters: technical metadata before business
# metadata, warehouse tables before the pipeline that loads them, staging
# before dimensions, dimensions before facts.
PIPELINE = [
    # --- Source discovery and profiling ---
    ("Profiling: technical metadata and column profile from the dumps",
     [PY, "profiling/profile_from_dumps.py"]),
    ("Profiling: columns and keys report",
     [PY, "profiling/columns_report.py"]),
    ("Profiling: referential integrity and cross-source correspondence",
     [PY, "profiling/referential_profiling.py"]),
    ("Profiling: undeclared relationship discovery",
     [PY, "profiling/discover_relationships.py"]),

    # --- Metadata repository: sources and business glossary ---
    ("Metadata repository: core schema",
     [PY, RUN_SQL, "metadata_repository/ddl/01_core_schema.sql", "METADATA_URL"]),
    ("Metadata repository: ETL staging schema",
     [PY, RUN_SQL, "metadata_repository/ddl/02_etl_staging.sql", "METADATA_URL"]),
    ("Metadata repository: technical metadata ETL",
     [PY, "metadata_repository/etl/etl_source_metadata.py"]),
    ("Metadata repository: business metadata and semantic lineage",
     [PY, RUN_SQL, "metadata_repository/seeds/business_metadata.sql", "METADATA_URL"]),
    ("Metadata repository: data warehouse extension",
     [PY, RUN_SQL, "metadata_repository/ddl/03_dw_extension.sql", "METADATA_URL"]),
    ("Metadata repository: data quality rules",
     [PY, RUN_SQL, "metadata_repository/seeds/dq_rules.sql", "METADATA_URL"]),
    ("Metadata repository: usage metadata extension",
     [PY, RUN_SQL, "metadata_repository/ddl/04_usage_extension.sql", "METADATA_URL"]),

    # --- Data warehouse (EDW and data marts), database dw ---
    ("Data warehouse: EDW star schema",
     [PY, RUN_SQL, "datawarehouse/edw/star_schema.sql"]),
    ("Data warehouse: special members (Desconocido, Sin asignar)",
     [PY, RUN_SQL, "datawarehouse/edw/special_members.sql"]),
    ("Data warehouse: data marts",
     [PY, RUN_SQL, "datawarehouse/data_marts/data_marts.sql"]),

    # --- Pipeline (7 integration layers), database staging ---
    ("Pipeline: staging database",
     [PY, "tools/create_database.py", "STAGING_URL"]),
    ("Pipeline: staging area tables",
     [PY, RUN_SQL, "pipeline/staging_dw.sql", "STAGING_URL"]),
    ("Pipeline: layers 1-4 (extract, quality, clean staging)",
     [PY, "pipeline/run_staging.py"]),
    ("Pipeline: layers 5-7, dimensions",
     [PY, "pipeline/run_dimensions.py"]),
    ("Pipeline: layers 5-7, facts",
     [PY, "pipeline/run_facts.py"]),

    # --- Warehouse metadata ---
    ("Metadata repository: warehouse catalogue and lineage",
     [PY, "metadata_repository/etl/etl_dw_metadata.py"]),
    ("Metadata repository: usage metadata",
     [PY, "metadata_repository/etl/etl_usage_metadata.py"]),

    # --- Checks ---
    ("Test: warehouse totals against the sources",
     [PY, "datawarehouse/tests/validate_against_sources.py"]),
    ("Test: data quality rejection path (synthetic data)",
     [PY, "pipeline/tests/test_dq_reject_path.py"]),
    ("Test: load is all-or-nothing (forced failure)",
     [PY, "pipeline/tests/test_load_atomic.py"]),
    ("Test: a load resumes without damaging the warehouse",
     [PY, "pipeline/tests/test_resume.py"]),

    # --- Deliverables ---
    ("Reports: Metabase dashboard",
     [PY, "reports/build_dashboard.py"]),
    ("Backup: data warehouse",
     [PY, "tools/generate_backup.py", "dw"]),
    ("Backup: metadata repository",
     [PY, "tools/generate_backup.py", "metadata"]),
    ("Test: backups restore correctly",
     [PY, "datawarehouse/tests/test_backup_restore.py"]),
    ("Report: data quality by stage",
     [PY, "tools/generate_quality_report.py"]),

    ("Diagrams: physical models and ETL pipeline",
     [PY, "tools/generate_diagrams.py"]),
]


def banner(text):
    print(f"\n{'=' * 66}\n  {text}\n{'=' * 66}")


# ============================================================
# Docker
# ============================================================

def compose_command():
    """The available compose command, or None if Docker is missing."""
    if shutil.which("docker") is None:
        return None
    for cmd in (["docker", "compose"], ["docker-compose"]):
        try:
            if subprocess.run(cmd + ["version"], capture_output=True, timeout=30).returncode == 0:
                return cmd
        except Exception:
            continue
    return None


def docker_running():
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=60).returncode == 0
    except Exception:
        return False


def start_stack(compose, reset=False):
    if reset:
        print("  Removing previous data...")
        subprocess.run(compose + ["down", "-v"], cwd=ROOT)
    print("  Starting containers (the first run downloads the images)...")
    if subprocess.run(compose + ["up", "-d"], cwd=ROOT).returncode != 0:
        sys.exit("\nCould not start the stack. Is Docker running?")


def wait_for_databases(timeout=420):
    """Wait until the three database containers report 'healthy'."""
    services = ["mysql", "postgres-cs", "postgres-dw"]
    print("  Waiting for the databases (MySQL restores classicmodels on first start)...")
    start = time.time()
    ready = set()
    while time.time() - start < timeout:
        for s in services:
            if s in ready:
                continue
            r = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Health.Status}}", f"mpd-{s}"],
                capture_output=True, text=True)
            if r.stdout.strip() == "healthy":
                ready.add(s)
                print(f"    {s}: ready ({int(time.time() - start)}s)")
        if len(ready) == len(services):
            return
        time.sleep(5)
    missing = set(services) - ready
    sys.exit(f"\nNot ready in time: {', '.join(missing)}\n"
             f"Check: docker compose logs {' '.join(missing)}")


def wait_for_metabase(timeout=300):
    url = os.getenv("METABASE_URL", "http://localhost:3000") + "/api/health"
    print("  Waiting for Metabase...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(url, timeout=5) as r:
                if b'"ok"' in r.read():
                    print(f"    metabase: ready ({int(time.time() - start)}s)")
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(6)
    print("    Warning: Metabase is taking longer than expected.")


# ============================================================
# Python environment
# ============================================================

def prepare_env_file():
    env, example = ROOT / ".env", ROOT / ".env.example"
    if not env.exists():
        shutil.copy(example, env)
        print("  .env created from .env.example (local stack).")
    else:
        print("  Using existing .env.")

    def variables(path):
        return {line.split("=", 1)[0].strip(): line
                for line in path.read_text(encoding="utf-8").splitlines()
                if "=" in line and not line.lstrip().startswith("#")}

    # Variables added to .env.example after this .env was created (e.g.
    # STAGING_URL) are copied over with their local-stack value.
    defined, template = variables(env), variables(example)
    added = [v for v in template if v not in defined]
    if added:
        with env.open("a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(template[v] for v in added) + "\n")
        print(f"  Added to .env from .env.example: {', '.join(added)}")

    required = ["CLASSICMODELS_URL", "CUSTOMERSERVICE_URL", "METADATA_URL",
                "STAGING_URL", "DW_URL"]
    missing = [v for v in required if v not in variables(env)]
    if missing:
        sys.exit(f"  .env is missing {', '.join(missing)}. "
                 f"Compare it with .env.example or delete it to regenerate it.")


def install_dependencies():
    print("  Installing Python dependencies...")
    r = subprocess.run([PY, "-m", "pip", "install", "-q", "-r", "requirements.txt"], cwd=ROOT)
    if r.returncode != 0:
        sys.exit("Dependency installation failed. Check requirements.txt.")


# ============================================================
# Pipeline
# ============================================================

def run_pipeline(first=1):
    """Run the steps from `first` on. The earlier ones are assumed done:
    what they left in the databases is kept, not rebuilt."""
    total = len(PIPELINE)
    if first > 1:
        print(f"  Resuming at step {first}: {PIPELINE[first - 1][0]}")
    for i, (title, cmd) in enumerate(PIPELINE, 1):
        if i < first:
            continue
        print(f"\n[{i}/{total}] {title}\n" + "-" * 66)
        if subprocess.run(cmd, cwd=ROOT).returncode != 0:
            print(f"\nStep {i} failed: {title}")
            print(f"Fix it and resume from this step with: "
                  f"python run_all.py --etl-only --from-step {i}")
            sys.exit(1)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Build the whole project: Docker stack and pipeline.")
    parser.add_argument("--etl-only", action="store_true",
                        help="skip Docker and run the pipeline against the databases in .env")
    parser.add_argument("--from-step", type=int, default=1, metavar="N",
                        help=f"resume at step N (1-{len(PIPELINE)}) without repeating the earlier ones")
    parser.add_argument("--reset", action="store_true",
                        help="wipe the Docker volumes and start over")
    parser.add_argument("--down", action="store_true",
                        help="stop the stack, keeping the data")
    args = parser.parse_args()
    if not 1 <= args.from_step <= len(PIPELINE):
        parser.error(f"--from-step must be between 1 and {len(PIPELINE)}")
    if args.reset and args.from_step > 1:
        parser.error("--reset wipes every database, so the build cannot resume "
                     "halfway; drop --from-step")
    return args


def main():
    args = parse_args()
    compose = compose_command()

    if args.down:
        if not compose:
            sys.exit("Docker not found.")
        subprocess.run(compose + ["down"], cwd=ROOT)
        print("\nStack stopped; data is kept. To wipe it: python run_all.py --reset")
        return

    etl_only = args.etl_only
    banner("Modelos y Persistencia de Datos - full build")

    banner("1. Infrastructure")
    if etl_only:
        print("  Skipped (--etl-only).")
    else:
        if not compose:
            sys.exit("\nDocker not found. Install Docker Desktop, or point .env to "
                     "existing databases and run: python run_all.py --etl-only")
        if not docker_running():
            sys.exit("\nDocker is installed but the daemon is not responding.")
        start_stack(compose, reset=args.reset)
        wait_for_databases()

    banner("2. Python environment")
    prepare_env_file()
    install_dependencies()

    banner("3. Pipeline")
    if not etl_only:
        wait_for_metabase()
    run_pipeline(args.from_step)

    banner("Done")
    print("""
    Reports (Metabase)   http://localhost:3000
        user             grupo@javeriana.edu.co
        password         Javeriana2026!

    Data warehouse       localhost:5434 / database 'dw'
    Pipeline staging     localhost:5434 / database 'staging'
    Metadata repository  localhost:5434 / database 'metadata'
    classicmodels        localhost:3307
    customerservice      localhost:5433
    (user 'postgres' or 'root', password 'javeriana')

  Stop the stack keeping the data:  python run_all.py --down
""")


if __name__ == "__main__":
    main()
