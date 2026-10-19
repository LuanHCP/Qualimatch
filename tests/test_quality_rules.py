from qualimatch.quality_reader import _correct_cap


def test_positive_cap_is_invalid_when_quantity_is_zero():
    value, source = _correct_cap(25715.33, 0.0, 0.052)
    assert value == 0.0
    assert 'QUANT PROJETO' in source


def test_normal_cap_is_preserved_when_plausible():
    value, source = _correct_cap(5.2, 100.0, 0.052)
    assert value == 5.2
    assert 'CAP PROJETO' in source
