from pathlib import Path
from types import SimpleNamespace

import app as appmod
import qualimatch.queries as q

ROOT = Path(__file__).resolve().parents[1]


def _kit(**kw):
    base = {
        'contractor': 'PAVIDEZ', 'application_date': '2026-08-15', 'receipt_date': None,
        'status': 'OK', 'sin_retro': 'OK',
    }
    base.update({f'status_{i}': 'OK' for i in range(1, 9)})
    base.update(kw)
    return base


def test_delivery_chart_falls_back_to_application_date(monkeypatch):
    def fake_rows(sql, params=()):
        if 'FROM kit_rows' in sql:
            return [
                _kit(application_date='2026-08-15', receipt_date=None),
                _kit(application_date='2026-08-17', receipt_date='2026-08-18'),
            ]
        if 'FROM measurements' in sql:
            return [
                {'contractor': 'PAVIDEZ', 'date': '2026-08-15'},
                {'contractor': 'PAVIDEZ', 'date': '2026-08-17'},
            ]
        return []
    monkeypatch.setattr(q, 'rows', fake_rows)
    out = q.kit_summary('PAVIDEZ')
    assert out['deliveries'] == [{'month': '2026-08', 'count': 2}]
    assert out['delivery_date_sources'] == {'application': 1, 'receipt': 1}


def test_kit_queries_ignore_archived_rows_source_code():
    text = (ROOT / 'qualimatch' / 'queries.py').read_text(encoding='utf-8')
    assert 'COALESCE(is_active,1)=1' in text
    assert 'Data Aplicação' in text or 'application_date' in text


def test_sync_preserves_manual_kit_overrides_source_code():
    text = (ROOT / 'qualimatch' / 'local_sync.py').read_text(encoding='utf-8')
    assert 'manual_override' in text
    assert 'DELETE FROM kit_rows WHERE contractor=? AND COALESCE(manual_override,0)=0' in text


def test_contractor_ui_has_preview_edit_and_archive():
    html = (ROOT / 'frontend' / 'index.html').read_text(encoding='utf-8')
    js = (ROOT / 'frontend' / 'static' / 'app.js').read_text(encoding='utf-8')
    assert 'Ações' in html
    assert 'previewKitDocument' in js
    assert 'openKitEdit' in js
    assert 'archiveKit' in js
    assert 'Data recebimento; fallback = Data aplicação' in html


def test_kit_edit_payload_normalizes_station_and_road(monkeypatch):
    current = {
        'id': 10, 'contractor': 'ARENA', 'source_row': 22, 'seq': '123',
        'is_active': 1,
    }
    monkeypatch.setattr(appmod, 'kit_detail', lambda kid: dict(current))
    monkeypatch.setattr(appmod, '_require_admin', lambda req: {'id': 1, 'role': 'ADMIN'})
    executed = {}
    class Tx:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, values): executed['sql'] = sql; executed['values'] = values
    monkeypatch.setattr(appmod, 'transaction', lambda: Tx())
    monkeypatch.setattr(appmod, 'audit', lambda *a, **k: None)
    monkeypatch.setattr(appmod, 'log_sync', lambda *a, **k: None)
    payload = appmod.KitEditPayload(
        seq='123', application_date='2026-08-15', period='DIURNO', road='BR376',
        kmi='405+845', kmf='406+100', status='OK', status_1='OK', status_2='OK',
        status_3='OK', status_4='OK', status_5='OK', status_6='OK', status_7='OK',
        status_8='N/A', sin_retro='OK'
    )
    req = SimpleNamespace(state=SimpleNamespace(user={'id': 1, 'role': 'ADMIN'}), headers={}, client=None)
    out = appmod.contractor_kit_edit(10, payload, req)
    vals = executed['values']
    assert 'manual_override=1' in executed['sql']
    assert 'BR-376' in vals
    assert 405845 in vals and 406100 in vals
    assert out['ok'] is True
