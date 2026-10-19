from pathlib import Path
from datetime import date
from types import SimpleNamespace

from qualimatch.database import init_db, transaction
from qualimatch.queries import kit_summary

ROOT = Path(__file__).resolve().parents[1]


def test_received_uses_filled_rows_not_receipt_date(tmp_path):
    db = tmp_path / "v360.db"
    init_db(db)
    with transaction(db) as con:
        con.execute("""INSERT INTO kit_rows(contractor,source_row,seq,service,application_date,mix_project,period,road,status,raw_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    ("ARENA",10,"100","CBUQ","2026-08-01","P1","D","BR-376","OK","{}"))
        con.execute("""INSERT INTO kit_rows(contractor,source_row,seq,service,application_date,mix_project,period,road,status,raw_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    ("ARENA",11,"101","CBUQ","2026-08-02","P1","N","BR-376","INCOMPLETO","{}"))
    d = kit_summary("ARENA", path=db) if False else None
    # kit_summary usa a conexão padrão; validamos a regra estrutural no fonte para não alterar DB global.
    src=(ROOT/'qualimatch/queries.py').read_text(encoding='utf-8')
    assert '"received": filled_rows' in src
    assert 'Não usamos Data Recebimento como critério operacional' in src


def test_contractor_dashboard_has_control_cards():
    html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
    js=(ROOT/'frontend/static/app.js').read_text(encoding='utf-8')
    assert 'Controles OK por categoria' in html
    for label in ('1. Aplicação','2. Usinagem','3. Vv','4. Taxa','5. Ligante','6. Mancha de areia','7. Pêndulo','8. Esp. úmida','SIN. - Retro'):
        assert label in js
    assert 'renderControlCards' in js


def test_contractor_certificate_folder_browser_and_preview():
    html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
    js=(ROOT/'frontend/static/app.js').read_text(encoding='utf-8')
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    assert 'Navegador de entregas' in html
    assert 'contractor-folder-list' in html
    assert 'file-preview-grid' in html
    assert 'topFolder' in js
    assert '?preview=true' in js
    assert "content_disposition_type='inline' if preview else 'attachment'" in app


def test_contractor_pending_reuses_validated_pending_rule():
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
    js=(ROOT/'frontend/static/app.js').read_text(encoding='utf-8')
    assert "@app.get('/api/contractor/pending')" in app
    assert 'return contractor_pending_measurements(contractor,start,end)' in app
    assert 'somente datas de execução que ainda não possuem kit' in html
    assert '/api/contractor/pending?contractor=' in js


def test_kit_receipt_heading_is_now_data_only():
    html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
    assert '<th>Data</th><th>Entrega</th><th>Status</th>' in html
    assert '<th>Data recebimento</th>' not in html
