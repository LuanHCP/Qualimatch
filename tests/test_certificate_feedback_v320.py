from datetime import date
import json

from qualimatch.pdf_reader import Sample, _parse_health
from qualimatch.queries import _cert_stats_loaded


def _sample() -> Sample:
    return Sample(
        phase='ROTINA', cp_number='1', application_date=date(2026, 1, 9),
        counterproof=False, direction='NORTE', lane='1', station=405900,
        position='EX', thickness_exec_cm=4.0, thickness_project_cm=4.0,
        ratio_ab_pct=100.0, gmb=2.5, voids_pct=4.0,
    )


def test_complete_read_is_carregado_and_bv_warning_is_separate():
    status, parse_warnings, validation = _parse_health(
        date(2026, 1, 10), ['2026-01-09'], 'BR-376', 405845, 406100,
        'TRACO TESTE', [_sample()], ['2026-01-09'], ['2026-01-12'],
    )
    assert status == 'CARREGADO'
    assert parse_warnings == []
    assert any('enviar para a BV' in w for w in validation)


def test_missing_structural_data_remains_partial():
    status, parse_warnings, validation = _parse_health(
        date(2026, 1, 10), ['2026-01-09'], 'BR-376', 405845, 406100,
        '', [_sample()], [], [],
    )
    assert status == 'PARCIAL'
    assert 'Traço aprovado não identificado' in parse_warnings
    assert validation == []


def test_legacy_ok_is_presented_as_carregado_and_old_date_warning_does_not_force_partial():
    sample = {
        'phase': 'ROTINA', 'cp_number': '1', 'application_date': '2026-01-09',
        'counterproof': 0, 'direction': 'NORTE', 'lane': '1', 'station': 405900,
        'position': 'EX', 'thickness_exec_cm': 4.0, 'thickness_project_cm': 4.0,
        'ratio_ab_pct': 100.0, 'gmb': 2.5, 'voids_pct': 4.0,
    }
    cert = {
        'id': 1, 'contractor': 'ARENA', 'number': 'BI330-0001',
        'service_date': '2026-01-09', 'extraction_date': '2026-01-10',
        'road': 'BR-376', 'kmi': 405845, 'kmf': 406100,
        'trace_approved': 'TRACO TESTE', 'routine_result': 'APROVADO',
        'counterproof_result': '', 'has_counterproof': 0,
        'raw_json': json.dumps({
            'parse_status': 'OK',
            'parse_warnings': ["Data Ext. dos CP's posterior ao recebimento no laboratório; conferir PDF"],
            'receipt_dates': ['2026-01-09'],
            'service_dates': ['2026-01-09'],
        }),
    }
    out = _cert_stats_loaded(cert, [sample], [], 2, True)
    assert out['parse_status'] == 'CARREGADO'
    assert out['parse_warnings'] == []
    assert any('enviar para a BV' in w for w in out['business_warnings'])


def test_receipt_after_extraction_does_not_trigger_bv_warning():
    status, parse_warnings, validation = _parse_health(
        date(2026, 1, 10), ['2026-01-09'], 'BR-376', 405845, 406100,
        'TRACO TESTE', [_sample()], ['2026-01-11'], ['2026-01-12'],
    )
    assert status == 'CARREGADO'
    assert parse_warnings == []
    assert not any('enviar para a BV' in w for w in validation)
