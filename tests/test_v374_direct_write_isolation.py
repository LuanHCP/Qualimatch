from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app as appmod
import qualimatch.quality_excel_writer as q
from qualimatch.auth import (
    allowed_contractors,
    create_or_update_admin,
    create_registration,
    get_user,
    has_contractor_access,
    set_user_permissions,
    set_user_status,
)
from qualimatch.database import init_db


def test_contractor_scope_permissions_are_independent(tmp_path: Path):
    db = tmp_path / "scope.db"
    init_db(db)
    admin = create_or_update_admin("Administrador", "admin@example.com", "Senha123", db)
    user = create_registration("Arena User", "arena@example.com", "Senha456", db)
    user = set_user_status(user["id"], "APPROVE", admin["id"], db)
    user = set_user_permissions(
        user["id"], False, True, False, admin["id"], db,
        access_arena=True, access_pavidez=False,
    )
    assert allowed_contractors(user) == ["ARENA"]
    assert has_contractor_access(user, "ARENA")
    assert not has_contractor_access(user, "PAVIDEZ")
    assert int(user["access_contractor"]) == 1

    req = SimpleNamespace(state=SimpleNamespace(user=user))
    assert appmod._contractor_for_user(req, "ALL") == "ARENA"
    assert appmod._contractor_for_user(req, "ARENA") == "ARENA"
    with pytest.raises(HTTPException) as exc:
        appmod._contractor_for_user(req, "PAVIDEZ")
    assert exc.value.status_code == 403

    # ADMIN continua vendo as duas.
    admin = get_user(admin["id"], db)
    assert allowed_contractors(admin) == ["ARENA", "PAVIDEZ"]


def test_direct_write_replaces_source_and_creates_backup(tmp_path: Path, monkeypatch):
    source = tmp_path / "BD.QUALIDADE_ARENA.xlsx"
    source.write_bytes(b"arquivo-original")
    original_hash = sha256(source.read_bytes()).hexdigest()
    new_content = b"arquivo-atualizado-validado"
    output_hash = sha256(new_content).hexdigest()
    backup_root = tmp_path / "backups"

    generated = q.GeneratedFile(
        contractor="ARENA",
        file_name="copy.xlsx",
        content=new_content,
        rows_written=2,
        certificates=1,
        updated_rows=0,
        appended_rows=2,
        source_path=str(source),
        source_sha256=original_hash,
        output_sha256=output_hash,
        target_rows=[101, 102],
        filters_cleared=False,
    )

    monkeypatch.setattr(q, "BACKUP_DIR", backup_root)
    monkeypatch.setattr(q, "_source_for_contractor", lambda contractor: source)
    monkeypatch.setattr(q, "patch_quality_workbook", lambda path, contractor, certs: generated)

    analysis = {
        "certificates": [{
            "contractor": "ARENA",
            "certificate": "BI330-9999",
            "excel_write": {"ready": True},
        }]
    }
    report = q.write_excel_to_main_sources(analysis)
    assert source.read_bytes() == new_content
    assert report["original_files_changed"] is True
    assert report["files"][0]["target_rows"] == [101, 102]
    backup = Path(report["files"][0]["backup_path"])
    assert backup.exists()
    assert backup.read_bytes() == b"arquivo-original"


def test_admin_ui_exposes_arena_and_pavidez_separately():
    root = Path(__file__).resolve().parents[1]
    js = (root / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'data-access="arena"' in js
    assert 'data-access="pavidez"' in js
    assert "Contratada • Arena" in js
    assert "Contratada • Pavidez" in js
    assert "Atualizar planilha principal" in html
    assert "/api/admin/tools/pdf-quality/write-main" in js
