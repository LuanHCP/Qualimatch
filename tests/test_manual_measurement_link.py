from __future__ import annotations

from qualimatch.manual_measurement_link import apply_manual_overrides


def _result(contractor="ARENA"):
    line = {
        "line_key": "arquivo|BI330-1|CP1|2026-08-01|309310",
        "contractor": contractor,
        "match_status": "SEM_MEDICAO",
        "match_score": 0,
        "match_reason": "Nenhuma medição automática.",
        "measurement": None,
    }
    return {
        "summary": {"linked": 0, "review": 0, "missing": 1},
        "lines": [line],
        "certificates": [{"contractor": contractor, "certificate": "BI330-0001", "lines": [line]}],
    }


def _measurement(contractor="ARENA"):
    return {
        "id": 77,
        "contractor": contractor,
        "source_row": 123,
        "line_measurement": "2175",
        "ref_measurement": "M14",
        "date": "2026-07-29",
        "road": "BR-376",
        "direction": "SUL",
        "kmi": 309000,
        "kmf": 310000,
        "lane": "FAIXA 1",
    }


def test_manual_override_accepts_measurement_outside_automatic_candidates():
    result = _result()
    planned = []

    def replan(data):
        planned.append(True)
        data["certificates"][0]["excel_write"] = {"ready": True}
        return data

    out = apply_manual_overrides(
        result,
        {result["lines"][0]["line_key"]: 77},
        measurement_lookup=lambda _id: _measurement(),
        replan=replan,
    )

    line = out["lines"][0]
    assert line["match_status"] == "VINCULADO"
    assert line["measurement"]["id"] == 77
    assert line["measurement"]["date"] == "2026-07-29"  # pode ser diferente da data do PDF
    assert line["manual_override"] is True
    assert out["summary"]["linked"] == 1
    assert out["summary"]["missing"] == 0
    assert out["summary"]["manual_links"] == 1
    assert planned == [True]


def test_manual_override_blocks_cross_contractor_link():
    result = _result("ARENA")
    planned = []
    out = apply_manual_overrides(
        result,
        {result["lines"][0]["line_key"]: 77},
        measurement_lookup=lambda _id: _measurement("PAVIDEZ"),
        replan=lambda data: planned.append(True) or data,
    )

    line = out["lines"][0]
    assert line["match_status"] == "SEM_MEDICAO"
    assert line["measurement"] is None
    assert "PAVIDEZ" in line["manual_link_error"]
    assert planned == []
