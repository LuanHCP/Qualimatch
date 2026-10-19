import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from qualimatch import database, local_sync, queries


def _patch_db(monkeypatch, db_path: Path):
    monkeypatch.setattr(local_sync, "transaction", lambda: database.transaction(db_path))
    monkeypatch.setattr(queries, "rows", lambda sql, params=(): database.rows(sql, params, db_path))
    monkeypatch.setattr(queries, "row", lambda sql, params=(): database.row(sql, params, db_path))


def _insert_certificate(db_path: Path, *, number="BI330-TESTE", trace="TRACO ANTIGO") -> int:
    with database.transaction(db_path) as con:
        cur = con.execute(
            """INSERT INTO certificates(
                identity_key,contractor,number,file_path,file_hash,service_date,extraction_date,
                road,kmi,kmf,trace_approved,routine_result,counterproof_result,has_counterproof,
                parsed_at,raw_json,is_active,manual_override
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"ARENA|{number}|2026-01-10|BR-376|100000|100500", "ARENA", number,
                "/origem/antigo.pdf", "hash-old", "2026-01-10", "2026-01-12", "BR-376",
                100000, 100500, trace, "APROVADO", "", 0, "2026-01-12T10:00:00",
                '{"service_dates":["2026-01-10"]}', 1, 0,
            ),
        )
        cid = cur.lastrowid
        con.execute(
            """INSERT INTO certificate_files(contractor,certificate_id,file_path,file_name,status,parser_version)
               VALUES(?,?,?,?,?,?)""",
            ("ARENA", cid, "/origem/antigo.pdf", "antigo.pdf", "OK", "2.1.1"),
        )
        con.execute(
            """INSERT INTO certificate_samples(certificate_id,phase,cp_number,application_date,station,voids_pct)
               VALUES(?,?,?,?,?,?)""",
            (cid, "ROTINA", "1", "2026-01-10", 100100, 4.5),
        )
        return cid


def _replacement_cert(number="BI330-NOVO", trace="TRACO NOVO"):
    sample = SimpleNamespace(
        phase="ROTINA", cp_number="9", application_date=date(2026, 1, 11), counterproof=False,
        direction="SUL", lane="FAIXA 1", station=100250, position="EIXO",
        thickness_exec_cm=5.0, thickness_project_cm=4.5, ratio_ab_pct=111.1, gmb=2.41, voids_pct=4.2,
    )
    return SimpleNamespace(
        contractor="ARENA", number=number, file_path="/gerenciado/novo.pdf", file_hash="hash-new",
        service_date=date(2026, 1, 11), extraction_date=date(2026, 1, 13), road="BR-376",
        kmi=100050, kmf=100550, trace_approved=trace, routine_result="APROVADO",
        counterproof_result="", has_counterproof=False, samples=[sample],
        raw={"service_dates": ["2026-01-11"], "parse_status": "OK"},
    )


def test_delete_is_logical_and_removes_certificate_from_statistics(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    database.init_db(db)
    cid = _insert_certificate(db)
    _patch_db(monkeypatch, db)

    assert queries.certificate_summary("ARENA")["total"] == 1
    contractor = local_sync.deactivate_certificate(cid)

    assert contractor == "ARENA"
    assert queries.certificate_summary("ARENA")["total"] == 0
    assert queries.certificate_detail(cid) is None

    con = database.connect(db)
    try:
        cert = con.execute("SELECT is_active,manual_override,deleted_at FROM certificates WHERE id=?", (cid,)).fetchone()
        doc = con.execute("SELECT status FROM certificate_files WHERE certificate_id=?", (cid,)).fetchone()
        total = con.execute("SELECT COUNT(*) FROM certificates WHERE id=?", (cid,)).fetchone()[0]
    finally:
        con.close()

    assert total == 1  # histórico preservado
    assert cert["is_active"] == 0
    assert cert["manual_override"] == 1
    assert cert["deleted_at"]
    assert doc["status"] == "EXCLUIDO"


def test_replace_preserves_id_replaces_samples_and_archives_old_document(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    database.init_db(db)
    cid = _insert_certificate(db)
    _patch_db(monkeypatch, db)

    local_sync.replace_certificate_record(cid, _replacement_cert())

    con = database.connect(db)
    try:
        cert = con.execute("SELECT * FROM certificates WHERE id=?", (cid,)).fetchone()
        docs = con.execute("SELECT status FROM certificate_files WHERE certificate_id=?", (cid,)).fetchall()
        samples = con.execute("SELECT cp_number,application_date FROM certificate_samples WHERE certificate_id=?", (cid,)).fetchall()
    finally:
        con.close()

    assert cert["id"] == cid
    assert cert["number"] == "BI330-NOVO"
    assert cert["trace_approved"] == "TRACO NOVO"
    assert cert["is_active"] == 1
    assert cert["manual_override"] == 1
    assert [d["status"] for d in docs] == ["SUBSTITUIDO"]
    assert [(s["cp_number"], s["application_date"]) for s in samples] == [("9", "2026-01-11")]


def test_deleted_manual_certificate_is_not_resurrected_by_normal_sync_upsert(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    database.init_db(db)
    cid = _insert_certificate(db, trace="ORIGINAL")
    _patch_db(monkeypatch, db)
    local_sync.deactivate_certificate(cid)

    same_identity = SimpleNamespace(
        contractor="ARENA", number="BI330-TESTE", file_path="/origem/antigo.pdf", file_hash="changed",
        service_date=date(2026, 1, 10), extraction_date=date(2026, 1, 12), road="BR-376",
        kmi=100000, kmf=100500, trace_approved="NAO DEVE SOBRESCREVER", routine_result="REPROVADO",
        counterproof_result="", has_counterproof=False, samples=[], raw={"parse_status": "OK"},
    )
    returned = local_sync._upsert_certificate(same_identity)

    con = database.connect(db)
    try:
        cert = con.execute("SELECT is_active,trace_approved,file_hash FROM certificates WHERE id=?", (cid,)).fetchone()
    finally:
        con.close()

    assert returned == cid
    assert cert["is_active"] == 0
    assert cert["trace_approved"] == "ORIGINAL"
    assert cert["file_hash"] == "hash-old"


def test_newer_sharepoint_correction_updates_active_record_not_deleted_duplicate(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    database.init_db(db)
    active_id = _insert_certificate(db, trace="VERSAO ANTIGA")
    _patch_db(monkeypatch, db)
    corrected = _replacement_cert(number="BI330-TESTE", trace="VERSAO CORRETA")
    corrected_path = tmp_path / "BI330-TESTE.pdf"
    corrected_path.write_bytes(b"pdf-corrigido")
    corrected.file_path = str(corrected_path.resolve())

    corrected_identity = local_sync._cert_identity(corrected)
    with database.transaction(db) as con:
        con.execute("UPDATE certificates SET manual_override=1 WHERE id=?", (active_id,))
        con.execute("UPDATE certificate_files SET mtime_ns=1,size=1 WHERE certificate_id=?", (active_id,))
        cur = con.execute(
            """INSERT INTO certificates(identity_key,contractor,number,file_path,file_hash,service_date,
               extraction_date,road,kmi,kmf,trace_approved,routine_result,counterproof_result,
               has_counterproof,parsed_at,raw_json,is_active,deleted_reason,manual_override)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                corrected_identity, "ARENA", "BI330-TESTE", corrected.file_path, "hash-historico",
                "2026-01-11", "2026-01-13", "BR-376", 100050, 100550, "HISTORICO",
                "APROVADO", "", 0, "2026-01-13T10:00:00", "{}", 0,
                "EXCLUIDO PELO USUARIO", 1,
            ),
        )
        deleted_id = cur.lastrowid
        con.execute(
            """INSERT INTO certificate_files(contractor,certificate_id,file_path,file_name,mtime_ns,size,status)
               VALUES(?,?,?,?,?,?,?)""",
            ("ARENA", deleted_id, corrected.file_path, corrected_path.name, 1, 1, "EXCLUIDO"),
        )

    returned = local_sync._upsert_certificate(corrected)

    con = database.connect(db)
    try:
        active = con.execute("SELECT * FROM certificates WHERE id=?", (active_id,)).fetchone()
        deleted = con.execute("SELECT identity_key,is_active FROM certificates WHERE id=?", (deleted_id,)).fetchone()
    finally:
        con.close()

    assert returned == active_id
    assert active["trace_approved"] == "VERSAO CORRETA"
    assert active["extraction_date"] == "2026-01-13"
    assert active["file_hash"] == "hash-new"
    assert deleted["is_active"] == 0
    assert "|HISTORICO|" in deleted["identity_key"]


