from datetime import date

from qualimatch.pdf_reader import Certificate, Sample
from qualimatch.tools_pdf_quality import analyze_certificates, routine_samples


def sample(cp, phase='ROTINA', counter=False, station=100100, lane='1', road_date=date(2026,8,12)):
    return Sample(phase, str(cp), road_date, counter, 'SUL', lane, station, 'BD', 4.0, 4.0, 100.0, 2.5, 5.0, 2.70)


def cert(samples, road='BR-376'):
    return Certificate('ARENA','BI330-0123','x.pdf','hash',date(2026,8,12),date(2026,8,15),road,100000,100300,'TR', 'APROVADO','', any(s.counterproof for s in samples), samples, {
        'phase_summaries': {'ROTINA': {'k':1.41,'sample_count':2}, 'CONTRA_PROVA': {'k':1.41,'sample_count':2}},
        'extraction_dates':['2026-08-15','2026-08-20'],'receipt_dates':['2026-08-17','2026-08-22'], 'parse_status':'CARREGADO'
    })


def test_counterproof_does_not_double_quality_rows():
    c=cert([sample(1),sample(2),sample(1,'CONTRA_PROVA',True),sample(2,'CONTRA_PROVA',True)])
    assert len(routine_samples(c)) == 2


def test_analyzer_matches_one_row_per_routine_cp(monkeypatch):
    c=cert([sample(1,station=100100),sample(2,station=100150)])
    def fake_rows(sql, params=()):
        if 'FROM measurements' in sql:
            return [
                {'id':1,'contractor':'ARENA','source_row':10,'line_measurement':'500','ref_measurement':'M14','date':'2026-08-12','road':'BR-376','direction':'SUL','kmi':100000,'kmf':100200,'lane':'1'},
            ]
        if 'FROM quality_rows' in sql:
            return []
        return []
    monkeypatch.setattr('qualimatch.tools_pdf_quality.rows', fake_rows)
    out=analyze_certificates([('BI330-0123-ARENA.pdf',c)])
    assert out['summary']['expected_rows'] == 2
    assert out['summary']['linked'] == 2
    assert [x['measurement']['line_measurement'] for x in out['lines']] == ['500','500']


def test_road_prefix_divergence_is_review(monkeypatch):
    c=cert([sample(1)], road='BR-323')
    def fake_rows(sql, params=()):
        if 'FROM measurements' in sql:
            return [{'id':1,'contractor':'ARENA','source_row':10,'line_measurement':'500','ref_measurement':'M14','date':'2026-08-12','road':'PR-323','direction':'SUL','kmi':100000,'kmf':100200,'lane':'1'}]
        return []
    monkeypatch.setattr('qualimatch.tools_pdf_quality.rows', fake_rows)
    out=analyze_certificates([('BI330-0123-ARENA.pdf',c)])
    assert out['summary']['review'] == 1
    assert out['lines'][0]['measurement']['road'] == 'PR-323'


def test_existing_quality_rows_are_reported(monkeypatch):
    c=cert([sample(1)])
    def fake_rows(sql, params=()):
        if 'FROM measurements' in sql:
            return [{'id':1,'contractor':'ARENA','source_row':10,'line_measurement':'500','ref_measurement':'M14','date':'2026-08-12','road':'BR-376','direction':'SUL','kmi':100000,'kmf':100200,'lane':'1'}]
        if 'FROM quality_rows' in sql:
            return [{'raw_json':'{"Nº CERTIFICADO Vv":123}'},{'raw_json':'{"Nº CERTIFICADO Vv":123}'}]
        return []
    monkeypatch.setattr('qualimatch.tools_pdf_quality.rows', fake_rows)
    out=analyze_certificates([('BI330-0123-ARENA.pdf',c)])
    assert out['certificates'][0]['existing_quality_rows'] == 2


def test_review_can_be_resolved_with_manual_measurement_override(monkeypatch):
    c=cert([sample(1)], road='BR-323')
    def fake_rows(sql, params=()):
        if 'FROM measurements' in sql:
            return [
                {'id':10,'contractor':'ARENA','source_row':20,'line_measurement':'700','ref_measurement':'M14','date':'2026-08-12','road':'PR-323','direction':'SUL','kmi':100000,'kmf':100200,'lane':'1'},
                {'id':11,'contractor':'ARENA','source_row':21,'line_measurement':'701','ref_measurement':'M14','date':'2026-08-12','road':'PR-323','direction':'NORTE','kmi':100000,'kmf':100200,'lane':'2'},
            ]
        return []
    monkeypatch.setattr('qualimatch.tools_pdf_quality.rows', fake_rows)
    first=analyze_certificates([('BI330-0123-ARENA.pdf',c)])
    line=first['lines'][0]
    assert line['match_status'] == 'REVISAR'
    assert line['measurement_candidates']
    chosen=line['measurement_candidates'][0]['id']
    second=analyze_certificates([('BI330-0123-ARENA.pdf',c)], {line['line_key']: chosen})
    assert second['lines'][0]['match_status'] == 'VINCULADO'
    assert 'VÍNCULO MANUAL' in second['lines'][0]['match_reason']
