import pytest

from qualimatch import management


@pytest.fixture(autouse=True)
def no_quality_override(monkeypatch):
    monkeypatch.setattr(management, "_quality_counterproof_reproved_numbers", lambda *args, **kwargs: set())


def test_bv_kpi_uses_separate_denominators_and_responsibilities(monkeypatch):
    certificates = [
        {"id": 1, "contractor": "ARENA", "number": "A-1", "service_date": "2026-03-02", "road": "BR-376", "overall_status": "APROVADO", "counterproof_state": "NÃO"},
        {"id": 2, "contractor": "ARENA", "number": "A-2", "service_date": "2026-03-03", "road": "BR-376", "overall_status": "REPROVADO", "counterproof_state": "PENDENTE"},
        {"id": 3, "contractor": "ARENA", "number": "A-3", "service_date": "2026-03-04", "road": "BR-376", "overall_status": "", "counterproof_state": "NÃO"},
    ]
    monkeypatch.setattr(management, "list_certificates", lambda **kwargs: {"items": certificates, "total": 3})
    monkeypatch.setattr(management, "bv_pending_workflow", lambda contractor: [
        {"contractor": "ARENA", "date": "2026-03-05", "road": "BR-376", "lines": 2, "responsibility": "CONTRATADA", "status": "PENDENTE CONTRATADA"},
        {"contractor": "ARENA", "date": "2026-03-06", "road": "BR-376", "lines": 1, "responsibility": "BV", "status": "NO PRAZO", "sla_status": "NO PRAZO"},
    ])

    result = management.bv_kpi_dashboard("ARENA")
    summary = result["summary"]
    assert summary["certificate_total"] == 3
    assert summary["classified_total"] == 2
    assert summary["obligation_total"] == 2
    assert summary["operational_total"] == 4
    assert summary["approved"] == {"count": 1, "percent": 25.0}
    assert summary["reproved"] == {"count": 0, "percent": 0.0}
    assert summary["counterproof_pending"] == {"count": 1, "percent": 25.0}
    assert summary["extraction_pending"] == {"count": 1, "percent": 25.0}
    assert summary["certificate_pending"] == {"count": 1, "percent": 25.0}
    assert {item["type"] for item in result["details"]} == {
        "PENDENTE_CONTRAPROVA", "PENDENTE_EXTRACAO", "PENDENTE_CERTIFICADO"
    }


def test_bv_kpi_filters_measurement(monkeypatch):
    monkeypatch.setattr(management, "list_certificates", lambda **kwargs: {"items": [
        {"id": 1, "contractor": "PAVIDEZ", "number": "P-1", "service_date": "2026-03-02", "overall_status": "APROVADO", "counterproof_state": "NÃO"},
        {"id": 2, "contractor": "PAVIDEZ", "number": "P-2", "service_date": "2026-04-12", "overall_status": "REPROVADO", "counterproof_state": "NÃO"},
    ], "total": 2})
    monkeypatch.setattr(management, "bv_pending_workflow", lambda contractor: [])
    first_measurement = management.measurement_cycle("2026-03-02")["measurement"]

    result = management.bv_kpi_dashboard("PAVIDEZ", first_measurement)
    assert result["summary"]["certificate_total"] == 1
    assert result["summary"]["approved"]["count"] == 1
    assert result["summary"]["reproved"]["count"] == 0


def test_statistically_approved_routine_is_not_moved_to_counterproof_pending(monkeypatch):
    monkeypatch.setattr(management, "list_certificates", lambda **kwargs: {"items": [{
        "id": 10, "contractor": "ARENA", "number": "A-10", "service_date": "2026-03-02",
        "overall_status": "APROVADO", "counterproof_state": "PENDENTE",
        "counterproof_delivered": False,
    }], "total": 1})
    monkeypatch.setattr(management, "bv_pending_workflow", lambda contractor: [])
    result = management.bv_kpi_dashboard("ARENA")
    assert result["summary"]["approved"] == {"count": 1, "percent": 100.0}
    assert result["summary"]["counterproof_pending"] == {"count": 0, "percent": 0.0}


def test_quality_counterproof_reproval_is_final(monkeypatch):
    monkeypatch.setattr(management, "list_certificates", lambda **kwargs: {"items": [{
        "id": 480, "contractor": "PAVIDEZ", "number": "BI330-0480", "service_date": "2026-08-21",
        "overall_status": "APROVADO", "counterproof_state": "NÃO", "counterproof_delivered": False,
    }], "total": 1})
    monkeypatch.setattr(management, "bv_pending_workflow", lambda contractor: [])
    monkeypatch.setattr(management, "_quality_counterproof_reproved_numbers", lambda *args, **kwargs: {"480"})
    summary = management.bv_kpi_dashboard("PAVIDEZ", "M14")["summary"]
    assert summary["approved"]["count"] == 0
    assert summary["reproved"] == {"count": 1, "percent": 100.0}


def test_bv_kpi_screen_is_wired():
    html = open("frontend/index.html", encoding="utf-8").read()
    js = open("frontend/static/app.js", encoding="utf-8").read()
    assert 'data-page="bv-kpi"' in html
    assert 'id="page-bv-kpi"' in html
    assert 'id="bv-kpi-detail-body"' in html
    assert "'bv-kpi':loadBvKpi" in js
    assert "/api/management/bv-kpi" in js
