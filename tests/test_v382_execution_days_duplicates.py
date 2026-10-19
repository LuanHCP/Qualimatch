from datetime import date
from pathlib import Path

import pytest

import qualimatch.queries as q
import qualimatch.management as mg
import qualimatch.local_sync as ls
from qualimatch.pdf_reader import Certificate, Sample


def _cert(path: str = '/tmp/a.pdf', *, vv: float = 5.0, file_hash: str = 'hash-a') -> Certificate:
    return Certificate(
        contractor='ARENA', number='BI330-999', file_path=path, file_hash=file_hash,
        service_date=date(2026, 8, 15), extraction_date=date(2026, 8, 18),
        road='BR-376', kmi=303000, kmf=304000, trace_approved='TRACO X',
        routine_result='APROVADO', counterproof_result='', has_counterproof=False,
        samples=[Sample(
            phase='ROTINA', cp_number='1', application_date=date(2026, 8, 15), counterproof=False,
            direction='SUL', lane='1', station=303500, position='BD', thickness_exec_cm=4.0,
            thickness_project_cm=4.0, ratio_ab_pct=100.0, gmb=2.55, voids_pct=vv, rice_gmm=2.68,
        )],
        raw={'service_dates':['2026-08-15'], 'phase_summaries':{'ROTINA':{'k':1.25,'vv_mean_pct':vv}}},
    )


def test_contractor_monthly_view_does_not_create_artificial_target_without_deliveries(monkeypatch):
    def fake_rows(sql, params=()):
        if 'FROM kit_rows' in sql:
            return []
        return []
    monkeypatch.setattr(q, 'rows', fake_rows)
    out = q.kit_summary('ALL')
    assert out['deliveries'] == []


def test_cycle_dashboard_counts_distinct_execution_dates_in_all_view(monkeypatch):
    def fake_rows(sql, params=(), path=None):
        if 'SELECT DISTINCT contractor,date FROM measurements' in sql:
            return [
                {'contractor':'ARENA','date':'2026-08-11'},
                {'contractor':'PAVIDEZ','date':'2026-08-11'},
                {'contractor':'ARENA','date':'2026-08-12'},
            ]
        if 'FROM kit_rows' in sql or 'FROM certificates' in sql or 'certificate_samples' in sql:
            return []
        return []
    monkeypatch.setattr(mg, 'rows', fake_rows)
    monkeypatch.setattr(mg, 'bv_pending_workflow', lambda contractor: [])
    out = mg.measurement_cycle_dashboard('ALL')
    m14 = next(x for x in out['cycles'] if x['measurement'] == 'M14')
    assert m14['execution_days'] == 2


def test_certificate_content_fingerprint_ignores_file_location_but_not_technical_data():
    a = _cert('/sharepoint/a.pdf', file_hash='aaa')
    b = _cert('/sharepoint/copia/a-renomeado.pdf', file_hash='bbb')
    assert ls._certificate_content_fingerprint(a) == ls._certificate_content_fingerprint(b)
    c = _cert('/sharepoint/c.pdf', vv=6.0, file_hash='ccc')
    assert ls._certificate_content_fingerprint(a) != ls._certificate_content_fingerprint(c)


def test_sync_source_marks_duplicate_as_skipped(monkeypatch, tmp_path: Path):
    pdf = tmp_path / 'duplicado.pdf'; pdf.write_bytes(b'%PDF fake')
    cert = _cert(str(pdf), file_hash='same')
    monkeypatch.setattr(ls, 'row', lambda *a, **k: None)
    monkeypatch.setattr(ls, '_parse_certificate_job', lambda p, c: (p, cert))
    monkeypatch.setattr(ls, '_upsert_certificate', lambda c: (_ for _ in ()).throw(ls.DuplicateCertificateError(12,'BI330-999','fp')))
    recorded = []
    monkeypatch.setattr(ls, '_record_certificate_file', lambda contractor,pdf,cid,cert,status=None,error='': recorded.append((cid,status,error)))
    monkeypatch.setattr(ls, 'log_sync', lambda *a, **k: None)
    parsed, skipped, errors, total = ls._sync_certificates('ARENA', tmp_path, True)
    assert (parsed, skipped, errors, total) == (0, 1, 0, 1)
    assert recorded and recorded[0][0] == 12 and recorded[0][1] == 'DUPLICADO'


def test_version_bumped_and_duplicate_status_is_stable():
    root = Path(__file__).resolve().parents[1]
    app = (root/'app.py').read_text(encoding='utf-8')
    version = (root/'qualimatch/version.py').read_text(encoding='utf-8')
    sync = (root/'qualimatch/local_sync.py').read_text(encoding='utf-8')
    assert 'version=APP_VERSION' in app
    assert 'APP_VERSION = "3.13.0"' in version
    assert '"DUPLICADO"' in sync
    assert 'DuplicateCertificateError' in sync
