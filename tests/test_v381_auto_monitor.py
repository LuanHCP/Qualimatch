from pathlib import Path
from types import SimpleNamespace

import qualimatch.local_sync as ls
from qualimatch.database import init_db, row


def test_monitor_schema_and_defaults_are_created(tmp_path: Path):
    db = tmp_path / 'monitor.db'
    init_db(db)
    assert row("SELECT name FROM sqlite_master WHERE type='table' AND name='auto_import_events'", path=db)
    assert row("SELECT value FROM settings WHERE key='auto_monitor_enabled'", path=db)['value'] == '1'
    assert row("SELECT value FROM settings WHERE key='auto_monitor_bv'", path=db)['value'] == '1'
    assert row("SELECT value FROM settings WHERE key='auto_monitor_contractor'", path=db)['value'] == '1'
    assert row("SELECT value FROM settings WHERE key='auto_monitor_seconds'", path=db)['value'] == '15'


def test_wait_file_ready_accepts_stable_file(tmp_path: Path):
    f = tmp_path / 'novo.pdf'
    f.write_bytes(b'%PDF-1.4\nconteudo-estavel')
    ls._wait_file_ready(f, checks=1, attempts=3, interval=.01)


def test_wait_file_ready_uses_retryable_error_for_unavailable_file(monkeypatch, tmp_path: Path):
    pdf = tmp_path / 'placeholder.pdf'
    pdf.write_bytes(b'pdf')
    monkeypatch.setattr(Path, 'open', lambda *a, **k: (_ for _ in ()).throw(PermissionError('offline')))
    try:
        ls._wait_file_ready(pdf, checks=1, attempts=1, interval=0)
    except ls.SourceFileUnavailable as exc:
        assert 'offline' in str(exc)
    else:
        raise AssertionError('placeholder indisponível deveria ser adiado')


def test_recursive_scan_reads_every_file_in_all_measurement_folders(monkeypatch, tmp_path: Path):
    for measurement, count in [('M01', 73), ('M02', 5), ('M06', 1), ('M11', 9)]:
        folder = tmp_path / measurement
        folder.mkdir()
        for index in range(count):
            (folder / f'documento-{index}.PDF').write_bytes(b'pdf')
    (tmp_path / 'M11' / 'evidencia-sem-extensao').write_bytes(b'doc')
    (tmp_path / 'M11' / 'correspondencia.msg').write_bytes(b'msg')
    monkeypatch.setattr(ls, 'log_sync', lambda *args, **kwargs: None)
    files, errors = ls._scan_tree_files('ARENA', 'bv_documentos', tmp_path, None)
    assert errors == 0
    assert len(files) == 90


def test_bi330_filter_accepts_common_name_variations_and_parent_folder(tmp_path: Path):
    assert ls._is_bi330_pdf(tmp_path / 'BI-330_0123.PDF')
    assert ls._is_bi330_pdf(tmp_path / 'BI 330 0124.pdf')
    assert ls._is_bi330_pdf(tmp_path / 'Certificados BI_330' / 'relatorio-0125.pdf')


def test_bv_report_scope_reads_01_to_04_0_and_ignores_04_volume(tmp_path: Path):
    root = tmp_path / 'contrato'; vv = root / '04.0 VV - CERTIFICADOS'
    wanted = [
        root / '01. CARACTERIZAÇÃO DE CA' / '2026' / '12_MED_JUN' / 'ca.pdf',
        root / '02. CARACTERIZAÇÃO LIGANTES' / '2026' / '12_MED_JUN' / 'ligante.pdf',
        root / '03. CARACTERIZAÇÃO AGREGADOS' / '2026' / '12_MED_JUN' / 'agregado.pdf',
        root / '07. DANO POR UMIDADE INDUZIDA (DUI)' / '2026' / '12_MED_JUN' / 'ensaio.pdf',
        vv / 'M12' / 'vv.pdf',
    ]
    ignored = root / '04. VOLUME DE VAZIO' / 'nao-indexar.pdf'
    for path in [*wanted, ignored]:
        path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'x')
    files, errors = ls._bv_report_files('ARENA', vv)
    assert errors == 0
    assert set(files) == set(wanted)
    assert ls._measurement_label_from_path('01. CARACTERIZAÇÃO DE CA/2026/12_MED_JUN/ca.pdf') == 'M12'


