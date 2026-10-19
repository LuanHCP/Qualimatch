from datetime import date
from pathlib import Path

import qualimatch.queries as q
import qualimatch.management as mg


def _sample(phase='ROTINA', vv=5.0, ratio=100.0):
    return {
        'phase': phase, 'cp_number': '1', 'application_date': '2026-08-15',
        'counterproof': 1 if phase == 'CONTRA_PROVA' else 0,
        'direction': 'SUL', 'lane': '1', 'station': 300100, 'position': 'EX',
        'thickness_exec_cm': 4.0, 'thickness_project_cm': 4.0,
        'ratio_ab_pct': ratio, 'rice_gmm': 2.6, 'gmb': 2.5, 'voids_pct': vv,
    }


def _cert(cid, result='', has_cp=0):
    return {
        'id': cid, 'contractor': 'ARENA', 'number': f'BI330-{cid:04d}',
        'service_date': '2026-08-15', 'extraction_date': '2026-08-18',
        'road': 'BR-376', 'kmi': 300000, 'kmf': 301000, 'trace_approved': 'TR',
        'routine_result': result, 'counterproof_result': '', 'has_counterproof': has_cp,
        'raw_json': '{}', 'is_active': 1,
    }


def test_certificate_summary_counterproof_is_subset_and_final_phase_wins(monkeypatch):
    certs = [_cert(1, 'APROVADO'), _cert(2, 'REPROVADO', 1), _cert(3)]
    samples = {
        1: [_sample('ROTINA', 5.0, 100.0)],
        2: [_sample('ROTINA', 8.0, 80.0), _sample('CONTRA_PROVA', 5.0, 100.0)],
        3: [],
    }
    # Contra-prova entregue deve ser a fase final. Sem resultado impresso nela,
    # o status calculado pelos próprios CPs é usado.
    monkeypatch.setattr(q, 'rows', lambda sql, params=(): certs if 'SELECT * FROM certificates' in sql else [])
    monkeypatch.setattr(q, '_bulk_certificate_context', lambda cs: (samples, {1: [], 2: [], 3: []}, {1: 0, 2: 0, 3: 0}))
    out = q.certificate_summary('ARENA')
    assert out['total'] == 3
    assert out['approved'] == 2
    assert out['reproved'] == 0
    assert out['adjustments'] == 1
    assert out['classified_total'] == out['total']
    assert out['counterproof_delivered'] == 1
    assert out['counterproof_delivered'] <= out['total']


def test_bv_responsibility_uses_entrega_even_inside_sla(monkeypatch):
    monkeypatch.setattr(mg, 'pending_days', lambda contractor='ALL', start=None, end=None: [
        {'contractor': 'ARENA', 'date': '2026-08-18', 'measurement': 'M14', 'road': 'BR-376'},
        {'contractor': 'ARENA', 'date': '2026-08-19', 'measurement': 'M14', 'road': 'BR-376'},
    ])
    monkeypatch.setattr(mg, '_today', lambda: date(2026, 8, 20))
    monkeypatch.setattr(mg, 'rows', lambda sql, params=(): [
        {'contractor': 'ARENA', 'application_date': '2026-08-18', 'receipt_date': '2026-08-19',
         'delivery_status': 'Entregue', 'status': 'OK', 'seq': '10', 'raw_json': '{}'},
        {'contractor': 'ARENA', 'application_date': '2026-08-19', 'receipt_date': None,
         'delivery_status': 'Não entregue', 'status': 'PENDENTE', 'seq': '11', 'raw_json': '{}'},
    ])
    all_items = mg.bv_pending_workflow('ARENA')
    assert all_items[0]['responsibility'] == 'BV'
    assert all_items[0]['status'] == 'NO PRAZO'
    assert all_items[1]['responsibility'] == 'CONTRATADA'
    bv = mg.bv_certificate_pending('ARENA')
    assert [x['date'] for x in bv] == ['2026-08-18']


def test_contractor_keeps_not_delivered_and_blank_entrega(monkeypatch):
    monkeypatch.setattr(q, 'pending_measurements', lambda contractor='ALL', start=None, end=None: [
        {'contractor': 'ARENA', 'date': '2026-08-18', 'road': 'BR-376', 'kmi': 1000, 'kmf': 2000},
        {'contractor': 'ARENA', 'date': '2026-08-19', 'road': 'BR-376', 'kmi': 2000, 'kmf': 3000},
        {'contractor': 'ARENA', 'date': '2026-08-20', 'road': 'BR-376', 'kmi': 3000, 'kmf': 4000},
    ])
    monkeypatch.setattr(q, 'rows', lambda sql, params=(): [
        {'contractor': 'ARENA', 'application_date': '2026-08-18', 'delivery_status': 'Entregue', 'raw_json': '{}', 'seq': '1'},
        {'contractor': 'ARENA', 'application_date': '2026-08-19', 'delivery_status': 'Não entregue', 'raw_json': '{}', 'seq': '2'},
        {'contractor': 'ARENA', 'application_date': '2026-08-20', 'delivery_status': '', 'raw_json': '{"_qualimatch_entrega_coluna": true}', 'seq': '3'},
    ])
    out = q.contractor_pending_measurements('ARENA')
    assert [x['date'] for x in out] == ['2026-08-20', '2026-08-19']
    assert {x['delivery_status'] for x in out} == {'NÃO ENTREGUE', 'SEM INFORMAÇÃO'}


def test_all_kits_must_be_entregue_before_responsibility_moves_to_bv(monkeypatch):
    monkeypatch.setattr(mg, 'pending_days', lambda contractor='ALL', start=None, end=None: [
        {'contractor': 'PAVIDEZ', 'date': '2026-08-15', 'measurement': 'M14', 'road': 'BR-376'},
    ])
    monkeypatch.setattr(mg, 'rows', lambda sql, params=(): [
        {'contractor': 'PAVIDEZ', 'application_date': '2026-08-15', 'receipt_date': '2026-08-16',
         'delivery_status': 'Entregue', 'status': 'OK', 'seq': '1', 'raw_json': '{}'},
        {'contractor': 'PAVIDEZ', 'application_date': '2026-08-15', 'receipt_date': None,
         'delivery_status': 'Não entregue', 'status': 'PENDENTE', 'seq': '2', 'raw_json': '{}'},
    ])
    out = mg.bv_pending_workflow('PAVIDEZ')
    assert out[0]['responsibility'] == 'CONTRATADA'
    assert out[0]['status'] == 'PENDENTE CONTRATADA'


def test_ui_explains_counterproof_subset_and_entrega_source():
    root = Path(__file__).resolve().parents[1]
    js = (root/'frontend/static/app.js').read_text(encoding='utf-8')
    html = (root/'frontend/index.html').read_text(encoding='utf-8')
    assert 'Subconjunto dos certificados acima' in js
    assert 'Ajustes / sem resultado' in js
    assert 'Fonte: coluna <b>Entrega</b> da d.KIT' in js
    assert '<th>Entrega</th>' in html
