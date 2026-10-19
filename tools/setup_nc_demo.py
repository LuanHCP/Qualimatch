#!/usr/bin/env python3
"""Prepara um PostgreSQL isolado e os dados fictícios do módulo NC.

O cluster fica dentro da própria integração e nunca utiliza o banco real
instalado na máquina. O script é idempotente e pode rodar a cada abertura.
"""
from __future__ import annotations

import os
import hashlib
import secrets
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
NC_ROOT = PROJECT / "integrations" / "sistema-nc"
BACKEND = NC_ROOT / "backend"
DATA_DIR = NC_ROOT / ".demo-postgres"
LOG_FILE = DATA_DIR / "postgres.log"
READY_MARKER = NC_ROOT / ".demo-ready"
_PORT_OFFSET = int.from_bytes(
    hashlib.sha256(str(NC_ROOT).casefold().encode("utf-8")).digest()[:2], "big"
) % 1000
PORT = os.getenv("QUALIMATCH_NC_DEMO_PORT", str(56000 + _PORT_OFFSET))
DB_NAME = "nc_sistema_demo"
DB_USER = "nc_demo"
DB_PASSWORD = "qualimatch_demo_local"


def run(command: list[str | Path], *, env: dict[str, str] | None = None,
        capture: bool = False, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(part) for part in command], env=env, text=True,
        capture_output=capture, check=check,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )


def find_pg_bin() -> Path:
    configured = os.getenv("QUALIMATCH_PG_BIN", "").strip()
    candidates: list[Path] = []
    if configured:
        candidates.append(Path(configured))
    psql = shutil.which("psql")
    if psql:
        candidates.append(Path(psql).parent)
    program_files = Path(os.getenv("ProgramFiles", r"C:\Program Files")) / "PostgreSQL"
    if program_files.is_dir():
        candidates.extend(sorted(program_files.glob("*/bin"), reverse=True))
    for candidate in candidates:
        if all((candidate / name).is_file() for name in ("initdb.exe", "pg_ctl.exe", "psql.exe")):
            return candidate.resolve()
    raise RuntimeError(
        "PostgreSQL não foi encontrado. Instale o PostgreSQL Database Server "
        "com as ferramentas de linha de comando."
    )


def pg_env(pg_bin: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PATH"] = str(pg_bin) + os.pathsep + env.get("PATH", "")
    env.update({
        "PGHOST": "127.0.0.1", "PGPORT": PORT, "PGDATABASE": DB_NAME,
        "PGUSER": DB_USER, "PGPASSWORD": DB_PASSWORD,
        "APP_SECRET_KEY": "qualimatch-v2-demo-" + secrets.token_hex(24),
        "COOKIE_SECURE": "false", "SESSION_LIFETIME_MINUTES": "480",
        "SESSION_ABSOLUTE_MAX_HOURS": "24", "LOGIN_MAX_ATTEMPTS": "5",
        "LOGIN_LOCKOUT_MINUTES": "15", "MAX_UPLOAD_MB": "15",
        "BOOTSTRAP_ADMIN_EMAIL": "admin@qualimatch.local",
        "BOOTSTRAP_ADMIN_NOME": "Administrador Demo",
        "EMAIL_USE_OUTLOOK": "false",
    })
    return env


def psql(pg_bin: Path, database: str, sql: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD
    return run([
        pg_bin / "psql.exe", "-X", "-h", "127.0.0.1", "-p", PORT,
        "-U", "postgres", "-d", database, "-v", "ON_ERROR_STOP=1", "-tAc", sql,
    ], env=env, capture=True, check=check)


def ensure_cluster(pg_bin: Path) -> None:
    if not (DATA_DIR / "PG_VERSION").is_file():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        run([
            pg_bin / "initdb.exe", "-D", DATA_DIR, "-U", "postgres",
            "-A", "trust", "--encoding=UTF8", "--no-locale",
        ])
        with (DATA_DIR / "postgresql.conf").open("a", encoding="utf-8") as config:
            config.write(
                "\n# QualiMatch V2 demo\nlisten_addresses = '127.0.0.1'\n"
                f"port = {PORT}\nmax_connections = 30\n"
            )

    probe = psql(pg_bin, "postgres", "SELECT 1;", check=False)
    if probe.returncode != 0:
        run([
            pg_bin / "pg_ctl.exe", "-D", DATA_DIR, "-l", LOG_FILE,
            "-o", f"-p {PORT}", "-w", "start",
        ])


def ensure_database(pg_bin: Path) -> None:
    role = psql(pg_bin, "postgres", f"SELECT 1 FROM pg_roles WHERE rolname='{DB_USER}';").stdout.strip()
    if not role:
        psql(pg_bin, "postgres", f"CREATE ROLE {DB_USER} LOGIN PASSWORD '{DB_PASSWORD}';")
    database = psql(pg_bin, "postgres", f"SELECT 1 FROM pg_database WHERE datname='{DB_NAME}';").stdout.strip()
    if not database:
        psql(pg_bin, "postgres", f"CREATE DATABASE {DB_NAME} OWNER {DB_USER};")


def ensure_python(env: dict[str, str]) -> Path:
    python = NC_ROOT / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        run([sys.executable, "-m", "venv", NC_ROOT / ".venv"])
    check = run([
        python, "-c", "import flask, psycopg, bcrypt, openpyxl, xlrd"
    ], capture=True, check=False)
    if check.returncode != 0:
        run([python, "-m", "pip", "install", "--disable-pip-version-check", "-r", BACKEND / "requirements.txt"])
    return python


def write_env(env: dict[str, str], pg_bin: Path) -> None:
    keys = (
        "PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "APP_SECRET_KEY",
        "COOKIE_SECURE", "SESSION_LIFETIME_MINUTES", "SESSION_ABSOLUTE_MAX_HOURS",
        "LOGIN_MAX_ATTEMPTS", "LOGIN_LOCKOUT_MINUTES", "MAX_UPLOAD_MB",
        "BOOTSTRAP_ADMIN_EMAIL", "BOOTSTRAP_ADMIN_NOME", "EMAIL_USE_OUTLOOK",
    )
    existing_secret = ""
    env_path = NC_ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("APP_SECRET_KEY="):
                existing_secret = line.split("=", 1)[1].strip()
                break
    if existing_secret:
        env["APP_SECRET_KEY"] = existing_secret
    env_path.write_text("\n".join(f"{key}={env[key]}" for key in keys) + "\n", encoding="utf-8")
    (NC_ROOT / ".postgres-bin").write_text(str(pg_bin), encoding="utf-8")


def main() -> int:
    pg_bin = find_pg_bin()
    ensure_cluster(pg_bin)
    ensure_database(pg_bin)
    env = pg_env(pg_bin)
    write_env(env, pg_bin)
    python = ensure_python(env)
    if READY_MARKER.is_file():
        print("Sistema de NC demonstrativo já está preparado.")
        return 0
    run([python, BACKEND / "migrate.py"], env=env)
    run([python, BACKEND / "seed_demo.py"], env=env)
    run([python, BACKEND / "ensure_demo_admin.py"], env=env)
    READY_MARKER.write_text("QualiMatch V2 NC demo pronta.\n", encoding="utf-8")
    print("Sistema de NC demonstrativo preparado com 200 registros fictícios.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
