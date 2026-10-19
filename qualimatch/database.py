from __future__ import annotations

import gzip
import json
import os
import re
import shutil
import sqlite3
import atexit
from threading import Lock
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator, Any

from dotenv import load_dotenv

from .config import BASE_DIR, DB_PATH, DEFAULT_SOURCES, BACKUP_DIR

load_dotenv(BASE_DIR / ".env")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
USE_POSTGRES = DATABASE_URL.lower().startswith(("postgresql://", "postgres://"))
_pg_pool = None
_pg_pool_lock = Lock()


def close_pool() -> None:
    global _pg_pool
    with _pg_pool_lock:
        pool, _pg_pool = _pg_pool, None
    if pool is not None:
        pool.close()


def _connection_pool():
    global _pg_pool
    with _pg_pool_lock:
        if _pg_pool is None:
            from psycopg_pool import ConnectionPool
            from psycopg.rows import dict_row
            _pg_pool = ConnectionPool(
                DATABASE_URL, min_size=1, max_size=8, timeout=10,
                kwargs={'row_factory': dict_row, 'connect_timeout': 8,
                        'prepare_threshold': None},
                check=ConnectionPool.check_connection,
                open=True,
            )
        return _pg_pool


atexit.register(close_pool)


def backend_name() -> str:
    return "postgresql" if USE_POSTGRES else "sqlite"


def _pg_sql(sql: str) -> str:
    """Converte a sintaxe parametrizada usada pelo projeto para psycopg.

    O código legado usa placeholders '?' para manter compatibilidade com SQLite.
    A conversão fica centralizada aqui, evitando espalhar diferenças do driver.
    """
    sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, flags=re.I)
    if re.search(r"INSERT\s+INTO", sql, re.I) and "OR IGNORE" not in sql.upper() and "ON CONFLICT" not in sql.upper():
        # Nada a fazer: INSERT normal.
        pass
    sql = sql.replace("?", "%s")
    return sql


class _PGConnection:
    backend = "postgresql"

    def __init__(self, raw, pool=None):
        self.raw = raw
        self.pool = pool
        self._closed = False

    def execute(self, sql: str, params=()):
        # INSERT OR IGNORE é usado apenas em inserts de configuração. Em PG,
        # acrescenta ON CONFLICT DO NOTHING quando ainda não há cláusula explícita.
        ignore = bool(re.search(r"INSERT\s+OR\s+IGNORE\s+INTO", sql, re.I))
        converted = _pg_sql(sql)
        if ignore and "ON CONFLICT" not in converted.upper():
            converted = converted.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        return self.raw.execute(converted, params)

    def executemany(self, sql: str, seq):
        ignore = bool(re.search(r"INSERT\s+OR\s+IGNORE\s+INTO", sql, re.I))
        converted = _pg_sql(sql)
        if ignore and "ON CONFLICT" not in converted.upper():
            converted = converted.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        with self.raw.cursor() as cur:
            cur.executemany(converted, seq)
        return cur

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self.pool is None:
            self.raw.close()
            return
        # Never return an uncommitted write or a failed transaction to another
        # request. Explicit transaction() callers have already committed.
        try:
            if not self.raw.closed:
                self.raw.rollback()
        except Exception:
            self.raw.close()
        finally:
            self.pool.putconn(self.raw)


class _SQLiteConnection:
    backend = "sqlite"

    def __init__(self, raw: sqlite3.Connection):
        self.raw = raw

    def execute(self, sql: str, params=()):
        return self.raw.execute(sql, params)

    def executemany(self, sql: str, seq):
        return self.raw.executemany(sql, seq)

    def executescript(self, script: str):
        return self.raw.executescript(script)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        self.raw.close()

    def backup(self, target):
        target_raw = getattr(target, "raw", target)
        return self.raw.backup(target_raw)


def connect(path: Path | str | None = None):
    # Um path explícito sempre significa SQLite (usado por testes e migração).
    if path is not None or not USE_POSTGRES:
        p = Path(path) if path is not None else DB_PATH
        raw = sqlite3.connect(str(p), timeout=30, check_same_thread=False)
        raw.row_factory = sqlite3.Row
        raw.execute("PRAGMA journal_mode=WAL")
        raw.execute("PRAGMA synchronous=NORMAL")
        raw.execute("PRAGMA busy_timeout=30000")
        raw.execute("PRAGMA foreign_keys=ON")
        return _SQLiteConnection(raw)

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as e:
        raise RuntimeError("PostgreSQL configurado, mas psycopg não está instalado. Rode instalar.bat.") from e
    try:
        pool = _connection_pool()
    except ImportError:
        # Existing installations remain usable until requirements are updated.
        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=8)
        return _PGConnection(raw)
    return _PGConnection(pool.getconn(), pool)


@contextmanager
def transaction(path: Path | str | None = None) -> Iterator[Any]:
    con = connect(path)
    try:
        if con.backend == "sqlite":
            con.execute("BEGIN IMMEDIATE")
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _column_names(con, table: str) -> set[str]:
    if con.backend == "sqlite":
        return {r[1] for r in con.raw.execute(f"PRAGMA table_info({table})").fetchall()}
    return {
        r["column_name"]
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=?",
            (table,),
        ).fetchall()
    }


