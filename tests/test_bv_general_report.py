from qualimatch import queries
from pathlib import Path


def test_bv_report_classifies_supported_certificate_types():
    cases = {
        "04.0 VV - CERTIFICADOS/M15/BI330-123.pdf": "VV/ESP",
        "M15/Certificado CA 42.pdf": "CA",
        "M15/Ensaios de Ligante.pdf": "LIGANTE",
        "M15/DUI 2026.pdf": "DUI",
        "07. DANO POR UMIDADE INDUZIDA (DUI)/2026/14_MED_AGO/ensaio-001.pdf": "DUI",
        "M15/Certificado Agregados.pdf": "AGREGADOS",
        "M15/ata de reunião.pdf": "OUTROS",
    }
    for path, expected in cases.items():
        assert queries._bv_report_category(path.rsplit("/", 1)[-1], path) == expected


def test_ca_folder_does_not_turn_unmarked_bi330_into_ca():
    wrong = "01. CARACTERIZAÇÃO DE CA/2026/08_MED_FEV/02. CARACTERIZAÇÕES/BI330-0343.26-PAVIDEZ_BR323.pdf"
    right = "01. CARACTERIZAÇÃO DE CA/2026/07_MED_JAN/02. CARACTERIZAÇÕES/BI330-PG-CA-0213_ARENA.pdf"
    assert queries._bv_report_category(wrong.rsplit('/', 1)[-1], wrong) == "OUTROS"
    assert queries._bv_report_category(right.rsplit('/', 1)[-1], right) == "CA"


def test_bv_general_report_groups_and_sorts_measurements(monkeypatch):
    docs = [
        {"id": 1, "contractor": "ARENA", "file_name": "DUI.pdf", "relative_path": "M2/DUI.pdf", "measurement_label": "M2", "top_folder": "M2", "extension": ".pdf"},
        {"id": 2, "contractor": "ARENA", "file_name": "BI330.pdf", "relative_path": "04.0 VV - CERTIFICADOS/M15/BI330.pdf", "measurement_label": "M15", "top_folder": "M15", "extension": ".pdf"},
    ]
    monkeypatch.setattr(queries, "rows", lambda *args, **kwargs: docs)
    report = queries.bv_general_report("ARENA")
    assert [item["measurement"] for item in report["measurements"]] == ["M15", "M2"]
    assert report["totals"]["VV/ESP"] == 1
    assert report["totals"]["DUI"] == 1


def test_bv_general_report_ignores_physical_sheets_and_non_pdf(monkeypatch):
    docs = [
        {"id": 1, "file_name": "ficha.pdf", "relative_path": "01. CARACTERIZAÇÃO DE CA/2026/10_MED_ABR/01. FICHAS FÍSICAS/ficha.pdf", "measurement_label": "M10", "extension": ".pdf"},
        {"id": 2, "file_name": "cert.xlsx", "relative_path": "01. CARACTERIZAÇÃO DE CA/2026/10_MED_ABR/02. CARACTERIZAÇÕES/cert.xlsx", "measurement_label": "M10", "extension": ".xlsx"},
    ]
    monkeypatch.setattr(queries, "rows", lambda *args, **kwargs: docs)
    assert queries.bv_general_report("ARENA")["total"] == 0


def test_bv_sample_target_always_rounds_twenty_percent_down():
    source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    assert "math.floor(execution_days*.20)" in source
    assert "math.ceil(execution_days*.20)" not in source
