from pathlib import Path

import app as webapp
from qualimatch import queries


def test_page_arguments_use_supported_sizes_and_offsets():
    assert webapp._page_args(3, 25) == (3, 25, 50)
    assert webapp._page_args(0, 100) == (1, 100, 0)
    assert webapp._page_args(2, 37) == (2, 25, 25)
    assert webapp._page_offset_for_total(99, 25, 51) == (3, 50)


def test_measurement_pagination_uses_limit_and_offset(monkeypatch):
    seen = {}

    def fake_rows(sql, params=(), path=None):
        seen["sql"] = sql
        seen["params"] = params
        return []

    monkeypatch.setattr(queries, "rows", fake_rows)
    assert queries.list_measurements("ARENA", "BR-277", 25, 50) == []
    assert "LIMIT ? OFFSET ?" in seen["sql"]
    assert seen["params"][-2:] == (25, 50)


def test_large_frontend_lists_request_server_pages():
    root = Path(__file__).resolve().parents[1]
    js = (root / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "page_size:String(measurementPageSize)" in js
    assert "page_size:String(certificatePageSize)" in js
    assert "page_size:String(kitPageSize)" in js
    assert "page_size:String(reviewPageSize)" in js
    assert "page_size:String(historyPageSize)" in js
    for element_id in (
        "m-pagination", "c-pagination", "kit-pagination", "bv-pagination",
        "review-pagination", "auto-monitor-pagination", "history-log-pagination",
        "history-change-pagination",
    ):
        assert f'id="{element_id}"' in html


def test_desktop_sidebar_collapses_and_expands_on_hover():
    css = (Path(__file__).resolve().parents[1] / "frontend" / "static" / "app.css").read_text(encoding="utf-8")
    assert ".layout{grid-template-columns:76px minmax(0,1fr)}" in css
    assert ".sidebar:hover{width:245px" in css
    assert ".sidebar:focus-within{width:245px" not in css
    assert "@media(min-width:821px)" in css
