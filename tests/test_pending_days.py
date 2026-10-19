import json

from qualimatch import queries


def test_pending_days_considers_pdf_and_bd_quali_coverage(monkeypatch):
    measurements = [
        {"contractor": "ARENA", "date": "2025-07-15", "lines": 2, "road": "BR-376"},
        {"contractor": "ARENA", "date": "2025-07-16", "lines": 3, "road": "BR-376"},
        {"contractor": "ARENA", "date": "2025-07-17", "lines": 1, "road": "BR-376"},
    ]
    pdf_coverage = [
        {"contractor": "ARENA", "covered_date": "2025-07-15"},
    ]
    quality_rows = [
        {
            "contractor": "ARENA",
            "date": "2025-07-16",
            "raw_json": json.dumps({"Nº CERTIFICADO Vv": 5}),
        }
    ]

    def fake_rows(sql, params=()):
        if "FROM measurements" in sql:
            return measurements
        if "FROM certificates c" in sql and "UNION" in sql:
            return pdf_coverage
        if "SELECT contractor,raw_json FROM certificates" in sql:
            return []
        if "FROM quality_rows" in sql:
            return quality_rows
        raise AssertionError(sql)

    monkeypatch.setattr(queries, "rows", fake_rows)
    result = queries.pending_days("ARENA")

    assert [r["date"] for r in result] == ["2025-07-17"]


def test_has_vv_certificate_rejects_pending_or_empty_values():
    assert queries._has_vv_certificate(json.dumps({"Nº CERTIFICADO Vv": "BI330-0005"}))
    assert queries._has_vv_certificate(json.dumps({"Link CertificadoVv": 5}))
    assert not queries._has_vv_certificate(json.dumps({"Nº CERTIFICADO Vv": "PENDENTE"}))
    assert not queries._has_vv_certificate(json.dumps({"Nº CERTIFICADO Vv": ""}))


def test_pending_days_uses_all_service_dates_from_certificate_raw(monkeypatch):
    measurements = [
        {"contractor": "ARENA", "date": "2025-07-15", "lines": 1, "road": "BR-376"},
        {"contractor": "ARENA", "date": "2025-07-16", "lines": 1, "road": "BR-376"},
    ]

    def fake_rows(sql, params=()):
        if "FROM measurements" in sql:
            return measurements
        if "FROM certificates c" in sql and "UNION" in sql:
            return [{"contractor": "ARENA", "covered_date": "2025-07-15"}]
        if "SELECT contractor,raw_json FROM certificates" in sql:
            return [{
                "contractor": "ARENA",
                "raw_json": json.dumps({"service_dates": ["2025-07-15", "2025-07-16"]}),
            }]
        if "FROM quality_rows" in sql:
            return []
        raise AssertionError(sql)

    monkeypatch.setattr(queries, "rows", fake_rows)
    assert queries.pending_days("ARENA") == []
