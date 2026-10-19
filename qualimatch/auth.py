from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .database import row, rows, transaction, json_dumps

PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
SESSION_HOURS = 12
RESET_MINUTES = 30
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_email(value: str) -> str:
    return (value or "").strip().lower()


def validate_name(name: str) -> str:
    name = " ".join((name or "").strip().split())
    if len(name) < 3 or len(name) > 120:
        raise ValueError("Informe um nome válido entre 3 e 120 caracteres.")
    return name


def validate_email(email: str) -> str:
    email = normalize_email(email)
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ValueError("Informe um e-mail válido.")
    return email


def validate_password(password: str) -> None:
    if len(password or "") < 8:
        raise ValueError("A senha precisa ter pelo menos 8 caracteres.")
    if len(password) > 128:
        raise ValueError("A senha é muito longa.")
    if not re.search(r"[A-Za-zÀ-ÿ]", password):
        raise ValueError("A senha precisa conter pelo menos uma letra.")
    if not re.search(r"\d", password):
        raise ValueError("A senha precisa conter pelo menos um número.")


def hash_password(password: str) -> str:
    validate_password(password)
    return PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return bool(PASSWORD_HASHER.verify(password_hash, password))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def admin_exists(path: Path | str | None = None) -> bool:
    return bool(row("SELECT id FROM users WHERE role='ADMIN' AND status='APPROVED' LIMIT 1", path=path))


