from pathlib import Path

import qualimatch.management as mg
import qualimatch.queries as q

ROOT = Path(__file__).resolve().parents[1]


def test_bv_screen_keeps_only_pending_certificate(monkeypatch):
    monkeypatch.setattr(mg, 'bv_pending_workflow', lambda contractor='ALL', start=None, end=None: [
        {'date':'2026-08-10','status':'PENDENTE CONTRATADA'},
        {'date':'2026-08-11','status':'NO PRAZO'},
        {'date':'2026-08-12','status':'PENDENTE CERTIFICADO'},
    ])
    out = mg.bv_certificate_pending('ARENA')
    assert [x['date'] for x in out] == ['2026-08-12']
    assert all(x['status'] == 'PENDENTE CERTIFICADO' for x in out)


def test_contractor_pending_is_labeled_contractor(monkeypatch):
    monkeypatch.setattr(q, 'pending_measurements', lambda contractor='ALL', start=None, end=None: [
        {'contractor':'ARENA','date':'2026-08-03','road':'BR-376','kmi':1000,'kmf':2000},
    ])
    monkeypatch.setattr(q, 'rows', lambda sql, params=(): [])
    out = q.contractor_pending_measurements('ARENA')
    assert len(out) == 1
    assert out[0]['status'] == 'PENDENTE CONTRATADA'


def test_footer_has_short_version_only():
    html = (ROOT/'frontend/index.html').read_text(encoding='utf-8')
    assert 'v__QUALIMATCH_VERSION__<br>Desenvolvido por Luan' in html
