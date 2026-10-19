#!/usr/bin/env python3
"""Carrega a configuração local e inicia o servidor no Windows."""
import os
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def load_env():
    for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if raw and not raw.startswith("#") and "=" in raw:
            key, value = raw.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
    pg_bin = ROOT / ".postgres-bin"
    if pg_bin.exists():
        os.environ["PATH"] = pg_bin.read_text(encoding="utf-8").strip() + os.pathsep + os.environ.get("PATH", "")

def scrub_bootstrap_password():
    """Remove do disco a senha usada somente durante a instalação inicial."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    lines = env_path.read_text(encoding="utf-8").splitlines()
    clean = [line for line in lines if not line.startswith("BOOTSTRAP_ADMIN_PASSWORD=")]
    if clean != lines:
        env_path.write_text("\n".join(clean) + "\n", encoding="utf-8")

load_env()
scrub_bootstrap_password()
subprocess.run([str(ROOT / ".venv" / "Scripts" / "python.exe"), str(ROOT / "backend" / "migrate.py")], check=True)
sys.path.insert(0, str(ROOT / "backend"))
from app import app  # noqa: E402

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Sistema disponivel em http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=False, threaded=True)
