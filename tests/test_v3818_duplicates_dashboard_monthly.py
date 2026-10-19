from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_financial_monthly_groups_by_month_and_status():
    from qualimatch.queries import _financial_monthly
    data = [
        {"date": "2026-07-01", "total_service": 100.0, "status_final": "APROVADO"},
        {"date": "2026-07-20", "total_service": 50.0, "status_final": "PENDENTE"},
        {"date": "2026-08-02", "total_service": 200.0, "status_final": "REPROVADO"},
    ]
    out = _financial_monthly(data)
    assert [x["month"] for x in out] == ["2026-07", "2026-08"]
    assert out[0]["total_service"] == 150.0
    assert out[0]["approved"] == 100.0
    assert out[0]["pending"] == 50.0
    assert out[1]["reproved"] == 200.0


def test_removed_duplicate_is_skipped_even_on_force(tmp_path, monkeypatch):
    import qualimatch.local_sync as ls
    pdf = tmp_path / "BI330-duplicado.pdf"
    pdf.write_bytes(b"%PDF fake")

    def fake_row(sql, params=()):
        if "FROM certificate_files" in sql:
            st = pdf.stat()
            return {
                "id": 10,
                "certificate_id": 2,
                "file_path": str(pdf.resolve()),
                "mtime_ns": st.st_mtime_ns,
                "size": st.st_size,
                "status": ls.DUPLICATE_REMOVED_STATUS,
                "parser_version": ls.PARSER_VERSION,
            }
        raise AssertionError(f"Consulta inesperada: {sql}")

    monkeypatch.setattr(ls, "row", fake_row)
    parsed, skipped, errors, total = ls._sync_certificate_paths("ARENA", [pdf], True)
    assert (parsed, skipped, errors, total) == (0, 1, 0, 1)


def test_unchanged_parser_error_is_not_reprocessed_without_force(tmp_path, monkeypatch):
    import qualimatch.local_sync as ls

    pdf = tmp_path / "BI330-PG_CA_incompativel.pdf"
    pdf.write_bytes(b"%PDF fake")
    st = pdf.stat()

    def fake_row(sql, params=()):
        if "FROM certificate_files" in sql:
            return {
                "id": 11,
                "certificate_id": None,
                "mtime_ns": st.st_mtime_ns,
                "size": st.st_size,
                "status": "ERRO",
                "parser_version": ls.PARSER_VERSION,
            }
        raise AssertionError(f"Consulta inesperada: {sql}")

    monkeypatch.setattr(ls, "row", fake_row)
    monkeypatch.setattr(ls, "_parse_certificate_job", lambda *_: (_ for _ in ()).throw(AssertionError("não deveria analisar")))
    assert ls._sync_certificate_paths("ARENA", [pdf], False) == (0, 1, 0, 1)


def test_duplicate_shortcut_remains_after_monthly_dashboard_removal():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/static/app.js").read_text(encoding="utf-8")
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'id="c-remove-duplicates"' in html
    assert 'id="bv-file-clean-duplicates"' not in html
    assert "/api/certificates/remove-duplicates" in app
    assert 'id="dashboard-financial-monthly"' not in html
    assert "renderFinancialMonthlyChart" not in js
    assert "monthly-target-line" not in js
    assert 'financial_monthly' in (ROOT / "qualimatch/queries.py").read_text(encoding="utf-8")
