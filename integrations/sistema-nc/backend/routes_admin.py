"""Administração: usuários, auditoria e histórico de importações.

Todas as rotas exigem perfil admin_geral ou admin_sede (equivalente a
App.perm.podeAdmUsuarios() no protótipo), validado no backend — a
existência do botão/tela no frontend nunca é a única barreira.

Regra de negócio protegida aqui (não só na interface): o último usuário
ativo com perfil admin_geral não pode ser bloqueado, desativado, rebaixado
ou excluído — impede que o sistema fique sem administrador.
"""
import re
from flask import Blueprint, request, jsonify, g

import db
import security
import audit
import permissions as perm
import serializers as ser
from auth_mw import login_required, csrf_required, permission_required, get_client_ip, destroy_all_sessions_for_user

bp = Blueprint("admin", __name__, url_prefix="/api/admin")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _user_with_scope(row):
    row = dict(row)
    sedes = db.fetchall(f"SELECT sede_id FROM user_sedes WHERE user_id = {db.lit(row['id'])};")
    contratos = db.fetchall(f"SELECT contrato_id FROM user_contratos WHERE user_id = {db.lit(row['id'])};")
    row["sede_ids"] = [s["sede_id"] for s in sedes]
    row["contrato_ids"] = [c["contrato_id"] for c in contratos]
    return row


def _count_active_admin_geral(exclude_id=None):
    excl = f"AND id != {db.lit(exclude_id)}" if exclude_id else ""
    row = db.fetchone(f"""
        SELECT count(*) AS n FROM users
        WHERE perfil = 'admin_geral' AND ativo = TRUE AND bloqueado = FALSE {excl};
    """)
    return int(row["n"])


# ----------------------------------------------------------------- users --
@bp.get("/usuarios")
@login_required
@permission_required(perm.pode_adm_usuarios)
def list_usuarios():
    rows = db.fetchall("SELECT * FROM users ORDER BY nome;")
    return jsonify([ser.usuario_out(_user_with_scope(r)) for r in rows])


@bp.post("/usuarios")
@login_required
@csrf_required
@permission_required(perm.pode_adm_usuarios)
def create_usuario():
    body = request.get_json(silent=True) or {}
    nome = (body.get("nome") or "").strip()
    email = (body.get("email") or "").strip().lower()
    perfil = body.get("perfil")
    senha_provisoria = body.get("senhaProvisoria") or security.new_token(9)
    if not nome or not email or not EMAIL_RE.match(email):
        return jsonify(error="Informe nome e e-mail válidos."), 400
    if perfil not in perm.PERFIS:
        return jsonify(error="Perfil inválido."), 400
    existing = db.fetchone(f"SELECT id FROM users WHERE email = {db.lit(email)};")
    if existing:
        return jsonify(error="Já existe um usuário com este e-mail."), 409
    senha_hash = security.hash_password(senha_provisoria)
    row = db.fetchone(f"""
        INSERT INTO users (nome, email, senha_hash, perfil, must_change_password, created_by)
        VALUES ({db.lit(nome)}, {db.lit(email)}, {db.lit(senha_hash)}, {db.lit(perfil)}, TRUE, {db.lit(g.user['id'])})
        RETURNING *;
    """)
    for sede_id in (body.get("sedeIds") or []):
        db.execute(f"INSERT INTO user_sedes (user_id, sede_id) VALUES ({db.lit(row['id'])}, {db.lit(sede_id)}) ON CONFLICT DO NOTHING;")
    for contrato_id in (body.get("contratoIds") or []):
        db.execute(f"INSERT INTO user_contratos (user_id, contrato_id) VALUES ({db.lit(row['id'])}, {db.lit(contrato_id)}) ON CONFLICT DO NOTHING;")
    audit.log(g.user, "user.create", "users", row["id"], {"email": email, "perfil": perfil}, get_client_ip())
    out = ser.usuario_out(_user_with_scope(row))
    out["senhaProvisoria"] = senha_provisoria  # devolvida uma única vez, para o admin repassar ao usuário
    return jsonify(out), 201


