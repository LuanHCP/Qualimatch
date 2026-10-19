import datetime
import hashlib
import hmac
import re
import secrets
import threading
import time
from pathlib import Path

from flask import Blueprint, request, jsonify, g, make_response, redirect

import config
import db
import security
import audit
import mailer
from auth_mw import (
    login_required, csrf_required, create_session, destroy_session,
    get_client_ip, set_auth_cookies, clear_auth_cookies, destroy_all_sessions_for_user,
)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SSO_KEY_PATH = Path(__file__).with_name("qualimatch-sso.key")
_SSO_TICKETS = {}
_SSO_LOCK = threading.Lock()


def _sso_secret():
    try:
        value = _SSO_KEY_PATH.read_text(encoding="utf-8").strip()
        if value:
            return value
    except OSError:
        pass
    value = secrets.token_hex(32)
    _SSO_KEY_PATH.write_text(value, encoding="utf-8")
    return value


QUALIMATCH_SSO_SECRET = _sso_secret()


def _public_user(row):
    sedes = db.fetchall(f"SELECT sede_id FROM user_sedes WHERE user_id = {db.lit(row['id'])};")
    contratos = db.fetchall(f"SELECT contrato_id FROM user_contratos WHERE user_id = {db.lit(row['id'])};")
    return {
        "id": row["id"], "nome": row["nome"], "email": row["email"],
        "perfil": row["perfil"], "mustChangePassword": row.get("must_change_password", False),
        "approvalStatus": row.get("approval_status", "aprovado"),
        "sedeIds": [x["sede_id"] for x in sedes], "contratoIds": [x["contrato_id"] for x in contratos],
    }


