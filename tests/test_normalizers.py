from qualimatch.normalizers import station,norm_road

def test_station():
    assert station('306+625')==306625
    assert station(269005)==269005
    assert station(306.625)==306625

def test_road(): assert norm_road('BR 376')=='BR-376'