@bp.post("/usuarios/<user_id>/aprovar")
@login_required
@csrf_required
@permission_required(perm.pode_adm_usuarios)
def aprovar_usuario(user_id):
    body = request.get_json(silent=True) or {}
    target = db.fetchone(f"SELECT * FROM users WHERE id = {db.lit(user_id)};")
    if not target:
        return jsonify(error="Usuário não encontrado."), 404
    perfil = body.get("perfil") or target["perfil"] or "consulta"
    if perfil not in perm.PERFIS:
        return jsonify(error="Perfil inválido."), 400
    db.execute(f"UPDATE users SET approval_status = 'aprovado', ativo = TRUE, perfil = {db.lit(perfil)}, updated_at = now() WHERE id = {db.lit(user_id)};")
    if "sedeIds" in body:
        db.execute(f"DELETE FROM user_sedes WHERE user_id = {db.lit(user_id)};")
        for sede_id in (body.get("sedeIds") or []):
            db.execute(f"INSERT INTO user_sedes (user_id, sede_id) VALUES ({db.lit(user_id)}, {db.lit(sede_id)}) ON CONFLICT DO NOTHING;")
    audit.log(g.user, "user.approve", "users", user_id, {"perfil": perfil}, get_client_ip())
    row = db.fetchone(f"SELECT * FROM users WHERE id = {db.lit(user_id)};")
    return jsonify(ser.usuario_out(_user_with_scope(row)))


@bp.patch("/usuarios/<user_id>")
@login_required
@csrf_required
@permission_required(perm.pode_adm_usuarios)
def update_usuario(user_id):
    body = request.get_json(silent=True) or {}
    target = db.fetchone(f"SELECT * FROM users WHERE id = {db.lit(user_id)};")
    if not target:
        return jsonify(error="Usuário não encontrado."), 404

    novo_perfil = body.get("perfil")
    if novo_perfil is not None and novo_perfil != target["perfil"]:
        if target["perfil"] == "admin_geral" and _count_active_admin_geral(exclude_id=user_id) == 0:
            return jsonify(error="Não é possível rebaixar o último administrador geral ativo."), 409
        if novo_perfil not in perm.PERFIS:
            return jsonify(error="Perfil inválido."), 400

    fields = {"nome": body.get("nome"), "email": (body.get("email") or "").lower() or None, "perfil": novo_perfil}
    set_clause = ", ".join(f"{k} = {db.lit(v)}" for k, v in fields.items() if v is not None)
    if set_clause:
        db.execute(f"UPDATE users SET {set_clause} WHERE id = {db.lit(user_id)};")

    if "sedeIds" in body:
        db.execute(f"DELETE FROM user_sedes WHERE user_id = {db.lit(user_id)};")
        for sede_id in (body.get("sedeIds") or []):
            db.execute(f"INSERT INTO user_sedes (user_id, sede_id) VALUES ({db.lit(user_id)}, {db.lit(sede_id)});")
    if "contratoIds" in body:
        db.execute(f"DELETE FROM user_contratos WHERE user_id = {db.lit(user_id)};")
        for contrato_id in (body.get("contratoIds") or []):
            db.execute(f"INSERT INTO user_contratos (user_id, contrato_id) VALUES ({db.lit(user_id)}, {db.lit(contrato_id)});")

    audit.log(g.user, "user.update", "users", user_id, fields, get_client_ip())
    row = db.fetchone(f"SELECT * FROM users WHERE id = {db.lit(user_id)};")
    return jsonify(ser.usuario_out(_user_with_scope(row)))


@bp.post("/usuarios/<user_id>/ativo")
@login_required
@csrf_required
@permission_required(perm.pode_adm_usuarios)
def set_ativo(user_id):
    body = request.get_json(silent=True) or {}
    ativo = bool(body.get("ativo", True))
    target = db.fetchone(f"SELECT * FROM users WHERE id = {db.lit(user_id)};")
    if not target:
        return jsonify(error="Usuário não encontrado."), 404
    if not ativo and target["perfil"] == "admin_geral" and _count_active_admin_geral(exclude_id=user_id) == 0:
        return jsonify(error="Não é possível desativar o último administrador geral ativo."), 409
    db.execute(f"UPDATE users SET ativo = {db.lit(ativo)} WHERE id = {db.lit(user_id)};")
    if not ativo:
        destroy_all_sessions_for_user(user_id)
    audit.log(g.user, "user.set_ativo", "users", user_id, {"ativo": ativo}, get_client_ip())
    return jsonify(ok=True)


