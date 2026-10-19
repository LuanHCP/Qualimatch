import gzip
import json
from pathlib import Path

import pytest

import qualimatch.database as dbm
import qualimatch.runtime_control as runtime


def test_runtime_blocks_parallel_jobs_and_supports_cancel():
    runtime.set_paused(False)
    with runtime.job("sync", "Teste", 2):
        runtime.update(processed=1, current="Fonte 1")
        state = runtime.snapshot()
        assert state["active"] is True
        assert state["progress_pct"] == 50
        with pytest.raises(runtime.JobBusyError):
            with runtime.job("other", "Outra"):
                pass
        runtime.request_cancel()
        with pytest.raises(runtime.JobCancelled):
            runtime.check_cancelled()
    assert runtime.snapshot()["active"] is False


def test_archive_old_sync_logs_keeps_recent_and_writes_gzip(tmp_path, monkeypatch):
    db = tmp_path / "main.db"
    backup_dir = tmp_path / "backups"
    monkeypatch.setattr(dbm, "DB_PATH", db)
    monkeypatch.setattr(dbm, "BACKUP_DIR", backup_dir)
    monkeypatch.setattr(dbm, "USE_POSTGRES", False)
    dbm.init_db(db)
    with dbm.transaction(db) as con:
        for index in range(1005):
            con.execute(
                "INSERT INTO sync_log(contractor,kind,status,message,records,source_path,created_at) VALUES(?,?,?,?,?,?,?)",
                ("ARENA", "teste", "OK", f"log {index}", 0, "", "2026-09-23T10:00:00"),
            )

    result = dbm.archive_old_sync_logs(1000)
    assert result["archived"] == 5
    assert result["remaining"] == 1000
    archive = backup_dir / result["name"]
    with gzip.open(archive, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["count"] == 5
    assert dbm.row("SELECT COUNT(*) n FROM sync_log", path=db)["n"] == 1000


def test_health_panel_exposes_runtime_controls():
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend/index.html").read_text(encoding="utf-8")
    js = (root / "frontend/static/app.js").read_text(encoding="utf-8")
    for control in ("runtime-pause", "runtime-cancel", "runtime-archive", "runtime-shutdown"):
        assert f'id="{control}"' in html
    assert "/api/admin/runtime/pause" in js
    assert "/api/admin/logs/archive" in js
    assert "/api/admin/shutdown" in js
