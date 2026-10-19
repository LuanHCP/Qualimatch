"""Inicialização controlada do Sistema de Não Conformidades local."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path


NC_URL = os.getenv("NC_PROJECT_URL", "http://127.0.0.1:3100").strip().rstrip("/")
NC_HEALTH_URL = f"{NC_URL}/api/health"
_DEFAULT_NC_PROJECT_DIR = Path(__file__).resolve().parents[1] / "integrations" / "sistema-nc"
NC_PROJECT_DIR = Path(
    os.getenv("NC_PROJECT_DIR", "").strip() or str(_DEFAULT_NC_PROJECT_DIR)
).expanduser()
_managed_process: subprocess.Popen | None = None
_claimed_by_qualimatch = False
_NC_SSO_SECRET_PATH = NC_PROJECT_DIR / "backend" / "qualimatch-sso.key"
_launch_lock = threading.Lock()


def _single_launch(func):
    def wrapped(*args, **kwargs):
        with _launch_lock:
            return func(*args, **kwargs)
    return wrapped


def _read_url(url: str, timeout: float = 1.5) -> bytes:
    request = urllib.request.Request(url, headers={"Accept": "application/json,text/html"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status >= 400:
            raise OSError(f"HTTP {response.status}")
        return response.read(8192)


def nc_project_ready() -> bool:
    try:
        html = _read_url(NC_URL).decode("utf-8", errors="ignore")
        health = json.loads(_read_url(NC_HEALTH_URL).decode("utf-8"))
        return (
            "Sistema de Gestão de NC" in html
            and health.get("status") == "ok"
            and health.get("app") == "sistema-nc"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def _stop_running_nc_instance() -> None:
    """Encerra apenas o serviço confirmado como Sistema de NC na porta 3100."""
    if os.name != "nt" or not nc_project_ready():
        return
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"], capture_output=True, text=True,
        errors="ignore", creationflags=subprocess.CREATE_NO_WINDOW, check=False,
    )
    pids: set[int] = set()
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) < 5 or columns[0].upper() != "TCP":
            continue
        local, state, pid = columns[1], columns[3].upper(), columns[4]
        if state == "LISTENING" and local.rsplit(":", 1)[-1] == "3100":
            try:
                pids.add(int(pid))
            except ValueError:
                pass
    for pid in pids:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW, check=False,
        )


def _validate_project() -> tuple[Path, Path]:
    root = NC_PROJECT_DIR.resolve()
    python = root / ".venv" / "Scripts" / "python.exe"
    required = (python, root / "backend" / "run_windows.py", root / ".env")
    if not root.is_dir() or not all(path.is_file() for path in required):
        raise RuntimeError(
            "Projeto Sistema de Não Conformidades não encontrado ou não instalado. "
            "Configure NC_PROJECT_DIR com o caminho da pasta sistema-nc-v2."
        )
    return root, python


def _prepare_demo_project(root: Path) -> None:
    """Prepara o banco e o ambiente isolados quando a V2 está em modo demo."""
    if os.getenv("QUALIMATCH_DEMO", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return
    setup = root.parents[1] / "tools" / "setup_nc_demo.py"
    if not setup.is_file():
        raise RuntimeError("Preparador demonstrativo do Sistema de NC não foi encontrado.")
    result = subprocess.run(
        [sys.executable, str(setup)], cwd=str(root.parents[1]),
        capture_output=True, text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "erro desconhecido").strip()
        raise RuntimeError(f"Não foi possível preparar o Sistema de NC: {detail[-1200:]}")


def _start_hidden(root: Path, python: Path) -> None:
    global _managed_process
    child_env = os.environ.copy()
    # Não herdar a conexão PostgreSQL do QualiMatch: run_windows.py carrega
    # as credenciais próprias do nc_sistema a partir do .env do projeto.
    for name in (
        "PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD",
        "APP_SECRET_KEY", "DATABASE_URL", "PORT",
    ):
        child_env.pop(name, None)
    child_env["PORT"] = "3100"
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    _managed_process = subprocess.Popen(
        [str(python), str(root / "backend" / "run_windows.py")],
        cwd=str(root),
        env=child_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )


def nc_project_login(
    email: str, name: str = "", is_admin: bool = False, permission_level: str = "VIEWER"
) -> str | None:
    email = (email or "").strip().lower()
    if not email:
        return None
    try:
        secret = _NC_SSO_SECRET_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not secret:
        return None
    name = (name or email.split("@", 1)[0]).strip()
    profile = "admin_geral" if is_admin else (
        "qualidade" if str(permission_level or "VIEWER").upper() == "EDITOR" else "consulta"
    )
    timestamp = int(time.time() * 1000)
    signed = f"{email}|{name}|{profile}|{timestamp}"
    signature = hmac.new(
        secret.encode("utf-8"), signed.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    body = json.dumps({
        "email": email, "name": name, "profile": profile,
        "timestamp": timestamp, "signature": signature,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{NC_URL}/api/auth/qualimatch-sso", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=4.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    entry_path = str(payload.get("entryPath") or "")
    return f"{NC_URL}{entry_path}" if entry_path.startswith("/") else None


@_single_launch
def launch_nc_project(
    wait_seconds: float = 45.0, user_email: str = "", user_name: str = "",
    is_admin: bool = False, permission_level: str = "VIEWER",
) -> dict:
    global _claimed_by_qualimatch
    if nc_project_ready():
        _claimed_by_qualimatch = True
        entry_url = nc_project_login(user_email, user_name, is_admin, permission_level)
        return {"ok": True, "url": entry_url or NC_URL, "started": False, "status": "ready", "sso": bool(entry_url)}
    root = NC_PROJECT_DIR.resolve()
    _prepare_demo_project(root)
    root, python = _validate_project()
    _start_hidden(root, python)
    deadline = time.monotonic() + max(1.0, wait_seconds)
    while time.monotonic() < deadline:
        if nc_project_ready():
            _claimed_by_qualimatch = True
            entry_url = nc_project_login(user_email, user_name, is_admin, permission_level)
            return {"ok": True, "url": entry_url or NC_URL, "started": True, "status": "ready", "sso": bool(entry_url)}
        if _managed_process is not None and _managed_process.poll() is not None:
            raise RuntimeError("O Sistema de Não Conformidades encerrou durante a inicialização.")
        time.sleep(0.5)
    raise RuntimeError("O Sistema de Não Conformidades não respondeu dentro do tempo esperado.")


@_single_launch
def shutdown_nc_project() -> None:
    global _managed_process, _claimed_by_qualimatch
    process = _managed_process
    _managed_process = None
    claimed = _claimed_by_qualimatch
    _claimed_by_qualimatch = False
    if process is not None and process.poll() is None and os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
    elif process is not None and process.poll() is None:
        process.terminate()
    elif claimed:
        _stop_running_nc_instance()
