#!/usr/bin/env python3
"""Executor de migrations SQL (idempotente, ordenado por nome de arquivo).

Uso:
    python3 migrate.py            # aplica todas as migrations pendentes
    python3 migrate.py --status   # lista o que já foi aplicado
"""
import os
import sys
import glob
import subprocess

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402


def ensure_migrations_table():
    db.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version text PRIMARY KEY,
            applied_at timestamptz NOT NULL DEFAULT now()
        );
    """)


def applied_versions():
    rows = db.fetchall("SELECT version FROM schema_migrations ORDER BY version;")
    return {r["version"] for r in rows}


def run_file(path, dsn):
    result = subprocess.run(
        ["psql", dsn, "-X", "-q", "-v", "ON_ERROR_STOP=1", "--single-transaction", "-f", path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Falha ao aplicar {path}:\n{result.stderr}")


def main():
    status_only = "--status" in sys.argv
    ensure_migrations_table()
    applied = applied_versions()
    files = sorted(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))
    dsn = db.dsn_string()
    for path in files:
        version = os.path.basename(path)
        state = "aplicada" if version in applied else "PENDENTE"
        if status_only:
            print(f"{state:10s} {version}")
            continue
        if version in applied:
            continue
        print(f"Aplicando {version} ...")
        run_file(path, dsn)
        db.execute(f"INSERT INTO schema_migrations (version) VALUES ({db.lit(version)});")
        print(f"  OK: {version}")
    if not status_only:
        print("Migrations em dia.")


if __name__ == "__main__":
    main()
