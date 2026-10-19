from __future__ import annotations

from dataclasses import asdict
from datetime import date
import json
import re
from typing import Any, Iterable

from .certificate_stats import summarize_phase
from .database import rows
from .pdf_reader import Certificate, Sample
from .quality_excel_writer import enrich_write_plan


CERT_RE = re.compile(r"BI330\s*[-_]?\s*0*(\d{1,5})", re.I)


def _cert_numeric(value: str | None) -> int | None:
    m = CERT_RE.search(value or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def contractor_hint_from_name(name: str | None) -> str | None:
    up = (name or "").upper()
    if "ARENA" in up:
        return "ARENA"
    if "PAVIDEZ" in up or "PAVDEZ" in up:
        return "PAVIDEZ"
    return None


def _iso(value: date | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _sample_key(sample: Sample) -> tuple[str, str | None, int | None, str]:
    return (
        str(sample.cp_number or "").strip(),
        _iso(sample.application_date),
        sample.station,
        str(sample.lane or "").strip(),
    )


def routine_samples(cert: Certificate) -> list[Sample]:
    """Retorna as amostras que definem a quantidade de linhas da BD_QUALI.

    Um BI330 com contra-prova pode conter a rotina e a contra-prova no mesmo PDF.
    Nesse caso a contra-prova complementa as mesmas linhas e não dobra a quantidade.
    """
    base = [s for s in cert.samples if str(s.phase).upper() == "ROTINA" and not s.counterproof]
    if not base:
        base = [s for s in cert.samples if not s.counterproof]
    if not base:
        base = list(cert.samples)
    seen: set[tuple[str, str | None, int | None, str]] = set()
    out: list[Sample] = []
    for sample in base:
        key = _sample_key(sample)
        if key in seen:
            continue
        seen.add(key)
        out.append(sample)
    return out


def counterproof_map(cert: Certificate) -> dict[str, Sample]:
    cp = [s for s in cert.samples if s.counterproof or str(s.phase).upper() == "CONTRA_PROVA"]
    out: dict[str, Sample] = {}
    for sample in cp:
        number = str(sample.cp_number or "").strip()
        if number:
            out[f"CP:{number}"] = sample
        if sample.station is not None:
            out.setdefault(f"ST:{sample.station}:{sample.lane or ''}", sample)
    return out


def _counter_for(sample: Sample, cp_map: dict[str, Sample]) -> Sample | None:
    number = str(sample.cp_number or "").strip()
    if number and f"CP:{number}" in cp_map:
        return cp_map[f"CP:{number}"]
    if sample.station is not None:
        return cp_map.get(f"ST:{sample.station}:{sample.lane or ''}")
    return None


def _segment_contains(station: int | None, kmi: int | None, kmf: int | None) -> bool:
    if station is None or kmi is None or kmf is None:
        return False
    return min(kmi, kmf) <= station <= max(kmi, kmf)


def _segment_distance(station: int | None, kmi: int | None, kmf: int | None) -> int | None:
    if station is None or kmi is None or kmf is None:
        return None
    lo, hi = sorted((kmi, kmf))
    if lo <= station <= hi:
        return 0
    return min(abs(station - lo), abs(station - hi))


def _measurement_score(sample: Sample, cert: Certificate, m: dict[str, Any], exact_road_available: bool) -> tuple[float, list[str], bool]:
    score = 35.0
    reasons = ["DATA=OK"]
    cert_road = str(cert.road or "")
    m_road = str(m.get("road") or "")
    road_ok = bool(cert_road and m_road and cert_road == m_road)
    if road_ok:
        score += 25
        reasons.append("RODOVIA=OK")
    elif cert_road and m_road:
        # Quando o PDF traz BR/PR incorreto por layout/nome de arquivo, ainda é
        # possível encontrar a execução pela data + estaca. Mantém REVISAR.
        score -= 5 if exact_road_available else 0
        reasons.append(f"RODOVIA PDF={cert_road} / MEDIÇÃO={m_road}")

    contains = _segment_contains(sample.station, m.get("kmi"), m.get("kmf"))
    distance = _segment_distance(sample.station, m.get("kmi"), m.get("kmf"))
    if contains:
        score += 45
        reasons.append("ESTACA DENTRO DO TRECHO")
    elif distance is not None:
        if distance <= 20:
            score += 18
            reasons.append(f"ESTACA A {distance} m DO TRECHO")
        elif distance <= 100:
            score += max(2, 12 - distance / 10)
            reasons.append(f"ESTACA A {distance} m DO TRECHO")

    sample_lane = str(sample.lane or "").strip().upper()
    m_lane = str(m.get("lane") or "").strip().upper()
    if sample_lane and m_lane and sample_lane == m_lane:
        score += 10
        reasons.append("FAIXA=OK")

    sample_dir = str(sample.direction or "").strip().upper()
    m_dir = str(m.get("direction") or "").strip().upper()
    if sample_dir and m_dir and sample_dir == m_dir:
        score += 8
        reasons.append("SENTIDO=OK")

    # Em empate, segmentos menores são mais específicos. O valor é pequeno para
    # nunca superar uma incompatibilidade real de data/estaca.
    if m.get("kmi") is not None and m.get("kmf") is not None:
        length = abs(int(m["kmf"]) - int(m["kmi"]))
        score += max(0.0, 2.0 - min(length, 2000) / 1000.0)
    return score, reasons, contains


def _candidate_payload(score: float, reasons: list[str], contains: bool, m: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": m.get("id"), "source_row": m.get("source_row"),
        "line_measurement": m.get("line_measurement"), "ref_measurement": m.get("ref_measurement"),
        "date": m.get("date"), "road": m.get("road"), "direction": m.get("direction"),
        "kmi": m.get("kmi"), "kmf": m.get("kmf"), "lane": m.get("lane"),
        "score": round(score, 1), "reason": " | ".join(reasons), "contains_station": bool(contains),
    }


def _best_measurement(sample: Sample, cert: Certificate, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    sample_date = _iso(sample.application_date)
    same_date = [m for m in candidates if m.get("contractor") == cert.contractor and m.get("date") == sample_date]
    if not same_date:
        return {"status": "SEM_MEDICAO", "score": 0, "reason": "Nenhuma medição da contratada nesta data.", "measurement": None, "candidates": []}

    exact_road = [m for m in same_date if cert.road and m.get("road") == cert.road]
    ranked_all: list[tuple[float, list[str], bool, dict[str, Any]]] = []
    for m in same_date:
        score, reasons, contains = _measurement_score(sample, cert, m, bool(exact_road))
        ranked_all.append((score, reasons, contains, m))
    ranked_all.sort(key=lambda item: item[0], reverse=True)

    # A seleção automática mantém a preferência histórica por rodovia exata.
    ranked_pool = [x for x in ranked_all if x[3] in exact_road] if exact_road else ranked_all
    score, reasons, contains, best = ranked_pool[0]

    road_mismatch = bool(cert.road and best.get("road") and cert.road != best.get("road"))
    if contains and score >= 75 and not road_mismatch:
        status = "VINCULADO"
    elif score >= 55:
        status = "REVISAR"
    else:
        status = "SEM_MEDICAO"
    return {
        "status": status, "score": round(score, 1), "reason": " | ".join(reasons),
        "measurement": best if status != "SEM_MEDICAO" else None,
        "candidates": [_candidate_payload(*x) for x in ranked_all[:8]],
    }


def _stats(cert: Certificate, phase: str) -> dict[str, Any]:
    samples = [s for s in cert.samples if str(s.phase).upper() == phase]
    printed = (cert.raw.get("phase_summaries") or {}).get(phase) or {}
    return summarize_phase([asdict(s) for s in samples], printed)


def _mean_rice(samples: Iterable[Sample]) -> float | None:
    vals = [float(s.rice_gmm) for s in samples if s.rice_gmm is not None]
    if not vals:
        return None
    return round(sum(vals) / len(vals), 3)


def _phase_dates(cert: Certificate) -> dict[str, str | None]:
    raw = cert.raw or {}
    ext = list(raw.get("extraction_dates") or [])
    rec = list(raw.get("receipt_dates") or [])
    return {
        "routine_extraction": ext[0] if ext else _iso(cert.extraction_date),
        "routine_receipt": rec[0] if rec else None,
        "counter_extraction": ext[1] if len(ext) > 1 else None,
        "counter_receipt": rec[1] if len(rec) > 1 else None,
    }


def _quality_fields(cert: Certificate, routine: list[Sample]) -> dict[str, Any]:
    rs = _stats(cert, "ROTINA")
    cs = _stats(cert, "CONTRA_PROVA")
    dates = _phase_dates(cert)
    cert_num = _cert_numeric(cert.number)

    def frac(v: Any) -> float | None:
        return None if v is None else float(v) / 100.0

    fields: dict[str, Any] = {
        "Nº CERTIFICADO Vv": cert_num if cert_num is not None else cert.number,
        "DATA EXTRAÇÃO": dates["routine_extraction"],
        "DATA RECEBIMENTO LABORATÓRIO": dates["routine_receipt"],
        "DENSIDADE RICE": _mean_rice(routine),
        "Vv médio %": frac(rs.get("vv_mean_pct")),
        "DESVIO PAD (%) Vv rotina": frac(rs.get("vv_std_pct")),
        "Xmin (%)": frac(rs.get("vv_xmin_pct")),
        "Xmáx (%)": frac(rs.get("vv_xmax_pct")),
        "TOTAL CPs": rs.get("sample_count"),
        "Vv REPROVADOS (un)": rs.get("vv_failed_samples"),
        "STATUS Vv rotina": "P CONTRA PROVA" if rs.get("status_vv") == "REPROVADO" else rs.get("status_vv"),
        "MEDIA (%)": frac(rs.get("ratio_mean_pct")),
        "DESVIO PAD (%) Esp rotina": frac(rs.get("ratio_std_pct")),
        "Xmin (>95%)": frac(rs.get("ratio_xmin_pct")),
        "ESP REPROV (<90%) (un) rotina": rs.get("ratio_failed_samples"),
        "STATUS ESPESSURA rotina": "P CONTRA PROVA" if rs.get("status_thickness") == "REPROVADO" else rs.get("status_thickness"),
    }
    if cs.get("sample_count"):
        fields.update({
            "Nº CERTIFICADO Vv CP": cert_num if cert_num is not None else cert.number,
            "DATA EXTRAÇÃO CP": dates["counter_extraction"],
            "DATA RECEBIMENTO LABORATÓRIO CP": dates["counter_receipt"],
            "Vv médio (%) CP": frac(cs.get("vv_mean_pct")),
            "DESVIO PAD (%)Vv CP": frac(cs.get("vv_std_pct")),
            "Vvmin (%) CP": frac(cs.get("vv_xmin_pct")),
            "Vvmáx (%) CP": frac(cs.get("vv_xmax_pct")),
            "Vv REPROVADOS CP (un)": cs.get("vv_failed_samples"),
            "STATUS Vv CP": cs.get("status_vv"),
            "MEDIA (%) CP": frac(cs.get("ratio_mean_pct")),
            "DESVIO PAD (%)CPesp": frac(cs.get("ratio_std_pct")),
            "Xmin (>95%) CP": frac(cs.get("ratio_xmin_pct")),
            "CP REPROVADOS (<90%) (un) CP": cs.get("ratio_failed_samples"),
            "STATUS ESPESSURA CP": cs.get("status_thickness"),
        })
    return fields


def _existing_quality_index(contractors: set[str]) -> dict[tuple[str, int], int]:
    index: dict[tuple[str, int], int] = {}
    for contractor in contractors:
        for r in rows("SELECT raw_json FROM quality_rows WHERE contractor=?", (contractor,)):
            try:
                raw = json.loads(r.get("raw_json") or "{}")
            except Exception:
                continue
            value = raw.get("Nº CERTIFICADO Vv")
            if value in (None, "", 0, "0"):
                continue
            try:
                number = int(float(str(value).replace(",", ".")))
            except Exception:
                m = re.search(r"\d+", str(value))
                if not m:
                    continue
                number = int(m.group())
            key = (contractor, number)
            index[key] = index.get(key, 0) + 1
    return index


def analyze_certificates(certificates: list[tuple[str, Certificate]], overrides: dict[str, int] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    contractors = {c.contractor for _, c in certificates}
    dates = sorted({_iso(s.application_date) for _, c in certificates for s in routine_samples(c) if s.application_date})
    measurements: list[dict[str, Any]] = []
    for contractor in contractors:
        if dates:
            placeholders = ",".join("?" for _ in dates)
            sql = f"SELECT * FROM measurements WHERE contractor=? AND date IN ({placeholders})"
            measurements.extend(dict(r) for r in rows(sql, tuple([contractor] + dates)))
    existing = _existing_quality_index(contractors)

    result_certs: list[dict[str, Any]] = []
    all_lines: list[dict[str, Any]] = []
    total_expected = total_linked = total_review = total_missing = 0

    for file_name, cert in certificates:
        routine = routine_samples(cert)
        cp_map = counterproof_map(cert)
        qfields = _quality_fields(cert, routine)
        numeric = _cert_numeric(cert.number)
        file_numeric = _cert_numeric(file_name)
        warnings = list(cert.raw.get("parse_warnings") or []) + list(cert.raw.get("validation_warnings") or [])
        if file_numeric is not None and numeric is not None and file_numeric != numeric:
            warnings.append(f"Número divergente: arquivo sugere BI330-{file_numeric:04d}, conteúdo foi lido como {cert.number}.")
        existing_rows = existing.get((cert.contractor, numeric), 0) if numeric is not None else 0
        cert_lines: list[dict[str, Any]] = []
        for sample in routine:
            match = _best_measurement(sample, cert, measurements)
            line_key = "|".join([
                file_name, str(cert.number or ""), str(sample.cp_number or ""),
                str(_iso(sample.application_date) or ""), str(sample.station if sample.station is not None else ""),
            ])
            selected_id = overrides.get(line_key)
            if selected_id is not None:
                chosen = next((x for x in match.get("candidates") or [] if int(x.get("id") or -1) == int(selected_id)), None)
                if chosen:
                    match = {
                        **match, "status": "VINCULADO", "score": chosen.get("score") or 100,
                        "reason": "VÍNCULO MANUAL • " + str(chosen.get("reason") or "medição escolhida pelo administrador"),
                        "measurement": chosen,
                    }
            m = match.get("measurement")
            cp = _counter_for(sample, cp_map)
            line = {
                "line_key": line_key,
                "file_name": file_name,
                "contractor": cert.contractor,
                "certificate": cert.number,
                "cp_number": sample.cp_number,
                "application_date": _iso(sample.application_date),
                "road_pdf": cert.road,
                "direction": sample.direction,
                "lane": sample.lane,
                "station": sample.station,
                "position": sample.position,
                "thickness_exec_cm": sample.thickness_exec_cm,
                "thickness_project_cm": sample.thickness_project_cm,
                "ratio_ab_pct": sample.ratio_ab_pct,
                "rice_gmm": sample.rice_gmm,
                "gmb": sample.gmb,
                "voids_pct": sample.voids_pct,
                "counterproof": ({
                    "voids_pct": cp.voids_pct,
                    "ratio_ab_pct": cp.ratio_ab_pct,
                    "rice_gmm": cp.rice_gmm,
                    "gmb": cp.gmb,
                    "thickness_exec_cm": cp.thickness_exec_cm,
                } if cp else None),
                "match_status": match["status"],
                "match_score": match["score"],
                "match_reason": match["reason"],
                "measurement_candidates": match.get("candidates") or [],
                "measurement": ({
                    "id": m.get("id"), "source_row": m.get("source_row"),
                    "line_measurement": m.get("line_measurement"), "ref_measurement": m.get("ref_measurement"),
                    "date": m.get("date"), "road": m.get("road"), "direction": m.get("direction"),
                    "kmi": m.get("kmi"), "kmf": m.get("kmf"), "lane": m.get("lane"),
                } if m else None),
                "projected_certificate_fields": qfields,
            }
            cert_lines.append(line)
            all_lines.append(line)
            total_expected += 1
            if match["status"] == "VINCULADO":
                total_linked += 1
            elif match["status"] == "REVISAR":
                total_review += 1
            else:
                total_missing += 1
        result_certs.append({
            "file_name": file_name,
            "contractor": cert.contractor,
            "certificate": cert.number,
            "road": cert.road,
            "service_dates": cert.raw.get("service_dates") or [],
            "extraction_date": _iso(cert.extraction_date),
            "parse_status": cert.raw.get("parse_status") or "",
            "routine_samples": len(routine),
            "counterproof_samples": sum(1 for s in cert.samples if s.counterproof or str(s.phase).upper() == "CONTRA_PROVA"),
            "expected_quality_rows": len(routine),
            "existing_quality_rows": existing_rows,
            "warnings": warnings,
            "quality_fields": qfields,
            "lines": cert_lines,
        })

    result = {
        "summary": {
            "pdfs": len(certificates),
            "expected_rows": total_expected,
            "linked": total_linked,
            "review": total_review,
            "missing": total_missing,
        },
        "certificates": result_certs,
        "lines": all_lines,
        "mode": "PREVIEW_ONLY",
        "message": "Prévia somente: nenhuma planilha foi alterada.",
    }
    return enrich_write_plan(result)
