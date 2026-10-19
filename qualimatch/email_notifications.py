"""Opt-in email delivery. No SMTP calls run inside imports or HTTP requests."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from urllib.parse import urlsplit
from uuid import uuid4

from .auth import has_portal_access
from .database import row, rows, transaction
from .emailer import email_configured, send_email

TOPIC = 'BV_NEW_CERTIFICATE'
logger = logging.getLogger(__name__)


def _now():
    return datetime.now().isoformat(timespec='seconds')


def preferences(user, path=None):
    saved = row('SELECT bv_new_certificates FROM email_notification_preferences WHERE user_id=?', (user['id'],), path) or {}
    counts = rows('SELECT status,COUNT(*) total FROM email_notification_outbox WHERE user_id=? GROUP BY status', (user['id'],), path)
    latest = row('SELECT MAX(sent_at) sent_at FROM email_notification_outbox WHERE user_id=?', (user['id'],), path) or {}
    return {
        'bv_new_certificates': bool(saved.get('bv_new_certificates')),
        'can_subscribe_bv': has_portal_access(user, 'BV'),
        'email': user.get('email', ''), 'smtp_configured': email_configured(),
        'delivery_counts': {x['status']: x['total'] for x in counts},
        'last_sent_at': latest.get('sent_at'),
    }


def save_preferences(user, enabled, path=None):
    if enabled and not has_portal_access(user, 'BV'):
        raise PermissionError('Seu usuário não possui acesso ao ambiente BV.')
    with transaction(path) as con:
        con.execute('''INSERT INTO email_notification_preferences(user_id,bv_new_certificates,updated_at)
            VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET
            bv_new_certificates=excluded.bv_new_certificates,updated_at=excluded.updated_at''',
            (user['id'], int(enabled), _now()))
        if not enabled:
            con.execute("""UPDATE email_notification_outbox SET status='CANCELLED',claim_token=''
                WHERE user_id=? AND status IN ('PENDING','SENDING','FAILED')""", (user['id'],))
    return preferences(user, path)


def retry_failed(user, path=None):
    """Return only this user's failed deliveries to the queue."""
    if not has_portal_access(user, 'BV'):
        raise PermissionError('Seu usuário não possui acesso ao ambiente BV.')
    with transaction(path) as con:
        result = con.execute("""UPDATE email_notification_outbox
            SET status='PENDING', attempts=0, next_attempt_at=0, claimed_at=0,
                claim_token='', last_error=''
            WHERE user_id=? AND topic=? AND status='FAILED'""", (user['id'], TOPIC))
        retried = max(0, int(result.rowcount or 0))
    result = preferences(user, path)
    result['retried'] = retried
    return result


def enqueue_new_bv_certificate(con, certificate_id):
    """Called only for a new successful insert, using the caller's transaction."""
    con.execute('''INSERT INTO email_notification_outbox(user_id,certificate_id,topic,created_at)
        SELECT u.id,?,?,? FROM users u JOIN email_notification_preferences p ON p.user_id=u.id
        WHERE p.bv_new_certificates=1 AND u.status='APPROVED'
          AND (u.role='ADMIN' OR u.access_bv=1)
        ON CONFLICT(user_id,certificate_id,topic) DO NOTHING''', (certificate_id, TOPIC, _now()))


def deliver_pending(path=None, limit=20):
    if not email_configured():
        return 0
    now = int(time.time())
    # Recover work interrupted by a process restart. SMTP delivery is at-least-once:
    # a crash after SMTP accepted a message but before recording SENT can repeat it.
    with transaction(path) as con:
        con.execute("""UPDATE email_notification_outbox SET status='PENDING',claim_token=''
            WHERE status='SENDING' AND claimed_at<?""", (now - 900,))
    pending = rows("""SELECT user_id,certificate_id,topic FROM email_notification_outbox
        WHERE status='PENDING' AND next_attempt_at<=? ORDER BY created_at,user_id,certificate_id LIMIT ?""",
        (now, max(1, min(int(limit), 100))), path)
    sent = 0
    for item in pending:
        key = (item['user_id'], item['certificate_id'], item['topic'])
        token = uuid4().hex
        with transaction(path) as con:
            claimed = con.execute("""UPDATE email_notification_outbox
                SET status='SENDING',claim_token=?,claimed_at=?,attempts=attempts+1
                WHERE user_id=? AND certificate_id=? AND topic=? AND status='PENDING'
                  AND next_attempt_at<=? RETURNING attempts""", (token, now, *key, now)).fetchone()
        if not claimed:
            continue
        # Recheck opt-in and access immediately before delivery, not only at enqueue.
        target = row('''SELECT u.email,c.number,c.contractor,c.road FROM email_notification_outbox o
            JOIN users u ON u.id=o.user_id
            JOIN email_notification_preferences p ON p.user_id=u.id
            JOIN certificates c ON c.id=o.certificate_id
            WHERE o.user_id=? AND o.certificate_id=? AND o.topic=? AND o.claim_token=?
              AND o.status='SENDING' AND p.bv_new_certificates=1 AND u.status='APPROVED'
              AND (u.role='ADMIN' OR u.access_bv=1) AND c.is_active=1''', (*key, token), path)
        status, error, sent_at = 'CANCELLED', '', None
        if target:
            subject = f"QualiMatch — novo certificado BV: {target['number']}"
            text = (f"Um novo certificado foi importado da pasta sincronizada do SharePoint.\n\n"
                    f"Certificado: {target['number']}\nContratada: {target['contractor']}\n"
                    f"Rodovia: {target['road'] or 'Não identificada'}\n\n"
                    "A importação não significa aprovação técnica. Confira os dados e eventuais avisos no site.\n\n")
            base = os.getenv('APP_BASE_URL', '').strip().rstrip('/')
            try:
                url = urlsplit(base)
                valid_url = url.scheme in {'http', 'https'} and bool(url.netloc) and not url.username
            except ValueError:
                valid_url = False
            if valid_url:
                text += f"Abrir QualiMatch (BV > Certificados): {base}/\n\n"
            text += 'Para desativar estes avisos, abra o sino no QualiMatch e escolha Notificações por e-mail.'
            try:
                ok = send_email(target['email'], subject, text)
            except Exception:
                logger.exception('Failed to deliver queued certificate email')
                ok = False
            status = 'SENT' if ok else ('FAILED' if claimed['attempts'] >= 5 else 'PENDING')
            error = '' if ok else 'Falha no envio. Consulte Administração > Histórico e a configuração SMTP.'
            sent_at = _now() if ok else None
            sent += int(ok)
        with transaction(path) as con:
            con.execute('''UPDATE email_notification_outbox SET status=?,last_error=?,sent_at=?,
                next_attempt_at=?,claim_token='' WHERE user_id=? AND certificate_id=? AND topic=? AND claim_token=?''',
                (status, error, sent_at, now + min(3600, 60 * 2 ** min(claimed['attempts'], 6)), *key, token))
    return sent


async def email_notification_loop(seconds=30):
    while True:
        try:
            await asyncio.to_thread(deliver_pending)
        except Exception:
            logger.exception('Email notification worker failed; will retry')
        await asyncio.sleep(seconds)
