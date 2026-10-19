from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from qualimatch import database, email_notifications as notices, local_sync


@pytest.fixture
def setup(tmp_path, monkeypatch):
    path = tmp_path / 'email.db'
    database.init_db(path)
    monkeypatch.setattr(local_sync, 'transaction', lambda: database.transaction(path))
    monkeypatch.setattr(notices, 'email_configured', lambda: True)
    sender = Mock(return_value=True)
    monkeypatch.setattr(notices, 'send_email', sender)
    with database.transaction(path) as con:
        con.execute("""INSERT INTO users(name,email,password_hash,status,access_bv,created_at)
            VALUES('Teste','teste@example.invalid','unused','APPROVED',1,'2026-09-08')""")
    user = database.row('SELECT * FROM users', path=path)
    return path, user, sender


def certificate(n=1, source='bv_documentos'):
    return SimpleNamespace(contractor='ARENA', number=f'BI330-{n:04d}',
        file_path=f'/test/{n}.pdf', file_hash=f'hash-{n}', service_date=None,
        extraction_date=None, road='BR-376', kmi=None, kmf=None, trace_approved='',
        routine_result='', counterproof_result='', has_counterproof=False, samples=[],
        raw={'source_kind': source, 'source_priority': 100})


def queue(path):
    return database.rows('SELECT * FROM email_notification_outbox', path=path)


def test_opt_in_only_new_imports_and_no_update_duplicates(setup):
    path, user, sender = setup
    old = certificate()
    local_sync._upsert_certificate(old)
    assert not queue(path)
    assert not notices.preferences(user, path)['bv_new_certificates']
    notices.save_preferences(user, True, path)
    local_sync._upsert_certificate(old)  # No retroactive notifications.
    fresh = certificate(2)
    cid = local_sync._upsert_certificate(fresh)
    local_sync._upsert_certificate(fresh)  # Unchanged scan.
    fresh.file_hash = 'corrected-content'
    local_sync._upsert_certificate(fresh)  # Correction of existing record.
    assert [x['certificate_id'] for x in queue(path)] == [cid]
    assert notices.deliver_pending(path) == 1
    assert notices.deliver_pending(path) == 0
    sender.assert_called_once()
    assert sender.call_args.args[0] == user['email']
    assert 'BI330-0002' in sender.call_args.args[1]
    assert notices.preferences(user, path)['last_sent_at']


def test_manual_upload_is_not_sharepoint_event(setup):
    path, user, _ = setup
    notices.save_preferences(user, True, path)
    local_sync._upsert_certificate(certificate(source='desconhecida'))
    assert not queue(path)
    local_sync._upsert_certificate(certificate(2, source='certificados'))
    assert len(queue(path)) == 1


def test_disable_cancels_and_reenable_does_not_replay_old_items(setup):
    path, user, sender = setup
    notices.save_preferences(user, True, path)
    local_sync._upsert_certificate(certificate())
    notices.save_preferences(user, False, path)
    notices.save_preferences(user, True, path)
    assert notices.deliver_pending(path) == 0
    assert queue(path)[0]['status'] == 'CANCELLED'
    sender.assert_not_called()


@pytest.mark.parametrize('change', ["access_bv=0", "status='BLOCKED'"])
def test_access_rechecked_before_sending(setup, change):
    path, user, sender = setup
    notices.save_preferences(user, True, path)
    local_sync._upsert_certificate(certificate())
    with database.transaction(path) as con:
        con.execute(f'UPDATE users SET {change} WHERE id=?', (user['id'],))
    assert notices.deliver_pending(path) == 0
    assert queue(path)[0]['status'] == 'CANCELLED'
    sender.assert_not_called()


def test_user_without_bv_cannot_enable(setup):
    path, user, _ = setup
    user['access_bv'] = 0
    with pytest.raises(PermissionError):
        notices.save_preferences(user, True, path)
    assert not notices.preferences(user, path)['bv_new_certificates']


def test_missing_smtp_preserves_queue_without_attempts(setup, monkeypatch):
    path, user, sender = setup
    notices.save_preferences(user, True, path)
    local_sync._upsert_certificate(certificate())
    monkeypatch.setattr(notices, 'email_configured', lambda: False)
    assert notices.deliver_pending(path) == 0
    assert queue(path)[0]['attempts'] == 0
    sender.assert_not_called()


def test_retry_backoff_and_final_failure_visible(setup, monkeypatch):
    path, user, sender = setup
    notices.save_preferences(user, True, path)
    local_sync._upsert_certificate(certificate())
    sender.return_value = False
    clock = [10000]
    monkeypatch.setattr(notices.time, 'time', lambda: clock[0])
    for attempt in range(1, 6):
        assert notices.deliver_pending(path) == 0
        item = queue(path)[0]
        assert item['attempts'] == attempt
        notices.deliver_pending(path)
        assert sender.call_count == attempt  # No immediate repeated attempt.
        clock[0] = item['next_attempt_at']
    assert item['status'] == 'FAILED'
    assert notices.preferences(user, path)['delivery_counts']['FAILED'] == 1


