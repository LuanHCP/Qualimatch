from __future__ import annotations

import os
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("QUALIMATCH_DEMO_DB", BASE_DIR / "data" / "qualimatch_demo.db"))

CONTRACTORS = ("CONTRATADA A", "CONTRATADA B")
ROADS = ("BR-901", "PR-902", "BR-903", "PR-904")
DIRECTIONS = ("NORTE", "SUL", "LESTE", "OESTE")
LANES = ("FAIXA 1", "FAIXA 2", "FAIXA ADICIONAL")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS certificates (
            id INTEGER PRIMARY KEY,
            number TEXT NOT NULL UNIQUE,
            contractor TEXT NOT NULL,
            service_date TEXT NOT NULL,
            extraction_date TEXT NOT NULL,
            road TEXT NOT NULL,
            kmi REAL,
            kmf REAL,
            trace_approved TEXT,
            sample_count INTEGER NOT NULL DEFAULT 0,
            mean_vv REAL,
            mean_thickness_cm REAL,
            mean_ratio REAL,
            status_vv TEXT,
            status_thickness TEXT,
            overall_status TEXT,
            counterproof_state TEXT,
            parse_status TEXT NOT NULL DEFAULT 'CARREGADO'
        );

        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY,
            contractor TEXT NOT NULL,
            date TEXT NOT NULL,
            line_measurement TEXT,
            ref_measurement TEXT,
            road TEXT NOT NULL,
            direction TEXT,
            kmi REAL,
            kmf REAL,
            lane TEXT,
            extension_m REAL,
            width_m REAL,
            thickness_m REAL,
            volume_mass_m3 REAL,
            quantity_t REAL,
            cap_project_t REAL,
            total_service REAL,
            status_final TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_cert_contract_date ON certificates(contractor, service_date);
        CREATE INDEX IF NOT EXISTS idx_cert_number ON certificates(number);
        CREATE INDEX IF NOT EXISTS idx_measure_contract_date ON measurements(contractor, date);
        """
    )


def _status(vv: float | None, ratio: float | None, thickness: float | None) -> tuple[str, str, str]:
    vv_status = "SEM RESULTADO" if vv is None else ("APROVADO" if 3.5 <= vv <= 7.5 else "REPROVADO")
    thickness_status = "SEM RESULTADO" if thickness is None else ("APROVADO" if thickness >= 4.5 else "REPROVADO")
    if vv_status == "REPROVADO" or thickness_status == "REPROVADO" or (ratio is not None and ratio < 90):
        overall = "REPROVADO"
    elif vv_status == "APROVADO" and thickness_status == "APROVADO" and ratio is not None:
        overall = "APROVADO"
    else:
        overall = "SEM RESULTADO"
    return vv_status, thickness_status, overall


def _business_days(start: date, end: date) -> list[date]:
    out: list[date] = []
    cur = start
    while cur <= end:
        if cur.weekday() < 6:
            out.append(cur)
        cur += timedelta(days=1)
    return out


def _seed(conn: sqlite3.Connection) -> None:
    rng = random.Random(3302026)
    days = _business_days(date(2026, 4, 14), date(2026, 9, 8))
    execution_days = sorted(rng.sample(days, 78))
    pending_dates = set(rng.sample(execution_days, 10))

    cert_rows = []
    cert_no = 101
    covered_by_contractor: dict[tuple[str, str], bool] = {}
    for idx, d in enumerate(execution_days):
        contractor = CONTRACTORS[idx % 2]
        if d in pending_dates:
            continue
        road = ROADS[(idx + (0 if contractor == CONTRACTORS[0] else 1)) % len(ROADS)]
        base_km = 24 + ((idx * 7) % 310)
        kmi = base_km * 1000 + rng.choice([120, 260, 480, 650, 820])
        ext = rng.choice([320, 450, 520, 680, 750])
        kmf = kmi + ext
        samples = rng.choice([2, 2, 2, 3, 3, 4])
        vv_roll = rng.random()
        if vv_roll < 0.07:
            vv = None
        elif vv_roll < 0.18:
            vv = round(rng.choice([2.9, 3.1, 8.0, 8.5]), 2)
        else:
            vv = round(rng.uniform(4.1, 6.8), 2)
        ratio = None if vv is None else round(rng.uniform(87.5, 101.2), 2)
        thickness = None if vv is None else round(rng.uniform(4.25, 5.65), 2)
        vv_status, th_status, overall = _status(vv, ratio, thickness)
        counterproof = "NÃO"
        if overall == "REPROVADO" and rng.random() < 0.55:
            counterproof = rng.choice(["PENDENTE", "ENTREGUE"])
            if counterproof == "ENTREGUE" and rng.random() < 0.55:
                vv = round(rng.uniform(4.0, 6.7), 2)
                ratio = round(rng.uniform(92.0, 99.8), 2)
                thickness = round(rng.uniform(4.7, 5.5), 2)
                vv_status, th_status, overall = _status(vv, ratio, thickness)
        extraction = d + timedelta(days=rng.randint(2, 9))
        cert_rows.append((
            cert_no - 100,
            f"BI330-{cert_no:04d}", contractor, d.isoformat(), extraction.isoformat(), road,
            float(kmi), float(kmf), f"MIX DEMO {1 + idx % 8:02d} • CAP 50/70", samples,
            vv, thickness, ratio, vv_status, th_status, overall, counterproof,
            "PARCIAL" if vv is None else "CARREGADO",
        ))
        covered_by_contractor[(contractor, d.isoformat())] = True
        cert_no += 1

    conn.executemany(
        """INSERT INTO certificates(
            id,number,contractor,service_date,extraction_date,road,kmi,kmf,trace_approved,sample_count,
            mean_vv,mean_thickness_cm,mean_ratio,status_vv,status_thickness,overall_status,counterproof_state,parse_status
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        cert_rows,
    )

    measurement_rows = []
    mid = 1
    for idx, d in enumerate(execution_days):
        contractor = CONTRACTORS[idx % 2]
        line_count = rng.choice([1, 2, 2, 3])
        for line in range(line_count):
            road = ROADS[(idx + line + (0 if contractor == CONTRACTORS[0] else 1)) % len(ROADS)]
            base_km = 24 + ((idx * 7 + line * 3) % 310)
            kmi = base_km * 1000 + rng.choice([100, 250, 500, 750])
            extension = float(rng.choice([300, 420, 500, 650, 800]))
            kmf = kmi + extension
            width = float(rng.choice([3.5, 3.6, 3.75]))
            thickness_m = rng.choice([0.045, 0.05, 0.055])
            volume = extension * width * thickness_m
            density = rng.uniform(2.32, 2.46)
            quantity = volume * density
            cap = quantity * rng.uniform(0.048, 0.055)
            unit_value = rng.uniform(620, 890)
            total_service = quantity * unit_value
            if (contractor, d.isoformat()) not in covered_by_contractor:
                status_final = "PENDENTE"
            else:
                roll = rng.random()
                status_final = "APROVADO" if roll < 0.78 else ("REPROVADO" if roll < 0.93 else "PENDENTE")
            measurement_rows.append((
                mid, contractor, d.isoformat(), f"L{mid:04d}", f"MED-{1 + idx // 16:02d}", road,
                DIRECTIONS[(idx + line) % len(DIRECTIONS)], float(kmi), float(kmf), LANES[(idx + line) % len(LANES)],
                extension, width, thickness_m, round(volume, 3), round(quantity, 3), round(cap, 3), round(total_service, 2), status_final,
            ))
            mid += 1

    conn.executemany(
        """INSERT INTO measurements(
            id,contractor,date,line_measurement,ref_measurement,road,direction,kmi,kmf,lane,
            extension_m,width_m,thickness_m,volume_mass_m3,quantity_t,cap_project_t,total_service,status_final
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        measurement_rows,
    )
    conn.commit()


def init_db(reset: bool = False) -> Path:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    with connect() as conn:
        _schema(conn)
        count = conn.execute("SELECT COUNT(*) FROM certificates").fetchone()[0]
        if count == 0:
            _seed(conn)
    return DB_PATH


def rows(query: str, params: Iterable[object] = ()) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(query, tuple(params)).fetchall()]


def row(query: str, params: Iterable[object] = ()) -> dict | None:
    with connect() as conn:
        found = conn.execute(query, tuple(params)).fetchone()
        return dict(found) if found else None
