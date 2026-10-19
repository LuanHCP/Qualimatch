import run


def test_existing_qualimatch_is_reused(monkeypatch):
    monkeypatch.setattr(run, "port_is_free", lambda port: port != 8001)
    monkeypatch.setattr(run, "is_qualimatch", lambda port: port == 8001)
    assert run.find_existing_qualimatch(8000, attempts=1) == 8001


def test_unrelated_busy_port_is_not_reused(monkeypatch):
    monkeypatch.setattr(run, "port_is_free", lambda port: port != 8000)
    monkeypatch.setattr(run, "is_qualimatch", lambda port: False)
    assert run.find_existing_qualimatch(8000, attempts=1) is None
    assert run.first_free_port(8000) == 8001
