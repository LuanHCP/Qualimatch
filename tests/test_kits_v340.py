from pathlib import Path

from qualimatch.config import DEFAULT_SOURCES
from qualimatch.database import init_db, row, rows


def test_kits_sources_and_table_are_created(tmp_path):
    db = tmp_path / "kits.db"
    init_db(db)
    sources = rows("SELECT contractor,kind,worksheet FROM sources WHERE kind='kits' ORDER BY contractor", path=db)
    assert sources == [
        {"contractor": "ARENA", "kind": "kits", "worksheet": "d.KIT"},
        {"contractor": "PAVIDEZ", "kind": "kits", "worksheet": "d.KIT"},
    ]
    assert row("SELECT COUNT(*) n FROM kit_rows", path=db)["n"] == 0


def test_default_sources_include_kits_for_both_contractors():
    configured = {(x["contractor"], x["kind"], x["worksheet"]) for x in DEFAULT_SOURCES}
    assert ("ARENA", "kits", "d.KIT") in configured
    assert ("PAVIDEZ", "kits", "d.KIT") in configured


def test_contractor_kits_ui_contains_requested_columns():
    html = (Path(__file__).parents[1] / "frontend" / "index.html").read_text(encoding="utf-8")
    for label in [
        "#SEQ", "Serviço", "Data aplicação", "Projeto mistura", "Período", "Rodovia",
        "KMI", "KMF", "Data", "1. Aplicação", "2. Usinagem", "3. Vv",
        "4. Taxa", "5. Ligante", "6. Mancha areia", "7. Pêndulo", "8. Esp. úmida", "SIN. - Retro",
    ]:
        assert label in html
    assert 'page-contractor-kits' in html
    assert '/static/app.css?v=__QUALIMATCH_VERSION__' in html
    assert '/static/app.js?v=__QUALIMATCH_VERSION__' in html


def test_kits_are_protected_by_contractor_portal():
    app = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    assert "'/api/contractor/kits'" in app
    assert "_require_portal(request,'CONTRACTOR')" in app
    assert "kits/discover" in app
