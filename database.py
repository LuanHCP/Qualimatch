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

        CREATE TABLE IF NOT EXISTS kits (
            id INTEGER PRIMARY KEY,
            seq TEXT NOT NULL,
            contractor TEXT NOT NULL,
            service TEXT,
            application_date TEXT,
            mix_project TEXT,
            period TEXT,
            road TEXT,
            kmi REAL,
            kmf REAL,
            receipt_date TEXT,
            delivery_status TEXT,
            status TEXT,
            status_1 TEXT,
            status_2 TEXT,
            status_3 TEXT,
            status_4 TEXT,
            status_5 TEXT,
            status_6 TEXT,
            status_7 TEXT,
            status_8 TEXT
        );

        CREATE TABLE IF NOT EXISTS contractor_documents (
            id INTEGER PRIMARY KEY,
            contractor TEXT NOT NULL,
            file_name TEXT NOT NULL,
            folder TEXT,
            document_type TEXT,
            linked_seq TEXT,
            status TEXT,
            modified_at TEXT
        );

        CREATE TABLE IF NOT EXISTS traces (
            id INTEGER PRIMARY KEY,
            contractor TEXT NOT NULL,
            code TEXT NOT NULL UNIQUE,
            plant TEXT,
            supplier TEXT,
            binder TEXT,
            mixture TEXT,
            status TEXT,
            valid_from TEXT,
            valid_to TEXT,
            revision INTEGER,
            notes TEXT
        );

        CREATE TABLE IF NOT EXISTS nonconformities (
            id INTEGER PRIMARY KEY,
            number TEXT NOT NULL UNIQUE,
            opened_date TEXT,
            contractor TEXT,
            road TEXT,
            km TEXT,
            description TEXT,
            category TEXT,
            severity TEXT,
            status TEXT,
            action TEXT,
            due_date TEXT
        );

        CREATE TABLE IF NOT EXISTS demo_users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            role TEXT,
            access_level TEXT,
            status TEXT,
            last_access TEXT
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY,
            created_at TEXT,
            actor TEXT,
            action TEXT,
            target TEXT,
            detail TEXT
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


