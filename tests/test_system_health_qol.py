from datetime import datetime, timedelta

import qualimatch.management as management
from qualimatch.doctor import run_doctor
from qualimatch.version import APP_VERSION


def test_system_health_reports_runtime_disk_and_stale_sources(monkeypatch, tmp_path):
    old = (datetime.now() - timedelta(hours=7)).isoformat(timespec="seconds")
    source_rows = [{
        "contractor": "ARENA",
        "kind": "medicao",
        "last_sync": old,
        "last_status": "OK",
        "last_error": "",
        "path": "C:/fonte.xlsx",
    }]
    monkeypatch.setattr(management, "rows", lambda sql, params=(): source_rows if "FROM sources" in sql else [])
    monkeypatch.setattr(management, "row", lambda *args, **kwargs: {"n": 2})
    monkeypatch.setattr(management, "DATA_DIR", tmp_path)
    monkeypatch.setattr("qualimatch.config.BACKUP_DIR", tmp_path / "backups")

    result = management.system_health()
    assert result["runtime"]["version"] == APP_VERSION
    assert result["disk"]["free_gb"] is not None
    assert result["stale_sources"] == 1
    assert result["sources"][0]["health"] == "DESATUALIZADO"
    assert any("mais de 6 horas" in warning for warning in result["warnings"])


def test_doctor_has_no_fatal_errors_in_repaired_workspace():
    report = run_doctor()
    assert report["version"] == APP_VERSION
    assert report["summary"]["errors"] == 0
    assert any(item["name"] == "Dados no Git" for item in report["checks"])


def test_reconciliation_filters_and_frontend_controls(monkeypatch):
    monkeypatch.setattr(management, "list_certificates", lambda **kwargs: [{
        "id": 10,
        "contractor": "ARENA",
        "number": "BI330-0100",
        "parse_warnings": ["Campo incompleto"],
        "business_warnings": [],
    }])
    monkeypatch.setattr(management, "rows", lambda *args, **kwargs: [])
    monkeypatch.setattr(management, "bv_pending_workflow", lambda contractor="ALL": [{
        "status": "PENDENTE CERTIFICADO",
        "contractor": "ARENA",
        "measurement": "M14",
        "date": "2026-08-20",
        "road": "BR-376",
    }])

    danger = management.review_queue("ARENA", severity="danger", search="M14")
    assert danger["total"] == 1
    assert danger["items"][0]["type"] == "PENDENTE_CERTIFICADO"

    warning = management.review_queue("ARENA", item_type="CERTIFICADO_PARCIAL")
    assert warning["total"] == 1
    assert warning["items"][0]["entity_id"] == "10"

    root = management.Path(__file__).resolve().parents[1]
    html = (root / "frontend/index.html").read_text(encoding="utf-8")
    js = (root / "frontend/static/app.js").read_text(encoding="utf-8")
    for control in ("review-severity", "review-type", "review-search", "review-export"):
        assert f'id="{control}"' in html
    assert "exportReviewCsv" in js
    assert "qualimatch_review_filters" in js
