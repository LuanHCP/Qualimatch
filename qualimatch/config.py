from __future__ import annotations

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
CERT_DIR = DATA_DIR / "certificados"
BACKUP_DIR = DATA_DIR / "backups"
DB_PATH = DATA_DIR / "qualimatch.db"
FRONTEND_DIR = BASE_DIR / "frontend"
DEMO_MODE = os.getenv("QUALIMATCH_DEMO", "true").strip().lower() not in {"0", "false", "no", "off"}

for p in (DATA_DIR, CACHE_DIR, CERT_DIR / "ARENA", CERT_DIR / "PAVIDEZ", BACKUP_DIR):
    p.mkdir(parents=True, exist_ok=True)

DEFAULT_SOURCES = [
    {
        "contractor": "ARENA",
        "kind": "medicao",
        "path": "",
        "worksheet": "RDO_RESTAURA",
    },
    {
        "contractor": "ARENA",
        "kind": "qualidade",
        "path": "",
        "worksheet": "BD_QUALI",
    },
    {
        "contractor": "PAVIDEZ",
        "kind": "medicao",
        "path": "",
        "worksheet": "RDO_RESTAURA",
    },
    {
        "contractor": "PAVIDEZ",
        "kind": "qualidade",
        "path": "",
        "worksheet": "BD_QUALI",
    },
    {"contractor": "ARENA", "kind": "kits", "path": "", "worksheet": "d.KIT"},
    {"contractor": "PAVIDEZ", "kind": "kits", "path": "", "worksheet": "d.KIT"},
    {"contractor": "ARENA", "kind": "kit_documentos", "path": "", "worksheet": ""},
    {"contractor": "PAVIDEZ", "kind": "kit_documentos", "path": "", "worksheet": ""},
    {"contractor": "ARENA", "kind": "certificados", "path": "", "worksheet": ""},
    {"contractor": "PAVIDEZ", "kind": "certificados", "path": "", "worksheet": ""},
    {"contractor": "ARENA", "kind": "bv_documentos", "path": "", "worksheet": ""},
    {"contractor": "PAVIDEZ", "kind": "bv_documentos", "path": "", "worksheet": ""},
]

AUTO_SYNC_SECONDS = 60
