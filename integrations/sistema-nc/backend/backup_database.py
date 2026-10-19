#!/usr/bin/env python3
"""Gera backup PostgreSQL compactado e mantém somente os últimos 30 dias."""
import datetime
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

for raw in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    if raw.strip() and not raw.lstrip().startswith("#") and "=" in raw:
        key, value = raw.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

pg_bin = ROOT / ".postgres-bin"
pg_dump = (Path(pg_bin.read_text(encoding="utf-8").strip()) / "pg_dump.exe") if pg_bin.exists() else Path("pg_dump")
backup_dir = ROOT / "backups"
backup_dir.mkdir(exist_ok=True)
stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
database = os.environ.get("PGDATABASE", "nc_sistema")
target = backup_dir / f"nc_sistema_{stamp}.backup"
env = os.environ.copy()
cmd = [str(pg_dump), "--format=custom", "--no-owner", "--file", str(target), database]
subprocess.run(cmd, env=env, check=True)

cutoff = datetime.datetime.now().timestamp() - (30 * 86400)
for old in backup_dir.glob("nc_sistema_*.backup"):
    if old != target and old.stat().st_mtime < cutoff:
        old.unlink()
print(f"Backup concluído: {target}")
