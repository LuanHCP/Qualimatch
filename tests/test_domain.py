from datetime import date

from domain import classify_ab, classify_certificate, classify_vv, measurement_cycle_bounds, measurement_cycle_number


def test_vv_limits():
    assert classify_vv(5.0) == "APROVADO"
    assert classify_vv(8.0) == "REPROVADO"
    assert classify_vv(None) == "SEM RESULTADO"


def test_ab_limits():
    assert classify_ab(92.0) == "APROVADO"
    assert classify_ab(88.0) == "REPROVADO"


def test_overall_result():
    assert classify_certificate(5.0, 95.0).overall_status == "APROVADO"
    assert classify_certificate(8.0, 95.0).overall_status == "REPROVADO"


def test_measurement_cycle_11_to_10():
    start, end = measurement_cycle_bounds(14)
    assert start == date(2026, 8, 11)
    assert end == date(2026, 9, 10)
    assert measurement_cycle_number(date(2026, 8, 20)) == 14
    assert measurement_cycle_number(date(2026, 9, 5)) == 14
