from pathlib import Path

from qualimatch import database, queries
from qualimatch.pdf_reader import _road_from_filename


def _patch_queries(monkeypatch, db_path: Path):
    monkeypatch.setattr(queries, "rows", lambda sql, params=(): database.rows(sql, params, db_path))
    monkeypatch.setattr(queries, "row", lambda sql, params=(): database.row(sql, params, db_path))


def _add_cert(db: Path, *, key: str, number: str, ext_date: str, road: str, kmi: int, kmf: int, result: str, cps: int):
    with database.transaction(db) as con:
        cur = con.execute(
            """INSERT INTO certificates(
                identity_key,contractor,number,file_path,file_hash,service_date,extraction_date,
                road,kmi,kmf,trace_approved,routine_result,counterproof_result,has_counterproof,
                parsed_at,raw_json,is_active,manual_override
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (key, "ARENA", number, f"/tmp/{number}_{road.replace('-', '')}.pdf", key, ext_date, ext_date,
             road, kmi, kmf, "TRACO", result, "", 0, ext_date + "T10:00:00",
             '{"parse_status":"OK"}', 1, 0),
        )
        cid = cur.lastrowid
        for i in range(cps):
            con.execute(
                """INSERT INTO certificate_samples(
                    certificate_id,phase,cp_number,application_date,counterproof,direction,lane,station,
                    position,thickness_exec_cm,thickness_project_cm,ratio_ab_pct,gmb,voids_pct
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (cid, "ROTINA", str(i + 1), ext_date, 0, "SUL", "1", kmi + i * 10,
                 "EIXO", 5.0, 5.0, 100.0, 2.4, 5.0),
            )


def test_road_from_filename_accepts_underscore_and_compact_road():
    assert _road_from_filename("BI330-0230.26-ARENA_BR376_TR1424.pdf") == "BR-376"
    assert _road_from_filename("BI330-0115_PR323-PAVIDEZ.pdf") == "PR-323"


def test_init_db_recovers_road_from_saved_windows_path(tmp_path):
    db = tmp_path / "roads.db"
    database.init_db(db)
    with database.transaction(db) as con:
        con.execute(
            """INSERT INTO certificates(
                identity_key,contractor,number,file_path,file_hash,parsed_at,raw_json,road,is_active
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            ("K", "PAVIDEZ", "BI330-0115", r"C:\PDFs\BI330-0115_PR323-PAVIDEZ.pdf", "h", "2026-01-01", "{}", "", 1),
        )
    database.init_db(db)
    cert = database.row("SELECT road,raw_json FROM certificates WHERE identity_key='K'", (), db)
    assert cert["road"] == "PR-323"
    assert "NOME_ARQUIVO_MIGRACAO" in cert["raw_json"]


def test_certificate_filters_combine_sort_cps_status_road_and_segment(tmp_path, monkeypatch):
    db = tmp_path / "filters.db"
    database.init_db(db)
    _add_cert(db, key="A", number="BI330-0001", ext_date="2026-01-10", road="BR-376", kmi=405000, kmf=406000, result="APROVADO", cps=2)
    _add_cert(db, key="B", number="BI330-0002", ext_date="2026-01-20", road="PR-323", kmi=100000, kmf=101000, result="REPROVADO", cps=4)
    _patch_queries(monkeypatch, db)

    oldest = queries.list_certificates("ARENA", sort="oldest", limit=10)
    assert [x["number"] for x in oldest] == ["BI330-0001", "BI330-0002"]
    assert [x["number"] for x in queries.list_certificates("ARENA", cp_min=3, limit=10)] == ["BI330-0002"]
    assert [x["number"] for x in queries.list_certificates("ARENA", status="APROVADO", limit=10)] == ["BI330-0001"]
    assert [x["number"] for x in queries.list_certificates("ARENA", road="PR323", limit=10)] == ["BI330-0002"]
    assert [x["number"] for x in queries.list_certificates("ARENA", segment="405+500", limit=10)] == ["BI330-0001"]
    assert [x["number"] for x in queries.list_certificates("ARENA", segment="405+500 a 405+800", limit=10)] == ["BI330-0001"]

    opts = queries.certificate_filter_options("ARENA")
    assert opts["roads"] == ["BR-376", "PR-323"]
    assert opts["max_cps"] == 4
