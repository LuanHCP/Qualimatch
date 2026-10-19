from __future__ import annotations

import importlib.util
import os
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import BACKUP_DIR, CERT_DIR, DATA_DIR, DB_PATH, FRONTEND_DIR
from .database import backend_name, connect
from .version import APP_VERSION


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


DEPENDENCIES = {
    "FastAPI": "fastapi",
    "Uvicorn": "uvicorn",
    "Pydantic": "pydantic",
    "OpenPyXL": "openpyxl",
    "PyPDF": "pypdf",
    "Argon2": "argon2",
    "PostgreSQL": "psycopg",
    "Pytest": "pytest",
}


def _check(name: str, ok: bool, detail: str, failure: str = "ERROR") -> DoctorCheck:
    return DoctorCheck(name, "OK" if ok else failure, detail)


def _tracked_operational_files(root: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--", "data/cache", "data/certificados"],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _sqlite_integrity() -> DoctorCheck:
    if backend_name() != "sqlite":
        try:
            connection = connect()
            connection.execute("SELECT 1").fetchone()
            connection.close()
            return DoctorCheck("Banco", "OK", "Conexão PostgreSQL validada.")
        except Exception as exc:
            return DoctorCheck("Banco", "ERROR", f"Falha na conexão PostgreSQL: {exc}")
    if not DB_PATH.exists():
        return DoctorCheck("Banco", "WARN", "Banco SQLite ainda não foi criado.")
    try:
        uri = f"file:{DB_PATH.resolve().as_posix()}?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
        return _check("Banco", str(result).lower() == "ok", f"SQLite: {result}")
    except Exception as exc:
        return DoctorCheck("Banco", "ERROR", f"Falha ao validar SQLite: {exc}")


def run_doctor(root: Path | None = None) -> dict:
    project_root = (root or Path(__file__).resolve().parents[1]).resolve()
    checks: list[DoctorCheck] = []

    supported_python = (3, 11) <= sys.version_info[:2] <= (3, 15)
    checks.append(_check("Python", supported_python, sys.version.split()[0]))
    checks.append(_check("Versão", bool(APP_VERSION), APP_VERSION))

    missing = [label for label, module in DEPENDENCIES.items() if importlib.util.find_spec(module) is None]
    checks.append(_check("Dependências", not missing, "Todas disponíveis" if not missing else "Ausentes: " + ", ".join(missing)))

    for label, directory in (
        ("Dados", DATA_DIR),
        ("Certificados", CERT_DIR),
        ("Backups", BACKUP_DIR),
    ):
        available = directory.exists() and os.access(directory, os.R_OK | os.W_OK)
        checks.append(_check(label, available, str(directory)))

    template = FRONTEND_DIR / "index.html"
    try:
        html = template.read_text(encoding="utf-8")
        version_slots = html.count("__QUALIMATCH_VERSION__")
        checks.append(_check("Frontend", version_slots >= 4, f"{version_slots} marcadores de versão canônica"))
    except Exception as exc:
        checks.append(DoctorCheck("Frontend", "ERROR", str(exc)))

    checks.append(_sqlite_integrity())

    tracked = _tracked_operational_files(project_root)
    checks.append(
        DoctorCheck(
            "Dados no Git",
            "WARN" if tracked else "OK",
            f"{len(tracked)} arquivo(s) operacional(is) ainda rastreado(s)" if tracked else "Caches e certificados fora do índice",
        )
    )

    summary = {
        "ok": sum(item.status == "OK" for item in checks),
        "warnings": sum(item.status == "WARN" for item in checks),
        "errors": sum(item.status == "ERROR" for item in checks),
    }
    return {
        "app": "QualiMatch",
        "version": APP_VERSION,
        "root": str(project_root),
        "summary": summary,
        "checks": [asdict(item) for item in checks],
    }


def format_doctor_report(report: dict) -> str:
    lines = [f"QualiMatch v{report['version']} — diagnóstico", ""]
    for item in report.get("checks") or []:
        marker = {"OK": "[OK]", "WARN": "[AVISO]", "ERROR": "[ERRO]"}.get(item["status"], "[?]")
        lines.append(f"{marker:<8} {item['name']}: {item['detail']}")
    summary = report.get("summary") or {}
    lines.extend([
        "",
        f"Resultado: {summary.get('ok', 0)} OK, {summary.get('warnings', 0)} aviso(s), {summary.get('errors', 0)} erro(s).",
    ])
    return "\n".join(lines)


def doctor_exit_code(report: dict) -> int:
    return 1 if int((report.get("summary") or {}).get("errors") or 0) else 0
