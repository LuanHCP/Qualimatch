from qualimatch.pdf_reader import _parse_sample_line

def test_parse_cp_line():
    s=_parse_sample_line('5 02/09/2025 SIM SUL 1 306+922 EX 4,45 4,00 111,3% 101,10 2,634 787,60 792,80 478,30 1,65 6.1 314,50 2,497 5,2%','CONTRA_PROVA')
    assert s is not None
    assert s.cp_number=='5' and s.counterproof is True
    assert s.station==306922 and s.voids_pct==5.2 and s.ratio_ab_pct==111.3

def test_parse_cp_line_with_execution_suffix_e3():
    s = _parse_sample_line(
        '736 09/10/2025-E3 NÃO NORTE 2 299+175 BD 4,10 4,00 102,5% 101,10 2,671 856,60 863,20 519,00 1,92 6.1 344,20 2,481 7,1%'
    )
    assert s is not None
    assert s.cp_number == '736'
    assert s.application_date.isoformat() == '2025-10-09'
    assert s.direction == 'NORTE'
    assert s.lane == '2'
    assert s.station == 299175
    assert s.rice_gmm == 2.671
    assert s.gmb == 2.481
    assert s.voids_pct == 7.1


def test_parse_cp_line_with_execution_suffix_e1():
    s = _parse_sample_line(
        '752 09/10/2025-E1 NÃO SUL 2 242+382 BE 4,55 4,00 113,8% 101,10 2,671 979,20 981,90 596,40 0,70 6.1 385,50 2,533 5,2%'
    )
    assert s is not None
    assert s.cp_number == '752'
    assert s.application_date.isoformat() == '2025-10-09'
    assert s.direction == 'SUL'
    assert s.station == 242382
    assert s.rice_gmm == 2.671
    assert s.gmb == 2.533
    assert s.voids_pct == 5.2
