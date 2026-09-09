from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import CONTRACTORS, DB_PATH, init_db, row, rows
from domain import measurement_cycle_bounds, measurement_cycle_number, parse_measurement

BASE_DIR = Path(__file__).resolve().parent
FRONTEND = BASE_DIR / "frontend"
init_db()

app = FastAPI(title="QualiMatch Portfolio Edition", version="2.0.0")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


def _contractor(value: str | None) -> str:
    text = (value or "ALL").strip().upper()
    valid = {"ALL", *CONTRACTORS}
    if text not in valid:
        raise HTTPException(400, "Contratada inválida")
    return text


def _status(value: str | None) -> str:
    text = (value or "ALL").strip().upper().replace(" ", "_")
    aliases = {"SEM_RESULTADO": "SEM RESULTADO"}
    text = aliases.get(text, text)
    valid = {"ALL", "APROVADO", "REPROVADO", "SEM RESULTADO"}
    if text not in valid:
        raise HTTPException(400, "Status inválido")
    return text


def _cycle_range(measurement: str | None) -> tuple[str | None, str | None, str]:
    n = parse_measurement(measurement)
    if n is None:
        return None, None, ""
    start, end = measurement_cycle_bounds(n)
    return start.isoformat(), end.isoformat(), f"M{n}"


def _where_common(contractor: str, start: str | None, end: str | None, date_column: str) -> tuple[list[str], list[Any]]:
    where: list[str] = []
    params: list[Any] = []
    if contractor != "ALL":
        where.append("contractor=?")
        params.append(contractor)
    if start:
        where.append(f"{date_column}>=?")
        params.append(start)
    if end:
        where.append(f"{date_column}<=?")
        params.append(end)
    return where, params


def _certificate_filters(
    contractor: str = "ALL", measurement: str = "", vv_status: str = "ALL",
    thickness_status: str = "ALL", road: str = "", number: str = "", segment: str = "",
    selected_numbers: list[str] | None = None,
) -> tuple[str, tuple[Any, ...]]:
    start, end, _ = _cycle_range(measurement)
    where, params = _where_common(contractor, start, end, "service_date")
    if vv_status != "ALL":
        where.append("status_vv=?")
        params.append(vv_status)
    if thickness_status != "ALL":
        where.append("status_thickness=?")
        params.append(thickness_status)
    if road:
        where.append("road=?")
        params.append(road)
    if number:
        where.append("number=?")
        params.append(number)
    if selected_numbers:
        placeholders = ",".join("?" for _ in selected_numbers)
        where.append(f"number IN ({placeholders})")
        params.extend(selected_numbers)
    if segment:
        q = "".join(ch for ch in segment if ch.isdigit())
        if q:
            value = float(q)
            where.append("kmi<=? AND kmf>=?")
            params += [value, value]
    sql = " WHERE " + " AND ".join(where) if where else ""
    return sql, tuple(params)


def _financial_breakdown(items: list[dict[str, Any]]) -> dict[str, float]:
    out = {"approved": 0.0, "pending": 0.0, "reproved": 0.0}
    for x in items:
        value = float(x.get("total_service") or 0)
        status = str(x.get("status_final") or "").upper()
        if status.startswith("APROVADO"):
            out["approved"] += value
        elif "REPROV" in status:
            out["reproved"] += value
        else:
            out["pending"] += value
    return out


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "edition": "portfolio", "version": "2.0.0", "database": str(DB_PATH.name)}


@app.get("/api/measurement-cycles/options")
def measurement_options(contractor: str = "ALL"):
    contractor = _contractor(contractor)
    where = "" if contractor == "ALL" else " WHERE contractor=?"
    params = () if contractor == "ALL" else (contractor,)
    data = rows(f"SELECT MIN(date) min_date, MAX(date) max_date FROM measurements{where}", params)
    if not data or not data[0].get("min_date"):
        return []
    first = measurement_cycle_number(date.fromisoformat(data[0]["min_date"]))
    last = measurement_cycle_number(date.fromisoformat(data[0]["max_date"]))
    out = []
    for n in range(last, first - 1, -1):
        start, end = measurement_cycle_bounds(n)
        out.append({"measurement": f"M{n}", "measurement_start": start.isoformat(), "measurement_end": end.isoformat()})
    return out


