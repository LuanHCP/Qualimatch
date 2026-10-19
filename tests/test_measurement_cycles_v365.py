from qualimatch.queries import measurement_cycle

def test_measurement_14_boundaries():
    assert measurement_cycle("2026-08-11")["measurement"] == "M14"
    assert measurement_cycle("2026-09-10")["measurement"] == "M14"

def test_measurement_13_boundaries():
    c1 = measurement_cycle("2026-07-11")
    c2 = measurement_cycle("2026-08-10")
    assert c1["measurement"] == "M13"
    assert c2["measurement"] == "M13"
    assert c1["measurement_start"] == "2026-07-11"
    assert c1["measurement_end"] == "2026-08-10"

def test_measurement_1_boundaries():
    assert measurement_cycle("2025-07-11")["measurement"] == "M1"
    assert measurement_cycle("2025-08-10")["measurement"] == "M1"

def test_future_measurement_rolls_forward():
    assert measurement_cycle("2026-09-11")["measurement"] == "M15"