def _ensure_column(con, table: str, definition: str) -> None:
    name = definition.split()[0]
    if name not in _column_names(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")


def _road_from_saved_path(value: str | None) -> str:
    m = re.search(r"(?<![A-Z0-9])(BR|PR)\s*[-_/ ]?\s*(\d{2,3})(?!\d)", value or "", re.I)
    return f"{m.group(1).upper()}-{m.group(2)}" if m else ""


SQLITE_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources (
 contractor TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL DEFAULT '', worksheet TEXT NOT NULL DEFAULT '',
 enabled INTEGER NOT NULL DEFAULT 1,last_mtime_ns INTEGER,last_size INTEGER,last_hash TEXT NOT NULL DEFAULT '',
 last_sync TEXT,last_status TEXT NOT NULL DEFAULT 'NUNCA',last_error TEXT NOT NULL DEFAULT '',PRIMARY KEY(contractor,kind));
CREATE TABLE IF NOT EXISTS sync_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT,contractor TEXT,kind TEXT NOT NULL,status TEXT NOT NULL,message TEXT NOT NULL DEFAULT '',
 records INTEGER NOT NULL DEFAULT 0,source_path TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS measurements (
 id INTEGER PRIMARY KEY AUTOINCREMENT,contractor TEXT NOT NULL,source_row INTEGER NOT NULL,line_measurement TEXT NOT NULL DEFAULT '',
 ref_measurement TEXT NOT NULL DEFAULT '',team TEXT NOT NULL DEFAULT '',inspector TEXT NOT NULL DEFAULT '',date TEXT,road TEXT NOT NULL DEFAULT '',
 direction TEXT NOT NULL DEFAULT '',kmi INTEGER,kmf INTEGER,lane TEXT NOT NULL DEFAULT '',extension_m REAL,width_m REAL,thickness_m REAL,
 scope TEXT NOT NULL DEFAULT '',mass_type TEXT NOT NULL DEFAULT '',area_m2 REAL,paint_m2 REAL,volume_mass_m3 REAL,volume_milled_m3 REAL,
 quantity_t REAL,dmt_milled_km REAL,raw_json TEXT NOT NULL DEFAULT '{}',UNIQUE(contractor,source_row));
CREATE TABLE IF NOT EXISTS quality_rows (
 id INTEGER PRIMARY KEY AUTOINCREMENT,contractor TEXT NOT NULL,source_row INTEGER NOT NULL,visible_excel INTEGER NOT NULL DEFAULT 1,
 line_measurement TEXT NOT NULL DEFAULT '',ref_measurement TEXT NOT NULL DEFAULT '',date TEXT,road TEXT NOT NULL DEFAULT '',direction TEXT NOT NULL DEFAULT '',
 kmi INTEGER,kmf INTEGER,lane TEXT NOT NULL DEFAULT '',trace_code TEXT NOT NULL DEFAULT '',status_final TEXT NOT NULL DEFAULT '',
 status_summary TEXT NOT NULL DEFAULT '',extension_m REAL,volume_mass_m3 REAL,quantity_t REAL,cap_project_t REAL,total_service REAL,
 proposed_retention REAL,raw_json TEXT NOT NULL DEFAULT '{}',UNIQUE(contractor,source_row));
CREATE TABLE IF NOT EXISTS quality_snapshots (
 id INTEGER PRIMARY KEY AUTOINCREMENT,contractor TEXT NOT NULL,synced_at TEXT NOT NULL,source_path TEXT NOT NULL,source_mtime TEXT NOT NULL DEFAULT '',
 total_service REAL,total_service_visible_sum REAL,total_difference REAL,total_source_cell TEXT NOT NULL DEFAULT '',extension_m REAL,
 volume_mass_m3 REAL,quantity_t REAL,cap_project_t REAL,proposed_retention REAL,visible_records INTEGER NOT NULL DEFAULT 0,
 total_records INTEGER NOT NULL DEFAULT 0,warning TEXT NOT NULL DEFAULT '',summary_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS certificates (
 id INTEGER PRIMARY KEY AUTOINCREMENT,identity_key TEXT NOT NULL UNIQUE,contractor TEXT NOT NULL,number TEXT NOT NULL,file_path TEXT NOT NULL,
 file_hash TEXT NOT NULL,service_date TEXT,extraction_date TEXT,road TEXT NOT NULL DEFAULT '',kmi INTEGER,kmf INTEGER,
 trace_approved TEXT NOT NULL DEFAULT '',routine_result TEXT NOT NULL DEFAULT '',counterproof_result TEXT NOT NULL DEFAULT '',
 has_counterproof INTEGER NOT NULL DEFAULT 0,parsed_at TEXT NOT NULL,raw_json TEXT NOT NULL DEFAULT '{}',is_active INTEGER NOT NULL DEFAULT 1,
 deleted_at TEXT,deleted_reason TEXT NOT NULL DEFAULT '',manual_override INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS certificate_files (
 id INTEGER PRIMARY KEY AUTOINCREMENT,contractor TEXT NOT NULL,certificate_id INTEGER REFERENCES certificates(id) ON DELETE SET NULL,
 file_path TEXT NOT NULL,file_name TEXT NOT NULL DEFAULT '',mtime_ns INTEGER,size INTEGER,file_hash TEXT NOT NULL DEFAULT '',kind TEXT NOT NULL DEFAULT 'ROTINA',
 status TEXT NOT NULL DEFAULT 'OK',parser_version TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',parsed_at TEXT NOT NULL DEFAULT '',UNIQUE(contractor,file_path));
CREATE TABLE IF NOT EXISTS certificate_samples (
 id INTEGER PRIMARY KEY AUTOINCREMENT,certificate_id INTEGER NOT NULL REFERENCES certificates(id) ON DELETE CASCADE,phase TEXT NOT NULL,
 cp_number TEXT NOT NULL DEFAULT '',application_date TEXT,counterproof INTEGER NOT NULL DEFAULT 0,direction TEXT NOT NULL DEFAULT '',lane TEXT NOT NULL DEFAULT '',
 station INTEGER,position TEXT NOT NULL DEFAULT '',thickness_exec_cm REAL,thickness_project_cm REAL,ratio_ab_pct REAL,rice_gmm REAL,gmb REAL,voids_pct REAL,
 UNIQUE(certificate_id,phase,cp_number,station,counterproof));
CREATE TABLE IF NOT EXISTS matches (
 measurement_id INTEGER PRIMARY KEY REFERENCES measurements(id) ON DELETE CASCADE,certificate_id INTEGER REFERENCES certificates(id) ON DELETE SET NULL,
 score INTEGER NOT NULL DEFAULT 0,reason TEXT NOT NULL DEFAULT '',matched_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS kit_rows (
 id INTEGER PRIMARY KEY AUTOINCREMENT,contractor TEXT NOT NULL,source_row INTEGER NOT NULL,seq TEXT NOT NULL DEFAULT '',service TEXT NOT NULL DEFAULT '',
 application_date TEXT,mix_project TEXT NOT NULL DEFAULT '',period TEXT NOT NULL DEFAULT '',road TEXT NOT NULL DEFAULT '',kmi INTEGER,kmf INTEGER,
 receipt_date TEXT,delivery_status TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT '',status_1 TEXT NOT NULL DEFAULT '',status_2 TEXT NOT NULL DEFAULT '',status_3 TEXT NOT NULL DEFAULT '',
 status_4 TEXT NOT NULL DEFAULT '',status_5 TEXT NOT NULL DEFAULT '',status_6 TEXT NOT NULL DEFAULT '',status_7 TEXT NOT NULL DEFAULT '',
 status_8 TEXT NOT NULL DEFAULT '',sin_retro TEXT NOT NULL DEFAULT '',raw_json TEXT NOT NULL DEFAULT '{}',UNIQUE(contractor,source_row));
CREATE TABLE IF NOT EXISTS kit_documents (
 id INTEGER PRIMARY KEY AUTOINCREMENT,contractor TEXT NOT NULL,kit_id INTEGER REFERENCES kit_rows(id) ON DELETE SET NULL,
 file_path TEXT NOT NULL,file_name TEXT NOT NULL,relative_path TEXT NOT NULL DEFAULT '',folder TEXT NOT NULL DEFAULT '',extension TEXT NOT NULL DEFAULT '',
 size INTEGER NOT NULL DEFAULT 0,mtime_ns INTEGER NOT NULL DEFAULT 0,seq_guess TEXT NOT NULL DEFAULT '',synced_at TEXT NOT NULL,UNIQUE(contractor,file_path));

CREATE TABLE IF NOT EXISTS pending_justifications (
 pending_key TEXT PRIMARY KEY,contractor TEXT NOT NULL,reason TEXT NOT NULL,item_json TEXT NOT NULL DEFAULT '{}',
 justified_by INTEGER,justified_at TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'USER',
 status TEXT NOT NULL DEFAULT 'PENDING',access_bv INTEGER NOT NULL DEFAULT 0,access_contractor INTEGER NOT NULL DEFAULT 0,access_quality_general INTEGER NOT NULL DEFAULT 0,
 access_quality_nc INTEGER NOT NULL DEFAULT 0,
 access_arena INTEGER NOT NULL DEFAULT 0,access_pavidez INTEGER NOT NULL DEFAULT 0,permission_level TEXT NOT NULL DEFAULT 'VIEWER',
 created_at TEXT NOT NULL,approved_at TEXT,approved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
 last_login TEXT,rejected_at TEXT,blocked_at TEXT,password_changed_at TEXT);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,created_at TEXT NOT NULL,expires_at TEXT NOT NULL,
 last_seen_at TEXT NOT NULL DEFAULT '',ip_address TEXT NOT NULL DEFAULT '',user_agent TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS password_reset_tokens (
 token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,created_at TEXT NOT NULL,expires_at TEXT NOT NULL,used_at TEXT);
CREATE TABLE IF NOT EXISTS audit_log (
 id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,action TEXT NOT NULL,entity_type TEXT NOT NULL DEFAULT '',
 entity_id TEXT NOT NULL DEFAULT '',details_json TEXT NOT NULL DEFAULT '{}',ip_address TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS change_history (
 id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,action TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,
 before_json TEXT NOT NULL DEFAULT '{}',after_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,undone_at TEXT,undone_by INTEGER REFERENCES users(id) ON DELETE SET NULL);
"""

POSTGRES_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sources (
 contractor TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL DEFAULT '', worksheet TEXT NOT NULL DEFAULT '',
 enabled INTEGER NOT NULL DEFAULT 1,last_mtime_ns BIGINT,last_size BIGINT,last_hash TEXT NOT NULL DEFAULT '',
 last_sync TEXT,last_status TEXT NOT NULL DEFAULT 'NUNCA',last_error TEXT NOT NULL DEFAULT '',PRIMARY KEY(contractor,kind));
CREATE TABLE IF NOT EXISTS sync_log (
 id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,contractor TEXT,kind TEXT NOT NULL,status TEXT NOT NULL,message TEXT NOT NULL DEFAULT '',
 records INTEGER NOT NULL DEFAULT 0,source_path TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS measurements (
 id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,contractor TEXT NOT NULL,source_row INTEGER NOT NULL,line_measurement TEXT NOT NULL DEFAULT '',
 ref_measurement TEXT NOT NULL DEFAULT '',team TEXT NOT NULL DEFAULT '',inspector TEXT NOT NULL DEFAULT '',date TEXT,road TEXT NOT NULL DEFAULT '',
 direction TEXT NOT NULL DEFAULT '',kmi INTEGER,kmf INTEGER,lane TEXT NOT NULL DEFAULT '',extension_m DOUBLE PRECISION,width_m DOUBLE PRECISION,
 thickness_m DOUBLE PRECISION,scope TEXT NOT NULL DEFAULT '',mass_type TEXT NOT NULL DEFAULT '',area_m2 DOUBLE PRECISION,paint_m2 DOUBLE PRECISION,
 volume_mass_m3 DOUBLE PRECISION,volume_milled_m3 DOUBLE PRECISION,quantity_t DOUBLE PRECISION,dmt_milled_km DOUBLE PRECISION,
 raw_json TEXT NOT NULL DEFAULT '{}',UNIQUE(contractor,source_row));
CREATE TABLE IF NOT EXISTS quality_rows (
 id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,contractor TEXT NOT NULL,source_row INTEGER NOT NULL,visible_excel INTEGER NOT NULL DEFAULT 1,
 line_measurement TEXT NOT NULL DEFAULT '',ref_measurement TEXT NOT NULL DEFAULT '',date TEXT,road TEXT NOT NULL DEFAULT '',direction TEXT NOT NULL DEFAULT '',
 kmi INTEGER,kmf INTEGER,lane TEXT NOT NULL DEFAULT '',trace_code TEXT NOT NULL DEFAULT '',status_final TEXT NOT NULL DEFAULT '',
 status_summary TEXT NOT NULL DEFAULT '',extension_m DOUBLE PRECISION,volume_mass_m3 DOUBLE PRECISION,quantity_t DOUBLE PRECISION,
 cap_project_t DOUBLE PRECISION,total_service DOUBLE PRECISION,proposed_retention DOUBLE PRECISION,raw_json TEXT NOT NULL DEFAULT '{}',
 UNIQUE(contractor,source_row));
CREATE TABLE IF NOT EXISTS quality_snapshots (
 id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,contractor TEXT NOT NULL,synced_at TEXT NOT NULL,source_path TEXT NOT NULL,
 source_mtime TEXT NOT NULL DEFAULT '',total_service DOUBLE PRECISION,total_service_visible_sum DOUBLE PRECISION,total_difference DOUBLE PRECISION,
 total_source_cell TEXT NOT NULL DEFAULT '',extension_m DOUBLE PRECISION,volume_mass_m3 DOUBLE PRECISION,quantity_t DOUBLE PRECISION,
 cap_project_t DOUBLE PRECISION,proposed_retention DOUBLE PRECISION,visible_records INTEGER NOT NULL DEFAULT 0,total_records INTEGER NOT NULL DEFAULT 0,
 warning TEXT NOT NULL DEFAULT '',summary_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS certificates (
 id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,identity_key TEXT NOT NULL UNIQUE,contractor TEXT NOT NULL,number TEXT NOT NULL,
 file_path TEXT NOT NULL,file_hash TEXT NOT NULL,service_date TEXT,extraction_date TEXT,road TEXT NOT NULL DEFAULT '',kmi INTEGER,kmf INTEGER,
 trace_approved TEXT NOT NULL DEFAULT '',routine_result TEXT NOT NULL DEFAULT '',counterproof_result TEXT NOT NULL DEFAULT '',
 has_counterproof INTEGER NOT NULL DEFAULT 0,parsed_at TEXT NOT NULL,raw_json TEXT NOT NULL DEFAULT '{}',is_active INTEGER NOT NULL DEFAULT 1,
 deleted_at TEXT,deleted_reason TEXT NOT NULL DEFAULT '',manual_override INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS certificate_files (
 id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,contractor TEXT NOT NULL,certificate_id INTEGER REFERENCES certificates(id) ON DELETE SET NULL,
 file_path TEXT NOT NULL,file_name TEXT NOT NULL DEFAULT '',mtime_ns BIGINT,size BIGINT,file_hash TEXT NOT NULL DEFAULT '',kind TEXT NOT NULL DEFAULT 'ROTINA',
 status TEXT NOT NULL DEFAULT 'OK',parser_version TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',parsed_at TEXT NOT NULL DEFAULT '',
 UNIQUE(contractor,file_path));
CREATE TABLE IF NOT EXISTS certificate_samples (
 id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,certificate_id INTEGER NOT NULL REFERENCES certificates(id) ON DELETE CASCADE,phase TEXT NOT NULL,
 cp_number TEXT NOT NULL DEFAULT '',application_date TEXT,counterproof INTEGER NOT NULL DEFAULT 0,direction TEXT NOT NULL DEFAULT '',lane TEXT NOT NULL DEFAULT '',
 station INTEGER,position TEXT NOT NULL DEFAULT '',thickness_exec_cm DOUBLE PRECISION,thickness_project_cm DOUBLE PRECISION,
 ratio_ab_pct DOUBLE PRECISION,rice_gmm DOUBLE PRECISION,gmb DOUBLE PRECISION,voids_pct DOUBLE PRECISION,
 UNIQUE(certificate_id,phase,cp_number,station,counterproof));
CREATE TABLE IF NOT EXISTS matches (
 measurement_id INTEGER PRIMARY KEY REFERENCES measurements(id) ON DELETE CASCADE,certificate_id INTEGER REFERENCES certificates(id) ON DELETE SET NULL,
 score INTEGER NOT NULL DEFAULT 0,reason TEXT NOT NULL DEFAULT '',matched_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS kit_rows (
 id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,contractor TEXT NOT NULL,source_row INTEGER NOT NULL,seq TEXT NOT NULL DEFAULT '',service TEXT NOT NULL DEFAULT '',
 application_date TEXT,mix_project TEXT NOT NULL DEFAULT '',period TEXT NOT NULL DEFAULT '',road TEXT NOT NULL DEFAULT '',kmi INTEGER,kmf INTEGER,
 receipt_date TEXT,delivery_status TEXT NOT NULL DEFAULT '',status TEXT NOT NULL DEFAULT '',status_1 TEXT NOT NULL DEFAULT '',status_2 TEXT NOT NULL DEFAULT '',status_3 TEXT NOT NULL DEFAULT '',
 status_4 TEXT NOT NULL DEFAULT '',status_5 TEXT NOT NULL DEFAULT '',status_6 TEXT NOT NULL DEFAULT '',status_7 TEXT NOT NULL DEFAULT '',
 status_8 TEXT NOT NULL DEFAULT '',sin_retro TEXT NOT NULL DEFAULT '',raw_json TEXT NOT NULL DEFAULT '{}',UNIQUE(contractor,source_row));
CREATE TABLE IF NOT EXISTS kit_documents (
 id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,contractor TEXT NOT NULL,kit_id INTEGER REFERENCES kit_rows(id) ON DELETE SET NULL,
 file_path TEXT NOT NULL,file_name TEXT NOT NULL,relative_path TEXT NOT NULL DEFAULT '',folder TEXT NOT NULL DEFAULT '',extension TEXT NOT NULL DEFAULT '',
 size BIGINT NOT NULL DEFAULT 0,mtime_ns BIGINT NOT NULL DEFAULT 0,seq_guess TEXT NOT NULL DEFAULT '',synced_at TEXT NOT NULL,UNIQUE(contractor,file_path));

CREATE TABLE IF NOT EXISTS pending_justifications (
 pending_key TEXT PRIMARY KEY,contractor TEXT NOT NULL,reason TEXT NOT NULL,item_json TEXT NOT NULL DEFAULT '{}',
 justified_by INTEGER,justified_at TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS users (
 id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,role TEXT NOT NULL DEFAULT 'USER',
 status TEXT NOT NULL DEFAULT 'PENDING',access_bv INTEGER NOT NULL DEFAULT 0,access_contractor INTEGER NOT NULL DEFAULT 0,access_quality_general INTEGER NOT NULL DEFAULT 0,
 access_quality_nc INTEGER NOT NULL DEFAULT 0,
 access_arena INTEGER NOT NULL DEFAULT 0,access_pavidez INTEGER NOT NULL DEFAULT 0,permission_level TEXT NOT NULL DEFAULT 'VIEWER',
 created_at TEXT NOT NULL,approved_at TEXT,approved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
 last_login TEXT,rejected_at TEXT,blocked_at TEXT,password_changed_at TEXT);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,created_at TEXT NOT NULL,expires_at TEXT NOT NULL,
 last_seen_at TEXT NOT NULL DEFAULT '',ip_address TEXT NOT NULL DEFAULT '',user_agent TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS password_reset_tokens (
 token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,created_at TEXT NOT NULL,expires_at TEXT NOT NULL,used_at TEXT);
CREATE TABLE IF NOT EXISTS audit_log (
 id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,action TEXT NOT NULL,entity_type TEXT NOT NULL DEFAULT '',
 entity_id TEXT NOT NULL DEFAULT '',details_json TEXT NOT NULL DEFAULT '{}',ip_address TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS change_history (
 id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,action TEXT NOT NULL,entity_type TEXT NOT NULL,entity_id TEXT NOT NULL,
 before_json TEXT NOT NULL DEFAULT '{}',after_json TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,undone_at TEXT,undone_by INTEGER REFERENCES users(id) ON DELETE SET NULL);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_measurements_date ON measurements(contractor,date)",
    "CREATE INDEX IF NOT EXISTS idx_measurements_road ON measurements(contractor,road,kmi,kmf)",
    "CREATE INDEX IF NOT EXISTS idx_quality_date ON quality_rows(contractor,date)",
    "CREATE INDEX IF NOT EXISTS idx_quality_status ON quality_rows(contractor,status_final)",
    "CREATE INDEX IF NOT EXISTS idx_quality_snapshots ON quality_snapshots(contractor,id DESC)",
    "CREATE INDEX IF NOT EXISTS idx_cert_number ON certificates(contractor,number)",
    "CREATE INDEX IF NOT EXISTS idx_cert_date ON certificates(contractor,service_date)",
    "CREATE INDEX IF NOT EXISTS idx_cert_extraction_date ON certificates(contractor,extraction_date)",
    "CREATE INDEX IF NOT EXISTS idx_cert_active ON certificates(contractor,is_active)",
    "CREATE INDEX IF NOT EXISTS idx_cert_active_date ON certificates(contractor,is_active,extraction_date)",
    "CREATE INDEX IF NOT EXISTS idx_cert_active_road_segment ON certificates(contractor,is_active,road,kmi,kmf)",
    "CREATE INDEX IF NOT EXISTS idx_certificate_files_cert ON certificate_files(certificate_id)",
    "CREATE INDEX IF NOT EXISTS idx_certificate_samples_cert ON certificate_samples(certificate_id)",
    "CREATE INDEX IF NOT EXISTS idx_certificate_samples_date ON certificate_samples(application_date)",
    "CREATE INDEX IF NOT EXISTS idx_matches_cert ON matches(certificate_id)",
    "CREATE INDEX IF NOT EXISTS idx_kits_date ON kit_rows(contractor,application_date)",
    "CREATE INDEX IF NOT EXISTS idx_kits_road ON kit_rows(contractor,road,kmi,kmf)",
    "CREATE INDEX IF NOT EXISTS idx_kits_status ON kit_rows(contractor,status)",
    "CREATE INDEX IF NOT EXISTS idx_kit_docs_contract ON kit_documents(contractor,kit_id)",
    "CREATE INDEX IF NOT EXISTS idx_kit_docs_name ON kit_documents(contractor,file_name)",
    "CREATE INDEX IF NOT EXISTS idx_pending_justifications ON pending_justifications(contractor,active,justified_at)",
    "CREATE INDEX IF NOT EXISTS idx_users_status ON users(status,role)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id,expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_reset_user ON password_reset_tokens(user_id,expires_at)",
    "CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)",
    "CREATE INDEX IF NOT EXISTS idx_change_history_entity ON change_history(entity_type,entity_id,id)",
]


def _run_script(con, script: str) -> None:
    if con.backend == "sqlite":
        con.executescript(script)
        return
    for statement in script.split(";"):
        statement = statement.strip()
        if statement:
            con.execute(statement)


def init_db(path: Path | str | None = None) -> None:
    with transaction(path) as con:
        _run_script(con, POSTGRES_SCHEMA if con.backend == "postgresql" else SQLITE_SCHEMA)
        con.execute("""CREATE TABLE IF NOT EXISTS email_notification_preferences (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            bv_new_certificates INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
        )""")
        con.execute("""CREATE TABLE IF NOT EXISTS email_notification_outbox (
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            certificate_id INTEGER NOT NULL REFERENCES certificates(id) ON DELETE CASCADE,
            topic TEXT NOT NULL DEFAULT 'BV_NEW_CERTIFICATE',
            status TEXT NOT NULL DEFAULT 'PENDING', attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at BIGINT NOT NULL DEFAULT 0, claimed_at BIGINT NOT NULL DEFAULT 0,
            claim_token TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            sent_at TEXT, last_error TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(user_id,certificate_id,topic)
        )""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_email_outbox_ready ON email_notification_outbox(status,next_attempt_at)")
        # v3.8.1 — eventos do monitor automático de pastas locais do SharePoint/OneDrive.
        # A tabela é criada fora dos schemas legados para manter a migração simples
        # tanto no SQLite quanto no PostgreSQL já existente.
        if con.backend == "postgresql":
            con.execute("""CREATE TABLE IF NOT EXISTS auto_import_events (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                contractor TEXT NOT NULL, portal TEXT NOT NULL, kind TEXT NOT NULL,
                file_path TEXT NOT NULL DEFAULT '', file_name TEXT NOT NULL DEFAULT '',
                signature TEXT NOT NULL DEFAULT '', event_type TEXT NOT NULL DEFAULT 'NOVO',
                status TEXT NOT NULL DEFAULT 'DETECTADO', message TEXT NOT NULL DEFAULT '',
                detected_at TEXT NOT NULL, processed_at TEXT,
                UNIQUE(contractor,kind,file_path,signature,event_type)
            )""")
        else:
            con.execute("""CREATE TABLE IF NOT EXISTS auto_import_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contractor TEXT NOT NULL, portal TEXT NOT NULL, kind TEXT NOT NULL,
                file_path TEXT NOT NULL DEFAULT '', file_name TEXT NOT NULL DEFAULT '',
                signature TEXT NOT NULL DEFAULT '', event_type TEXT NOT NULL DEFAULT 'NOVO',
                status TEXT NOT NULL DEFAULT 'DETECTADO', message TEXT NOT NULL DEFAULT '',
                detected_at TEXT NOT NULL, processed_at TEXT,
                UNIQUE(contractor,kind,file_path,signature,event_type)
            )""")
        # v3.8.3 — índice recursivo de arquivos da BV organizados por pasta/medição.
        if con.backend == "postgresql":
            con.execute("""CREATE TABLE IF NOT EXISTS bv_documents (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                contractor TEXT NOT NULL, file_path TEXT NOT NULL, file_name TEXT NOT NULL,
                relative_path TEXT NOT NULL DEFAULT '', folder TEXT NOT NULL DEFAULT '', top_folder TEXT NOT NULL DEFAULT '',
                measurement_label TEXT NOT NULL DEFAULT '', extension TEXT NOT NULL DEFAULT '', size BIGINT NOT NULL DEFAULT 0,
                mtime_ns BIGINT NOT NULL DEFAULT 0, synced_at TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1,
                manual_override INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by INTEGER, UNIQUE(contractor,file_path)
            )""")
        else:
            con.execute("""CREATE TABLE IF NOT EXISTS bv_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contractor TEXT NOT NULL, file_path TEXT NOT NULL, file_name TEXT NOT NULL,
                relative_path TEXT NOT NULL DEFAULT '', folder TEXT NOT NULL DEFAULT '', top_folder TEXT NOT NULL DEFAULT '',
                measurement_label TEXT NOT NULL DEFAULT '', extension TEXT NOT NULL DEFAULT '', size INTEGER NOT NULL DEFAULT 0,
                mtime_ns INTEGER NOT NULL DEFAULT 0, synced_at TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 1,
                manual_override INTEGER NOT NULL DEFAULT 0, archived_at TEXT, archived_by INTEGER, UNIQUE(contractor,file_path)
            )""")
        for idx in INDEXES:
            con.execute(idx)
        con.execute("CREATE INDEX IF NOT EXISTS idx_auto_import_events_created ON auto_import_events(detected_at)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_auto_import_events_kind ON auto_import_events(contractor,kind,status)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_bv_documents_contract ON bv_documents(contractor,measurement_label)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_bv_documents_name ON bv_documents(contractor,file_name)")

        # Colunas de compatibilidade para bancos SQLite/PostgreSQL antigos.
        # IMPORTANTE: índices que usam colunas novas precisam ser criados somente
        # depois de _ensure_column, senão um banco existente da v3.8.3 falha no startup.
        _ensure_column(con, "sources", "last_hash TEXT NOT NULL DEFAULT ''")
        _ensure_column(con, "quality_snapshots", "summary_json TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(con, "certificates", "extraction_date TEXT")
        _ensure_column(con, "certificates", "is_active INTEGER NOT NULL DEFAULT 1")
        _ensure_column(con, "certificates", "deleted_at TEXT")
        _ensure_column(con, "certificates", "deleted_reason TEXT NOT NULL DEFAULT ''")
        _ensure_column(con, "certificates", "manual_override INTEGER NOT NULL DEFAULT 0")
        _ensure_column(con, "certificate_files", "parser_version TEXT NOT NULL DEFAULT ''")
        _ensure_column(con, "certificate_files", "snapshot_path TEXT NOT NULL DEFAULT ''")
        _ensure_column(con, "certificate_samples", "rice_gmm DOUBLE PRECISION")
        # v3.7.5 — edição lógica dos kits sem perder alterações em novas sincronizações.
        _ensure_column(con, "kit_rows", "is_active INTEGER NOT NULL DEFAULT 1")
        _ensure_column(con, "kit_rows", "manual_override INTEGER NOT NULL DEFAULT 0")
        _ensure_column(con, "kit_rows", "updated_at TEXT")
        _ensure_column(con, "kit_rows", "updated_by INTEGER")
        # v3.8.8 — situação explícita da coluna ENTREGA da planilha da construtora.
        _ensure_column(con, "kit_rows", "delivery_status TEXT NOT NULL DEFAULT ''")
        # v3.8.4 — Arquivos BV podem ser arquivados logicamente sem apagar o SharePoint.
        _ensure_column(con, "bv_documents", "is_active INTEGER NOT NULL DEFAULT 1")
        _ensure_column(con, "bv_documents", "manual_override INTEGER NOT NULL DEFAULT 0")
        _ensure_column(con, "bv_documents", "archived_at TEXT")
        _ensure_column(con, "bv_documents", "archived_by INTEGER")
        con.execute("CREATE INDEX IF NOT EXISTS idx_bv_documents_active ON bv_documents(contractor,is_active,measurement_label)")
        users_columns_before = _column_names(con, "users")
        had_portal_access_columns = "access_bv" in users_columns_before and "access_contractor" in users_columns_before
        had_quality_general_access = "access_quality_general" in users_columns_before
        had_quality_nc_access = "access_quality_nc" in users_columns_before
        had_contractor_scope_columns = "access_arena" in users_columns_before and "access_pavidez" in users_columns_before
        _ensure_column(con, "users", "access_bv INTEGER NOT NULL DEFAULT 0")
        _ensure_column(con, "users", "access_contractor INTEGER NOT NULL DEFAULT 0")
        _ensure_column(con, "users", "access_quality_general INTEGER NOT NULL DEFAULT 0")
        _ensure_column(con, "users", "access_quality_nc INTEGER NOT NULL DEFAULT 0")
        _ensure_column(con, "users", "access_arena INTEGER NOT NULL DEFAULT 0")
        _ensure_column(con, "users", "access_pavidez INTEGER NOT NULL DEFAULT 0")
        permission_columns_before = _column_names(con, "users")
        had_permission_level = "permission_level" in permission_columns_before
        _ensure_column(con, "users", "permission_level TEXT NOT NULL DEFAULT 'VIEWER'")
        _ensure_column(con, "users", "last_login TEXT")
        _ensure_column(con, "users", "rejected_at TEXT")
        _ensure_column(con, "users", "blocked_at TEXT")
        _ensure_column(con, "users", "password_changed_at TEXT")

        # v3.3.0 — somente na primeira migração: preserva o comportamento das
        # versões anteriores dando BV aos usuários já aprovados. Depois disso,
        # acesso zero é uma decisão administrativa válida e não pode ser revertida
        # automaticamente em cada reinício.
        if not had_portal_access_columns:
            con.execute("UPDATE users SET access_bv=1 WHERE status='APPROVED' AND role<>'ADMIN'")
            con.execute("UPDATE users SET access_bv=1,access_contractor=1 WHERE role='ADMIN'")
        if not had_quality_general_access:
            con.execute("UPDATE users SET access_quality_general=1 WHERE role='ADMIN'")
        # v3.9.0 — separa Traços e Não conformidades em permissões independentes
        # (antes as duas ficavam atrás do mesmo access_quality_general, igual a
        # ter que "logar de novo" para algo que já devia estar liberado). Em
        # bancos existentes, quem já tinha a permissão combinada recebe as duas
        # uma única vez; depois o ADMIN pode conceder cada uma separadamente,
        # igual já acontece com BV/Contratada.
        if not had_quality_nc_access:
            con.execute("UPDATE users SET access_quality_nc=1 WHERE role='ADMIN'")
            con.execute("UPDATE users SET access_quality_nc=1 WHERE access_quality_general=1")
        # v3.7.4 — isola Arena/Pavidez dentro do portal Contratada. Em bancos
        # existentes preserva o acesso atual: quem já tinha Contratada recebe as
        # duas empresas uma única vez; depois o ADMIN pode restringir individualmente.
        if not had_contractor_scope_columns:
            con.execute("UPDATE users SET access_arena=1,access_pavidez=1 WHERE access_contractor=1")
            con.execute("UPDATE users SET access_arena=1,access_pavidez=1 WHERE role='ADMIN'")
        # v3.8.0 — nível operacional. Para preservar o comportamento anterior,
        # usuários já existentes passam a EDITOR apenas na primeira migração.
        if not had_permission_level:
            con.execute("UPDATE users SET permission_level='EDITOR' WHERE role<>'ADMIN' AND status='APPROVED'")
            con.execute("UPDATE users SET permission_level='ADMIN' WHERE role='ADMIN'")

        for cert in con.execute("SELECT id,raw_json FROM certificates WHERE extraction_date IS NULL").fetchall():
            try:
                raw = json.loads(cert["raw_json"] or "{}")
                dates = raw.get("extraction_dates") or []
                if dates:
                    con.execute("UPDATE certificates SET extraction_date=? WHERE id=?", (str(dates[0]), cert["id"]))
            except Exception:
                pass

        # Recupera BR/PR de caminhos antigos sem reprocessar os PDFs.
        for cert in con.execute("SELECT id,file_path,raw_json FROM certificates WHERE COALESCE(road,'')='' AND is_active=1").fetchall():
            candidates = [cert["file_path"] or ""]
            candidates += [r["file_name"] or "" for r in con.execute(
                "SELECT file_name FROM certificate_files WHERE certificate_id=? ORDER BY id DESC", (cert["id"],)
            ).fetchall()]
            detected = next((_road_from_saved_path(x) for x in candidates if _road_from_saved_path(x)), "")
            if not detected:
                continue
            try:
                raw = json.loads(cert["raw_json"] or "{}")
            except Exception:
                raw = {}
            raw.setdefault("road_source", "NOME_ARQUIVO_MIGRACAO")
            warnings = [w for w in (raw.get("parse_warnings") or []) if "Rodovia não identificada" not in str(w)]
            raw["parse_warnings"] = warnings
            if raw.get("parse_status") == "PARCIAL" and not warnings:
                raw["parse_status"] = "CARREGADO"
            con.execute("UPDATE certificates SET road=?,raw_json=? WHERE id=?", (detected, json_dumps(raw), cert["id"]))

        # v3.2: normaliza o estado técnico salvo no raw_json. O status de
        # certificate_files antigo não é alterado em massa, porque versões antigas
        # gravavam OK mesmo em leituras que hoje são identificadas como PARCIAL.
        for cert in con.execute("SELECT id,raw_json FROM certificates WHERE is_active=1").fetchall():
            try:
                raw = json.loads(cert["raw_json"] or "{}")
            except Exception:
                raw = {}
            if str(raw.get("parse_status") or "").upper() == "OK":
                raw["parse_status"] = "CARREGADO"
                con.execute("UPDATE certificates SET raw_json=? WHERE id=?", (json_dumps(raw), cert["id"]))

        for src in DEFAULT_SOURCES:
            con.execute(
                """INSERT INTO sources(contractor,kind,path,worksheet) VALUES(?,?,?,?)
                   ON CONFLICT(contractor,kind) DO NOTHING""",
                (src["contractor"], src["kind"], src["path"], src["worksheet"]),
            )
        con.execute("INSERT INTO settings(key,value) VALUES('auto_sync_seconds','60') ON CONFLICT(key) DO NOTHING")
        con.execute("INSERT INTO settings(key,value) VALUES('auto_monitor_enabled','1') ON CONFLICT(key) DO NOTHING")
        con.execute("INSERT INTO settings(key,value) VALUES('auto_monitor_bv','1') ON CONFLICT(key) DO NOTHING")
        con.execute("INSERT INTO settings(key,value) VALUES('auto_monitor_contractor','1') ON CONFLICT(key) DO NOTHING")
        con.execute("INSERT INTO settings(key,value) VALUES('auto_bdquali_enabled','1') ON CONFLICT(key) DO NOTHING")
        con.execute("INSERT INTO settings(key,value) VALUES('auto_monitor_seconds','15') ON CONFLICT(key) DO NOTHING")
        con.execute("INSERT INTO settings(key,value) VALUES('maintenance_last_backup_date','') ON CONFLICT(key) DO NOTHING")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sync_log_created_at ON sync_log(created_at)")


def rows(sql: str, params: tuple[Any, ...] = (), path: Path | str | None = None) -> list[dict[str, Any]]:
    con = connect(path)
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def row(sql: str, params: tuple[Any, ...] = (), path: Path | str | None = None) -> dict[str, Any] | None:
    con = connect(path)
    try:
        r = con.execute(sql, params).fetchone()
        return dict(r) if r else None
    finally:
        con.close()


def log_sync(contractor: str | None, kind: str, status: str, message: str, records: int = 0, source_path: str = "") -> None:
    with transaction() as con:
        con.execute(
            "INSERT INTO sync_log(contractor,kind,status,message,records,source_path,created_at) VALUES(?,?,?,?,?,?,?)",
            (contractor, kind, status, message, records, source_path, datetime.now().isoformat(timespec="seconds")),
        )


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def automatic_backup(action: str, cert_id: int) -> str:
    """Backup antes de substituir/excluir certificado, em ambos os bancos."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    safe_action = "".join(ch for ch in action.lower() if ch.isalnum() or ch in {"_", "-"})
    if not USE_POSTGRES:
        name = f"auto_{safe_action}_cert_{cert_id}_{stamp}.db"
        dest = BACKUP_DIR / name
        src = connect(); out = connect(dest)
        try:
            src.backup(out)
        finally:
            src.close(); out.close()
        return name

    # Snapshot lógico comprimido. Não depende de pg_dump/PATH e preserva IDs,
    # inclusive registros inativos/substituídos.
    name = f"auto_{safe_action}_cert_{cert_id}_{stamp}.json.gz"
    dest = BACKUP_DIR / name
    tables = [
        "settings", "sources", "sync_log", "measurements", "quality_rows", "quality_snapshots",
        "certificates", "certificate_files", "certificate_samples", "matches", "kit_rows", "kit_documents", "bv_documents", "auto_import_events", "users", "audit_log", "change_history",
    ]
    payload = {
        "format": "QualiMatch PostgreSQL logical backup v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "certificate_id": cert_id,
        "tables": {t: rows(f"SELECT * FROM {t}") for t in tables},
    }
    with gzip.open(dest, "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, default=str)
    return name


def archive_old_sync_logs(retain: int = 10000) -> dict[str, Any]:
    """Compacta logs antigos antes de removê-los do banco operacional."""
    retain = max(1000, int(retain or 10000))
    found = row("SELECT COUNT(*) total FROM sync_log") or {}
    total = int(found.get("total") or 0)
    remove_count = max(0, total - retain)
    if not remove_count:
        return {"ok": True, "archived": 0, "remaining": total, "name": None}

    old = rows("SELECT * FROM sync_log ORDER BY id ASC LIMIT ?", (remove_count,))
    if not old:
        return {"ok": True, "archived": 0, "remaining": total, "name": None}
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    name = f"logs_arquivados_{stamp}.json.gz"
    dest = BACKUP_DIR / name
    payload = {
        "format": "QualiMatch sync log archive v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(old),
        "first_id": old[0]["id"],
        "last_id": old[-1]["id"],
        "logs": old,
    }
    with gzip.open(dest, "wt", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, default=str)
    with transaction() as con:
        con.execute("DELETE FROM sync_log WHERE id<=?", (old[-1]["id"],))
    return {"ok": True, "archived": len(old), "remaining": total - len(old), "name": name}


def restore_backup(name: str) -> dict[str, Any]:
    """Restaura um backup criado pelo QualiMatch.

    A operação é propositalmente explícita e deve ser chamada apenas por ADMIN.
    Antes da restauração é criado um novo backup do estado atual.
    """
    source = BACKUP_DIR / Path(name).name
    if not source.exists():
        raise FileNotFoundError("Backup não encontrado.")
    safety = automatic_backup("antes_restauracao", 0)
    if not USE_POSTGRES:
        if source.suffix.lower() != ".db":
            raise ValueError("No SQLite, somente backups .db podem ser restaurados.")
        # Valida o arquivo antes de tocar no banco principal.
        src_raw = sqlite3.connect(str(source))
        try:
            ok = src_raw.execute("PRAGMA integrity_check").fetchone()[0]
            if str(ok).lower() != "ok":
                raise ValueError(f"Backup SQLite inválido: {ok}")
            # SQLite Backup API copia um snapshot consistente para o banco em uso
            # sem depender de trocar o arquivo principal/WAL por os.replace.
            dest_raw = sqlite3.connect(str(DB_PATH), timeout=30)
            try:
                src_raw.backup(dest_raw)
                dest_raw.commit()
            finally:
                dest_raw.close()
        finally:
            src_raw.close()
        init_db()
        return {"ok": True, "restored": source.name, "safety_backup": safety, "database": "sqlite"}

    if not source.name.endswith(".json.gz"):
        raise ValueError("No PostgreSQL, restaure um snapshot lógico .json.gz criado pelo QualiMatch.")
    with gzip.open(source, "rt", encoding="utf-8") as f:
        payload = json.load(f)
    tables = payload.get("tables") or {}
    # Ordem de deleção respeita FKs; a de inserção é o inverso lógico.
    delete_order = [
        "change_history", "audit_log", "password_reset_tokens", "sessions", "matches",
        "certificate_samples", "certificate_files", "kit_documents", "bv_documents", "auto_import_events", "quality_snapshots",
        "quality_rows", "measurements", "kit_rows", "certificates", "sync_log", "sources",
        "settings", "users",
    ]
    insert_order = [
        "users", "settings", "sources", "sync_log", "measurements", "quality_rows",
        "quality_snapshots", "certificates", "certificate_files", "certificate_samples",
        "matches", "kit_rows", "kit_documents", "bv_documents", "auto_import_events", "audit_log", "change_history",
    ]
    with transaction() as con:
        # Sessões e tokens nunca são recuperados de snapshots antigos.
        for table in delete_order:
            try:
                con.execute(f"DELETE FROM {table}")
            except Exception:
                if table not in {"change_history", "password_reset_tokens", "sessions"}:
                    raise
        pending_user_approvals: list[tuple[Any, Any]] = []
        for table in insert_order:
            data = tables.get(table)
            if not data:
                continue
            current_cols = _column_names(con, table)
            for original in data:
                rec = dict(original)
                # users.approved_by aponta para a própria tabela. Para o restore
                # não depender da ordem física do snapshot, cria os usuários sem
                # essa FK e recompõe o vínculo depois que todos já existem.
                if table == "users" and "approved_by" in rec:
                    pending_user_approvals.append((rec.get("id"), rec.get("approved_by")))
                    rec["approved_by"] = None
                cols = [c for c in rec.keys() if c in current_cols]
                if not cols:
                    continue
                placeholders = ",".join("?" for _ in cols)
                con.execute(
                    f"INSERT INTO {table}({','.join(cols)}) VALUES({placeholders})",
                    tuple(rec.get(c) for c in cols),
                )
        for user_id, approved_by in pending_user_approvals:
            if user_id is not None and approved_by is not None:
                con.execute("UPDATE users SET approved_by=? WHERE id=?", (approved_by, user_id))
        # Reseed das identities do PostgreSQL.
        for table in ["sync_log","measurements","quality_rows","quality_snapshots","certificates","certificate_files","certificate_samples","kit_rows","kit_documents","bv_documents","auto_import_events","users","audit_log","change_history"]:
            if "id" not in _column_names(con, table):
                continue
            try:
                con.execute(f"SELECT setval(pg_get_serial_sequence('{table}','id'), COALESCE((SELECT MAX(id) FROM {table}),1), true)")
            except Exception:
                pass
    init_db()
    return {"ok": True, "restored": source.name, "safety_backup": safety, "database": "postgresql"}