@app.get("/api/certificates-filter-options")
def certificate_filter_options(contractor: str = "ALL"):
    contractor = _contractor(contractor)
    where = "" if contractor == "ALL" else " WHERE contractor=?"
    params = () if contractor == "ALL" else (contractor,)
    roads_found = rows(f"SELECT DISTINCT road FROM certificates{where} ORDER BY road", params)
    numbers_found = rows(f"SELECT DISTINCT number FROM certificates{where} ORDER BY number", params)
    return {
        "roads": [x["road"] for x in roads_found],
        "numbers": [x["number"] for x in numbers_found],
        "measurements": measurement_options(contractor),
    }


@app.get("/api/dashboard")
def dashboard(
    contractor: str = "ALL", status: str = "ALL", measurement: str = "",
    start: str | None = None, end: str | None = None, certificates: str = "",
):
    contractor = _contractor(contractor)
    status = _status(status)
    cycle_start, cycle_end, cycle_name = _cycle_range(measurement)
    if measurement:
        start, end = cycle_start, cycle_end
    selected = [x.strip() for x in certificates.split(",") if x.strip()]

    cert_sql, cert_params = _certificate_filters(contractor, measurement, selected_numbers=selected)
    certs = rows(f"SELECT * FROM certificates{cert_sql} ORDER BY extraction_date DESC, number DESC", cert_params)
    if not measurement and (start or end):
        certs = [x for x in certs if (not start or x["service_date"] >= start) and (not end or x["service_date"] <= end)]
    if status != "ALL":
        certs = [x for x in certs if x["overall_status"] == status]

    m_where, m_params = _where_common(contractor, start, end, "date")
    if selected:
        selected_dates = sorted({x["service_date"] for x in certs})
        if selected_dates:
            placeholders = ",".join("?" for _ in selected_dates)
            m_where.append(f"date IN ({placeholders})")
            m_params.extend(selected_dates)
        else:
            m_where.append("1=0")
    mw = " WHERE " + " AND ".join(m_where) if m_where else ""
    measurements = rows(f"SELECT * FROM measurements{mw} ORDER BY date DESC", tuple(m_params))
    if status != "ALL":
        measurements = [x for x in measurements if ("SEM RESULTADO" if x["status_final"] == "PENDENTE" else x["status_final"]) == status]

    totals = {
        "total_service": sum(float(x.get("total_service") or 0) for x in measurements),
        "extension_m": sum(float(x.get("extension_m") or 0) for x in measurements),
        "quantity_t": sum(float(x.get("quantity_t") or 0) for x in measurements),
        "cap_project_t": sum(float(x.get("cap_project_t") or 0) for x in measurements),
    }
    fin = _financial_breakdown(measurements)
    approved = sum(1 for x in certs if x["overall_status"] == "APROVADO")
    reproved = sum(1 for x in certs if x["overall_status"] == "REPROVADO")
    adjustments = len(certs) - approved - reproved
    covered = {(x["contractor"], x["service_date"]) for x in certs if x["overall_status"] != "SEM RESULTADO"}
    pending_days = len({(x["contractor"], x["date"]) for x in measurements if (x["contractor"], x["date"]) not in covered})
    statuses: dict[str, int] = {}
    for item in measurements:
        st = item["status_final"] or "SEM STATUS"
        statuses[st] = statuses.get(st, 0) + 1
    period = None
    if cycle_name:
        period = {"measurement": cycle_name, "measurement_start": start, "measurement_end": end}
    return {
        "totals": totals,
        "financial": fin,
        "financial_trends": {},
        "pending_days": pending_days,
        "statuses": [{"status": k, "count": v} for k, v in sorted(statuses.items())],
        "measurement_period": period,
        "certificate_summary": {
            "total": len(certs), "approved": approved, "reproved": reproved, "adjustments": adjustments,
            "sample_count": sum(int(x.get("sample_count") or 0) for x in certs), "recent": certs[:6],
        },
        "sources": [
            {"contractor": c, "summary_source": "DEMO", "cell": "SQLite local", "total_records": sum(1 for x in measurements if x["contractor"] == c), "visible_records": sum(1 for x in measurements if x["contractor"] == c), "synced_at": "Banco fictício local", "all_rows_total": round(sum(float(x["total_service"]) for x in measurements if x["contractor"] == c), 2)}
            for c in CONTRACTORS if contractor in {"ALL", c}
        ],
        "warnings": [],
    }


