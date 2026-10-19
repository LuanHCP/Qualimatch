"""Notificação administrativa por SMTP ou Outlook clássico no Windows."""
import os
import smtplib
import ssl
import subprocess
from email.message import EmailMessage


def send_email(recipient, subject, body):
    recipient = (recipient or "").strip()
    if not recipient:
        return False
    host = os.environ.get("SMTP_HOST", "").strip()
    if host:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or recipient
        msg["To"] = recipient
        msg.set_content(body)
        port = int(os.environ.get("SMTP_PORT", "587"))
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            if os.environ.get("SMTP_STARTTLS", "true").lower() == "true":
                smtp.starttls(context=ssl.create_default_context())
            user = os.environ.get("SMTP_USER", "")
            password = os.environ.get("SMTP_PASSWORD", "")
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)
        return True
    if os.name == "nt" and os.environ.get("EMAIL_USE_OUTLOOK", "true").lower() == "true":
        env = os.environ.copy()
        env.update({"NC_MAIL_TO": recipient, "NC_MAIL_SUBJECT": subject, "NC_MAIL_BODY": body})
        script = "$o=New-Object -ComObject Outlook.Application;$m=$o.CreateItem(0);$m.To=$env:NC_MAIL_TO;$m.Subject=$env:NC_MAIL_SUBJECT;$m.Body=$env:NC_MAIL_BODY;$m.Send()"
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        result = subprocess.run(["powershell", "-NoProfile", "-Command", script], env=env, capture_output=True, text=True, creationflags=flags, timeout=20)
        return result.returncode == 0
    return False


def notify_admin(subject, body):
    recipient = os.environ.get("ADMIN_NOTIFICATION_EMAIL", "admin@qualimatch.local")
    return send_email(recipient, subject, body)