def test_certificate_save_error_does_not_stop_remaining_files(monkeypatch, tmp_path: Path):
    first = tmp_path / 'BI330-001.pdf'; first.write_bytes(b'pdf-1')
    second = tmp_path / 'BI330-002.pdf'; second.write_bytes(b'pdf-2')
    monkeypatch.setattr(ls, 'row', lambda *args, **kwargs: None)
    monkeypatch.setattr(ls, '_parse_certificate_job', lambda pdf, contractor: (pdf, SimpleNamespace(raw={'file_name': pdf.name})))
    monkeypatch.setattr(ls, '_upsert_certificate', lambda cert: (_ for _ in ()).throw(RuntimeError('falha simulada')) if cert.raw['file_name'] == first.name else 2)
    recorded = []
    monkeypatch.setattr(ls, '_record_certificate_file', lambda *args, **kwargs: recorded.append(args[1].name))
    monkeypatch.setattr(ls, '_record_certificate_issue', lambda *args, **kwargs: None)
    logs = []
    monkeypatch.setattr(ls, 'log_sync', lambda *args, **kwargs: logs.append(args))
    parsed, skipped, errors, total = ls._sync_certificate_paths('ARENA', [first, second], True, 'certificados')
    assert (parsed, skipped, errors, total) == (1, 0, 1, 2)
    assert recorded == [second.name]
    assert any(first.name in str(entry) for entry in logs)


def test_auto_quality_queue_deduplicates_and_drains(monkeypatch, tmp_path: Path):
    pdf = tmp_path / 'BI330-999.pdf'
    pdf.write_bytes(b'pdf')
    monkeypatch.setattr(ls, '_AUTO_QUALITY_PENDING', {})

    assert ls._enqueue_auto_quality('arena', [pdf, pdf]) == 1
    assert ls._enqueue_auto_quality('ARENA', [pdf]) == 0
    assert ls._take_auto_quality_jobs() == {'ARENA': [pdf]}
    assert ls._take_auto_quality_jobs() == {}


def test_bv_monitor_ignores_archived_documents(monkeypatch, tmp_path: Path):
    archived_pdf = tmp_path / 'BI330-001.pdf'
    archived_pdf.write_bytes(b'pdf')
    stat = archived_pdf.stat()
    monkeypatch.setattr(ls, 'rows', lambda *a, **k: [{
        'file_path': str(archived_pdf.resolve()),
        'mtime_ns': stat.st_mtime_ns,
        'size': stat.st_size,
        'is_active': 0,
        'manual_override': 1,
    }])

    assert ls._bv_document_drop_changes('ARENA', tmp_path) == []


def test_bv_monitor_reopens_archived_document_when_file_changes(monkeypatch, tmp_path: Path):
    archived_pdf = tmp_path / 'BI330-001.pdf'
    archived_pdf.write_bytes(b'pdf-corrigido')
    monkeypatch.setattr(ls, 'rows', lambda *a, **k: [{
        'file_path': str(archived_pdf.resolve()),
        'mtime_ns': 1,
        'size': 3,
        'is_active': 0,
        'manual_override': 1,
    }])

    changes = ls._bv_document_drop_changes('ARENA', tmp_path)
    assert len(changes) == 1
    assert changes[0][0] == archived_pdf
    assert changes[0][1] == 'ALTERADO'


