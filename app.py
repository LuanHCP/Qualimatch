from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from demo_data import CERTIFICATES, MEASUREMENTS
from domain import classify_certificate, measurement_cycle_bounds, parse_measurement


BASE_DIR = Path(__file__).resolve().parent
FRONTEND = BASE_DIR / "frontend"

app = FastAPI(title="QualiMatch Portfolio Edition", version="1.0.0")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


def _contractor(value: str | None) -> str:
    text = (value or "ALL").strip().upper()
    return text if text in {"ALL", "CONTRATADA A", "CONTRATADA B"} else "ALL"


def _cycle_filter(items: list[dict[str, Any]], measurement: str | None) -> list[dict[str, Any]]:
    number = parse_measurement(measurement)
    if number is None:
        return items
    start, end = measurement_cycle_bounds(number)
    return [
        x for x in items
        if start <= date.fromisoformat(x["date"] if "date" in x else x["service_date"]) <= end
    ]


def _certificate_rows(contractor: str = "ALL", measurement: str | None = None) -> list[dict[str, Any]]:
    items = [dict(x) for x in CERTIFICATES]
    if contractor != "ALL":
        items = [x for x in items if x["contractor"] == contractor]
    items = _cycle_filter(items, measurement)
    for item in items:
        result = classify_certificate(item.get("vv"), item.get("ab"))
        item.update({
            "vv_status": result.vv_status,
            "ab_status": result.ab_status,
            "status": result.overall_status,
        })
    return items


def _measurement_rows(contractor: str = "ALL", measurement: str | None = None) -> list[dict[str, Any]]:
    items = [dict(x) for x in MEASUREMENTS]
    if contractor != "ALL":
        items = [x for x in items if x["contractor"] == contractor]
    return _cycle_filter(items, measurement)


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "edition": "portfolio", "version": "1.0.0"}


@app.get("/api/dashboard")
def dashboard(contractor: str = "ALL", measurement: str = ""):
    contractor = _contractor(contractor)
    certs = _certificate_rows(contractor, measurement)
    measurements = _measurement_rows(contractor, measurement)
    counts = {"APROVADO": 0, "REPROVADO": 0, "SEM RESULTADO": 0}
    for cert in certs:
        counts[cert["status"]] += 1
    covered_dates = {x["service_date"] for x in certs if x["status"] != "SEM RESULTADO"}
    pending = [x for x in measurements if x["date"] not in covered_dates]
    return {
        "certificates": len(certs),
        "approved": counts["APROVADO"],
        "reproved": counts["REPROVADO"],
        "without_result": counts["SEM RESULTADO"],
        "measurements": len(measurements),
        "pending_days": len({x["date"] for x in pending}),
        "quantity_t": round(sum(float(x["quantity_t"]) for x in measurements), 2),
        "recent": sorted(certs, key=lambda x: x["service_date"], reverse=True)[:5],
    }


@app.get("/api/certificates")
def certificates(
    contractor: str = "ALL",
    measurement: str = "",
    search: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
):
    contractor = _contractor(contractor)
    items = _certificate_rows(contractor, measurement)
    q = search.strip().upper()
    if q:
        items = [
            x for x in items
            if q in " ".join(str(x.get(k, "")) for k in ("number", "road", "trace", "contractor")).upper()
        ]
    items.sort(key=lambda x: (x["service_date"], x["number"]), reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "page": page, "page_size": page_size, "total": total}


@app.get("/api/measurements")
def measurements(
    contractor: str = "ALL",
    measurement: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(40, ge=1, le=100),
):
    contractor = _contractor(contractor)
    items = _measurement_rows(contractor, measurement)
    items.sort(key=lambda x: x["date"], reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    return {"items": items[start:start + page_size], "page": page, "page_size": page_size, "total": total}


@app.get("/api/pending")
def pending(contractor: str = "ALL", measurement: str = ""):
    contractor = _contractor(contractor)
    certs = _certificate_rows(contractor, measurement)
    measurements = _measurement_rows(contractor, measurement)
    covered_dates = {x["service_date"] for x in certs if x["status"] != "SEM RESULTADO"}
    items = [x for x in measurements if x["date"] not in covered_dates]
    return {"items": items, "total": len(items)}
