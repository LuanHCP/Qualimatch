from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_certificate_status_styles_are_preserved():
    css = (ROOT / "frontend" / "static" / "app.css").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    for cls in (".phase-card.metric-ok", ".phase-card.metric-bad", ".value-ok", ".value-bad", ".cert-row-approved", ".cert-row-reproved"):
        assert cls in css
    assert "sampleState" in js
    assert "stateClass" in js

def test_static_assets_are_versioned():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "/static/app.css?v=__QUALIMATCH_VERSION__" in html
    assert "/static/app.js?v=__QUALIMATCH_VERSION__" in html
    assert "/static/general_quality.js?v=__QUALIMATCH_VERSION__" in html
