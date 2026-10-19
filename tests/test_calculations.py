from qualimatch.calculations import calculate_service

def test_exemplo_financeiro_validado():
    r=calculate_service(152,4,0.04,15.5,1.70,1500.57,214.61,2.54)
    assert round(r.area_m2,2)==608.00
    assert round(r.volume_m3,2)==24.32
    assert round(r.milled_m3km,2)==376.96
    assert round(r.total,2)==43704.26
