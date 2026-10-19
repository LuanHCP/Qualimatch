from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from .database import row


TREND_KEYS = ("total_service", "approved", "pending", "reproved")


def _summary(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not snapshot:
        return {}
    try:
        return json.loads(snapshot.get("summary_json") or "{}")
    except Exception:
        return {}


def _snapshot_values(snapshot: dict[str, Any] | None) -> dict[str, float] | None:
    """Extrai os quatro valores financeiros usados nos cards do Dashboard."""
    if not snapshot:
        return None
    summary = _summary(snapshot)
    required = ("approved_value", "pending_value", "reproved_value")
    if any(summary.get(key) is None for key in required):
        return None
    try:
        return {
            "total_service": float(snapshot.get("total_service") or 0.0),
            "approved": float(summary.get("approved_value") or 0.0),
            "pending": float(summary.get("pending_value") or 0.0),
            "reproved": float(summary.get("reproved_value") or 0.0),
        }
    except (TypeError, ValueError):
        return None


def _baseline_snapshot(contractor: str, cycle_start: str, cycle_end: str) -> dict[str, Any] | None:
    """Escolhe uma referência estável para o início do ciclo 11→10.

    Ordem de preferência:
    1. primeira sincronização feita no próprio dia 11;
    2. última sincronização do dia 10 (fechamento imediatamente anterior);
    3. primeira sincronização disponível depois do dia 11 dentro do mesmo ciclo.

    Depois que uma dessas referências existe, novas sincronizações durante a
    medição não mudam o ponto de partida.
    """
    on_start = row(
        "SELECT * FROM quality_snapshots WHERE contractor=? AND substr(synced_at,1,10)=? "
        "ORDER BY synced_at ASC,id ASC LIMIT 1",
        (contractor, cycle_start),
    )
    if on_start:
        return dict(on_start)

    try:
        previous_day = (date.fromisoformat(cycle_start) - timedelta(days=1)).isoformat()
    except ValueError:
        previous_day = ""
    if previous_day:
        previous = row(
            "SELECT * FROM quality_snapshots WHERE contractor=? AND substr(synced_at,1,10)=? "
            "ORDER BY synced_at DESC,id DESC LIMIT 1",
            (contractor, previous_day),
        )
        if previous:
            return dict(previous)

    first_after = row(
        "SELECT * FROM quality_snapshots WHERE contractor=? "
        "AND substr(synced_at,1,10)>? AND substr(synced_at,1,10)<=? "
        "ORDER BY synced_at ASC,id ASC LIMIT 1",
        (contractor, cycle_start, cycle_end),
    )
    return dict(first_after) if first_after else None


def _cycle_financial_trends(
    result: dict[str, Any],
    contractors: list[str],
    cycle: dict[str, Any],
    today: date,
    trend_value,
) -> dict[str, Any]:
    baseline = {key: 0.0 for key in TREND_KEYS}
    snapshot_dates: list[str] = []

    for contractor in contractors:
        snap = _baseline_snapshot(contractor, cycle["measurement_start"], cycle["measurement_end"])
        values = _snapshot_values(snap)
        if not values:
            # Sem uma referência histórica confiável, é melhor não exibir uma
            # seta do que comparar contra zero ou contra um valor arbitrário.
            return {}
        for key in TREND_KEYS:
            baseline[key] += values[key]
        snapshot_dates.append(str(snap.get("synced_at") or "")[:10])

    current = {
        "total_service": float((result.get("totals") or {}).get("total_service") or 0.0),
        "approved": float((result.get("financial") or {}).get("approved") or 0.0),
        "pending": float((result.get("financial") or {}).get("pending") or 0.0),
        "reproved": float((result.get("financial") or {}).get("reproved") or 0.0),
    }

    out: dict[str, Any] = {
        "mode": "measurement_cycle_baseline",
        "measurement": cycle.get("measurement"),
        "measurement_start": cycle.get("measurement_start"),
        "measurement_end": cycle.get("measurement_end"),
        "latest_date": today.isoformat(),
        "comparison_date": cycle.get("measurement_start"),
        "baseline_snapshot_dates": snapshot_dates,
    }
    for key in TREND_KEYS:
        trend = trend_value(
            current[key], baseline[key], mode="measurement_cycle_baseline",
            latest_date=today.isoformat(), comparison_date=cycle.get("measurement_start"),
        )
        trend["measurement"] = cycle.get("measurement")
        trend["measurement_start"] = cycle.get("measurement_start")
        trend["measurement_end"] = cycle.get("measurement_end")
        trend["baseline_snapshot_dates"] = snapshot_dates
        out[key] = trend
    return out


def install_financial_cycle_baseline_policy() -> None:
    """Troca apenas a referência das setas financeiras do consolidado.

    O valor grande de cada card continua vindo do mesmo resumo oficial. Somente
    a comparação deixa de ser mês-calendário contra mês-calendário e passa a ser
    "valor atual menos valor travado no início da medição (dia 11)".
    """
    from . import queries

    original = queries.dashboard
    if getattr(original, "_qualimatch_financial_cycle_baseline", False):
        return

    def wrapped(contractor="ALL", start=None, end=None, status="ALL", measurement="", selected_numbers=None):
        result = original(contractor, start, end, status, measurement, selected_numbers)

        # Recortes manuais e filtro Mxx já possuem outra semântica. A nova base
        # fixa é aplicada somente ao Resumo oficial consolidado sem filtros.
        if start or end or str(status or "ALL").upper() != "ALL" or str(measurement or "").strip() or selected_numbers:
            return result

        today = date.today()
        cycle = queries.measurement_cycle(today)
        if not cycle:
            return result
        contractors = ["ARENA", "PAVIDEZ"] if str(contractor or "ALL").upper() == "ALL" else [str(contractor).upper()]
        result["financial_trends"] = _cycle_financial_trends(
            result, contractors, cycle, today, queries._trend_value
        )
        result["financial_trend_cycle"] = {
            "measurement": cycle.get("measurement"),
            "start": cycle.get("measurement_start"),
            "end": cycle.get("measurement_end"),
            "baseline_rule": "Primeiro snapshot do dia 11; fallback fechamento do dia 10; depois primeiro snapshot do ciclo.",
        }
        return result

    wrapped._qualimatch_financial_cycle_baseline = True  # type: ignore[attr-defined]
    wrapped._qualimatch_original_dashboard = original  # type: ignore[attr-defined]
    queries.dashboard = wrapped