def test_sharepoint_priority_updates_even_without_newer_file_timestamp(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    database.init_db(db)
    cid = _insert_certificate(db, trace="VERSAO MANUAL")
    _patch_db(monkeypatch, db)
    with database.transaction(db) as con:
        con.execute("UPDATE certificates SET raw_json=? WHERE id=?", ('{"source_priority":10}', cid))

    corrected = _replacement_cert(number="BI330-TESTE", trace="VERSAO SHAREPOINT")
    corrected.raw["source_priority"] = 100
    returned = local_sync._upsert_certificate(corrected)

    con = database.connect(db)
    try:
        current = con.execute("SELECT trace_approved,raw_json FROM certificates WHERE id=?", (cid,)).fetchone()
    finally:
        con.close()
    assert returned == cid
    assert current["trace_approved"] == "VERSAO SHAREPOINT"
    assert json.loads(current["raw_json"])["source_priority"] == 100


def test_manual_source_cannot_revert_sharepoint_certificate(tmp_path, monkeypatch):
    db = tmp_path / "test.db"
    database.init_db(db)
    cid = _insert_certificate(db, trace="VERSAO SHAREPOINT")
    _patch_db(monkeypatch, db)
    with database.transaction(db) as con:
        con.execute("UPDATE certificates SET raw_json=? WHERE id=?", ('{"source_priority":100}', cid))

    stale = _replacement_cert(number="BI330-TESTE", trace="VERSAO MANUAL ANTIGA")
    stale.raw["source_priority"] = 10
    returned = local_sync._upsert_certificate(stale)

    con = database.connect(db)
    try:
        current = con.execute("SELECT trace_approved,raw_json FROM certificates WHERE id=?", (cid,)).fetchone()
    finally:
        con.close()
    assert returned == cid
    assert current["trace_approved"] == "VERSAO SHAREPOINT"
    assert json.loads(current["raw_json"])["source_priority"] == 100