@bp.post("/usuarios/<user_id>/bloqueio")
@login_required
@csrf_required
@permission_required(perm.pode_adm_usuarios)
def set_bloqueio(user_id):
    body = request.get_json(silent=True) or {}
    bloqueado = bool(body.get("bloqueado", True))
    target = db.fetchone(f"SELECT * FROM users WHERE id = {db.lit(user_id)};")
    if not target:
        return jsonify(error="Usuário não encontrado."), 404
    if bloqueado and target["perfil"] == "admin_geral" and _count_active_admin_geral(exclude_id=user_id) == 0:
        return jsonify(error="Não é possível bloquear o último administrador geral ativo."), 409
    db.execute(f"UPDATE users SET bloqueado = {db.lit(bloqueado)}, failed_login_attempts = 0, locked_until = NULL WHERE id = {db.lit(user_id)};")
    if bloqueado:
        destroy_all_sessions_for_user(user_id)
    audit.log(g.user, "user.set_bloqueio", "users", user_id, {"bloqueado": bloqueado}, get_client_ip())
    return jsonify(ok=True)


@bp.delete("/usuarios/<user_id>")
@login_required
@csrf_required
@permission_required(perm.pode_adm_usuarios)
def delete_usuario(user_id):
    target = db.fetchone(f"SELECT * FROM users WHERE id = {db.lit(user_id)};")
    if not target:
        return jsonify(error="Usuário não encontrado."), 404
    if target["perfil"] == "admin_geral" and _count_active_admin_geral(exclude_id=user_id) == 0:
        return jsonify(error="Não é possível excluir o último administrador geral ativo."), 409
    if target["id"] == g.user["id"]:
        return jsonify(error="Você não pode excluir o próprio usuário logado."), 409
    db.execute(f"DELETE FROM users WHERE id = {db.lit(user_id)};")
    audit.log(g.user, "user.delete", "users", user_id, {"email": target["email"]}, get_client_ip())
    return jsonify(ok=True)


@bp.post("/usuarios/<user_id>/reset-senha")
@login_required
@csrf_required
@permission_required(perm.pode_adm_usuarios)
def reset_senha(user_id):
    target = db.fetchone(f"SELECT * FROM users WHERE id = {db.lit(user_id)};")
    if not target:
        return jsonify(error="Usuário não encontrado."), 404
    nova_provisoria = security.new_token(9)
    senha_hash = security.hash_password(nova_provisoria)
    db.execute(f"""
        UPDATE users SET senha_hash = {db.lit(senha_hash)}, must_change_password = TRUE,
               failed_login_attempts = 0, locked_until = NULL, bloqueado = FALSE,
               ativo = TRUE, approval_status = 'aprovado', password_changed_at = now()
        WHERE id = {db.lit(user_id)};
    """)
    db.execute(f"UPDATE password_reset_tokens SET used_at = now() WHERE user_id = {db.lit(user_id)} AND used_at IS NULL;")
    destroy_all_sessions_for_user(user_id)
    audit.log(g.user, "user.reset_password", "users", user_id, None, get_client_ip())
    return jsonify(ok=True, senhaProvisoria=nova_provisoria)


# -------------------------------------------------------------- auditoria -
@bp.get("/auditoria")
@login_required
@permission_required(perm.pode_adm_usuarios)
def list_auditoria():
    limit = min(int(request.args.get("limit", 200)), 1000)
    rows = db.fetchall(f"SELECT * FROM audit_log ORDER BY created_at DESC LIMIT {limit};")
    return jsonify([{
        "id": r["id"], "userNome": r.get("user_nome"), "action": r["action"], "entity": r["entity"],
        "entityId": r.get("entity_id"), "detail": r.get("detail"), "ip": r.get("ip"), "createdAt": str(r["created_at"]),
    } for r in rows])


# ------------------------------------------------------- import history ---
@bp.get("/importacoes")
@login_required
@permission_required(perm.pode_adm_usuarios)
def list_importacoes():
    rows = db.fetchall("SELECT * FROM import_logs ORDER BY started_at DESC LIMIT 200;")
    return jsonify([ser.import_log_out(r) for r in rows])
