from pathlib import Path

import qualimatch.local_sync as local_sync
import qualimatch.nc_launcher as nc_launcher
import qualimatch.traces_launcher as traces_launcher


ROOT = Path(__file__).resolve().parents[1]


def test_folder_monitor_uses_adaptive_backoff(tmp_path):
    local_sync._FOLDER_SCAN_STATE.clear()
    calls = []

    def scan(_contractor, _folder):
        calls.append(True)
        return []

    first = local_sync._scheduled_folder_changes(
        "ARENA", "kit_documentos", tmp_path, 15, scan,
    )
    second = local_sync._scheduled_folder_changes(
        "ARENA", "kit_documentos", tmp_path, 15, scan,
    )

    assert first == []
    assert second == []
    assert len(calls) == 1
    state = next(iter(local_sync._FOLDER_SCAN_STATE.values()))
    assert state["interval"] == 30


def test_tree_sync_does_not_prescan_the_whole_folder(tmp_path, monkeypatch):
    source = {
        "contractor": "ARENA", "kind": "kit_documentos", "path": str(tmp_path),
        "worksheet": "", "last_mtime_ns": 0, "last_size": 0, "last_hash": "",
    }
    monkeypatch.setattr(local_sync, "row", lambda *_args, **_kwargs: source)
    monkeypatch.setattr(
        local_sync, "_source_signature",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("varredura duplicada")),
    )
    monkeypatch.setattr(local_sync, "_sync_kit_documents", lambda *_args: 3)
    monkeypatch.setattr(local_sync, "_mark_source_ok", lambda *_args: None)
    monkeypatch.setattr(local_sync, "log_sync", lambda *_args: None)

    result = local_sync.sync_source("ARENA", "kit_documentos", recalc=False)

    assert result["ok"] is True
    assert result["records"] == 3


def test_external_modules_are_lazy_and_released_by_frontend():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")

    assert "qualimatch-traces-prewarm" not in app_source
    assert "qualimatch-nc-prewarm" not in app_source
    assert '@app.post("/api/embedded-projects/{project}/release")' in app_source
    assert "/api/embedded-projects/${kind}/release" in js
    assert "pagehide" in js


def test_shutdown_releases_reused_traces_instance(monkeypatch):
    stopped = []
    monkeypatch.setattr(traces_launcher, "_managed_process", None)
    monkeypatch.setattr(traces_launcher, "_claimed_by_qualimatch", True)
    monkeypatch.setattr(traces_launcher, "traces_project_ready", lambda: True)
    monkeypatch.setattr(traces_launcher, "_stop_stale_instance", lambda: stopped.append(True))

    traces_launcher.shutdown_traces_project()

    assert stopped == [True]
    assert traces_launcher._claimed_by_qualimatch is False


def test_shutdown_releases_reused_nc_instance(monkeypatch):
    stopped = []
    monkeypatch.setattr(nc_launcher, "_managed_process", None)
    monkeypatch.setattr(nc_launcher, "_claimed_by_qualimatch", True)
    monkeypatch.setattr(nc_launcher, "_stop_running_nc_instance", lambda: stopped.append(True))

    nc_launcher.shutdown_nc_project()

    assert stopped == [True]
    assert nc_launcher._claimed_by_qualimatch is False