@app.get("/api/certificates")
def certificates(
    contractor: str = "ALL", measurement: str = "", sort: str = "newest", vv_status: str = "ALL",
    thickness_status: str = "ALL", road: str = "", segment: str = "", number: str = "",
    page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100),
):
    contractor = _contractor(contractor)
    vv_status = _status(vv_status)
    thickness_status = _status(thickness_status)
    sql, params = _certificate_filters(contractor, measurement, vv_status, thickness_status, road, number, segment)
    order = "ASC" if sort.lower() == "oldest" else "DESC"
    total = row(f"SELECT COUNT(*) n FROM certificates{sql}", params)["n"]
    offset = (page - 1) * page_size
    items = rows(
        f"SELECT * FROM certificates{sql} ORDER BY extraction_date {order}, number {order} LIMIT ? OFFSET ?",
        params + (page_size, offset),
    )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.get("/api/certificates/{certificate_id}")
def certificate_detail(certificate_id: int):
    cert = row("SELECT * FROM certificates WHERE id=?", (certificate_id,))
    if not cert:
        raise HTTPException(404, "Certificado não encontrado")
    samples = []
    count = max(1, int(cert.get("sample_count") or 1))
    for i in range(count):
        samples.append({
            "cp": i + 1,
            "application_date": cert["service_date"],
            "road": cert["road"],
            "kmi": float(cert["kmi"] or 0) + i * 45,
            "lane": "FAIXA 1" if i % 2 == 0 else "FAIXA 2",
            "vv": None if cert["mean_vv"] is None else round(float(cert["mean_vv"]) + (i - (count - 1) / 2) * 0.12, 2),
            "thickness_cm": None if cert["mean_thickness_cm"] is None else round(float(cert["mean_thickness_cm"]) + (i - (count - 1) / 2) * 0.05, 2),
            "ratio": None if cert["mean_ratio"] is None else round(float(cert["mean_ratio"]) + (i - (count - 1) / 2) * 0.3, 2),
        })
    cert["samples"] = samples
    return cert


@app.get("/api/pending")
def pending(contractor: str = "ALL", measurement: str = ""):
    contractor = _contractor(contractor)
    start, end, cycle_name = _cycle_range(measurement)
    m_where, m_params = _where_common(contractor, start, end, "date")
    mw = " WHERE " + " AND ".join(m_where) if m_where else ""
    measurements = rows(f"SELECT * FROM measurements{mw} ORDER BY date DESC, id DESC", tuple(m_params))
    cert_sql, cert_params = _certificate_filters(contractor, measurement)
    certs = rows(f"SELECT contractor,service_date,number,overall_status FROM certificates{cert_sql}", cert_params)
    covered = {(x["contractor"], x["service_date"]) for x in certs if x["overall_status"] != "SEM RESULTADO"}
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for m in measurements:
        key = (m["contractor"], m["date"])
        if key in covered:
            continue
        if key not in grouped:
            grouped[key] = {
                "contractor": m["contractor"], "measurement": cycle_name or f"M{measurement_cycle_number(date.fromisoformat(m['date']))}",
                "date": m["date"], "road": m["road"], "lines": 0, "delivery": "ENTREGUE", "status": "PENDENTE CERTIFICADO",
            }
        grouped[key]["lines"] += 1
    items = sorted(grouped.values(), key=lambda x: x["date"], reverse=True)
    return {"items": items, "total": len(items)}


@app.get("/api/measurements")
def measurements(
    contractor: str = "ALL", search: str = "", measurement: str = "",
    page: int = Query(1, ge=1), page_size: int = Query(40, ge=1, le=100),
):
    contractor = _contractor(contractor)
    start, end, _ = _cycle_range(measurement)
    where, params = _where_common(contractor, start, end, "date")
    if search.strip():
        q = f"%{search.strip()}%"
        where.append("(date LIKE ? OR road LIKE ? OR ref_measurement LIKE ? OR line_measurement LIKE ?)")
        params += [q, q, q, q]
    w = " WHERE " + " AND ".join(where) if where else ""
    total = row(f"SELECT COUNT(*) n FROM measurements{w}", tuple(params))["n"]
    offset = (page - 1) * page_size
    items = rows(f"SELECT * FROM measurements{w} ORDER BY date DESC,id DESC LIMIT ? OFFSET ?", tuple(params + [page_size, offset]))
    return {"items": items, "total": total, "page": page, "page_size": page_size}
