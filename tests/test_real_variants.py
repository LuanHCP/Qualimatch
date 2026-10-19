from qualimatch.normalizers import norm_road
from qualimatch.pdf_reader import _parse_sample_line


def test_sequence_before_cp_is_not_the_cp_number():
    s = _parse_sample_line(
        '1 179 16/08/2025 NÃO SUL 2 309+620 BE 4,39 4,00 109,8% 101,10 2,607 777,60 781,70 472,70 1,33 6.1 309,00 2,509 3,8%'
    )
    assert s is not None
    assert s.cp_number == '179'
    assert s.station == 309620
    assert s.voids_pct == 3.8


def test_station_with_spaces_inside_pdf_row():
    s = _parse_sample_line(
        '1279 13/08/2025 NÃO NORTE 1 404 + 50 EX 4,43 4,00 110,8% 101,10 2,715 977,30 980,30 598,60 0,79 6.1 381,70 2,553 6,0%'
    )
    assert s is not None
    assert s.cp_number == '1279'
    assert s.station == 404050


def test_pr_road_normalization():
    assert norm_road('PR 090 - PR') == 'PR-090'


def test_lane_written_as_faixa_2_is_parsed():
    s = _parse_sample_line(
        '43 25/08/2025 Não Norte Faixa 2 311 + 326 EX 4,16 4,00 104,0% 10,16 2,675 825,1 828,3 500 0,97 6.1 328,30 2,506 6,3%'
    )
    assert s is not None
    assert s.lane == '2'
    assert s.application_date.isoformat() == '2025-08-25'


def test_lane_faixa_adicional_old_bv_layout_is_parsed():
    s = _parse_sample_line(
        '4036 15/06/2026 Não Sul Faixa adicional 34 + 130 BD 4,32 4,00 108,0% 10,16 2,635 667,3 668,6 406,2 0,50 6.1 262,40 2,536 3,8%'
    )
    assert s is not None
    assert s.cp_number == '4036'
    assert s.lane == 'FAIXA ADICIONAL'
    assert s.station == 34130
    assert s.rice_gmm == 2.635
    assert s.gmb == 2.536
    assert s.voids_pct == 3.8


def test_new_bv_layout_with_voids_film_keeps_main_gmb_and_vv():
    s = _parse_sample_line(
        '4279 28/07/2026 Não Norte Faixa 1 182 + 90 BD 5,50 5,00 110,0% 10,160 2,679 1057,9 1061,6 642,2 0,88 6.1 419,40 2,515 6,1% 6,1%'
    )
    assert s is not None
    assert s.cp_number == '4279'
    assert s.lane == '1'
    assert s.station == 182090
    assert s.rice_gmm == 2.679
    assert s.gmb == 2.515
    assert s.voids_pct == 6.1
