from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import floor
import os
import re


VV_MIN = float(os.getenv("VV_MIN", "3.5"))
VV_MAX = float(os.getenv("VV_MAX", "7.5"))
AB_MIN = float(os.getenv("AB_MIN", "90"))


@dataclass(frozen=True)
class TechnicalResult:
    vv_status: str
    ab_status: str
    overall_status: str


def classify_vv(value: float | None) -> str:
    if value is None:
        return "SEM RESULTADO"
    return "APROVADO" if VV_MIN <= float(value) <= VV_MAX else "REPROVADO"


def classify_ab(value: float | None) -> str:
    if value is None:
        return "SEM RESULTADO"
    return "APROVADO" if float(value) >= AB_MIN else "REPROVADO"


def classify_certificate(vv: float | None, ab: float | None) -> TechnicalResult:
    vv_status = classify_vv(vv)
    ab_status = classify_ab(ab)
    statuses = {vv_status, ab_status}
    if "REPROVADO" in statuses:
        overall = "REPROVADO"
    elif statuses == {"APROVADO"}:
        overall = "APROVADO"
    else:
        overall = "SEM RESULTADO"
    return TechnicalResult(vv_status, ab_status, overall)


def measurement_cycle_number(day: date) -> int:
    start_month = day.replace(day=1) if day.day >= 11 else (day.replace(day=1) - timedelta(days=1)).replace(day=1)
    anchor_index = 2026 * 12 + 7
    month_index = start_month.year * 12 + start_month.month - 1
    return 14 + (month_index - anchor_index)


def measurement_cycle_bounds(number: int) -> tuple[date, date]:
    anchor_index = 2026 * 12 + 7
    index = anchor_index + (number - 14)
    year = floor(index / 12)
    month = index % 12 + 1
    start = date(year, month, 11)
    next_index = index + 1
    next_year = floor(next_index / 12)
    next_month = next_index % 12 + 1
    end = date(next_year, next_month, 10)
    return start, end


def parse_measurement(value: str | None) -> int | None:
    text = (value or "").strip().upper()
    if not text:
        return None
    match = re.fullmatch(r"M?(\d+)", text)
    return int(match.group(1)) if match else None
