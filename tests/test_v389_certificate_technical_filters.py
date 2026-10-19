from pathlib import Path

import qualimatch.queries as q

ROOT = Path(__file__).resolve().parents[1]


def _fake_cert(cid, vv, thickness):
    return {
        'id': cid,
        'is_active': 1,
        'contractor': 'ARENA',
        'number': f'BI330-{cid:04d}',
        'road': 'BR-376',
        'service_date': '2026-08-20',
        'extraction_date': '2026-08-20',
        '_vv': vv,
        '_th': thickness,
    }


def test_list_certificates_filters_vv_and_thickness_independently(monkeypatch):
    data = [
        _fake_cert(1, 'APROVADO', 'APROVADO'),
        _fake_cert(2, 'REPROVADO', 'APROVADO'),
        _fake_cert(3, 'APROVADO', 'REPROVADO'),
        _fake_cert(4, 'REPROVADO', 'REPROVADO'),
    ]
    monkeypatch.setattr(q, 'rows', lambda sql, params=(): data)
    monkeypatch.setattr(q, '_bulk_certificate_context', lambda candidates: ({}, {}, {}))

    def stats(cert, samples, docs, matched_count=0, include_samples=False):
        return {
            **cert,
            'sample_count': 1,
            'overall_status': 'REPROVADO' if 'REPROVADO' in {cert['_vv'], cert['_th']} else 'APROVADO',
            'status_vv': cert['_vv'],
            'status_thickness': cert['_th'],
        }
    monkeypatch.setattr(q, '_cert_stats_loaded', stats)

    vv_bad = q.list_certificates(vv_status='REPROVADO')
    assert [x['id'] for x in vv_bad] == [2, 4]

    thickness_bad = q.list_certificates(thickness_status='REPROVADO')
    assert [x['id'] for x in thickness_bad] == [3, 4]

    both_bad = q.list_certificates(vv_status='REPROVADO', thickness_status='REPROVADO')
    assert [x['id'] for x in both_bad] == [4]


def test_certificate_screen_has_both_technical_filters():
    html = (ROOT / 'frontend/index.html').read_text(encoding='utf-8')
    js = (ROOT / 'frontend/static/app.js').read_text(encoding='utf-8')
    assert 'id="c-vv-status"' in html
    assert 'id="c-thickness-status"' in html
    assert "vv_status:$('#c-vv-status').value" in js
    assert "thickness_status:$('#c-thickness-status').value" in js
    assert 'v__QUALIMATCH_VERSION__<br>Desenvolvido por Luan' in html
