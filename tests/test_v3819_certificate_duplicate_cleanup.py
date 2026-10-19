from pathlib import Path

from qualimatch import database
import qualimatch.queries as queries


def _patch_queries(monkeypatch, db_path: Path):
    monkeypatch.setattr(queries, "rows", lambda sql, params=(): database.rows(sql, params, db_path))
    monkeypatch.setattr(queries, "row", lambda sql, params=(): database.row(sql, params, db_path))
    monkeypatch.setattr(queries, "transaction", lambda: database.transaction(db_path))


def test_certificate_cleanup_preserves_canonical_and_marks_copy_removed(tmp_path, monkeypatch):
    db = tmp_path / "dup.db"
    database.init_db(db)
    _patch_queries(monkeypatch, db)
    now = "2026-08-24T10:30:00"
    with database.transaction(db) as con:
        con.execute("INSERT INTO certificates(contractor,number,identity_key,file_path,file_hash,parsed_at,raw_json,is_active) VALUES(?,?,?,?,?,?,?,1)",
                    ("ARENA","BI330-100","ARENA|BI330-100|A","C:/original.pdf","hash-original",now,"{}"))
        cid = con.execute("SELECT id FROM certificates WHERE identity_key='ARENA|BI330-100|A'").fetchone()["id"]
        con.execute("INSERT INTO certificate_files(contractor,certificate_id,file_path,file_name,status,parsed_at,mtime_ns,size) VALUES(?,?,?,?,?,?,?,?)",
                    ("ARENA",cid,"C:/original.pdf","original.pdf","CARREGADO",now,1,100))
        con.execute("INSERT INTO certificate_files(contractor,certificate_id,file_path,file_name,status,parsed_at,mtime_ns,size) VALUES(?,?,?,?,?,?,?,?)",
                    ("ARENA",cid,"C:/copy.pdf","copy.pdf","DUPLICADO",now,2,100))
        con.execute("INSERT INTO bv_documents(contractor,file_path,file_name,relative_path,synced_at,is_active) VALUES(?,?,?,?,?,1)",
                    ("ARENA","C:/copy.pdf","copy.pdf","M14/copy.pdf",now))

    out = queries.remove_duplicate_certificate_files("ARENA", user_id=9)
    assert out["removed"] == 1
    assert out["canonical_certificates"] == 1
    assert database.row("SELECT COUNT(*) n FROM certificates WHERE is_active=1", (), db)["n"] == 1
    copy = database.row("SELECT certificate_id,status FROM certificate_files WHERE file_path='C:/copy.pdf'", (), db)
    assert copy == {"certificate_id": None, "status": "DUPLICADO_REMOVIDO"}
    doc = database.row("SELECT is_active,manual_override,archived_by FROM bv_documents WHERE file_path='C:/copy.pdf'", (), db)
    assert doc == {"is_active": 0, "manual_override": 1, "archived_by": 9}


def test_same_certificate_number_is_not_a_duplicate_by_itself(tmp_path, monkeypatch):
    db = tmp_path / "numbers.db"
    database.init_db(db)
    _patch_queries(monkeypatch, db)
    now = "2026-08-24T10:30:00"
    with database.transaction(db) as con:
        for i, identity in enumerate(("ARENA|BI330-1|2025-01-01|BR-376|1|2", "ARENA|BI330-1|2025-02-01|BR-376|3|4"), 1):
            con.execute("INSERT INTO certificates(contractor,number,identity_key,file_path,file_hash,parsed_at,raw_json,is_active) VALUES(?,?,?,?,?,?,?,1)",
                        ("ARENA","BI330-0001",identity,f"C:/valid{i}.pdf",f"hash{i}",now,"{}"))
    out = queries.remove_duplicate_certificate_files("ARENA", user_id=9)
    assert out["removed"] == 0
    assert database.row("SELECT COUNT(*) n FROM certificates WHERE is_active=1", (), db)["n"] == 2



def test_removed_duplicate_does_not_reappear_on_force_when_file_unchanged(tmp_path, monkeypatch):
    import qualimatch.local_sync as ls
    pdf = tmp_path / "copy.pdf"
    pdf.write_bytes(b"%PDF fake")
    st = pdf.stat()

    def fake_row(sql, params=()):
        if "FROM certificate_files" in sql:
            return {
                "id": 1, "certificate_id": None, "file_path": str(pdf.resolve()),
                "mtime_ns": st.st_mtime_ns, "size": st.st_size,
                "status": ls.DUPLICATE_REMOVED_STATUS, "parser_version": ls.PARSER_VERSION,
            }
        raise AssertionError(sql)

    monkeypatch.setattr(ls, "row", fake_row)
    assert ls._sync_certificate_paths("ARENA", [pdf], True) == (0, 1, 0, 1)

def test_v3819_duplicate_button_is_on_certificate_tab_not_bv_files():
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend/index.html").read_text(encoding="utf-8")
    js = (root / "frontend/static/app.js").read_text(encoding="utf-8")
    app = (root / "app.py").read_text(encoding="utf-8")
    assert 'id="c-remove-duplicates"' in html
    assert 'id="bv-file-clean-duplicates"' not in html
    assert "/api/certificates/remove-duplicates" in app
    assert "removeCertificateDuplicates" in js
    assert "__QUALIMATCH_VERSION__" in html
