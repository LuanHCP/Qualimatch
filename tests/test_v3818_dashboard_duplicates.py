from pathlib import Path

from qualimatch import database
import qualimatch.queries as queries


def _patch_queries(monkeypatch, db_path: Path):
    monkeypatch.setattr(queries, "rows", lambda sql, params=(): database.rows(sql, params, db_path))
    monkeypatch.setattr(queries, "row", lambda sql, params=(): database.row(sql, params, db_path))
    monkeypatch.setattr(queries, "transaction", lambda: database.transaction(db_path))


def test_bulk_duplicate_cleanup_keeps_canonical_and_archives_only_duplicates(tmp_path, monkeypatch):
    db = tmp_path / 'dup.db'
    database.init_db(db)
    _patch_queries(monkeypatch, db)
    now='2026-08-24T10:00:00'
    with database.transaction(db) as con:
        con.execute("INSERT INTO certificates(contractor,number,identity_key,file_path,file_hash,parsed_at,raw_json,is_active) VALUES(?,?,?,?,?,?,?,1)",
                    ('ARENA','BI330-1','ARENA|BI330-1','C:/original.pdf','hash-original',now,'{}'))
        cid=con.execute("SELECT id FROM certificates WHERE number='BI330-1'").fetchone()['id']
        for path,name,status in [
            ('C:/original.pdf','original.pdf','CARREGADO'),
            ('C:/copia1.pdf','copia1.pdf','DUPLICADO'),
            ('C:/copia2.pdf','copia2.pdf','DUPLICADO'),
        ]:
            con.execute("INSERT INTO certificate_files(contractor,certificate_id,file_path,file_name,status,parsed_at) VALUES(?,?,?,?,?,?)",
                        ('ARENA',cid,path,name,status,now))
            con.execute("INSERT INTO bv_documents(contractor,file_path,file_name,relative_path,synced_at,is_active) VALUES(?,?,?,?,?,1)",
                        ('ARENA',path,name,'M14/'+name,now))

    out=queries.archive_duplicate_bv_documents('ARENA', user_id=7)
    assert out['removed']==2
    active=database.rows("SELECT file_name FROM bv_documents WHERE is_active=1 ORDER BY id",(),db)
    assert [x['file_name'] for x in active]==['original.pdf']
    archived=database.rows("SELECT file_name,manual_override,archived_by FROM bv_documents WHERE is_active=0 ORDER BY id",(),db)
    assert [x['file_name'] for x in archived]==['copia1.pdf','copia2.pdf']
    assert all(x['manual_override']==1 and x['archived_by']==7 for x in archived)
    cf=database.rows("SELECT file_name,status FROM certificate_files ORDER BY id",(),db)
    assert cf==[{'file_name':'original.pdf','status':'CARREGADO'}]


def test_v3818_ui_has_duplicate_shortcut_and_monthly_dashboard():
    root=Path(__file__).resolve().parents[1]
    html=(root/'frontend/index.html').read_text(encoding='utf-8')
    js=(root/'frontend/static/app.js').read_text(encoding='utf-8')
    app=(root/'app.py').read_text(encoding='utf-8')
    assert 'id="c-remove-duplicates"' in html
    assert '/api/bv-documents/remove-duplicates' in app
    assert 'removeCertificateDuplicates' in js
    # v3.9.7: o painel "Visão financeira por mês" foi removido do Dashboard a
    # pedido do usuário (os 4 cards de Total/Aprovado/Pendente/Reprovado já
    # resumem o financeiro); a função de agregação mensal continua disponível
    # em queries.py mesmo sem UI própria.
    assert 'financial_monthly' in (root/'qualimatch/queries.py').read_text(encoding='utf-8')
