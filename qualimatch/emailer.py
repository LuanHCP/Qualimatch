from __future__ import annotations

import os
import smtplib
from html import escape
from email.message import EmailMessage
from pathlib import Path

from dotenv import load_dotenv

from .config import BASE_DIR
from .database import log_sync

load_dotenv(BASE_DIR / ".env", override=True)


def email_configured() -> bool:
    return bool(os.getenv("SMTP_HOST", "").strip() and os.getenv("SMTP_USER", "").strip() and os.getenv("SMTP_PASSWORD", "").strip())


def _bool_env(name: str, default: bool = True) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "sim", "s"}


def send_email(to: str | list[str], subject: str, text: str, html: str | None = None) -> bool:
    recipients = [to] if isinstance(to, str) else list(to)
    recipients = [x.strip() for x in recipients if x and x.strip()]
    if not recipients:
        return False
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")
    if not (host and user and password):
        log_sync(None, "email", "AVISO", f"E-mail não enviado ({subject}): SMTP não configurado.", 0, "")
        return False
    port = int(os.getenv("SMTP_PORT", "587") or "587")
    sender = os.getenv("SMTP_FROM", "").strip() or user
    use_tls = _bool_env("SMTP_STARTTLS", True)
    use_ssl = _bool_env("SMTP_SSL", False)
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=12) as smtp:
                smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=12) as smtp:
                smtp.ehlo()
                if use_tls:
                    smtp.starttls()
                    smtp.ehlo()
                smtp.login(user, password)
                smtp.send_message(msg)
        log_sync(None, "email", "OK", f"E-mail enviado: {subject} -> {', '.join(recipients)}", len(recipients), "")
        return True
    except Exception as exc:
        log_sync(None, "email", "ERRO", f"Falha ao enviar e-mail '{subject}': {exc}", 0, "")
        return False


def registration_email(admin_emails: list[str], applicant: dict, base_url: str) -> bool:
    link = base_url.rstrip("/") + "/?page=admin"
    subject = "QualiMatch — nova solicitação de acesso"
    text = (
        "Uma nova pessoa solicitou acesso ao QualiMatch.\n\n"
        f"Nome: {applicant.get('name','')}\n"
        f"E-mail: {applicant.get('email','')}\n"
        f"Cadastro: {applicant.get('created_at','')}\n\n"
        f"Acesse {link} e abra Administração > Usuários para aprovar ou recusar.\n"
        "A senha do usuário não é enviada nem armazenada em texto aberto."
    )
    html = f"""<h2>Nova solicitação de acesso ao QualiMatch</h2>
    <p><b>Nome:</b> {escape(str(applicant.get('name','')))}</p><p><b>E-mail:</b> {escape(str(applicant.get('email','')))}</p>
    <p><a href=\"{link}\">Abrir QualiMatch</a> e acesse <b>Administração &gt; Usuários</b>.</p>
    <p style=\"color:#666\">A senha do usuário não é enviada por e-mail e fica protegida por hash Argon2.</p>"""
    return send_email(admin_emails, subject, text, html)


def user_status_email(user: dict, approved: bool, base_url: str) -> bool:
    link = base_url.rstrip("/") + "/"
    if approved:
        subject = "QualiMatch — acesso aprovado"
        text = f"Olá, {user.get('name','')}.\n\nSeu acesso ao QualiMatch foi aprovado.\nEntre em: {link}\n"
        html = f"<h2>Acesso aprovado</h2><p>Olá, {escape(str(user.get('name','')))}.</p><p>Seu acesso ao QualiMatch foi aprovado.</p><p><a href=\"{link}\">Entrar no QualiMatch</a></p>"
    else:
        subject = "QualiMatch — solicitação de acesso"
        text = f"Olá, {user.get('name','')}.\n\nSua solicitação de acesso ao QualiMatch não foi aprovada.\n"
        html = f"<h2>Solicitação de acesso</h2><p>Olá, {escape(str(user.get('name','')))}.</p><p>Sua solicitação de acesso ao QualiMatch não foi aprovada.</p>"
    return send_email(str(user.get("email") or ""), subject, text, html)


def password_reset_email(user: dict, token: str, base_url: str) -> bool:
    link = base_url.rstrip("/") + "/?reset_token=" + token
    subject = "QualiMatch — redefinição de senha"
    text = (
        f"Olá, {user.get('name','')}.\n\n"
        "Foi solicitada uma redefinição de senha para sua conta QualiMatch.\n"
        f"Use este link, válido por 30 minutos: {link}\n\n"
        "Se você não solicitou, ignore este e-mail."
    )
    html = f"""<h2>Redefinição de senha</h2><p>Olá, {escape(str(user.get('name','')))}.</p>
    <p>Use o link abaixo, válido por 30 minutos:</p><p><a href=\"{link}\">Criar nova senha</a></p>
    <p style=\"color:#666\">Se você não solicitou, ignore este e-mail.</p>"""
    return send_email(str(user.get("email") or ""), subject, text, html)
