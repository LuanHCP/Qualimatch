from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_pending_title_is_bv():
    js = (ROOT / "frontend/static/app.js").read_text(encoding="utf-8")
    assert "pending:['Pendências BV'" in js

def test_measurements_show_real_line_before_contractor():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend/static/app.js").read_text(encoding="utf-8")
    assert '<th>Linha</th><th>Empresa</th>' in html
    assert "<td>${esc(x.line_measurement||'—')}</td><td>${x.contractor}</td>" in js
    assert 'colspan="13"' in js

def test_cache_version_326():
    html = (ROOT / "frontend/index.html").read_text(encoding="utf-8")
    assert '/static/app.css?v=__QUALIMATCH_VERSION__' in html
    assert '/static/app.js?v=__QUALIMATCH_VERSION__' in html
