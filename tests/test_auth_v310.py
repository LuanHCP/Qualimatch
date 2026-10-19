from pathlib import Path

from qualimatch import database
from qualimatch.auth import (
    create_or_update_admin, create_registration, authenticate, create_session, user_from_session,
    set_user_status, create_password_reset, consume_password_reset,
)


def test_registration_approval_login_and_session(tmp_path: Path):
    db = tmp_path / 'auth.db'
    database.init_db(db)
    admin = create_or_update_admin('Administrador', 'admin@example.com', 'Senha123', db)
    user = create_registration('Pessoa Usuária', 'pessoa@example.com', 'Senha456', db)
    assert user['status'] == 'PENDING'
    logged, error = authenticate('pessoa@example.com', 'Senha456', db)
    assert logged is None and 'aguardando' in error.lower()
    approved = set_user_status(user['id'], 'APPROVE', admin['id'], db)
    assert approved['status'] == 'APPROVED'
    logged, error = authenticate('pessoa@example.com', 'Senha456', db)
    assert error is None and logged['id'] == user['id']
    token, _ = create_session(user['id'], '127.0.0.1', 'pytest', db)
    session_user = user_from_session(token, db)
    assert session_user and session_user['email'] == 'pessoa@example.com'


def test_password_reset_invalidates_old_password(tmp_path: Path):
    db = tmp_path / 'auth.db'
    database.init_db(db)
    admin = create_or_update_admin('Administrador', 'admin@example.com', 'Senha123', db)
    user, token = create_password_reset(admin['email'], db)
    assert user and token
    consume_password_reset(token, 'SenhaNova789', db)
    assert authenticate(admin['email'], 'Senha123', db)[0] is None
    assert authenticate(admin['email'], 'SenhaNova789', db)[0] is not None


def test_admin_cannot_block_self(tmp_path: Path):
    db = tmp_path / 'auth.db'
    database.init_db(db)
    admin = create_or_update_admin('Administrador', 'admin@example.com', 'Senha123', db)
    try:
        set_user_status(admin['id'], 'BLOCK', admin['id'], db)
    except ValueError as exc:
        assert 'própria' in str(exc)
    else:
        raise AssertionError('admin deveria ser impedido de bloquear a própria conta')