def test_monitor_once_processes_bv_kits_and_contractor_documents(monkeypatch, tmp_path: Path):
    cert_dir = tmp_path / 'certs'; cert_dir.mkdir()
    doc_dir = tmp_path / 'docs'; doc_dir.mkdir()
    kit_file = tmp_path / 'kits.xlsx'; kit_file.write_bytes(b'xlsx')
    cert = cert_dir / 'BI330-999.pdf'; cert.write_bytes(b'pdf')
    doc = doc_dir / '1.0.pdf'; doc.write_bytes(b'pdf')

    monkeypatch.setattr(ls, 'monitor_config', lambda: {'enabled': True, 'bv': True, 'contractor': True, 'auto_quality': True, 'seconds': 15})
    monkeypatch.setattr(ls, '_certificate_drop_changes', lambda c, f: [(cert, 'NOVO', '1:3')] if c == 'ARENA' else [])
    monkeypatch.setattr(ls, '_kit_document_drop_changes', lambda c, f: [(doc, 'NOVO', '2:3')] if c == 'ARENA' else [])
    monkeypatch.setattr(ls, '_source_changed', lambda c, k: (kit_file, 'ALTERADO', '3:4') if c == 'ARENA' and k == 'kits' else None)
    ids = iter(range(1, 20))
    monkeypatch.setattr(ls, '_begin_monitor_event', lambda *a, **k: next(ids))
    finished = []
    monkeypatch.setattr(ls, '_finish_monitor_event', lambda eid, status, message='': finished.append((eid, status)))
    calls = []
    monkeypatch.setattr(ls, 'sync_source', lambda c, k, force=False, recalc=True: calls.append((c, k)) or {'ok': True, 'records': 1, 'message': 'OK'})
    incremental = []
    monkeypatch.setattr(ls, '_sync_certificate_paths', lambda c, paths, force=False, source_kind='': incremental.append((c, list(paths))) or (1, 0, 0, 1))
    kit_incremental = []
    monkeypatch.setattr(
        ls, '_apply_kit_document_changes',
        lambda c, f, changes: kit_incremental.append((c, f, list(changes))) or {str(doc.resolve()): 'INDEXADO'},
    )
    monkeypatch.setattr(ls, 'recalculate_matches', lambda c: None)
    monkeypatch.setattr(ls, '_mark_source_monitor_ok', lambda c, k: None)
    monkeypatch.setattr(ls, '_reset_unreadable_bv_document_metadata', lambda c: 0)
    queued = []
    monkeypatch.setattr(ls, '_enqueue_auto_quality', lambda c, paths: queued.append((c, list(paths))) or len(paths))
    monkeypatch.setattr(
        ls, 'auto_fill_quality_for_certificate_paths',
        lambda *a, **k: (_ for _ in ()).throw(AssertionError('BD_QUALI não deve bloquear monitor_once')),
    )

    def fake_row(sql, params=()):
        if "kind='certificados'" in sql:
            return {'path': str(cert_dir), 'enabled': 1}
        if "kind='kit_documentos'" in sql:
            return {'path': str(doc_dir), 'enabled': 1}
        if 'FROM certificate_files' in sql:
            return {'status': 'CARREGADO', 'error': ''}
        if 'FROM kit_documents' in sql:
            return {'id': 7}
        return None
    monkeypatch.setattr(ls, 'row', fake_row)

    out = ls.monitor_once()
    assert incremental == [('ARENA', [cert])]
    assert ('ARENA', 'kits') in calls
    assert ('ARENA', 'kit_documentos') not in calls
    assert kit_incremental == [('ARENA', doc_dir, [(doc, 'NOVO', '2:3')])]
    assert out['detected'] == 3
    assert out['processed'] == 3
    assert out['errors'] == 0
    assert {x[1] for x in finished} >= {'CARREGADO', 'INDEXADO'}
    assert queued == [('ARENA', [cert])]


def test_v381_ui_exposes_auto_monitor_controls():
    root = Path(__file__).resolve().parents[1]
    html = (root / 'frontend' / 'index.html').read_text(encoding='utf-8')
    js = (root / 'frontend' / 'static' / 'app.js').read_text(encoding='utf-8')
    assert 'Monitor SharePoint / OneDrive' in html
    assert 'Novos PDFs BI330' in html
    assert 'd.KIT + árvore Entrega Contratada' in html
    assert '/api/admin/auto-monitor' in js
    assert 'runAutoMonitor' in js


def test_contractor_folder_browser_has_no_pdf_filter_or_100_file_limit():
    root = Path(__file__).resolve().parents[1]
    js = (root / 'frontend' / 'static' / 'app.js').read_text(encoding='utf-8')
    assert "extension:'pdf',limit:'100'" not in js
    assert "limit:'5000',top_folder:contractorSelectedFolder" in js
    assert "kit-document-folders?contractor='+encodeURIComponent(contractor)+'&extension=pdf'" not in js


def test_v381_backend_has_both_monitor_loops():
    root = Path(__file__).resolve().parents[1]
    app = (root / 'app.py').read_text(encoding='utf-8')
    sync = (root / 'qualimatch' / 'local_sync.py').read_text(encoding='utf-8')
    assert 'auto_monitor_loop' in app
    assert 'auto_quality_loop' in app
    assert "'certificados'" in sync
    assert "'kit_documentos'" in sync
    assert "'kits'" in sync
    assert '_wait_file_ready' in sync
