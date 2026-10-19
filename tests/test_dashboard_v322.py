from qualimatch.queries import _financial_trends, _financial_monthly_series


def row(day, value, status):
    return {"date": day, "total_service": value, "status_final": status}


def test_financial_trends_compare_two_latest_months():
    qr = [
        row("2026-07-01", 100.0, "APROVADO"),
        row("2026-07-20", 200.0, "PENDENTE"),
        row("2026-08-03", 300.0, "APROVADO"),
        row("2026-08-10", 50.0, "REPROVADO"),
    ]
    trends = _financial_trends(qr, ["EMPRESA_TESTE"])
    assert trends["mode"] == "monthly"
    assert trends["comparison_month"] == "2026-07"
    assert trends["latest_month"] == "2026-08"
    assert trends["total_service"]["delta"] == 50.0
    assert trends["approved"]["delta"] == 200.0
    assert trends["pending"]["delta"] == -200.0
    assert trends["reproved"]["delta"] == 50.0


def test_financial_trends_do_not_fluctuate_between_days_of_same_month():
    qr = [
        row("2026-08-01", 100.0, "APROVADO"),
        row("2026-08-02", 200.0, "PENDENTE"),
        row("2026-08-03", 300.0, "APROVADO"),
    ]
    assert _financial_trends(qr, ["EMPRESA_TESTE"]) == {}


def test_monthly_series_keeps_monthly_breakdown():
    qr = [
        row("2026-07-01", 100.0, "APROVADO"),
        row("2026-07-20", 200.0, "PENDENTE"),
        row("2026-08-03", 300.0, "REPROVADO"),
    ]
    out = _financial_monthly_series(qr)
    assert [x["month"] for x in out] == ["2026-07", "2026-08"]
    assert out[0]["total_service"] == 300.0
    assert out[0]["approved"] == 100.0
    assert out[0]["pending"] == 200.0
    assert out[1]["reproved"] == 300.0
