from pathlib import Path

import qualimatch.queries as q
import qualimatch.management as mg


def test_measurement_cycle_inverse_keeps_11_to_10_rule():
    m14 = q.measurement_cycle_bounds("M14")
    assert m14["measurement_start"] == "2026-08-11"
    assert m14["measurement_end"] == "2026-09-10"
    m13 = q.measurement_cycle_bounds("13")
    assert m13["measurement_start"] == "2026-07-11"
    assert m13["measurement_end"] == "2026-08-10"
    m1 = q.measurement_cycle_bounds("M1")
    assert m1["measurement_start"] == "2025-07-11"
    assert m1["measurement_end"] == "2025-08-10"


def test_legacy_certificate_filename_dates_are_used_before_extraction_date():
    cert = {"service_date": None, "extraction_date": "2025-12-05", "raw_json": "{}"}
    docs = [{"file_name": "BI330-0169_BR376-ARENA_29.11.25_02.12.25_TR1288.pdf"}]
    dates = q._certificate_execution_dates(cert, [], docs)
    assert dates == ["2025-11-29", "2025-12-02"]
    assert q._certificate_in_measurement(cert, [], "M5", docs) is True
    assert q._certificate_in_measurement(cert, [], "M6", docs) is False


def test_pending_days_legacy_169_filename_prevents_false_pending(monkeypatch):
    def fake_rows(sql, params=(), path=None):
        norm = " ".join(sql.split()).lower()
        if "from measurements" in norm and "group by" in norm:
            return [{"contractor": "ARENA", "date": "2025-11-29", "lines": 2, "road": "BR-376"}]
        if "select c.contractor, c.service_date as covered_date" in norm:
            return []
        if "select contractor,raw_json from certificates" in norm:
            return [{"contractor": "ARENA", "raw_json": "{}"}]
        if "from matches x" in norm:
            return []
        if "join certificate_files cf" in norm:
            return [{
                "id": 154, "contractor": "ARENA", "raw_json": "{}",
                "file_name": "BI330-0169_BR376-ARENA_29.11.25_02.12.25_TR1288.pdf",
            }]
        if "from quality_rows" in norm:
            return []
        return []

    monkeypatch.setattr(q, "rows", fake_rows)
    assert q.pending_days("ARENA") == []


def test_contractor_missing_date_is_pending_unless_kmi_and_kmf_exist(monkeypatch):
    monkeypatch.setattr(q, "pending_measurements", lambda *args, **kwargs: [])

    def fake_rows(sql, params=(), path=None):
        if "from kit_rows" in sql.lower() and "application_date is null" in sql.lower():
            return [
                {"id": 1, "contractor": "ARENA", "seq": "10", "road": "BR-376", "kmi": None, "kmf": None, "delivery_status": "", "raw_json": "{}"},
                {"id": 2, "contractor": "ARENA", "seq": "11", "road": "BR-376", "kmi": 100000, "kmf": 101000, "delivery_status": "", "raw_json": "{}"},
            ]
        return []

    monkeypatch.setattr(q, "rows", fake_rows)
    out = q.contractor_pending_measurements("ARENA")
    assert len(out) == 1
    assert out[0]["pending_reason"] == "DATA_NAO_PREENCHIDA"
    assert out[0]["kit_sequences"] == ["10"]


def test_history_change_filter_uses_iso_date_prefix(monkeypatch):
    seen = {}

    def fake_rows(sql, params=(), path=None):
        seen["sql"] = sql
        seen["params"] = params
        seen["path"] = path
        return []

    monkeypatch.setattr(mg, "rows", fake_rows)
    assert mg.list_changes(150, date_filter="2026-08-24") == []
    assert "created_at LIKE ?" in seen["sql"]
    assert seen["params"] == ("2026-08-24%",)


def test_v3820_ui_contains_requested_filters_and_trees():
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (root / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "frontend" / "static" / "app.css").read_text(encoding="utf-8")
    assert 'id="dash-measurement"' in html
    assert 'id="c-measurement"' in html
    assert 'id="history-date"' in html
    assert 'class="forest-scene"' in html
    assert ".forest-scene .tree" in css
    assert "measurement:$('#c-measurement')" in js
    assert "__QUALIMATCH_VERSION__" in html
