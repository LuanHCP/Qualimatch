from pathlib import Path
from qualimatch.database import init_db, rows
from qualimatch.queries import certificate_filter_options, certificate_summary

ROOT=Path(__file__).parents[1]

def test_dashboard_has_status_filter_and_no_volume_mass_card():
    html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
    js=(ROOT/'frontend/static/app.js').read_text(encoding='utf-8')
    assert 'id="dash-status"' in html
    assert 'value="APROVADO"' in html and 'value="REPROVADO"' in html
    assert "metric('Volume massa'" not in js
    assert "metric('Quantidade CPs'" in js

def test_certificate_filters_use_number_dropdown_without_cp_minmax():
    html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
    assert 'id="c-number"' in html
    assert 'id="c-cp-min"' not in html
    assert 'id="c-cp-max"' not in html
    opts=certificate_filter_options('ALL')
    assert 'numbers' in opts

def test_kit_documents_source_and_ui_exist():
    html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
    cfg=(ROOT/'qualimatch/config.py').read_text(encoding='utf-8')
    sync=(ROOT/'qualimatch/local_sync.py').read_text(encoding='utf-8')
    assert 'Documentos dos kits' in html
    assert 'kit_documentos' in cfg
    assert 'rglob' in sync and '_sync_kit_documents' in sync

def test_certificate_summary_exposes_sample_count():
    d=certificate_summary('ALL')
    assert 'sample_count' in d
    assert int(d['sample_count']) >= 0


def test_kit_documents_allowed_in_source_update_api():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    assert "'kit_documentos'" in app.split("def source_update",1)[1].split("@app.post",1)[0]
