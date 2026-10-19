"""Sessão de servidor, autenticação e CSRF (double-submit cookie)."""
import datetime
from functools import wraps

from flask import request, g, jsonify, make_response

import config
import db
import security


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def create_session(user_row, ip, user_agent):
    token = security.new_token(32)
    token_hash = security.sha256_hex(token)
    csrf_token = security.new_token(24)
    expires_at = (_now() + datetime.timedelta(minutes=config.SESSION_LIFETIME_MINUTES)).isoformat()
    row = db.fetchone(f"""
        INSERT INTO sessions (user_id, token_hash, csrf_token, ip, user_agent, expires_at)
        VALUES ({db.lit(user_row['id'])}, {db.lit(token_hash)}, {db.lit(csrf_token)},
                {db.lit(ip)}, {db.lit(user_agent)}, {db.lit(expires_at)}::timestamptz)
        RETURNING id, csrf_token;
    """)
    return token, row["csrf_token"]


def destroy_session(token):
    if not token:
        return
    token_hash = security.sha256_hex(token)
    db.execute(f"DELETE FROM sessions WHERE token_hash = {db.lit(token_hash)};")


def destroy_all_sessions_for_user(user_id):
    db.execute(f"DELETE FROM sessions WHERE user_id = {db.lit(user_id)};")


def load_session_user(token):
    if not token:
        return None
    token_hash = security.sha256_hex(token)
    row = db.fetchone(f"""
        SELECT s.id AS session_id, s.csrf_token, s.expires_at, s.user_id,
               u.id, u.nome, u.email, u.perfil, u.ativo, u.bloqueado, u.must_change_password
        FROM sessions s JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = {db.lit(token_hash)} AND s.expires_at > now();
    """)
    if not row or not row["ativo"] or row["bloqueado"]:
        return None
    # sliding expiration
    new_expires = (_now() + datetime.timedelta(minutes=config.SESSION_LIFETIME_MINUTES)).isoformat()
    db.execute(f"""
        UPDATE sessions SET last_seen_at = now(), expires_at = {db.lit(new_expires)}::timestamptz
        WHERE id = {db.lit(row['session_id'])};
    """)
    return row


def get_client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.remote_addr or ""


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = request.cookies.get(config.SESSION_COOKIE_NAME)
        user = load_session_user(token)
        if not user:
            return jsonify(error="não autenticado"), 401
        g.user = user
        return fn(*args, **kwargs)
    return wrapper


def csrf_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            header_token = request.headers.get("X-CSRF-Token", "")
            if not getattr(g, "user", None) or not security.constant_time_eq(header_token, g.user["csrf_token"]):
                return jsonify(error="token CSRF inválido ou ausente"), 403
        return fn(*args, **kwargs)
    return wrapper


def roles_required(*perfis):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if g.user["perfil"] not in perfis:
                return jsonify(error="sem permissão para esta ação"), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def permission_required(check_fn):
    """check_fn(perfil) -> bool"""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not check_fn(g.user["perfil"]):
                return jsonify(error="sem permissão para esta ação"), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def set_auth_cookies(resp, token, csrf_token):
    resp.set_cookie(
        config.SESSION_COOKIE_NAME, token, httponly=True, secure=config.COOKIE_SECURE,
        samesite="Lax", max_age=config.SESSION_LIFETIME_MINUTES * 60, path="/",
    )
    # cookie CSRF legível por JS (double-submit) — não é segredo por si só,
    # a proteção vem de o token também estar amarrado à sessão no servidor.
    resp.set_cookie(
        config.CSRF_COOKIE_NAME, csrf_token, httponly=False, secure=config.COOKIE_SECURE,
        samesite="Lax", max_age=config.SESSION_LIFETIME_MINUTES * 60, path="/",
    )
    return resp


def clear_auth_cookies(resp):
    resp.delete_cookie(config.SESSION_COOKIE_NAME, path="/")
    resp.delete_cookie(config.CSRF_COOKIE_NAME, path="/")
    return resp
