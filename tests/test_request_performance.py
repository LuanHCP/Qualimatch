import asyncio
import threading
from unittest.mock import Mock

from starlette.requests import Request
from starlette.responses import Response

import app
from qualimatch import database, queries
from qualimatch.certificate_stats import _stats


def test_statistics_cache_does_not_leak_printed_overrides():
    first = _stats([4.0, 5.0], 1.41)
    first['mean'] = 99
    assert _stats([4.0, 5.0], 1.41)['mean'] == 4.5
    assert _stats([4.0, 6.0], 1.41)['mean'] == 5.0


def test_pool_release_rolls_back_before_reuse():
    events = []
    raw = Mock(closed=False)
    raw.rollback.side_effect = lambda: events.append('rollback')
    pool = Mock()
    pool.putconn.side_effect = lambda conn: events.append('release')
    con = database._PGConnection(raw, pool)
    con.close()
    con.close()
    assert events == ['rollback', 'release']
    raw.close.assert_not_called()


def test_pool_discards_connection_if_cleanup_fails():
    raw = Mock(closed=False)
    raw.rollback.side_effect = RuntimeError('connection lost')
    pool = Mock()
    database._PGConnection(raw, pool).close()
    raw.close.assert_called_once()
    pool.putconn.assert_called_once_with(raw)


def test_session_lookup_does_not_block_other_requests(monkeypatch):
    started, release = threading.Event(), threading.Event()

    def lookup(token):
        started.set()
        release.wait(2)
        return {'role': 'ADMIN'}

    monkeypatch.setattr(app, 'user_from_session', lookup)

    async def run():
        async def next_handler(request):
            return Response(status_code=200)

        request = Request({'type': 'http', 'path': '/api/auth/me', 'headers': []})
        task = asyncio.create_task(app.auth_guard(request, next_handler))
        try:
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(.005)
            assert started.is_set()
            # The lookup is still blocked, yet the event loop serves public HTTP.
            assert not task.done()
            public = Request({'type': 'http', 'path': '/', 'headers': []})
            assert (await app.auth_guard(public, next_handler)).status_code == 200
        finally:
            release.set()
            await task

    asyncio.run(run())


def test_pending_skips_already_covered_quality_rows(monkeypatch):
    def rows(sql, params=()):
        if 'GROUP BY contractor,date' in sql:
            return [{'contractor': 'ARENA', 'date': '2026-09-01', 'lines': 1}]
        if 'UNION' in sql:
            return [{'contractor': 'ARENA', 'covered_date': '2026-09-01'}]
        if 'FROM quality_rows' in sql:
            return [{'contractor': 'ARENA', 'date': '2026-09-01', 'raw_json': '{}'}]
        return []

    monkeypatch.setattr(queries, 'rows', rows)
    check = Mock(side_effect=AssertionError('Already covered: do not parse again'))
    monkeypatch.setattr(queries, '_has_vv_certificate', check)
    assert queries.pending_days('ARENA') == []


def test_replacement_preserves_pdf_after_database_commit(tmp_path, monkeypatch):
    pdf = tmp_path / 'corrected.pdf'
    pdf.write_bytes(b'pdf')
    monkeypatch.setattr(app, 'parse_pdf', lambda *args: Mock(number='BI330-123'))
    monkeypatch.setattr(app, '_automatic_backup', lambda *args: 'backup')
    monkeypatch.setattr(app, 'replace_certificate_record', lambda *args: None)
    monkeypatch.setattr(app, '_record_certificate_file', lambda *args: None)
    monkeypatch.setattr(app, 'recalculate_matches', Mock(side_effect=RuntimeError('matching failed')))
    try:
        app._replace_uploaded_certificate(1, pdf, 'ARENA', {'number': 'BI330-123'})
    except RuntimeError:
        pass
    assert pdf.exists()