def test_user_can_retry_only_their_failed_deliveries(setup):
    path, user, _ = setup
    notices.save_preferences(user, True, path)
    local_sync._upsert_certificate(certificate())
    with database.transaction(path) as con:
        con.execute("""UPDATE email_notification_outbox SET status='FAILED',attempts=5,
            next_attempt_at=999,last_error='smtp error' WHERE user_id=?""", (user['id'],))
        con.execute("""INSERT INTO users(name,email,password_hash,status,access_bv,created_at)
            VALUES('Outro','outro@example.invalid','unused','APPROVED',1,'2026-09-08')""")
        other_id = con.execute("SELECT id FROM users WHERE email='outro@example.invalid'").fetchone()['id']
        con.execute("""INSERT INTO email_notification_outbox
            (user_id,certificate_id,topic,status,attempts,created_at,last_error)
            SELECT ?,certificate_id,topic,'FAILED',5,'2026-09-08','other error'
            FROM email_notification_outbox WHERE user_id=?""", (other_id, user['id']))
    result = notices.retry_failed(user, path)
    assert result['retried'] == 1
    mine = database.row('SELECT * FROM email_notification_outbox WHERE user_id=?', (user['id'],), path)
    assert mine['status'] == 'PENDING'
    assert mine['attempts'] == 0
    assert mine['next_attempt_at'] == 0
    assert mine['last_error'] == ''
    assert database.row('SELECT status FROM email_notification_outbox WHERE user_id=?', (other_id,), path)['status'] == 'FAILED'


def test_enqueue_rollback_and_idempotency(setup):
    path, user, _ = setup
    cid = local_sync._upsert_certificate(certificate())
    notices.save_preferences(user, True, path)
    with pytest.raises(RuntimeError):
        with database.transaction(path) as con:
            notices.enqueue_new_bv_certificate(con, cid)
            raise RuntimeError('Import failed')
    assert not queue(path)
    with database.transaction(path) as con:
        notices.enqueue_new_bv_certificate(con, cid)
        notices.enqueue_new_bv_certificate(con, cid)
    assert len(queue(path)) == 1


def test_workers_claim_each_email_only_once(setup):
    path, user, sender = setup
    notices.save_preferences(user, True, path)
    local_sync._upsert_certificate(certificate())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: notices.deliver_pending(path), range(2)))
    assert sum(results) == 1
    sender.assert_called_once()


def test_restart_recovers_expired_claim(setup):
    path, user, sender = setup
    notices.save_preferences(user, True, path)
    local_sync._upsert_certificate(certificate())
    with database.transaction(path) as con:
        con.execute("UPDATE email_notification_outbox SET status='SENDING',claimed_at=1,claim_token='crashed'")
    assert notices.deliver_pending(path) == 1
    sender.assert_called_once()


def test_api_auth_and_preference_isolation(setup, monkeypatch):
    import asyncio
    import app
    from starlette.requests import Request
    from starlette.responses import JSONResponse
    path, user, _ = setup
    monkeypatch.setattr(app, 'user_from_session', lambda token: user if token else None)
    monkeypatch.setattr(app, 'email_preferences', lambda u: notices.preferences(u, path))
    monkeypatch.setattr(app, 'save_email_preferences', lambda u, enabled: notices.save_preferences(u, enabled, path))
    monkeypatch.setattr(app, 'audit', lambda *args: None)
    # Exercise the auth middleware and endpoint without starting lifespan workers.
    async def update(request):
        payload = app.EmailNotificationPayload(bv_new_certificates=True, user_id=999)
        try:
            return JSONResponse(app.update_email_notifications(payload, request))
        except app.HTTPException as exc:
            return JSONResponse({'detail': exc.detail}, status_code=exc.status_code)
    def request(headers):
        return Request({'type':'http','path':'/api/auth/email-notifications','method':'PUT','headers':headers})
    assert asyncio.run(app.auth_guard(request([]), update)).status_code == 401
    response = asyncio.run(app.auth_guard(request([(b'cookie', b'qm_session=test')]), update))
    assert response.status_code == 200
    import json
    assert json.loads(response.body)['email'] == user['email']
    assert database.rows('SELECT user_id FROM email_notification_preferences', path=path) == [{'user_id': user['id']}]
    user['access_bv'] = 0
    assert asyncio.run(app.auth_guard(request([(b'cookie', b'qm_session=test')]), update)).status_code == 403
