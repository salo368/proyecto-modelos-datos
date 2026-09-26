"""
Check that the backups restore correctly.

For the data warehouse and the metadata repository: create a scratch
database on the same server, restore the backup file into it, compare
row counts of every table and view (plus total sales for the warehouse)
against the live database, and drop the scratch database.

Usage (from the project root):
    python datawarehouse/tests/test_backup_restore.py
"""
import os
import sys
from pathlib import Path

import sqlalchemy as sa
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from generate_backup import TARGETS  # noqa: E402

load_dotenv(ROOT / ".env")

SCRATCH_DB = "restore_test"


def scratch_url(url):
    return url.rsplit("/", 1)[0] + f"/{SCRATCH_DB}"


def check_target(name, cfg, admin):
    backup = ROOT / cfg["output"]
    if not backup.exists():
        raise SystemExit(f"{backup} not found. Run: python tools/generate_backup.py {name}")

    with admin.connect() as c:
        c.execute(sa.text(f"DROP DATABASE IF EXISTS {SCRATCH_DB}"))
        c.execute(sa.text(f"CREATE DATABASE {SCRATCH_DB}"))

    live = sa.create_engine(os.getenv(cfg["url_var"]))
    restored = sa.create_engine(scratch_url(os.getenv(cfg["url_var"])),
                                isolation_level="AUTOCOMMIT")
    with restored.connect() as c:
        c.execute(sa.text(backup.read_text(encoding="utf-8")))

    print(f"\n{cfg['output']}")
    print(f"{'Relation':<40}{'Live':>14}{'Restored':>14}   Status")
    print("-" * 80)
    all_ok = True
    with live.connect() as a, restored.connect() as b:
        checks = [(r, f"SELECT COUNT(*) FROM {r}") for r in cfg["tables"] + cfg["views"]]
        if name == "dw":
            checks.append(("total monto_linea",
                           "SELECT ROUND(SUM(monto_linea), 2) FROM fact_ventas"))
        for label, sql in checks:
            v1 = a.execute(sa.text(sql)).scalar()
            v2 = b.execute(sa.text(sql)).scalar()
            ok = v1 == v2
            all_ok &= ok
            print(f"{label:<40}{v1:>14}{v2:>14}   {'OK' if ok else 'DIFFERS'}")

    restored.dispose()
    live.dispose()
    with admin.connect() as c:
        c.execute(sa.text(f"DROP DATABASE {SCRATCH_DB}"))
    return all_ok


def main():
    # Any database on the server works as the admin connection.
    admin = sa.create_engine(os.getenv("METADATA_URL"), isolation_level="AUTOCOMMIT")
    all_ok = True
    for name, cfg in TARGETS.items():
        all_ok &= check_target(name, cfg, admin)

    print()
    print("Backups restore correctly." if all_ok else "A restored backup does not match.")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
