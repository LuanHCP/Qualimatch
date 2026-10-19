from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_contractor_pending_is_grouped_one_row_per_day(monkeypatch):
    import qualimatch.queries as q
    monkeypatch.setattr(q,'pending_measurements',lambda contractor='ALL',start=None,end=None:[
        {'contractor':'ARENA','date':'2026-08-03','road':'BR-376','kmi':1000,'kmf':1500},
        {'contractor':'ARENA','date':'2026-08-03','road':'BR-376','kmi':1500,'kmf':2000},
        {'contractor':'ARENA','date':'2026-08-04','road':'BR-376','kmi':2000,'kmf':2500},
    ])
    monkeypatch.setattr(q,'rows',lambda sql,params=():[] if 'FROM kit_rows' in sql else [])
    out=q.contractor_pending_measurements('ARENA')
    assert len(out)==2
    d3=next(x for x in out if x['date']=='2026-08-03')
    assert d3['lines']==2
    assert d3['kmi']==1000 and d3['kmf']==2000

def test_delivery_chart_has_visual_css():
    css=(ROOT/'frontend/static/app.css').read_text(encoding='utf-8')
    js=(ROOT/'frontend/static/app.js').read_text(encoding='utf-8')
    assert '.delivery-bars{' in css and '.delivery-track span{' in css
    assert 'renderDeliveryChart' in js

def test_kit_filters_match_bv_style():
    html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
    app=(ROOT/'app.py').read_text(encoding='utf-8')
    js=(ROOT/'frontend/static/app.js').read_text(encoding='utf-8')
    for field in ('kit-sort','kit-status','kit-road','kit-period','kit-start','kit-end','kit-search','kit-clear'):
        assert f'id="{field}"' in html
    assert '/api/contractor/kits/filter-options' in app
    assert 'loadKitFilterOptions' in js
