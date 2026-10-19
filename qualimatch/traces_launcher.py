"""Inicialização controlada do projeto local Controle de Traços."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path


TRACES_URL = os.getenv("TRACES_PROJECT_URL", "http://localhost:3000").strip().rstrip("/")
TRACES_API_HEALTH = os.getenv(
    "TRACES_PROJECT_HEALTH_URL", "http://127.0.0.1:3001/health"
).strip()
_DEFAULT_TRACES_PROJECT_DIR = Path(__file__).resolve().parents[1] / "integrations" / "controle-tracos"
TRACES_PROJECT_DIR = Path(
    os.getenv("TRACES_PROJECT_DIR", "").strip() or str(_DEFAULT_TRACES_PROJECT_DIR)
).expanduser()
# Mesma chave que o servidor Node do Controle de Traços gera e grava em
# server/qualimatch-sso.key na primeira vez que sobe — usada só para assinar
# o login automático (ver traces_project_login abaixo). Nunca fica no
# código-fonte de nenhum dos dois lados.
_TRACES_SSO_SECRET_PATH = TRACES_PROJECT_DIR / "server" / "qualimatch-sso.key"
_TRACES_API_BASE = TRACES_API_HEALTH.rsplit("/health", 1)[0] or "http://127.0.0.1:3001"
_managed_process: subprocess.Popen | None = None
_claimed_by_qualimatch = False
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


def traces_project_ready() -> bool:
    """Confirma a interface e a API para não reutilizar outra aplicação na porta."""
    try:
        html = _read_url(TRACES_URL).decode("utf-8", errors="ignore")
        health = json.loads(_read_url(TRACES_API_HEALTH).decode("utf-8"))
        return (
            "Controle de Traços" in html
            and health.get("ok") is True
            and health.get("app") == "controle-tracos"
            and (
                health.get("database") is not True
                or health.get("schemaReady") is True
            )
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def _stale_instance_is_traces() -> bool:
    """Confirma que as portas ocupadas pertencem a uma versão antiga deste app."""
    try:
        html = _read_url(TRACES_URL).decode("utf-8", errors="ignore")
        config = json.loads(
            _read_url("http://127.0.0.1:3001/api/config").decode("utf-8")
        )
        return "Controle de Traços" in html and "traceLibraryPath" in config
    except (OSError, ValueError, json.JSONDecodeError):
        return False


def _stop_stale_instance() -> None:
    if os.name != "nt" or not _stale_instance_is_traces():
        return
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        errors="ignore",
        creationflags=subprocess.CREATE_NO_WINDOW,
        check=False,
    )
    pids: set[int] = set()
    for line in result.stdout.splitlines():
        columns = line.split()
        if len(columns) < 5 or columns[0].upper() != "TCP":
            continue
        local, state, pid = columns[1], columns[3].upper(), columns[4]
        if state == "LISTENING" and local.rsplit(":", 1)[-1] in {"3000", "3001"}:
            try:
                pids.add(int(pid))
            except ValueError:
                pass
    for pid in pids:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
            check=False,
        )
    if pids:
        time.sleep(1.0)


def _validate_project() -> Path:
    root = TRACES_PROJECT_DIR.resolve()
    required = (root / "package.json", root / "server" / "api.mjs")
    if not root.is_dir() or not all(path.is_file() for path in required):
        raise RuntimeError(
            "Projeto Controle de Traços não encontrado. "
            "Configure TRACES_PROJECT_DIR com o caminho da pasta prototipo-tracos."
        )
    return root


def _prepare_demo_project(root: Path) -> None:
    """Instala e compila Traços automaticamente em um clone público novo."""
    if os.getenv("QUALIMATCH_DEMO", "true").strip().lower() not in {"1", "true", "yes", "on"}:
        return
    if (root / "node_modules").is_dir() and (root / "dist" / "server").is_dir():
        return
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise RuntimeError("Node.js 22 ou superior não foi encontrado para preparar o módulo Traços.")
    for arguments in (("ci",), ("run", "build")):
        result = subprocess.run(
            [npm, *arguments], cwd=str(root), capture_output=True, text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "erro desconhecido").strip()
            raise RuntimeError(f"Não foi possível preparar o módulo Traços: {detail[-1200:]}")


def _remove_stale_dev_lock(root: Path) -> None:
    """Remove apenas a trava do vinext cujo processo já não existe."""
    lock = root / ".vinext" / "dev" / "lock.json"
    if not lock.is_file():
        return
    try:
        payload = json.loads(lock.read_text(encoding="utf-8"))
        pid = int(payload.get("pid") or 0)
    except (OSError, ValueError, json.JSONDecodeError):
        pid = 0
    if pid:
        try:
            os.kill(pid, 0)
            return
        except OSError:
            pass
    try:
        lock.unlink()
    except FileNotFoundError:
        pass


def _start_hidden(root: Path) -> None:
    global _managed_process
    child_env = os.environ.copy()
    # O QualiMatch pode usar outro DATABASE_URL. O Node só carrega valores do
    # .env.local quando eles ainda não existem no ambiente; portanto, herdar a
    # conexão daqui faria o Controle de Traços abrir o banco errado.
    for name in ("DATABASE_URL", "API_PORT", "APP_ORIGIN"):
        child_env.pop(name, None)
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", "npm run serve"]
    else:
        command = ["npm", "run", "serve"]
    _managed_process = subprocess.Popen(
        command,
        cwd=str(root),
        env=child_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
        close_fds=True,
    )


@_single_launch
def shutdown_traces_project() -> None:
    """Libera a instância que o usuário abriu pelo QualiMatch."""
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
    elif claimed and traces_project_ready():
        # A aplicação já podia estar ativa quando foi incorporada. Depois que
        # o QualiMatch a assume, também precisa liberá-la ao trocar de módulo.
        _stop_stale_instance()


def traces_project_login(
    email: str, name: str = "", is_admin: bool = False, permission_level: str = "VIEWER"
) -> dict | None:
    """Loga automaticamente no Controle de Traços com o e-mail já autenticado
    no QualiMatch, assinando a requisição com a chave compartilhada.

    Best-effort: qualquer falha (chave ainda não gerada, servidor sem banco,
    e-mail sem usuário cadastrado lá dentro etc.) só faz o iframe cair na tela
    de login normal — nunca impede o Controle de Traços de abrir.
    """
    email = (email or "").strip().lower()
    if not email:
        return None
    try:
        secret = _TRACES_SSO_SECRET_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not secret:
        return None
    name = (name or email.split("@", 1)[0]).strip()
    access = "ADMIN" if is_admin else str(permission_level or "VIEWER").upper().strip()
    timestamp = int(time.time() * 1000)
    signed = f"{email}|{name}|{access}|{timestamp}"
    signature = hmac.new(
        secret.encode("utf-8"), signed.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    body = json.dumps({
        "email": email, "name": name, "access": access,
        "timestamp": timestamp, "signature": signature,
    }).encode("utf-8")
    request = urllib.request.Request(
        f"{_TRACES_API_BASE}/api/sso-login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=3.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.HTTPError, ValueError):
        return None
    token, user = payload.get("token"), payload.get("user")
    if not token or not user:
        return None
    return {"token": token, "user": user}


@_single_launch
def launch_traces_project(
    wait_seconds: float = 150.0, user_email: str = "", user_name: str = "",
    is_admin: bool = False, permission_level: str = "VIEWER",
) -> dict:
    """Inicia o projeto somente quando necessário e aguarda ficar acessível."""
    global _claimed_by_qualimatch
    if traces_project_ready():
        _claimed_by_qualimatch = True
        result = {"ok": True, "url": TRACES_URL, "started": False, "status": "ready"}
        sso = traces_project_login(user_email, user_name, is_admin, permission_level)
        if sso:
            result["sso"] = sso
        return result

    root = _validate_project()
    _prepare_demo_project(root)
    _stop_stale_instance()
    _remove_stale_dev_lock(root)
    _start_hidden(root)
    deadline = time.monotonic() + max(1.0, wait_seconds)
    while time.monotonic() < deadline:
        if traces_project_ready():
            _claimed_by_qualimatch = True
            result = {"ok": True, "url": TRACES_URL, "started": True, "status": "ready"}
            sso = traces_project_login(user_email, user_name, is_admin, permission_level)
            if sso:
                result["sso"] = sso
            return result
        if _managed_process is not None and _managed_process.poll() is not None:
            raise RuntimeError(
                "O Controle de Traços encerrou durante a inicialização."
            )
        time.sleep(0.75)

    return {
        "ok": False,
        "url": TRACES_URL,
        "started": True,
        "status": "starting",
        "message": "O Controle de Traços foi iniciado, mas ainda está preparando a interface.",
    }
