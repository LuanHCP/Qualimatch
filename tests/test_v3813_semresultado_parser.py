from qualimatch.pdf_reader import _parse_sample_line, _samples_from_text


def test_v3813_accepts_lane_blank_using_station_as_anchor():
    sample = _parse_sample_line(
        '3551 10/04/2026 NÃO SUL 498+020 BD 4,10 4,00 102,5% 10,16 2,671 '
        '856,60 863,20 519,00 1,92 6.1 344,20 2,481 7,1%'
    )
    assert sample is not None
    assert sample.cp_number == '3551'
    assert sample.direction == 'SUL'
    assert sample.lane == ''
    assert sample.station == 498020
    assert sample.position == 'BD'
    assert sample.rice_gmm == 2.671
    assert sample.gmb == 2.481
    assert sample.voids_pct == 7.1


def test_v3813_accepts_stage_suffix_without_hyphen():
    sample = _parse_sample_line(
        '736 09/10/2025 E3 NÃO NORTE 2 299+175 BD 4,10 4,00 102,5% 101,10 2,671 '
        '856,60 863,20 519,00 1,92 6.1 344,20 2,481 7,1%'
    )
    assert sample is not None
    assert sample.application_date.isoformat() == '2025-10-09'
    assert sample.cp_number == '736'


def test_v3813_joins_wrapped_visual_cp_row():
    text = '''
RESULTADOS DOS ENSAIOS
4036 15/06/2026 Não Sul Faixa adicional 34 + 130 BD 4,32 4,00 108,0% 10,16 2,635 667,3
668,6 406,2 0,50 6.1 262,40 2,536 3,8%
Limites: Xmín 95,0%
'''
    samples = _samples_from_text(text)
    assert len(samples) == 1
    sample = samples[0]
    assert sample.cp_number == '4036'
    assert sample.lane == 'FAIXA ADICIONAL'
    assert sample.station == 34130
    assert sample.rice_gmm == 2.635
    assert sample.gmb == 2.536
    assert sample.voids_pct == 3.8


def test_v3813_new_layout_two_vv_percentages_keeps_primary_values():
    sample = _parse_sample_line(
        '4279 28/07/2026 Não Norte Faixa 1 182 + 90 BD 5,50 5,00 110,0% 10,160 2,679 '
        '1057,9 1061,6 642,2 0,88 6.1 419,40 2,515 6,1% 6,1%'
    )
    assert sample is not None
    assert sample.rice_gmm == 2.679
    assert sample.gmb == 2.515
    assert sample.voids_pct == 6.1


def test_v3813_aggregate_passivos_pdf_is_not_treated_as_single_bi330():
    from pathlib import Path
    from qualimatch.local_sync import _is_bi330_pdf

    assert not _is_bi330_pdf(Path('BI330_Passivos Manutenção_PAVIDEZ-M3.pdf'))
    assert _is_bi330_pdf(Path('BI330-0446-PAVIDEZ_ICA_PR323_TR1537-15.06.26.pdf'))


def test_v3813_ui_exposes_admin_batch_revalidation():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    html = (root / 'frontend' / 'index.html').read_text(encoding='utf-8')
    js = (root / 'frontend' / 'static' / 'app.js').read_text(encoding='utf-8')
    app = (root / 'app.py').read_text(encoding='utf-8')
    assert 'id="c-reprocess-no-result"' in html
    assert 'reprocessNoResultCertificates' in js
    assert '/api/certificates/reprocess-no-result' in app
