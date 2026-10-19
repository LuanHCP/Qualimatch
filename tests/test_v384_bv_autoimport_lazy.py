from pathlib import Path

import qualimatch.local_sync as ls
from qualimatch.database import init_db, row


def test_bv_document_schema_has_logical_archive(tmp_path: Path):
    db = tmp_path / 'v384.db'
    init_db(db)
    cols = {r['name'] for r in __import__('qualimatch.database', fromlist=['rows']).rows('PRAGMA table_info(bv_documents)', path=db)}
    assert {'is_active','manual_override','archived_at','archived_by'} <= cols


def test_bv_auto_certificate_pipeline_only_accepts_bi330_named_pdfs(monkeypatch, tmp_path: Path):
    bi = tmp_path / 'M14' / 'BI330-999-ARENA.pdf'
    other = tmp_path / 'M14' / 'RELATORIO_FOTOGRAFICO.pdf'
    bi.parent.mkdir(parents=True)
    bi.write_bytes(b'%PDF fake')
    other.write_bytes(b'%PDF other')
    monkeypatch.setattr(ls, '_sync_certificate_paths', lambda contractor,pdfs,force,source_kind='': (len(pdfs),0,0,len(pdfs)))
    out = ls._sync_bv_certificates('ARENA', tmp_path, False)
    assert out == (1,0,0,1)
    assert ls._is_bi330_pdf(bi)
    assert not ls._is_bi330_pdf(other)


def test_v384_ui_is_lazy_and_allows_logical_delete():
    root=Path(__file__).resolve().parents[1]
    app=(root/'app.py').read_text(encoding='utf-8')
    js=(root/'frontend/static/app.js').read_text(encoding='utf-8')
    html=(root/'frontend/index.html').read_text(encoding='utf-8')
    sync=(root/'qualimatch/local_sync.py').read_text(encoding='utf-8')
    assert '/api/bv-documents/groups' in app
    assert "@app.delete('/api/bv-documents/{doc_id}')" in app
    assert 'deleteBvFile' in js
    assert 'loadBvFolderDocs' in js
    assert 'bvVisibleLimit=100' in js
    # A grade não cria iframe/img para cada arquivo; bytes entram somente no modal de preview.
    render = js.split('function renderBvFiles()',1)[1].split('async function loadBvFolderDocs',1)[0]
    assert '<iframe' not in render
    assert '<img ' not in render
    assert '_sync_bv_certificates' in sync
    assert 'id="page-bv-files"' in html