@bp.post("/qualimatch-sso")
def qualimatch_sso():
    """Entrada automática assinada para uma conta local já ativa."""
    if get_client_ip() not in ("127.0.0.1", "::1"):
        return jsonify(error="SSO disponível somente no computador local."), 403
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    nome = (body.get("name") or "").strip()
    profile = (body.get("profile") or "").strip()
    signature = body.get("signature") or ""
    try:
        timestamp = int(body.get("timestamp"))
    except (TypeError, ValueError):
        return jsonify(error="Requisição de SSO incompleta."), 400
    if not email or not nome or not profile or not signature:
        return jsonify(error="Requisição de SSO incompleta."), 400
    if abs(int(time.time() * 1000) - timestamp) > 60_000:
        return jsonify(error="Requisição de SSO expirada."), 401
    signed = f"{email}|{nome}|{profile}|{timestamp}"
    expected = hmac.new(
        QUALIMATCH_SSO_SECRET.encode("utf-8"), signed.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return jsonify(error="Assinatura de SSO inválida."), 401
    user = db.fetchone(f"""
        SELECT * FROM users
        WHERE email = {db.lit(email)} AND ativo = TRUE AND bloqueado = FALSE
          AND COALESCE(approval_status, 'aprovado') = 'aprovado';
    """)
    if not user:
        return jsonify(error="Usuário não está ativo no Sistema de Não Conformidades."), 403
    token, csrf_token = create_session(user, get_client_ip(), request.headers.get("User-Agent", "QualiMatch"))
    ticket = secrets.token_urlsafe(32)
    now = time.time()
    with _SSO_LOCK:
        for old, item in list(_SSO_TICKETS.items()):
            if item[2] < now:
                _SSO_TICKETS.pop(old, None)
        _SSO_TICKETS[ticket] = (token, csrf_token, now + 30)
    audit.log(user, "login.qualimatch_sso", "users", user["id"], None, get_client_ip())
    return jsonify(entryPath=f"/api/auth/qualimatch-enter?ticket={ticket}")


@bp.get("/qualimatch-enter")
def qualimatch_enter():
    ticket = request.args.get("ticket") or ""
    with _SSO_LOCK:
        item = _SSO_TICKETS.pop(ticket, None)
    if not item or item[2] < time.time():
        return jsonify(error="Acesso automático inválido ou expirado."), 401
    resp = make_response(redirect("/"))
    return set_auth_cookies(resp, item[0], item[1])


@bp.post("/register")
def register():
    body = request.get_json(silent=True) or {}
    nome = (body.get("nome") or "").strip()
    email = (body.get("email") or "").strip().lower()
    senha = body.get("senha") or ""
    if not nome or not EMAIL_RE.match(email):
        return jsonify(error="Informe nome e e-mail válidos."), 400
    if len(senha) < 8:
        return jsonify(error="A senha deve ter pelo menos 8 caracteres."), 400
    if db.fetchone(f"SELECT id FROM users WHERE email = {db.lit(email)};"):
        return jsonify(error="Já existe uma conta ou solicitação com este e-mail."), 409
    row = db.fetchone(f"""
        INSERT INTO users (nome, email, senha_hash, perfil, ativo, must_change_password, approval_status, requested_at)
        VALUES ({db.lit(nome)}, {db.lit(email)}, {db.lit(security.hash_password(senha))}, 'consulta', FALSE, FALSE, 'pendente', now())
        RETURNING id;
    """)
    audit.log(None, "register.request", "users", row["id"], {"email": email}, get_client_ip())
    try:
        mailer.notify_admin("Novo cadastro aguardando aprovação", f"{nome} ({email}) solicitou acesso ao Sistema de Não Conformidades.\n\nAcesse a tela Usuários para aprovar ou ajustar o perfil.\nIP: {get_client_ip()}")
    except Exception as exc:
        print(f"Aviso: não foi possível enviar a notificação de cadastro: {exc}")
    return jsonify(ok=True, message="Cadastro enviado. Aguarde a aprovação do administrador."), 201


def _create_password_reset(user, ip):
    token = security.new_token(32)
    token_hash = security.sha256_hex(token)
    expires_at = (_now() + datetime.timedelta(minutes=config.PASSWORD_RESET_MINUTES)).isoformat()
    db.execute(f"UPDATE password_reset_tokens SET used_at = now() WHERE user_id = {db.lit(user['id'])} AND used_at IS NULL;")
    db.execute(f"""
        INSERT INTO password_reset_tokens (user_id, token_hash, requested_ip, expires_at)
        VALUES ({db.lit(user['id'])}, {db.lit(token_hash)}, {db.lit(ip)}, {db.lit(expires_at)}::timestamptz);
    """)
    base_url = config.APP_PUBLIC_URL or request.host_url.rstrip("/")
    link = f"{base_url}/?reset_token={token}"
    sent = mailer.send_email(
        user["email"], "Redefinição de senha — Sistema de Não Conformidades",
        f"Olá, {user['nome']}.\n\nUse o link abaixo para criar uma nova senha. "
        f"Ele expira em {config.PASSWORD_RESET_MINUTES} minutos e só pode ser usado uma vez.\n\n{link}\n\n"
        "Se você não solicitou a alteração, ignore esta mensagem."
    )
    return sent


@bp.post("/request-password-reset")
def request_password_reset():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    generic = "Se o e-mail estiver cadastrado e liberado, enviaremos as instruções de recuperação."
    if not EMAIL_RE.match(email):
        return jsonify(ok=True, message=generic)
    user = db.fetchone(f"SELECT * FROM users WHERE email = {db.lit(email)};")
    if user and user["ativo"] and not user["bloqueado"] and user.get("approval_status", "aprovado") == "aprovado":
        recent = db.fetchone(f"SELECT count(*) AS n FROM password_reset_tokens WHERE user_id = {db.lit(user['id'])} AND created_at > now() - interval '2 minutes';")
        if not recent or int(recent["n"]) == 0:
            try:
                _create_password_reset(user, get_client_ip())
            except Exception as exc:
                print(f"Aviso: não foi possível enviar a recuperação de senha: {exc}")
        audit.log(None, "password_reset.request", "users", user["id"], None, get_client_ip())
    return jsonify(ok=True, message=generic)


@bp.post("/reset-password")
def reset_password():
    body = request.get_json(silent=True) or {}
    token = body.get("token") or ""
    nova_senha = body.get("novaSenha") or ""
    if len(nova_senha) < 8:
        return jsonify(error="A nova senha deve ter pelo menos 8 caracteres."), 400
    row = db.fetchone(f"""
        SELECT prt.id AS token_id, prt.user_id, u.*
        FROM password_reset_tokens prt JOIN users u ON u.id = prt.user_id
        WHERE prt.token_hash = {db.lit(security.sha256_hex(token))}
          AND prt.used_at IS NULL AND prt.expires_at > now();
    """)
    if not row:
        return jsonify(error="Link inválido ou expirado. Solicite uma nova recuperação."), 400
    senha_hash = security.hash_password(nova_senha)
    db.execute(f"""
        UPDATE users SET senha_hash = {db.lit(senha_hash)}, must_change_password = FALSE,
          failed_login_attempts = 0, locked_until = NULL, password_changed_at = now()
        WHERE id = {db.lit(row['user_id'])};
    """)
    db.execute(f"UPDATE password_reset_tokens SET used_at = now() WHERE id = {db.lit(row['token_id'])};")
    destroy_all_sessions_for_user(row["user_id"])
    audit.log(row, "password_reset.complete", "users", row["user_id"], None, get_client_ip())
    return jsonify(ok=True, message="Senha redefinida. Você já pode entrar no sistema.")


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


@bp.post("/login")
def login():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    senha = body.get("senha") or ""
    ip = get_client_ip()

    if not email or not senha:
        return jsonify(error="Informe e-mail e senha."), 400
    if not EMAIL_RE.match(email):
        return jsonify(error="E-mail inválido."), 400

    # limitação de tentativas por identificador+IP (janela deslizante)
    window_start = (_now() - datetime.timedelta(minutes=config.LOGIN_WINDOW_MINUTES)).isoformat()
    recent_fail = db.fetchone(f"""
        SELECT count(*) AS n FROM login_attempts
        WHERE identifier = {db.lit(email)} AND success = FALSE AND created_at > {db.lit(window_start)}::timestamptz;
    """)
    if recent_fail and int(recent_fail["n"]) >= config.LOGIN_MAX_ATTEMPTS:
        db.execute(f"""
            INSERT INTO login_attempts (identifier, ip, success) VALUES ({db.lit(email)}, {db.lit(ip)}, FALSE);
        """)
        return jsonify(error="Muitas tentativas de login. Tente novamente mais tarde."), 429

    user = db.fetchone(f"SELECT * FROM users WHERE email = {db.lit(email)};")

    def record_fail():
        db.execute(f"INSERT INTO login_attempts (identifier, ip, success) VALUES ({db.lit(email)}, {db.lit(ip)}, FALSE);")

    if not user:
        record_fail()
        return jsonify(error="E-mail ou senha inválidos."), 401

    if user.get("approval_status") == "pendente":
        if int(recent_fail["n"] or 0) == 0:
            try:
                mailer.notify_admin("Tentativa de acesso aguardando aprovação", f"O usuário {user['nome']} ({email}) tentou entrar e ainda aguarda aprovação.\nIP: {ip}")
            except Exception as exc:
                print(f"Aviso: não foi possível enviar a notificação de login: {exc}")
        record_fail()
        return jsonify(error="Seu cadastro ainda está aguardando aprovação do administrador."), 403
    if user.get("approval_status") == "rejeitado":
        record_fail()
        return jsonify(error="Esta solicitação de acesso foi recusada."), 403

    if user["locked_until"] and str(user["locked_until"]) > _now().isoformat():
        record_fail()
        return jsonify(error="Conta bloqueada temporariamente por excesso de tentativas. Tente novamente mais tarde."), 423

    if not user["ativo"]:
        record_fail()
        return jsonify(error="Conta inativa. Fale com o administrador."), 403

    if user["bloqueado"]:
        record_fail()
        return jsonify(error="Conta bloqueada. Fale com o administrador."), 403

    if not security.verify_password(senha, user["senha_hash"]):
        record_fail()
        new_attempts = int(user["failed_login_attempts"] or 0) + 1
        lock_clause = ""
        if new_attempts >= config.LOGIN_MAX_ATTEMPTS:
            locked_until = (_now() + datetime.timedelta(minutes=config.LOGIN_LOCKOUT_MINUTES)).isoformat()
            lock_clause = f", locked_until = {db.lit(locked_until)}::timestamptz"
        db.execute(f"""
            UPDATE users SET failed_login_attempts = {new_attempts}{lock_clause}
            WHERE id = {db.lit(user['id'])};
        """)
        if new_attempts >= config.LOGIN_MAX_ATTEMPTS:
            audit.log(None, "login.lockout", "users", user["id"], {"email": email}, ip)
            return jsonify(error=f"Muitas tentativas inválidas. Conta bloqueada por {config.LOGIN_LOCKOUT_MINUTES} minutos."), 423
        return jsonify(error="E-mail ou senha inválidos."), 401

    # sucesso
    db.execute(f"""
        UPDATE users SET failed_login_attempts = 0, locked_until = NULL, last_login_at = now()
        WHERE id = {db.lit(user['id'])};
    """)
    db.execute(f"INSERT INTO login_attempts (identifier, ip, success) VALUES ({db.lit(email)}, {db.lit(ip)}, TRUE);")
    token, csrf_token = create_session(user, ip, request.headers.get("User-Agent", ""))
    audit.log(user, "login.success", "users", user["id"], None, ip)

    resp = make_response(jsonify(user=_public_user(user), csrfToken=csrf_token))
    return set_auth_cookies(resp, token, csrf_token)


@bp.post("/logout")
@login_required
def logout():
    token = request.cookies.get(config.SESSION_COOKIE_NAME)
    destroy_session(token)
    audit.log(g.user, "logout", "users", g.user["id"], None, get_client_ip())
    resp = make_response(jsonify(ok=True))
    return clear_auth_cookies(resp)


@bp.get("/me")
@login_required
def me():
    return jsonify(user=_public_user(g.user), csrfToken=g.user["csrf_token"])


@bp.post("/change-password")
@login_required
@csrf_required
def change_password():
    body = request.get_json(silent=True) or {}
    senha_atual = body.get("senhaAtual") or ""
    nova_senha = body.get("novaSenha") or ""
    user = db.fetchone(f"SELECT * FROM users WHERE id = {db.lit(g.user['id'])};")
    if not user or not security.verify_password(senha_atual, user["senha_hash"]):
        return jsonify(error="Senha atual incorreta."), 400
    if len(nova_senha) < 8:
        return jsonify(error="A nova senha deve ter pelo menos 8 caracteres."), 400
    if nova_senha == senha_atual:
        return jsonify(error="A nova senha deve ser diferente da senha atual."), 400
    new_hash = security.hash_password(nova_senha)
    db.execute(f"""
        UPDATE users SET senha_hash = {db.lit(new_hash)}, must_change_password = FALSE,
               password_changed_at = now()
        WHERE id = {db.lit(user['id'])};
    """)
    db.execute(f"UPDATE password_reset_tokens SET used_at = now() WHERE user_id = {db.lit(user['id'])} AND used_at IS NULL;")
    audit.log(g.user, "password.change", "users", user["id"], None, get_client_ip())
    return jsonify(ok=True)
