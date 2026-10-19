from pathlib import Path

import qualimatch.local_sync as ls
import qualimatch.tools_pdf_quality as toolmod
import qualimatch.quality_excel_writer as writermod
from qualimatch.database import init_db, row


def test_v387_setting_created(tmp_path: Path):
    db = tmp_path / 'v387.db'
    init_db(db)
    assert row("SELECT value FROM settings WHERE key='auto_bdquali_enabled'", path=db)['value'] == '1'


def test_auto_bdquali_writes_ready_new_certificate(monkeypatch, tmp_path: Path):
    pdf = tmp_path / 'BI330-9999-ARENA.pdf'
    pdf.write_bytes(b'%PDF-1.4\nmock')

    def fake_row(sql, params=()):
        if 'FROM certificate_files' in sql:
            return {'certificate_id': 10, 'file_hash': 'abc', 'status': 'CARREGADO', 'error': ''}
        if 'FROM certificates' in sql:
            return {'id': 10, 'is_active': 1}
        if "kind='medicao'" in sql:
            return {'last_hash': 'med1', 'last_mtime_ns': 1, 'last_size': 2}
        if "kind='qualidade'" in sql:
            return {'last_hash': 'qua1', 'last_mtime_ns': 3, 'last_size': 4}
        return None

    monkeypatch.setattr(ls, 'row', fake_row)
    monkeypatch.setattr(ls, '_setting_bool', lambda key, default=False: True)
    monkeypatch.setattr(ls, '_is_bi330_pdf', lambda p: True)
    monkeypatch.setattr(ls, '_wait_file_ready', lambda *a, **k: None)
    monkeypatch.setattr(ls, 'parse_pdf', lambda *a, **k: object())
    monkeypatch.setattr(ls, '_begin_monitor_event', lambda *a, **k: 77)
    finished = []
    monkeypatch.setattr(ls, '_finish_monitor_event', lambda eid, status, message='': finished.append((eid, status, message)))

    analysis = {
        'summary': {},
        'lines': [{'file_name': str(pdf.resolve())}, {'file_name': str(pdf.resolve())}],
        'certificates': [{
            'file_name': str(pdf.resolve()), 'contractor': 'ARENA', 'certificate': 'BI330-9999',
            'expected_quality_rows': 2, 'existing_quality_rows': 0,
            'lines': [{}, {}],
            'excel_write': {'ready': True, 'mode': 'ADICIONAR_NOVO', 'reason': ''},
        }],
    }
    monkeypatch.setattr(toolmod, 'analyze_certificates', lambda parsed: analysis)
    monkeypatch.setattr(writermod, 'write_excel_to_main_sources', lambda a: {
        'files': [{'contractor': 'ARENA', 'rows_written': 2, 'target_rows': [100, 101]}], 'blocked': []
    })
    monkeypatch.setattr(ls, 'sync_source', lambda *a, **k: {'ok': True, 'records': 2})

    out = ls.auto_fill_quality_for_certificate_paths('ARENA', [pdf])
    assert out['written_certificates'] == 1
    assert out['written_rows'] == 2
    assert out['errors'] == 0
    assert any(status == 'BD_QUALI_OK' for _, status, _ in finished)


def test_auto_bdquali_never_writes_review_case(monkeypatch, tmp_path: Path):
    pdf = tmp_path / 'BI330-8888-PAVIDEZ.pdf'
    pdf.write_bytes(b'%PDF-1.4\nmock')

    def fake_row(sql, params=()):
        if 'FROM certificate_files' in sql:
            return {'certificate_id': 20, 'file_hash': 'def', 'status': 'CARREGADO', 'error': ''}
        if 'FROM certificates' in sql:
            return {'id': 20, 'is_active': 1}
        if 'FROM sources' in sql:
            return {'last_hash': 'x', 'last_mtime_ns': 1, 'last_size': 2}
        return None
    monkeypatch.setattr(ls, 'row', fake_row)
    monkeypatch.setattr(ls, '_setting_bool', lambda key, default=False: True)
    monkeypatch.setattr(ls, '_is_bi330_pdf', lambda p: True)
    monkeypatch.setattr(ls, '_wait_file_ready', lambda *a, **k: None)
    monkeypatch.setattr(ls, 'parse_pdf', lambda *a, **k: object())
    monkeypatch.setattr(ls, '_begin_monitor_event', lambda *a, **k: 88)
    finished=[]
    monkeypatch.setattr(ls, '_finish_monitor_event', lambda eid, status, message='': finished.append((eid,status,message)))
    analysis = {
        'summary': {}, 'lines': [],
        'certificates': [{
            'file_name': str(pdf.resolve()), 'contractor':'PAVIDEZ', 'certificate':'BI330-8888',
            'expected_quality_rows': 3, 'existing_quality_rows': 0, 'lines':[{}, {}, {}],
            'excel_write': {'ready': False, 'mode':'BLOQUEADO', 'reason':'Há CP(s) em REVISAR.'},
        }],
    }
    monkeypatch.setattr(toolmod, 'analyze_certificates', lambda parsed: analysis)
    called=[]
    monkeypatch.setattr(writermod, 'write_excel_to_main_sources', lambda a: called.append(a) or {})
    out=ls.auto_fill_quality_for_certificate_paths('PAVIDEZ',[pdf])
    assert out['review'] == 1
    assert out['written_certificates'] == 0
    assert not called
    assert any(status == 'REVISAR' for _,status,_ in finished)


def test_v387_ui_exposes_auto_bdquali_control():
    root=Path(__file__).resolve().parents[1]
    html=(root/'frontend'/'index.html').read_text(encoding='utf-8')
    js=(root/'frontend'/'static'/'app.js').read_text(encoding='utf-8')
    assert 'Preencher BD_QUALI' in html
    assert 'auto-monitor-quality' in html
    assert 'bd_quali_auto' in js
    assert '__QUALIMATCH_VERSION__' in html
