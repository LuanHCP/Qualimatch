from __future__ import annotations

from datetime import date, datetime, timedelta
import math
import re
import unicodedata
from typing import Any


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).strip()


def norm_text(value: Any) -> str:
    s = text(value)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.upper().replace("_", " ")
    s = re.sub(r"[^A-Z0-9%$()/+.-]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_header(value: Any) -> str:
    s = norm_text(value)
    s = s.replace("³", "3").replace("²", "2")
    return s


def number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        try:
            if math.isnan(float(value)):
                return None
        except Exception:
            pass
        return float(value)
    s = text(value).replace("R$", "").replace("%", "").replace("\u00a0", " ").strip()
    if not s:
        return None
    s = s.replace(" ", "")
    # pt-BR: 1.234,56 -> 1234.56; 1234,56 -> 1234.56
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)) and 20000 <= float(value) <= 90000:
        return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
    s = text(value)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            pass
    return None


def station(value: Any) -> int | None:
    """Normaliza estaca/km para metros inteiros no padrão 306+625 -> 306625."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        if math.isnan(v):
            return None
        # Planilhas de medição normalmente usam 306625. Caso venha 306.625, assume km decimal.
        if abs(v) < 10000 and not float(v).is_integer():
            return int(round(v * 1000))
        return int(round(v))
    s = text(value).upper().replace("KM", "").strip()
    m = re.search(r"(\d{1,4})\s*\+\s*(\d{1,3})", s)
    if m:
        return int(m.group(1)) * 1000 + int(m.group(2))
    s2 = re.sub(r"[^0-9.,-]", "", s)
    n = number(s2)
    if n is None:
        return None
    if abs(n) < 10000 and not float(n).is_integer():
        return int(round(n * 1000))
    return int(round(n))


def format_station(value: int | None) -> str:
    if value is None:
        return ""
    km, m = divmod(int(value), 1000)
    return f"{km}+{m:03d}"


def norm_road(value: Any) -> str:
    s = norm_text(value).replace(" ", "")
    m = re.search(r"(BR|PR)[-]?(\d+)", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return s


def norm_direction(value: Any) -> str:
    s = norm_text(value)
    aliases = {"S": "SUL", "N": "NORTE", "L": "LESTE", "O": "OESTE"}
    return aliases.get(s, s)


def norm_lane(value: Any) -> str:
    s = norm_text(value)
    if not s:
        return ""
    # Mantém identificação numérica de faixa quando possível.
    m = re.search(r"\b(\d+)\b", s)
    if m:
        return m.group(1)
    return s
