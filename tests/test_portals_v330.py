from pathlib import Path
import sqlite3

from qualimatch.database import init_db, row
from qualimatch.auth import (
    create_or_update_admin, create_registration, set_user_status,
    set_user_permissions, has_portal_access, get_user,
)


def test_portal_permissions_flow(tmp_path: Path):
    db = tmp_path / "portals.db"
    init_db(db)
    admin = create_or_update_admin("Administrador", "admin@example.com", "Senha123", db)
    assert admin["role"] == "ADMIN"
    assert int(admin["access_bv"]) == 1
    assert int(admin["access_contractor"]) == 1
    assert has_portal_access(admin, "BV")
    assert has_portal_access(admin, "CONTRACTOR")
    assert has_portal_access(admin, "ADMIN")

    user = create_registration("Pessoa Teste", "user@example.com", "Senha456", db)
    assert int(user["access_bv"]) == 0
    assert int(user["access_contractor"]) == 0
    assert not has_portal_access(user, "BV")

    user = set_user_status(user["id"], "APPROVE", admin["id"], db)
    assert int(user["access_bv"]) == 0  # v3.7.4: aprovação não libera dados automaticamente
    assert not has_portal_access(user, "BV")
    assert not has_portal_access(user, "CONTRACTOR")

    user = set_user_permissions(user["id"], False, True, False, admin["id"], db)
    assert int(user["access_bv"]) == 0
    assert int(user["access_contractor"]) == 1
    assert not has_portal_access(user, "BV")
    assert has_portal_access(user, "CONTRACTOR")

    # Reiniciar a inicialização não pode "ressuscitar" a permissão BV removida.
    init_db(db)
    user = get_user(user["id"], db)
    assert int(user["access_bv"]) == 0
    assert int(user["access_contractor"]) == 1

    promoted = set_user_permissions(user["id"], False, False, True, admin["id"], db)
    assert promoted["role"] == "ADMIN"
    assert has_portal_access(promoted, "ADMIN")
    assert has_portal_access(promoted, "BV")
    assert has_portal_access(promoted, "CONTRACTOR")


def test_admin_cannot_remove_own_admin_access(tmp_path: Path):
    db = tmp_path / "admin.db"
    init_db(db)
    admin = create_or_update_admin("Administrador", "admin@example.com", "Senha123", db)
    try:
        set_user_permissions(admin["id"], True, True, False, admin["id"], db)
    except ValueError as exc:
        assert "própria permissão" in str(exc)
    else:
        raise AssertionError("admin deveria ser impedido de remover sua própria administração")


def test_legacy_approved_users_receive_bv_only_once(tmp_path: Path):
    db = tmp_path / "legacy.db"
    con = sqlite3.connect(db)
    con.execute("""CREATE TABLE users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,email TEXT NOT NULL UNIQUE,password_hash TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'USER',status TEXT NOT NULL DEFAULT 'PENDING',created_at TEXT NOT NULL,
        approved_at TEXT,approved_by INTEGER,last_login TEXT,rejected_at TEXT,blocked_at TEXT,password_changed_at TEXT
    )""")
    con.execute("INSERT INTO users(name,email,password_hash,role,status,created_at) VALUES('Legado','legado@example.com','x','USER','APPROVED','2026-01-01')")
    con.commit(); con.close()

    init_db(db)
    migrated = row("SELECT access_bv,access_contractor FROM users WHERE email=?", ("legado@example.com",), db)
    assert int(migrated["access_bv"]) == 1
    assert int(migrated["access_contractor"]) == 0


def test_portal_selector_ui_is_present():
    root = Path(__file__).resolve().parents[1]
    html = (root / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (root / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    css = (root / "frontend" / "static" / "app.css").read_text(encoding="utf-8")
    assert 'id="portal-shell"' in html
    assert 'data-portal-card="BV"' in html
    assert 'data-portal-card="CONTRACTOR"' in html
    assert 'data-portal-card="ADMIN"' in html
    assert 'id="page-contractor-home"' in html
    assert "showPortalSelector" in js and "enterPortal" in js
    assert ".portal-cards" in css and ".access-editor" in css
