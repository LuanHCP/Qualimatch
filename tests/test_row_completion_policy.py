from qualimatch.row_completion_policy import _completion_plan


def test_completion_plan_updates_existing_and_appends_missing(monkeypatch):
    from qualimatch import quality_excel_writer as qew

    monkeypatch.setattr(
        qew,
        "_existing_rows_for_cert",
        lambda contractor, certificate: [
            {"source_row": 101, "line_measurement": "121"},
            {"source_row": 102, "line_measurement": "121"},
            {"source_row": 103, "line_measurement": "121"},
            {"source_row": 104, "line_measurement": "121"},
            {"source_row": 105, "line_measurement": "121"},
        ],
    )
    monkeypatch.setattr(
        qew,
        "_template_candidates",
        lambda contractor, line_measurements: {
            "121": [{"source_row": 50, "line_measurement": "121", "raw_json": "{}"}]
        },
    )

    cert = {
        "contractor": "PAVIDEZ",
        "certificate": "BI330-0170",
        "parse_status": "CARREGADO",
        "warnings": [],
        "quality_fields": {"Nº CERTIFICADO Vv": 170},
        "lines": [
            {
                "match_status": "VINCULADO",
                "measurement": {"id": 1, "line_measurement": "121"},
            }
            for _ in range(6)
        ],
    }

    plan = _completion_plan(cert)

    assert plan is not None
    assert plan["ready"] is True
    assert plan["mode"] == "ATUALIZAR_E_COMPLETAR"
    assert len([a for a in plan["assignments"] if a.get("target_row")]) == 5
    assert len([a for a in plan["assignments"] if a.get("template_row")]) == 1
    assert "Atualiza 5" in plan["placement"]
    assert "adiciona 1" in plan["placement"]


def test_completion_plan_never_deletes_extra_existing_rows(monkeypatch):
    from qualimatch import quality_excel_writer as qew

    monkeypatch.setattr(
        qew,
        "_existing_rows_for_cert",
        lambda contractor, certificate: [
            {"source_row": 100 + i, "line_measurement": "121"} for i in range(7)
        ],
    )

    cert = {
        "contractor": "PAVIDEZ",
        "certificate": "BI330-0170",
        "parse_status": "CARREGADO",
        "warnings": [],
        "quality_fields": {"Nº CERTIFICADO Vv": 170},
        "lines": [
            {
                "match_status": "VINCULADO",
                "measurement": {"id": 1, "line_measurement": "121"},
            }
            for _ in range(6)
        ],
    }

    assert _completion_plan(cert) is None
