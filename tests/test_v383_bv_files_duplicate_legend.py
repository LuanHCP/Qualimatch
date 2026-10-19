from pathlib import Path
import tempfile


def test_v383_sources_and_visual_legend_present():
    root=Path(__file__).resolve().parents[1]
    cfg=(root/'qualimatch/config.py').read_text(encoding='utf-8')
    app=(root/'app.py').read_text(encoding='utf-8')
    js=(root/'frontend/static/app.js').read_text(encoding='utf-8')
    css=(root/'frontend/static/app.css').read_text(encoding='utf-8')
    html=(root/'frontend/index.html').read_text(encoding='utf-8')
    assert 'bv_documentos' in cfg
    assert '/api/bv-documents' in app
    assert 'Roxo: duplicado' in js
    assert 'cert-row-duplicate' in css
    assert 'id="page-bv-files"' in html
    assert 'Arquivos BV' not in html


def test_measurement_folder_detection():
    from qualimatch.local_sync import _measurement_label_from_path
    assert _measurement_label_from_path(r'M14\\Certificados\\arquivo.pdf') == 'M14'
    assert _measurement_label_from_path(r'14 - Medição\\PDFs\\arquivo.pdf') == 'M14'
    assert _measurement_label_from_path(r'Pasta\\MEDIÇÃO 03\\arquivo.pdf') == 'M3'
