from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_contractor_pending_adds_kit_application_date_coverage():
    q=(ROOT/'qualimatch/queries.py').read_text(encoding='utf-8')
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    assert 'def contractor_pending_measurements' in q
    assert 'delivery_status,raw_json,seq FROM kit_rows' in q
    assert 'delivered=(' in q
    assert 'return contractor_pending_measurements(contractor,start,end)' in app

def test_v361_visual_requests_are_preserved():
    html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
    js=(ROOT/'frontend/static/app.js').read_text(encoding='utf-8')
    assert 'Entregas por mês' in html
    assert 'Verde ≥ 95%' in html
    assert "extension=pdf" in js
    assert "pct>=95?'ok':pct>=85?'warn':'bad'" in js


def test_kit_application_date_removes_date_from_contractor_pending(monkeypatch):
    import qualimatch.queries as q
    monkeypatch.setattr(q, 'pending_measurements', lambda contractor='ALL',start=None,end=None: [
        {'contractor':'ARENA','date':'2026-08-03','line_measurement':'1'},
        {'contractor':'ARENA','date':'2026-08-04','line_measurement':'2'},
    ])
    monkeypatch.setattr(q, 'rows', lambda sql, params=(): [
        {'contractor':'ARENA','application_date':'2026-08-04'}
    ] if 'FROM kit_rows' in sql else [])
    out=q.contractor_pending_measurements('ARENA')
    assert [x['date'] for x in out] == ['2026-08-03']
