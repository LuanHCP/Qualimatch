from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_monthly_delivery_summary_has_no_artificial_target(monkeypatch):
    import qualimatch.queries as q
    def fake_rows(sql, params=()):
        if 'FROM kit_rows' in sql:
            return [
                {'contractor':'ARENA','application_date':'2026-08-01','receipt_date':'2026-08-03','delivery_status':'ENTREGUE','status':'OK',
                 **{f'status_{i}':'OK' for i in range(1,9)},'sin_retro':'OK','raw_json':'{}'},
                {'contractor':'ARENA','application_date':'2026-08-02','receipt_date':'2026-08-10','delivery_status':'ENTREGUE','status':'OK',
                 **{f'status_{i}':'OK' for i in range(1,9)},'sin_retro':'OK','raw_json':'{}'},
            ]
        return []
    monkeypatch.setattr(q,'rows',fake_rows)
    out=q.kit_summary('ARENA')
    assert out['deliveries']==[{'month':'2026-08','count':2}]
    assert all('target' not in x for x in out['deliveries'])

def test_filter_options_are_closed_and_roads_direct(monkeypatch):
    import qualimatch.queries as q
    monkeypatch.setattr(q,'rows',lambda sql,params=():[{'road':'BR-376'},{'road':'BR-373'},{'road':'-'},{'road':''}])
    out=q.kit_filter_options('ARENA')
    assert out['statuses']==['OK','INCOMPLETO','PENDENTE']
    assert out['periods']==['DIURNO','NOTURNO']
    assert out['roads']==['BR-373','BR-376']
    assert 'services' not in out

def test_ui_has_monthly_chart_without_target_line_and_no_service_filter():
    html=(ROOT/'frontend/index.html').read_text(encoding='utf-8')
    js=(ROOT/'frontend/static/app.js').read_text(encoding='utf-8')
    assert 'Entregas por mês' in html
    assert 'Sem linha de meta' in html
    assert 'id="kit-service"' not in html
    assert 'INCOMPLETO' in html and 'PENDENTE' in html
    assert 'DIURNO' in html and 'NOTURNO' in html
    assert 'monthly-target-line' not in js
    assert 'meta de dias com medição' not in js
    assert "'contractor-kits':async()=>{await loadKitFilterOptions();await loadKits();await loadKitDocuments()}" in js
