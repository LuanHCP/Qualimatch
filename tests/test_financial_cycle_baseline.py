from __future__ import annotations

from datetime import date

import qualimatch.financial_cycle_baseline as fcb


def _snap(day: str, total=100.0, approved=70.0, pending=20.0, reproved=10.0, sid=1):
    import json
    return {
        "id": sid,
        "synced_at": day + "T08:00:00",
        "total_service": total,
        "summary_json": json.dumps({
            "approved_value": approved,
            "pending_value": pending,
            "reproved_value": reproved,
        }),
    }


def test_baseline_prefere_primeiro_snapshot_do_dia_11(monkeypatch):
    calls = []
    start = _snap("2026-08-11", sid=2)

    def fake_row(sql, params):
        calls.append(params)
        if "substr(synced_at,1,10)=?" in sql and params[1] == "2026-08-11":
            return start
        return None

    monkeypatch.setattr(fcb, "row", fake_row)
    found = fcb._baseline_snapshot("ARENA", "2026-08-11", "2026-09-10")
    assert found["id"] == 2
    assert calls[0] == ("ARENA", "2026-08-11")


def test_baseline_usa_fechamento_do_dia_10_quando_nao_ha_snapshot_no_dia_11(monkeypatch):
    previous = _snap("2026-08-10", sid=3)

    def fake_row(sql, params):
        if params[1] == "2026-08-11":
            return None
        if params[1] == "2026-08-10":
            return previous
        return None

    monkeypatch.setattr(fcb, "row", fake_row)
    found = fcb._baseline_snapshot("PAVIDEZ", "2026-08-11", "2026-09-10")
    assert found["id"] == 3


def test_baseline_usa_primeiro_snapshot_do_ciclo_como_ultimo_fallback(monkeypatch):
    after = _snap("2026-08-13", sid=4)
    calls = 0

    def fake_row(sql, params):
        nonlocal calls
        calls += 1
        if calls < 3:
            return None
        return after

    monkeypatch.setattr(fcb, "row", fake_row)
    found = fcb._baseline_snapshot("ARENA", "2026-08-11", "2026-09-10")
    assert found["id"] == 4


def test_trend_consolidado_compara_atual_contra_base_travada(monkeypatch):
    baselines = {
        "ARENA": _snap("2026-08-11", total=100, approved=70, pending=20, reproved=10, sid=10),
        "PAVIDEZ": _snap("2026-08-11", total=60, approved=50, pending=8, reproved=2, sid=11),
    }
    monkeypatch.setattr(fcb, "_baseline_snapshot", lambda contractor, *_: baselines[contractor])

    result = {
        "totals": {"total_service": 175.0},
        "financial": {"approved": 128.0, "pending": 32.0, "reproved": 15.0},
    }
    cycle = {
        "measurement": "M14",
        "measurement_start": "2026-08-11",
        "measurement_end": "2026-09-10",
    }

    def trend(current, previous, **kwargs):
        return {"current": current, "previous": previous, "delta": current - previous, **kwargs}

    out = fcb._cycle_financial_trends(result, ["ARENA", "PAVIDEZ"], cycle, date(2026, 8, 25), trend)
    assert out["mode"] == "measurement_cycle_baseline"
    assert out["measurement"] == "M14"
    assert out["total_service"]["previous"] == 160.0
    assert out["total_service"]["delta"] == 15.0
    assert out["approved"]["delta"] == 8.0
    assert out["pending"]["delta"] == 4.0
    assert out["reproved"]["delta"] == 3.0
    assert out["total_service"]["comparison_date"] == "2026-08-11"