def create_or_update_admin(name: str, email: str, password: str, path: Path | str | None = None) -> dict[str, Any]:
    name = validate_name(name)
    email = validate_email(email)
    password_hash = hash_password(password)
    now = now_iso()
    with transaction(path) as con:
        existing = con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            uid = int(existing["id"])
            con.execute(
                """UPDATE users SET name=?,password_hash=?,role='ADMIN',status='APPROVED',access_bv=1,access_contractor=1,access_quality_general=1,access_quality_nc=1,access_arena=1,access_pavidez=1,permission_level='ADMIN',
                   approved_at=?,approved_by=NULL,rejected_at=NULL,blocked_at=NULL,password_changed_at=? WHERE id=?""",
                (name, password_hash, now, now, uid),
            )
        else:
            cur = con.execute(
                """INSERT INTO users(name,email,password_hash,role,status,access_bv,access_contractor,access_quality_general,access_quality_nc,access_arena,access_pavidez,permission_level,created_at,approved_at,password_changed_at)
                   VALUES(?,?,?,'ADMIN','APPROVED',1,1,1,1,1,1,'ADMIN',?,?,?)""",
                (name, email, password_hash, now, now, now),
            )
            if con.backend == "sqlite":
                uid = int(cur.lastrowid)
            else:
                uid = int(con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"])
    return get_user(uid, path=path) or {"id": uid, "name": name, "email": email, "role": "ADMIN", "status": "APPROVED"}


def create_registration(name: str, email: str, password: str, path: Path | str | None = None) -> dict[str, Any]:
    if not admin_exists(path):
        raise RuntimeError("O administrador inicial ainda não foi configurado.")
    name = validate_name(name)
    email = validate_email(email)
    password_hash = hash_password(password)
    now = now_iso()
    with transaction(path) as con:
        existing = con.execute("SELECT id,status FROM users WHERE email=?", (email,)).fetchone()
        if existing:
            status = str(existing["status"] or "").upper()
            if status == "REJECTED":
                con.execute(
                    """UPDATE users SET name=?,password_hash=?,status='PENDING',role='USER',access_bv=0,access_contractor=0,access_quality_general=0,access_quality_nc=0,access_arena=0,access_pavidez=0,permission_level='VIEWER',created_at=?,
                       rejected_at=NULL,blocked_at=NULL,approved_at=NULL,approved_by=NULL,password_changed_at=? WHERE id=?""",
                    (name, password_hash, now, now, existing["id"]),
                )
                uid = int(existing["id"])
            else:
                raise ValueError("Já existe uma conta ou solicitação para este e-mail.")
        else:
            cur = con.execute(
                """INSERT INTO users(name,email,password_hash,role,status,created_at,password_changed_at)
                   VALUES(?,?,?,'USER','PENDING',?,?)""",
                (name, email, password_hash, now, now),
            )
            if con.backend == "sqlite":
                uid = int(cur.lastrowid)
            else:
                uid = int(con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"])
    return get_user(uid, path=path) or {"id": uid, "name": name, "email": email, "role": "USER", "status": "PENDING"}


def get_user(user_id: int, path: Path | str | None = None) -> dict[str, Any] | None:
    return row(
        """SELECT id,name,email,role,status,access_bv,access_contractor,access_quality_general,access_quality_nc,access_arena,access_pavidez,permission_level,created_at,approved_at,approved_by,last_login,
           rejected_at,blocked_at,password_changed_at FROM users WHERE id=?""",
        (user_id,), path,
    )


def get_user_by_email(email: str, include_hash: bool = False, path: Path | str | None = None) -> dict[str, Any] | None:
    fields = "*" if include_hash else "id,name,email,role,status,access_bv,access_contractor,access_quality_general,access_quality_nc,access_arena,access_pavidez,permission_level,created_at,approved_at,approved_by,last_login,rejected_at,blocked_at,password_changed_at"
    return row(f"SELECT {fields} FROM users WHERE email=?", (normalize_email(email),), path)


def list_users(path: Path | str | None = None) -> list[dict[str, Any]]:
    return rows(
        """SELECT id,name,email,role,status,access_bv,access_contractor,access_quality_general,access_quality_nc,access_arena,access_pavidez,permission_level,created_at,approved_at,approved_by,last_login,rejected_at,blocked_at
           FROM users ORDER BY CASE status WHEN 'PENDING' THEN 0 WHEN 'APPROVED' THEN 1 WHEN 'BLOCKED' THEN 2 ELSE 3 END, created_at DESC""",
        path=path,
    )


def list_admin_emails(path: Path | str | None = None) -> list[str]:
    return [str(x["email"]) for x in rows("SELECT email FROM users WHERE role='ADMIN' AND status='APPROVED' ORDER BY id", path=path)]


def authenticate(email: str, password: str, path: Path | str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    user = get_user_by_email(email, include_hash=True, path=path)
    if not user or not verify_password(str(user.get("password_hash") or ""), password or ""):
        return None, "E-mail ou senha inválidos."
    status = str(user.get("status") or "").upper()
    if status == "PENDING":
        return None, "Seu cadastro ainda está aguardando aprovação do administrador."
    if status == "REJECTED":
        return None, "Esta solicitação de acesso foi recusada."
    if status == "BLOCKED":
        return None, "Esta conta está bloqueada. Procure o administrador."
    if status != "APPROVED":
        return None, "Conta indisponível."
    return user, None


def create_session(user_id: int, ip_address: str = "", user_agent: str = "", path: Path | str | None = None) -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    hashed = token_hash(token)
    created = datetime.now()
    expires = created + timedelta(hours=SESSION_HOURS)
    with transaction(path) as con:
        con.execute("DELETE FROM sessions WHERE expires_at<?", (created.isoformat(timespec="seconds"),))
        con.execute(
            """INSERT INTO sessions(token_hash,user_id,created_at,expires_at,last_seen_at,ip_address,user_agent)
               VALUES(?,?,?,?,?,?,?)""",
            (hashed, user_id, created.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds"), created.isoformat(timespec="seconds"), ip_address[:80], user_agent[:300]),
        )
        con.execute("UPDATE users SET last_login=? WHERE id=?", (created.isoformat(timespec="seconds"), user_id))
    return token, expires.isoformat(timespec="seconds")


def user_from_session(token: str | None, path: Path | str | None = None) -> dict[str, Any] | None:
    if not token:
        return None
    now = now_iso()
    record = row(
        """SELECT u.id,u.name,u.email,u.role,u.status,u.access_bv,u.access_contractor,u.access_quality_general,u.access_quality_nc,u.access_arena,u.access_pavidez,u.permission_level,u.created_at,u.approved_at,u.last_login,s.expires_at,s.last_seen_at
           FROM sessions s JOIN users u ON u.id=s.user_id
           WHERE s.token_hash=? AND s.expires_at>? AND u.status='APPROVED'""",
        (token_hash(token), now), path,
    )
    if record:
        try:
            last_seen = datetime.fromisoformat(str(record.get("last_seen_at") or ""))
            should_touch = datetime.now() - last_seen >= timedelta(minutes=5)
        except Exception:
            should_touch = True
        if should_touch:
            try:
                with transaction(path) as con:
                    con.execute("UPDATE sessions SET last_seen_at=? WHERE token_hash=?", (now, token_hash(token)))
            except Exception:
                pass
    return record


def revoke_session(token: str | None, path: Path | str | None = None) -> None:
    if not token:
        return
    with transaction(path) as con:
        con.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),))


def revoke_user_sessions(user_id: int, path: Path | str | None = None) -> None:
    with transaction(path) as con:
        con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


def set_user_status(user_id: int, action: str, admin_id: int, path: Path | str | None = None) -> dict[str, Any]:
    action = action.upper().strip()
    target = get_user(user_id, path=path)
    if not target:
        raise ValueError("Usuário não encontrado.")
    if user_id == admin_id and action in {"REJECT", "BLOCK"}:
        raise ValueError("Você não pode bloquear ou recusar sua própria conta administrativa.")
    now = now_iso()
    with transaction(path) as con:
        if action == "APPROVE":
            con.execute("""UPDATE users SET status='APPROVED',approved_at=?,approved_by=?,rejected_at=NULL,blocked_at=NULL
                       WHERE id=?""", (now, admin_id, user_id))
        elif action == "REJECT":
            con.execute("UPDATE users SET status='REJECTED',access_bv=0,access_contractor=0,access_quality_general=0,access_quality_nc=0,access_arena=0,access_pavidez=0,rejected_at=?,approved_at=NULL,approved_by=? WHERE id=?", (now, admin_id, user_id))
            con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        elif action == "BLOCK":
            con.execute("UPDATE users SET status='BLOCKED',blocked_at=? WHERE id=?", (now, user_id))
            con.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        elif action == "REACTIVATE":
            con.execute("UPDATE users SET status='APPROVED',blocked_at=NULL,rejected_at=NULL,approved_at=COALESCE(approved_at,?),approved_by=COALESCE(approved_by,?) WHERE id=?", (now, admin_id, user_id))
        else:
            raise ValueError("Ação de usuário inválida.")
    return get_user(user_id, path=path) or target


def has_portal_access(user: dict[str, Any] | None, portal: str) -> bool:
    if not user or str(user.get("status") or "").upper() != "APPROVED":
        return False
    portal = (portal or "").upper().strip()
    if str(user.get("role") or "").upper() == "ADMIN":
        return portal in {"BV", "CONTRACTOR", "ADMIN", "QUALITY", "TRACES", "NC", "PERSONAL"}
    if portal == "BV":
        return bool(int(user.get("access_bv") or 0))
    # "QUALITY"/"TRACES" seguem o mesmo significado histórico (permissão de
    # Traços). "NC" (Não conformidades) tem sua própria permissão, igual BV e
    # Contratada já são liberados separadamente — antes as duas ficavam atrás
    # do mesmo botão, o que parecia um segundo login desnecessário.
    if portal in {"QUALITY", "TRACES"}:
        return bool(int(user.get("access_quality_general") or 0))
    if portal == "NC":
        return bool(int(user.get("access_quality_nc") or 0))
    if portal == "PERSONAL":
        return True
    if portal in {"CONTRACTOR", "CONTRATADA"}:
        return bool(int(user.get("access_contractor") or 0)) and bool(allowed_contractors(user))
    return False


def allowed_contractors(user: dict[str, Any] | None) -> list[str]:
    if not user or str(user.get("status") or "").upper() != "APPROVED":
        return []
    if str(user.get("role") or "").upper() == "ADMIN":
        return ["ARENA", "PAVIDEZ"]
    if not bool(int(user.get("access_contractor") or 0)):
        return []
    out: list[str] = []
    if bool(int(user.get("access_arena") or 0)):
        out.append("ARENA")
    if bool(int(user.get("access_pavidez") or 0)):
        out.append("PAVIDEZ")
    return out


def has_contractor_access(user: dict[str, Any] | None, contractor: str) -> bool:
    contractor = (contractor or "").upper().strip()
    return contractor in allowed_contractors(user)


def can_edit(user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    if str(user.get('role') or '').upper() == 'ADMIN':
        return True
    if str(user.get('status') or '').upper() != 'APPROVED':
        return False
    return str(user.get('permission_level') or 'VIEWER').upper() == 'EDITOR'


def set_user_permissions(
    user_id: int, access_bv: bool, access_contractor: bool, admin_access: bool, admin_id: int,
    path: Path | str | None = None, access_arena: bool | None = None, access_pavidez: bool | None = None,
    access_quality_general: bool | None = None, access_quality_nc: bool | None = None, permission_level: str | None = None,
) -> dict[str, Any]:
    target = get_user(user_id, path=path)
    if not target:
        raise ValueError("Usuário não encontrado.")
    current_admin = str(target.get("role") or "").upper() == "ADMIN"
    if user_id == admin_id and not admin_access:
        raise ValueError("Você não pode remover sua própria permissão de administrador.")
    if current_admin and not admin_access and str(target.get("status") or "").upper() == "APPROVED":
        admins = row("SELECT COUNT(*) total FROM users WHERE role='ADMIN' AND status='APPROVED'", path=path) or {"total": 0}
        if int(admins.get("total") or 0) <= 1:
            raise ValueError("É necessário manter pelo menos um administrador aprovado.")
    role = "ADMIN" if admin_access else "USER"
    requested_level = str(permission_level or target.get('permission_level') or 'VIEWER').upper().strip()
    if requested_level not in {'VIEWER','EDITOR','ADMIN'}:
        raise ValueError('Nível deve ser VIEWER ou EDITOR.')
    if not admin_access and requested_level == 'ADMIN':
        requested_level = 'EDITOR'
    if admin_access:
        requested_level = 'ADMIN'
        bv = contractor = quality_general = quality_nc = arena = pavidez = 1
    else:
        bv = int(bool(access_bv))
        quality_general = int(bool(access_quality_general)) if access_quality_general is not None else int(bool(target.get("access_quality_general") or 0))
        quality_nc = int(bool(access_quality_nc)) if access_quality_nc is not None else int(bool(target.get("access_quality_nc") or 0))
        # Compatibilidade com chamadas antigas da API Python: antes da v3.7.4
        # existia apenas o booleano Contratada. Se nenhum escopo explícito for
        # informado, manter Contratada significa liberar as duas empresas.
        if access_arena is None and access_pavidez is None:
            arena = pavidez = int(bool(access_contractor))
        else:
            arena = int(bool(access_arena))
            pavidez = int(bool(access_pavidez))
        # O portal Contratada só existe quando ao menos uma empresa foi liberada.
        contractor = int(bool(access_contractor) and bool(arena or pavidez))
        if access_contractor and not (arena or pavidez):
            raise ValueError("Selecione ARENA e/ou PAVIDEZ para liberar o ambiente Contratada.")
    with transaction(path) as con:
        con.execute(
            "UPDATE users SET role=?,access_bv=?,access_contractor=?,access_quality_general=?,access_quality_nc=?,access_arena=?,access_pavidez=?,permission_level=? WHERE id=?",
            (role, bv, contractor, quality_general, quality_nc, arena, pavidez, requested_level, user_id),
        )
    return get_user(user_id, path=path) or target


def create_password_reset(email: str, path: Path | str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    user = get_user_by_email(email, include_hash=False, path=path)
    if not user or str(user.get("status") or "").upper() != "APPROVED":
        return None, None
    token = secrets.token_urlsafe(48)
    now = datetime.now()
    expires = now + timedelta(minutes=RESET_MINUTES)
    with transaction(path) as con:
        con.execute("DELETE FROM password_reset_tokens WHERE user_id=? OR expires_at<?", (user["id"], now.isoformat(timespec="seconds")))
        con.execute(
            "INSERT INTO password_reset_tokens(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)",
            (token_hash(token), user["id"], now.isoformat(timespec="seconds"), expires.isoformat(timespec="seconds")),
        )
    return user, token


def consume_password_reset(token: str, new_password: str, path: Path | str | None = None) -> dict[str, Any]:
    validate_password(new_password)
    hashed = token_hash(token or "")
    now = now_iso()
    rec = row(
        """SELECT r.token_hash,r.user_id FROM password_reset_tokens r JOIN users u ON u.id=r.user_id
           WHERE r.token_hash=? AND r.used_at IS NULL AND r.expires_at>? AND u.status='APPROVED'""",
        (hashed, now), path,
    )
    if not rec:
        raise ValueError("Link de redefinição inválido ou expirado.")
    password_hash = hash_password(new_password)
    with transaction(path) as con:
        con.execute("UPDATE users SET password_hash=?,password_changed_at=? WHERE id=?", (password_hash, now, rec["user_id"]))
        con.execute("UPDATE password_reset_tokens SET used_at=? WHERE token_hash=?", (now, hashed))
        con.execute("DELETE FROM sessions WHERE user_id=?", (rec["user_id"],))
    return get_user(int(rec["user_id"]), path=path) or {}


def audit(user_id: int | None, action: str, entity_type: str = "", entity_id: str = "", details: Any = None,
          ip_address: str = "", path: Path | str | None = None) -> None:
    try:
        with transaction(path) as con:
            con.execute(
                """INSERT INTO audit_log(user_id,action,entity_type,entity_id,details_json,ip_address,created_at)
                   VALUES(?,?,?,?,?,?,?)""",
                (user_id, action[:100], entity_type[:80], str(entity_id or "")[:120], json_dumps(details or {}), ip_address[:80], now_iso()),
            )
    except Exception:
        # Auditoria não deve derrubar a operação principal.
        pass


def list_audit(limit: int = 100, path: Path | str | None = None) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    return rows(
        f"""SELECT a.id,a.user_id,u.name user_name,u.email user_email,a.action,a.entity_type,a.entity_id,a.details_json,a.ip_address,a.created_at
            FROM audit_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT {limit}""",
        path=path,
    )