def _seed_portfolio_modules(conn: sqlite3.Connection) -> None:
    rng = random.Random(77442026)

    if conn.execute("SELECT COUNT(*) FROM kits").fetchone()[0] == 0:
        kit_rows = []
        for i in range(1, 31):
            contractor = CONTRACTORS[(i - 1) % 2]
            d = date(2026, 6, 3) + timedelta(days=i * 3)
            road = ROADS[i % len(ROADS)]
            kmi = float((35 + i * 5) * 1000 + rng.choice([120, 350, 620]))
            kmf = kmi + rng.choice([350, 500, 700])
            status = "OK" if i % 6 not in {0, 5} else ("PENDENTE" if i % 6 == 0 else "INCOMPLETO")
            delivery = "RECEBIDO" if i % 5 else "AGUARDANDO"
            controls = []
            for n in range(8):
                if status == "OK":
                    controls.append("OK")
                elif status == "PENDENTE" and n in {2, 5}:
                    controls.append("PENDENTE")
                elif status == "INCOMPLETO" and n in {3, 7}:
                    controls.append("INCOMPLETO")
                else:
                    controls.append("OK")
            kit_rows.append((
                i, f"KIT-{i:03d}", contractor, "CBUQ - CAMADA DE ROLAMENTO", d.isoformat(),
                f"MIX DEMO {1 + i % 8:02d}", "DIURNO" if i % 3 else "NOTURNO", road, kmi, kmf,
                (d + timedelta(days=rng.randint(1, 4))).isoformat(), delivery, status, *controls
            ))
        conn.executemany(
            """INSERT INTO kits(
                id,seq,contractor,service,application_date,mix_project,period,road,kmi,kmf,receipt_date,
                delivery_status,status,status_1,status_2,status_3,status_4,status_5,status_6,status_7,status_8
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            kit_rows,
        )

    if conn.execute("SELECT COUNT(*) FROM contractor_documents").fetchone()[0] == 0:
        docs = []
        doc_id = 1
        for i in range(1, 31):
            contractor = CONTRACTORS[(i - 1) % 2]
            if i % 4 == 0:
                continue
            docs.append((
                doc_id, contractor, f"KIT-{i:03d}_ensaio_demo.pdf", f"M{12 + i // 7}/Ensaios",
                "RELATÓRIO DE ENSAIO", f"KIT-{i:03d}", "INDEXADO",
                (date(2026, 6, 5) + timedelta(days=i * 3)).isoformat()
            ))
            doc_id += 1
        conn.executemany(
            "INSERT INTO contractor_documents(id,contractor,file_name,folder,document_type,linked_seq,status,modified_at) VALUES (?,?,?,?,?,?,?,?)",
            docs,
        )

    if conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0] == 0:
        trace_rows = []
        for i in range(1, 15):
            contractor = CONTRACTORS[(i - 1) % 2]
            valid_from = date(2026, 1, 10) + timedelta(days=i * 12)
            trace_rows.append((
                i, contractor, f"TR-{1200 + i:04d}-R{1 + i % 3:02d}",
                f"Usina Demo {1 + i % 3}", f"Fornecedor Sintético {1 + i % 4}", "CAP 50/70",
                f"Faixa granulométrica {chr(64 + 1 + i % 4)}",
                "VIGENTE" if i % 5 else "EM REVISÃO", valid_from.isoformat(),
                (valid_from + timedelta(days=210)).isoformat(), 1 + i % 3,
                "Traço sintético para demonstração pública."
            ))
        conn.executemany(
            "INSERT INTO traces(id,contractor,code,plant,supplier,binder,mixture,status,valid_from,valid_to,revision,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            trace_rows,
        )

    if conn.execute("SELECT COUNT(*) FROM nonconformities").fetchone()[0] == 0:
        descriptions = [
            "Volume de vazios fora da faixa de controle.",
            "Espessura executada inferior ao valor de referência.",
            "Documentação do lote recebida com campo obrigatório ausente.",
            "Ponto de extração divergente do trecho programado.",
            "Resultado de controle requer verificação complementar.",
            "Rastreabilidade de material incompleta na inspeção.",
            "Amostra de contra-prova aguardando resultado.",
            "Divergência entre data de execução e registro laboratorial.",
            "Controle geométrico com valor fora da tolerância demonstrativa.",
            "Revisão de traço pendente para novo lote."
        ]
        nc_rows = []
        for i, desc in enumerate(descriptions, 1):
            d = date(2026, 5, 8) + timedelta(days=i * 10)
            status = ["ABERTA", "EM TRATAMENTO", "ENCERRADA"][i % 3]
            severity = ["BAIXA", "MÉDIA", "ALTA"][i % 3]
            nc_rows.append((
                i, f"NC-{50 + i:03d}", d.isoformat(), CONTRACTORS[(i - 1) % 2], ROADS[i % len(ROADS)],
                f"{42 + i * 7}+{rng.choice([120, 380, 750]):03d}", desc,
                ["LABORATÓRIO", "EXECUÇÃO", "DOCUMENTAÇÃO"][i % 3], severity, status,
                "Analisar evidências, registrar tratativa e validar encerramento.",
                (d + timedelta(days=20 + i)).isoformat()
            ))
        conn.executemany(
            "INSERT INTO nonconformities(id,number,opened_date,contractor,road,km,description,category,severity,status,action,due_date) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            nc_rows,
        )

    if conn.execute("SELECT COUNT(*) FROM demo_users").fetchone()[0] == 0:
        users = [
            (1, "Luan HCP", "luan.demo@qualimatch.local", "Administrador", "ADMIN", "ATIVO", "2026-09-09 14:20"),
            (2, "Analista Demo", "analista@qualimatch.local", "Analista BV", "EDITOR", "ATIVO", "2026-09-09 13:48"),
            (3, "Técnico A", "tecnico.a@qualimatch.local", "Contratada A", "EDITOR", "ATIVO", "2026-09-08 17:31"),
            (4, "Técnico B", "tecnico.b@qualimatch.local", "Contratada B", "VIEWER", "ATIVO", "2026-09-08 16:05"),
            (5, "Auditoria Demo", "auditoria@qualimatch.local", "Auditoria", "VIEWER", "BLOQUEADO", "2026-08-29 10:12"),
        ]
        conn.executemany("INSERT INTO demo_users(id,name,email,role,access_level,status,last_access) VALUES (?,?,?,?,?,?,?)", users)

    if conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0:
        actions = [
            ("Luan HCP", "SYNC_DEMO", "Base SQLite", "Atualização demonstrativa concluída"),
            ("Analista Demo", "VIEW_CERTIFICATE", "BI330-0142", "Consulta de certificado"),
            ("Técnico A", "UPLOAD_KIT", "KIT-018", "Documento sintético indexado"),
            ("Luan HCP", "UPDATE_TRACE", "TR-1208-R03", "Revisão de traço demonstrativa"),
            ("Analista Demo", "CLOSE_NC", "NC-054", "Encerramento simulado"),
        ]
        logs = []
        base = date(2026, 9, 1)
        lid = 1
        for day in range(9):
            for actor, action, target, detail in actions[: 2 + day % 4]:
                logs.append((lid, f"{(base + timedelta(days=day)).isoformat()} {8 + lid % 9:02d}:{(lid * 7) % 60:02d}", actor, action, target, detail))
                lid += 1
        conn.executemany("INSERT INTO audit_log(id,created_at,actor,action,target,detail) VALUES (?,?,?,?,?,?)", logs)

    conn.commit()


def init_db(reset: bool = False) -> Path:
    if reset and DB_PATH.exists():
        DB_PATH.unlink()
    with connect() as conn:
        _schema(conn)
        count = conn.execute("SELECT COUNT(*) FROM certificates").fetchone()[0]
        if count == 0:
            _seed(conn)
        _seed_portfolio_modules(conn)
    return DB_PATH


def rows(query: str, params: Iterable[object] = ()) -> list[dict]:
    with connect() as conn:
        return [dict(r) for r in conn.execute(query, tuple(params)).fetchall()]


def row(query: str, params: Iterable[object] = ()) -> dict | None:
    with connect() as conn:
        found = conn.execute(query, tuple(params)).fetchone()
        return dict(found) if found else None
