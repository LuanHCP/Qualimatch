from __future__ import annotations

import json
import os
import re
from pathlib import Path
from datetime import date, datetime
from collections import Counter, defaultdict
from typing import Any

from .database import rows, row, transaction
from .certificate_stats import summarize_phase, raw_json
from .normalizers import norm_road, station, norm_header, norm_text


def _money(v):
    return float(v or 0)


def _path_is_file(value: str) -> bool:
    raw=os.path.abspath(str(value))
    if os.name=='nt' and not raw.startswith('\\\\?\\'):
        raw='\\\\?\\UNC\\'+raw[2:] if raw.startswith('\\\\') else '\\\\?\\'+raw
    try:
        return Path(raw).is_file()
    except OSError:
        return False


def _snapshot_summary(snap: dict[str, Any] | None) -> dict[str, Any]:
    if not snap:
        return {}
    try:
        return json.loads(snap.get("summary_json") or "{}")
    except Exception:
        return {}


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None




def measurement_cycle(value: Any) -> dict[str, Any] | None:
    """Retorna a medição Motiva (M1, M2...) para uma data de execução.

    Referência operacional informada: M14 = 11/08/2026 a 10/09/2026.
    Cada medição inicia no dia 11 e termina no dia 10 do mês seguinte.
    """
    d = _as_date(value)
    if not d:
        return None
    if d.day >= 11:
        sy, sm = d.year, d.month
    elif d.month == 1:
        sy, sm = d.year - 1, 12
    else:
        sy, sm = d.year, d.month - 1
    anchor_y, anchor_m, anchor_n = 2026, 8, 14
    diff = (sy - anchor_y) * 12 + (sm - anchor_m)
    number = anchor_n + diff
    if number < 1:
        return None
    start_date = date(sy, sm, 11)
    if sm == 12:
        ey, em = sy + 1, 1
    else:
        ey, em = sy, sm + 1
    end_date = date(ey, em, 10)
    return {
        "measurement": f"M{number}",
        "measurement_number": number,
        "measurement_start": start_date.isoformat(),
        "measurement_end": end_date.isoformat(),
    }


def measurement_cycle_bounds(value: Any) -> dict[str, Any] | None:
    """Faz o caminho inverso de :func:`measurement_cycle`.

    M14 = 11/08/2026 a 10/09/2026. Cada incremento de M avança um mês.
    """
    text = str(value or "").strip().upper()
    m = re.fullmatch(r"M?\s*(\d+)", text)
    if not m:
        return None
    number = int(m.group(1))
    if number < 1:
        return None
    anchor_y, anchor_m, anchor_n = 2026, 8, 14
    month_index = anchor_y * 12 + (anchor_m - 1) + (number - anchor_n)
    sy, sm0 = divmod(month_index, 12)
    sm = sm0 + 1
    start_date = date(sy, sm, 11)
    if sm == 12:
        ey, em = sy + 1, 1
    else:
        ey, em = sy, sm + 1
    end_date = date(ey, em, 10)
    return {
        "measurement": f"M{number}",
        "measurement_number": number,
        "measurement_start": start_date.isoformat(),
        "measurement_end": end_date.isoformat(),
    }


def measurement_cycle_options(contractor: str = "ALL") -> list[dict[str, Any]]:
    """Lista os Mxx que possuem execução importada para o filtro das telas."""
    where = ["date IS NOT NULL", "TRIM(date)<>''"]
    params: list[Any] = []
    if contractor != "ALL":
        where.append("contractor=?")
        params.append(contractor)
    try:
        data = rows(
            "SELECT DISTINCT date FROM measurements WHERE " + " AND ".join(where) + " ORDER BY date DESC",
            tuple(params),
        )
    except Exception:
        data = []
    found: dict[int, dict[str, Any]] = {}
    for item in data:
        cyc = measurement_cycle(item.get("date"))
        if cyc:
            found[int(cyc["measurement_number"])] = cyc
    return [found[n] for n in sorted(found, reverse=True)]


def _effective_cycle_range(measurement: str = "", start: str | None = None, end: str | None = None) -> tuple[str | None, str | None, dict[str, Any] | None]:
    cyc = measurement_cycle_bounds(measurement) if str(measurement or "").strip() else None
    if not cyc:
        return start, end, None
    cstart, cend = cyc["measurement_start"], cyc["measurement_end"]
    effective_start = max(str(start)[:10], cstart) if start else cstart
    effective_end = min(str(end)[:10], cend) if end else cend
    return effective_start, effective_end, cyc


def _certificate_execution_dates(cert: dict[str, Any], samples: list[dict[str, Any]] | None = None, docs: list[dict[str, Any]] | None = None) -> list[str]:
    """Datas de execução que posicionam o BI330 dentro de uma medição Mxx.

    Prioriza Data ex. serviço / Data Aplicação dos CPs. Data Ext. dos CPs só é
    fallback para certificados antigos que ainda não possuem nenhuma data de execução.
    """
    values: list[str] = []
    if cert.get("service_date"):
        values.append(str(cert.get("service_date"))[:10])
    raw = cert.get("raw") if isinstance(cert.get("raw"), dict) else None
    if raw is None:
        try:
            raw = json.loads(cert.get("raw_json") or "{}")
        except Exception:
            raw = {}
    for value in (raw.get("service_dates") or []):
        if value:
            values.append(str(value)[:10])
    for sample in (samples or []):
        value = sample.get("application_date")
        if value:
            values.append(str(value)[:10])
    # Legados como o BI330-0169 podem não ter service_date/CPs, embora o nome
    # do PDF tenha as datas de execução. Usa o nome antes da Data Ext. dos CPs.
    if not values:
        for doc in (docs or []):
            for parsed in _dates_from_certificate_filename(doc.get("file_name")):
                values.append(parsed)
    # Só usa a data de extração quando o legado realmente não oferece nenhuma
    # data operacional nem no registro nem no nome do documento.
    if not values and cert.get("extraction_date"):
        values.append(str(cert.get("extraction_date"))[:10])
    return list(dict.fromkeys(x for x in values if _as_date(x)))


def _certificate_in_measurement(cert: dict[str, Any], samples: list[dict[str, Any]], measurement: str, docs: list[dict[str, Any]] | None = None) -> bool:
    cyc = measurement_cycle_bounds(measurement)
    if not cyc:
        return True
    start, end = cyc["measurement_start"], cyc["measurement_end"]
    return any(start <= d <= end for d in _certificate_execution_dates(cert, samples, docs))


def _dates_from_certificate_filename(value: Any) -> list[str]:
    """Fallback conservador para legados sem Data ex. serviço no parser.

    Os nomes operacionais dos BI330 normalmente carregam DD.MM.AA/DD-MM-AA. O
    fallback só é usado quando o certificado não possui qualquer data técnica.
    """
    text = str(value or "")
    out: list[str] = []
    for dd, mm, yy in re.findall(r"(?<!\d)(\d{1,2})[._-](\d{1,2})[._-](\d{2,4})(?!\d)", text):
        try:
            year = int(yy)
            if year < 100:
                year += 2000
            d = date(year, int(mm), int(dd))
        except ValueError:
            continue
        out.append(d.isoformat())
    return list(dict.fromkeys(out))


def _certificate_business_warnings(cert: dict[str, Any], raw: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    extraction = _as_date(cert.get("extraction_date"))
    receipts = [_as_date(x) for x in (raw.get("receipt_dates") or [])]
    receipts = [x for x in receipts if x]
    if extraction and any(x < extraction for x in receipts):
        warnings.append("Data de recebimento em laboratório anterior à Data Ext. dos CPs — enviar para a BV")
    return warnings


def _current_parse_warnings(cert: dict[str, Any], raw: dict[str, Any], samples: list[dict[str, Any]]) -> list[str]:
    # Recalcula os avisos estruturais com o estado atual do registro. Isso evita
    # manter PARCIAL por um aviso antigo depois que rodovia/trecho foi recuperado.
    generated_prefixes = (
        "Data Ext. dos CP's não encontrada", "Data de execução não identificada",
        "Data ex. serviço não identificada", "Rodovia não identificada",
        "Segmento ensaiado não identificado", "Traço aprovado não identificado",
        "Nenhum corpo de prova extraído", "Data Ext. dos CP's anterior",
        "Data Ext. dos CP's posterior", "Data de recebimento em laboratório posterior",
        "Data de recebimento em laboratório anterior",
    )
    warnings = [
        str(w) for w in (raw.get("parse_warnings") or [])
        if not str(w).startswith(generated_prefixes)
    ]
    if not cert.get("extraction_date"):
        warnings.append("Data Ext. dos CP's não encontrada")
    if not cert.get("service_date") and not (raw.get("service_dates") or []) and not any(x.get("application_date") for x in samples):
        warnings.append("Data ex. serviço não identificada")
    if not cert.get("road"):
        warnings.append("Rodovia não identificada")
    if cert.get("kmi") is None or cert.get("kmf") is None:
        warnings.append("Segmento ensaiado não identificado")
    if not cert.get("trace_approved") or "DIA 1 DIA 2" in str(cert.get("trace_approved") or "").upper():
        warnings.append("Traço aprovado não identificado")
    if not samples:
        warnings.append("Nenhum corpo de prova extraído")
    if raw.get("segment_source") == "CPS_ESTIMADO":
        warnings.append("Segmento estimado pelas estacas dos CPs; cabeçalho do PDF não identificado")
    return list(dict.fromkeys(warnings))


def _number_duplicate_context(certs: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Para cada certificado, verifica se existe(m) outro(s) certificado(s) ATIVO(s)
    da mesma contratada com o MESMO número (o cenário do bug de identidade já
    corrigido em local_sync.py) e aponta qual deles é o mais recente por
    parsed_at — sem excluir/desativar nada, só para exibição.

    Sempre olha para TODOS os certificados ativos com aquele número, não só os
    que sobreviveram aos filtros da consulta atual, então a resposta não muda
    dependendo de quais filtros a pessoa aplicou.
    """
    pairs = {(c["contractor"], c["number"]) for c in certs if c.get("number")}
    if not pairs:
        return {}
    where = " OR ".join(["(contractor=? AND number=?)"] * len(pairs))
    params = [v for pair in pairs for v in pair]
    all_matches = rows(
        f"SELECT id,contractor,number,parsed_at FROM certificates WHERE is_active=1 AND ({where})",
        tuple(params),
    )
    grupos: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for m in all_matches:
        m = dict(m)
        grupos[(m["contractor"], m["number"])].append(m)

    result: dict[int, dict[str, Any]] = {}
    for linhas in grupos.values():
        linhas.sort(key=lambda x: (str(x.get("parsed_at") or ""), int(x["id"])), reverse=True)
        mais_recente = linhas[0]
        for item in linhas:
            result[int(item["id"])] = {
                "number_duplicate_count": len(linhas),
                "is_latest_version": item["id"] == mais_recente["id"],
                "latest_version_id": int(mais_recente["id"]),
                "latest_version_parsed_at": mais_recente.get("parsed_at"),
            }
    return result


def _bulk_certificate_context(certs: list[dict[str, Any]]) -> tuple[dict[int, list[dict[str, Any]]], dict[int, list[dict[str, Any]]], dict[int, int]]:
    """Carrega CPs, documentos e vínculos em lote para evitar N+1 queries."""
    if not certs:
        return {}, {}, {}
    ids = [int(c["id"]) for c in certs]
    placeholders = ",".join("?" for _ in ids)
    sample_rows = rows(
        f"""SELECT * FROM certificate_samples WHERE certificate_id IN ({placeholders})
             ORDER BY certificate_id, CASE phase WHEN 'ROTINA' THEN 1 ELSE 2 END, station, id""",
        tuple(ids),
    )
    doc_rows = rows(
        f"""SELECT id,certificate_id,file_name,file_path,kind,status,parser_version,error,parsed_at,size
              FROM certificate_files WHERE certificate_id IN ({placeholders})
             ORDER BY certificate_id, CASE kind WHEN 'ROTINA' THEN 1 ELSE 2 END,id""",
        tuple(ids),
    )
    match_rows = rows(
        f"SELECT certificate_id,COUNT(*) n FROM matches WHERE certificate_id IN ({placeholders}) GROUP BY certificate_id",
        tuple(ids),
    )
    samples_by: dict[int, list[dict[str, Any]]] = {}
    docs_by: dict[int, list[dict[str, Any]]] = {}
    for x in sample_rows:
        samples_by.setdefault(int(x["certificate_id"]), []).append(x)
    for x in doc_rows:
        docs_by.setdefault(int(x["certificate_id"]), []).append(x)
    matches_by = {int(x["certificate_id"]): int(x["n"] or 0) for x in match_rows}
    return samples_by, docs_by, matches_by


def _routine_failed_vv_or_thickness(samples: list[dict[str, Any]]) -> bool:
    """Reprovação que justifica pedir contra-prova: em qualquer CP de ROTINA,
    Vv fora de 3,5%–7,5% (o valor já considera o filme quando existe — o
    parser resolve isso na extração, ver pdf_reader.py) OU relação A/B abaixo
    de 90%. É um critério fixo de regulamento, independente da meta específica
    do traço (diferente de status_vv/status_thickness, que comparam com o
    projeto)."""
    for s in samples:
        if s.get("phase") != "ROTINA":
            continue
        vv = s.get("voids_pct")
        if vv is not None and (float(vv) < 3.5 or float(vv) > 7.5):
            return True
        ratio = s.get("ratio_ab_pct")
        if ratio is not None and float(ratio) < 90:
            return True
    return False


def _cert_stats_loaded(
    cert: dict[str, Any], samples: list[dict[str, Any]], docs: list[dict[str, Any]],
    matched_count: int = 0, include_samples: bool = False,
) -> dict[str, Any]:
    raw = raw_json(cert)
    printed = raw.get("phase_summaries") or {}
    phases = []
    for phase in ("ROTINA", "CONTRA_PROVA"):
        ps = [x for x in samples if x["phase"] == phase]
        if not ps:
            continue
        st = summarize_phase(ps, printed.get(phase) or {})
        st["phase"] = phase
        printed_overall = cert.get("counterproof_result") if phase == "CONTRA_PROVA" else cert.get("routine_result")
        if printed_overall:
            st["calculated_overall_status"] = st.get("overall_status", "")
            st["overall_status"] = printed_overall
        if include_samples:
            st["samples"] = ps
        phases.append(st)

    counterproof_phase = next((x for x in phases if x["phase"] == "CONTRA_PROVA"), None)
    final = counterproof_phase or (phases[0] if phases else {})
    # Contra-prova é uma FASE do mesmo certificado, não um certificado adicional.
    # A existência real da fase/CPs é a fonte de verdade para "entregue"; isso
    # corrige flags antigos que podiam ficar defasados após substituições/mesclas.
    counterproof_delivered = bool(counterproof_phase and int(counterproof_phase.get("sample_count") or 0) > 0)
    # PENDENTE = ainda não tem contra-prova entregue E a rotina reprovou por Vv
    # ou espessura (ver _routine_failed_vv_or_thickness) — não depende mais só
    # de uma flag marcada no PDF, e sim do resultado técnico de fato.
    counterproof_state = "ENTREGUE" if counterproof_delivered else ("PENDENTE" if _routine_failed_vv_or_thickness(samples) else "NÃO")
    sample_count = sum(x["sample_count"] for x in phases)
    parse_warnings = _current_parse_warnings(cert, raw, samples)
    parse_status = "PARCIAL" if parse_warnings else "CARREGADO"
    business_warnings = _certificate_business_warnings(cert, raw)

    return {
        **cert,
        # Mantém todas as datas operacionais no objeto já carregado. Consumidores
        # por medição não podem usar apenas service_date, que guarda somente a
        # primeira data de certificados com vários dias de execução.
        "execution_dates": _certificate_execution_dates(cert, samples, docs),
        "sample_count": sample_count,
        "phase_count": len(phases),
        "final_phase": final.get("phase", ""),
        "final_status_source": "CONTRA_PROVA" if counterproof_delivered else ("ROTINA" if final else ""),
        "has_counterproof": counterproof_delivered,
        "counterproof_delivered": counterproof_delivered,
        "counterproof_state": counterproof_state,
        "mean_vv": final.get("vv_mean_pct"),
        "mean_thickness_cm": final.get("thickness_mean_cm"),
        "mean_ratio": final.get("ratio_mean_pct"),
        "status_vv": final.get("status_vv", ""),
        "status_thickness": final.get("status_thickness", ""),
        "overall_status": final.get("overall_status", ""),
        "matched_measurements": matched_count,
        "documents": docs,
        "duplicate_count": sum(1 for d in docs if str(d.get("status") or "").upper()=="DUPLICADO"),
        "has_duplicate": any(str(d.get("status") or "").upper()=="DUPLICADO" for d in docs),
        "parse_status": parse_status,
        "parse_warnings": parse_warnings,
        "business_warnings": business_warnings,
        "certificate_date": cert.get("extraction_date") or cert.get("service_date"),
        "raw": raw,
        "phases": phases,
    }


def _cert_stats(cert: dict[str, Any], include_samples: bool = False) -> dict[str, Any]:
    samples_by, docs_by, matches_by = _bulk_certificate_context([cert])
    cid = int(cert["id"])
    return _cert_stats_loaded(
        cert, samples_by.get(cid, []), docs_by.get(cid, []), matches_by.get(cid, 0), include_samples
    )

def certificate_summary(contractor="ALL", start=None, end=None, status="ALL", measurement: str = "", selected_numbers: list[str] | None = None) -> dict[str, Any]:
    # Certificados excluídos permanecem no banco como histórico, mas não entram
    # em indicadores, médias ou listas operacionais.
    where = ["is_active=1"]
    params = []
    if contractor != "ALL":
        where.append("contractor=?")
        params.append(contractor)
    # O filtro Mxx usa datas de execução (service_dates/CPs), e por isso é feito
    # depois do carregamento em lote. Sem Mxx, preserva o filtro histórico por data.
    if not measurement:
        if start:
            where.append("COALESCE(extraction_date,service_date)>=?")
            params.append(start)
        if end:
            where.append("COALESCE(extraction_date,service_date)<=?")
            params.append(end)
    w = " WHERE " + " AND ".join(where) if where else ""
    certs = rows(f"SELECT * FROM certificates{w} ORDER BY COALESCE(extraction_date,service_date) DESC,number DESC,kmi DESC", tuple(params))
    samples_by, docs_by, matches_by = _bulk_certificate_context(certs)
    if measurement:
        effective_start, effective_end, _ = _effective_cycle_range(measurement, start, end)
        filtered = []
        for c in certs:
            cid = int(c["id"])
            samples = samples_by.get(cid, [])
            dates = _certificate_execution_dates(c, samples, docs_by.get(cid, []))
            if any((not effective_start or d >= effective_start) and (not effective_end or d <= effective_end) for d in dates):
                filtered.append(c)
        certs = filtered
    detailed = [
        _cert_stats_loaded(c, samples_by.get(int(c["id"]), []), docs_by.get(int(c["id"]), []), matches_by.get(int(c["id"]), 0), False)
        for c in certs
    ]
    selected = {str(x).strip() for x in (selected_numbers or []) if str(x).strip()}
    if selected:
        detailed = [c for c in detailed if str(c.get("number") or "").strip() in selected]
    wanted_status = str(status or "ALL").upper().strip()
    if wanted_status in {"APROVADO", "REPROVADO"}:
        detailed = [c for c in detailed if str(c.get("overall_status") or "").upper() == wanted_status]
    finals = [c for c in detailed if c.get("final_phase")]
    vv = [c["mean_vv"] for c in finals if c.get("mean_vv") is not None]
    th = [c["mean_thickness_cm"] for c in finals if c.get("mean_thickness_cm") is not None]
    approved = sum(1 for c in detailed if c.get("overall_status") == "APROVADO")
    reproved = sum(1 for c in detailed if c.get("overall_status") == "REPROVADO")
    adjustments = max(0, len(detailed) - approved - reproved)
    cp_delivered = sum(1 for c in detailed if c.get("counterproof_delivered"))
    cp_pending = sum(1 for c in detailed if c.get("counterproof_state") == "PENDENTE")
    return {
        "total": len(detailed),
        "with_stats": len(finals),
        "approved": approved,
        "reproved": reproved,
        "adjustments": adjustments,
        "classified_total": approved + reproved + adjustments,
        "counterproof": cp_delivered,
        "counterproof_delivered": cp_delivered,
        "counterproof_pending": cp_pending,
        "sample_count": sum(int(c.get("sample_count") or 0) for c in detailed),
        "mean_vv": round(sum(vv) / len(vv), 2) if vv else None,
        "mean_thickness_cm": round(sum(th) / len(th), 2) if th else None,
        "recent": detailed[:6],
    }


def _financial_breakdown_from_rows(qr: list[dict[str, Any]]) -> dict[str, float]:
    out = {"approved": 0.0, "pending": 0.0, "reproved": 0.0, "unclassified": 0.0}
    for r in qr:
        value = _money(r.get("total_service"))
        st = (r.get("status_final") or "").upper().strip()
        if st.startswith("APROVADO"):
            out["approved"] += value
        elif st.startswith("P.") or "PEND" in st:
            out["pending"] += value
        elif "REP" in st or "REPROV" in st or "RETRAB" in st:
            out["reproved"] += value
        else:
            out["unclassified"] += value
    return out


def _trend_value(current: float, previous: float, *, mode: str, latest_date: str | None = None, comparison_date: str | None = None) -> dict[str, Any]:
    delta = current - previous
    if abs(delta) < 1e-7:
        delta = 0.0
    percent = (delta / abs(previous) * 100.0) if abs(previous) > 1e-9 else None
    return {
        "current": current,
        "previous": previous,
        "delta": delta,
        "percent": percent,
        "mode": mode,
        "latest_date": latest_date,
        "comparison_date": comparison_date,
    }


def _financial_monthly_series(qr: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    """Agrupa a produção financeira por mês de execução.

    A visão mensal usa as linhas da BD_QUALI e, por isso, não oscila a cada
    sincronização do mesmo dia. Cada mês representa a produção classificada
    naquele período (aprovado, pendente e reprovado).
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    for r in qr:
        d = _as_date(r.get("date"))
        if not d:
            continue
        grouped.setdefault(f"{d.year:04d}-{d.month:02d}", []).append(r)

    out: list[dict[str, Any]] = []
    for month in sorted(grouped):
        month_rows = grouped[month]
        fb = _financial_breakdown_from_rows(month_rows)
        out.append({
            "month": month,
            "total_service": sum(_money(r.get("total_service")) for r in month_rows),
            "approved": _money(fb.get("approved")),
            "pending": _money(fb.get("pending")),
            "reproved": _money(fb.get("reproved")),
            "unclassified": _money(fb.get("unclassified")),
            "records": len(month_rows),
        })
    if limit and len(out) > limit:
        out = out[-limit:]
    return out


def _financial_monthly(qr: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Alias legado da visão mensal, mantido para integrações anteriores."""
    return _financial_monthly_series(qr, limit=0)


def _financial_by_measurement_series(qr: list[dict[str, Any]], limit: int = 60) -> tuple[list[dict[str, Any]], int]:
    """Agrupa a produção financeira por medição (Ref./Linha de Medição).

    Complementa a visão mensal: em vez de somar por mês de execução, soma por
    medição — útil para achar rapidamente o total/andamento de uma medição
    específica, independente de quando cada CP foi lançado. Ordenado do maior
    para o menor valor total; se houver mais medições que `limit`, o restante
    fica de fora e o total de grupos é devolvido para a tela avisar o corte.
    """
    grouped: dict[str, list[dict[str, Any]]] = {}
    meta: dict[str, dict[str, Any]] = {}
    for r in qr:
        key = str(r.get("ref_measurement") or r.get("line_measurement") or "").strip()
        if not key:
            continue
        grouped.setdefault(key, []).append(r)
        if key not in meta:
            meta[key] = {
                "road": r.get("road"),
                "direction": r.get("direction"),
                "kmi": r.get("kmi"),
                "kmf": r.get("kmf"),
                "line_measurement": r.get("line_measurement"),
            }

    out: list[dict[str, Any]] = []
    for key, group_rows in grouped.items():
        fb = _financial_breakdown_from_rows(group_rows)
        out.append({
            "measurement": key,
            **meta.get(key, {}),
            "total_service": sum(_money(r.get("total_service")) for r in group_rows),
            "approved": _money(fb.get("approved")),
            "pending": _money(fb.get("pending")),
            "reproved": _money(fb.get("reproved")),
            "unclassified": _money(fb.get("unclassified")),
            "records": len(group_rows),
        })
    out.sort(key=lambda x: x["total_service"], reverse=True)
    total_groups = len(out)
    if limit and total_groups > limit:
        out = out[:limit]
    return out, total_groups


def _financial_trends(
    qr: list[dict[str, Any]], contractors: list[str], start: str | None = None, end: str | None = None, status: str = "ALL"
) -> dict[str, Any]:
    """Compara os dois meses mais recentes disponíveis no Dashboard.

    Desde a v3.8.18 a seta financeira deixou de representar a última
    sincronização ou o último dia. Isso evitava oscilações visuais a cada
    alteração da BD_QUALI. Agora a referência é sempre mês contra mês.
    """
    monthly = _financial_monthly_series(qr, limit=0)
    if len(monthly) < 2:
        return {}
    previous, latest = monthly[-2], monthly[-1]
    latest_date = latest["month"] + "-01"
    comparison_date = previous["month"] + "-01"
    out: dict[str, Any] = {
        "mode": "monthly",
        "latest_date": latest_date,
        "comparison_date": comparison_date,
        "latest_month": latest["month"],
        "comparison_month": previous["month"],
    }
    for key in ("total_service", "approved", "pending", "reproved"):
        out[key] = _trend_value(
            _money(latest.get(key)), _money(previous.get(key)), mode="monthly",
            latest_date=latest_date, comparison_date=comparison_date,
        )
    return out


def dashboard(contractor: str = "ALL", start: str | None = None, end: str | None = None, status: str = "ALL", measurement: str = "", selected_numbers: list[str] | None = None) -> dict[str, Any]:
    contractors = ["ARENA", "PAVIDEZ"] if contractor == "ALL" else [contractor]
    effective_start, effective_end, cycle_filter = _effective_cycle_range(measurement, start, end)
    totals = {k: 0.0 for k in ["total_service", "extension_m", "volume_mass_m3", "quantity_t", "cap_project_t", "proposed_retention"]}
    financial = {"approved": 0.0, "pending": 0.0, "reproved": 0.0, "unclassified": 0.0}
    official_sources = []
    warnings = []
    quality_rows = []

    for c in contractors:
        snap = row("SELECT * FROM quality_snapshots WHERE contractor=? ORDER BY id DESC LIMIT 1", (c,))
        summary = _snapshot_summary(snap)
        if snap:
            official_sources.append(
                {
                    "contractor": c,
                    "cell": snap.get("total_source_cell"),
                    "summary_source": summary.get("summary_source", ""),
                    "subtotal_cell": summary.get("subtotal_source_cell", ""),
                    "subtotal_excel": summary.get("subtotal_excel"),
                    "all_rows_total": summary.get("total_service_all_rows"),
                    "cap_source": summary.get("cap_source", ""),
                    "synced_at": snap.get("synced_at"),
                    "source_mtime": snap.get("source_mtime"),
                    "warning": snap.get("warning"),
                    "visible_records": snap.get("visible_records"),
                    "total_records": snap.get("total_records"),
                    "period_start": summary.get("period_start"),
                    "period_end": summary.get("period_end"),
                }
            )
            if snap.get("warning"):
                warnings.append(f"{c}: {snap.get('warning')}")

        # O raw_json é grande e não participa de nenhum indicador do Dashboard.
        # Buscar só as colunas utilizadas reduz muito o tráfego com o PostgreSQL.
        q = """SELECT contractor,date,road,direction,kmi,kmf,line_measurement,ref_measurement,
                       status_final,total_service,extension_m,volume_mass_m3,quantity_t,
                       cap_project_t,proposed_retention
                  FROM quality_rows WHERE contractor=?"""
        params = [c]
        if effective_start:
            q += " AND date>=?"
            params.append(effective_start)
        if effective_end:
            q += " AND date<=?"
            params.append(effective_end)
        qr = rows(q, tuple(params))
        wanted_status = str(status or "ALL").upper().strip()
        if wanted_status == "APROVADO":
            qr = [r for r in qr if str(r.get("status_final") or "").upper().strip().startswith("APROVADO")]
        elif wanted_status == "REPROVADO":
            qr = [r for r in qr if ("REP" in str(r.get("status_final") or "").upper() or "RETRAB" in str(r.get("status_final") or "").upper())]
        quality_rows.extend(qr)

        # Snapshots antigos podem guardar fórmula/cache inválido da aba RELATÓRIO.
        # Se houver divergência radical, as linhas da BD_QUALI recuperam o painel
        # imediatamente, sem esperar uma nova sincronização da planilha.
        snapshot_total = _money(snap.get("total_service")) if snap else 0.0
        all_rows_total = _money(summary.get("total_service_all_rows"))
        snapshot_plausible = bool(
            snap and (
                abs(all_rows_total) < 0.01
                or abs(snapshot_total - all_rows_total) <= max(1.0, abs(all_rows_total) * 0.20)
            )
        )
        # O resumo oficial da planilha inteira só é válido sem nenhum recorte.
        if not effective_start and not effective_end and snap and wanted_status == "ALL" and snapshot_plausible:
            for k in totals:
                totals[k] += _money(snap.get(k))
            financial["approved"] += _money(summary.get("approved_value"))
            financial["pending"] += _money(summary.get("pending_value"))
            financial["reproved"] += _money(summary.get("reproved_value"))
            financial["unclassified"] += _money(summary.get("unclassified_value"))
        else:
            if snap and not effective_start and not effective_end and wanted_status == "ALL" and not snapshot_plausible:
                warnings.append(
                    f"{c}: consolidado incompatível ({snapshot_total:.2f}); usada a soma completa da BD_QUALI ({all_rows_total:.2f})."
                )
            for r in qr:
                totals["total_service"] += _money(r.get("total_service"))
                totals["extension_m"] += _money(r.get("extension_m"))
                totals["volume_mass_m3"] += _money(r.get("volume_mass_m3"))
                totals["quantity_t"] += _money(r.get("quantity_t"))
                totals["cap_project_t"] += _money(r.get("cap_project_t"))
                totals["proposed_retention"] += _money(r.get("proposed_retention"))
            fb = _financial_breakdown_from_rows(qr)
            for k in financial:
                financial[k] += fb[k]

    statuses = Counter((str(r.get("status_final") or "SEM STATUS").strip() or "SEM STATUS") for r in quality_rows)

    # O Dashboard é a tela inicial do sistema. Uma falha em um indicador
    # secundário não deve derrubar a página inteira com HTTP 500.
    try:
        financial_monthly = _financial_monthly_series(quality_rows, limit=12)
    except Exception as exc:
        financial_monthly = []
        warnings.append(f"Visão mensal indisponível: {type(exc).__name__}: {exc}")
    try:
        financial_by_measurement, financial_by_measurement_total = _financial_by_measurement_series(quality_rows, limit=60)
    except Exception as exc:
        financial_by_measurement, financial_by_measurement_total = [], 0
        warnings.append(f"Visão por medição indisponível: {type(exc).__name__}: {exc}")
    try:
        financial_trends = {} if cycle_filter else _financial_trends(quality_rows, contractors, effective_start, effective_end, status)
    except Exception as exc:
        financial_trends = {}
        warnings.append(f"Tendência financeira indisponível: {type(exc).__name__}: {exc}")
    try:
        pending = pending_days(contractor, effective_start, effective_end)
    except Exception as exc:
        pending = []
        warnings.append(f"Pendências indisponíveis: {type(exc).__name__}: {exc}")
    try:
        cert = certificate_summary(contractor, effective_start, effective_end, status, measurement, selected_numbers)
    except Exception as exc:
        cert = {
            "total": 0, "with_stats": 0, "approved": 0, "reproved": 0, "adjustments": 0,
            "classified_total": 0, "counterproof": 0, "counterproof_delivered": 0,
            "counterproof_pending": 0, "sample_count": 0, "mean_vv": None,
            "mean_thickness_cm": None, "recent": [],
        }
        warnings.append(f"Resumo de certificados indisponível: {type(exc).__name__}: {exc}")
    return {
        "contractor": contractor,
        "status_filter": status,
        "measurement_filter": cycle_filter.get("measurement") if cycle_filter else "",
        "selected_certificates": sorted({str(x).strip() for x in (selected_numbers or []) if str(x).strip()}),
        "measurement_period": cycle_filter,
        "totals": totals,
        "financial": financial,
        "financial_trends": financial_trends,
        "financial_monthly": financial_monthly,
        "financial_by_measurement": financial_by_measurement,
        "financial_by_measurement_total": financial_by_measurement_total,
        "quality_records": len(quality_rows),
        "certificates": cert["total"],
        "pending_days": len(pending),
        "statuses": [{"status": k, "count": v} for k, v in statuses.most_common()],
        "sources": official_sources,
        "warnings": warnings,
        "certificate_summary": cert,
    }


def _has_vv_certificate(raw_value) -> bool:
    """Retorna True quando a linha do BD_QUALI já possui certificado VV/ESP.

    O número do certificado é mantido dentro de raw_json porque as planilhas
    ARENA/PAVIDEZ possuem layouts diferentes. Para pendência, a existência do
    número é suficiente: se uma execução de 15/07 possui Nº CERTIFICADO Vv,
    15/07 não pode aparecer como pendente.
    """
    if not raw_value:
        return False
    try:
        raw = json.loads(raw_value) if isinstance(raw_value, str) else dict(raw_value)
    except Exception:
        return False

    empty_values = {"", "0", "0.0", "-", "PENDENTE", "N/A", "NA", "NÃO", "NAO", "NAO ENCONTRADO", "NÃO ENCONTRADO", "NONE", "NULL"}
    for key, value in raw.items():
        # Most columns aren't certificate fields. Avoid normalizing hundreds of
        # unrelated headers for every historical spreadsheet row.
        if 'CERTIFICADO' not in str(key).upper():
            continue
        normalized = str(key).upper().replace("º", "").replace("°", "")
        normalized = " ".join(normalized.split())
        # Aceita rotina e contra-prova. Qualquer um deles comprova que já existe
        # um certificado de VV/espessura associado à data de execução.
        if "CERTIFICADO" not in normalized or "VV" not in normalized:
            continue
        if value is None:
            continue
        if str(value).strip().upper() not in empty_values:
            return True
    return False


def pending_days(contractor="ALL", start=None, end=None):
    params = []
    where = []
    if contractor != "ALL":
        where.append("contractor=?")
        params.append(contractor)
    if start:
        where.append("date>=?")
        params.append(start)
    if end:
        where.append("date<=?")
        params.append(end)
    w = " WHERE " + " AND ".join(where) if where else ""
    ms = rows(
        f"SELECT contractor,date,COUNT(*) lines,MIN(road) road FROM measurements{w} GROUP BY contractor,date ORDER BY date DESC",
        tuple(params),
    )

    # REGRA DE NEGÓCIO DA PENDÊNCIA:
    # 1) parte somente dos dias que realmente possuem execução na medição;
    # 2) um dia deixa de ser pendente se o BD_QUALI já possui Nº CERTIFICADO Vv
    #    naquela data de execução; OU
    # 3) se algum BI330 lido dos PDFs informa a mesma data em "Datas ex. serviço"
    #    / service_date / Data Aplicação dos CPs.
    #
    # Isso evita dois erros antigos: contar dias sem execução e ignorar certificados
    # existentes apenas porque o parser do PDF não conseguiu preencher service_date.
    contractor_filter = " AND c.contractor=?" if contractor != "ALL" else ""
    coverage_params = [contractor] if contractor != "ALL" else []

    covered = {
        (r["contractor"], r["covered_date"])
        for r in rows(
            f"""
            SELECT c.contractor, c.service_date AS covered_date
              FROM certificates c
             WHERE c.is_active=1 AND c.service_date IS NOT NULL{contractor_filter}
            UNION
            SELECT c.contractor, cs.application_date AS covered_date
              FROM certificate_samples cs
              JOIN certificates c ON c.id=cs.certificate_id
             WHERE c.is_active=1 AND cs.application_date IS NOT NULL{contractor_filter}
            """,
            tuple(coverage_params + coverage_params),
        )
        if r.get("covered_date")
    }

    # Inclui TODAS as "Datas ex. serviço" guardadas no raw_json. A coluna
    # service_date representa apenas a primeira data e não é suficiente para BIs
    # que cobrem dois ou mais dias quando os CPs não foram extraídos.
    cert_where = " WHERE is_active=1 AND contractor=?" if contractor != "ALL" else " WHERE is_active=1"
    cert_params = (contractor,) if contractor != "ALL" else ()
    for c in rows(f"SELECT contractor,raw_json FROM certificates{cert_where}", cert_params):
        try:
            raw = json.loads(c.get("raw_json") or "{}")
        except Exception:
            raw = {}
        for d in raw.get("service_dates") or []:
            if d:
                covered.add((c["contractor"], str(d)))

    # Vínculo formal Medição ↔ Certificado também é cobertura. É a fonte mais
    # forte quando um BI legado não guardou Data ex. serviço no cabeçalho.
    try:
        match_where = ["c.is_active=1", "m.date IS NOT NULL"]
        match_params: list[Any] = []
        if contractor != "ALL":
            match_where.append("c.contractor=?")
            match_params.append(contractor)
        for linked in rows(
            "SELECT DISTINCT c.contractor,m.date covered_date FROM matches x "
            "JOIN certificates c ON c.id=x.certificate_id "
            "JOIN measurements m ON m.id=x.measurement_id WHERE " + " AND ".join(match_where),
            tuple(match_params),
        ):
            if linked.get("covered_date"):
                covered.add((linked["contractor"], str(linked["covered_date"])[:10]))
    except Exception:
        pass

    # Legado: alguns registros (ex.: BI330-0169) foram importados sem service_date
    # e sem CPs, embora o próprio nome do PDF traga a(s) data(s) de execução.
    # Só usa esse fallback quando NÃO existe nenhuma data técnica no certificado.
    try:
        file_where = ["c.is_active=1", "c.service_date IS NULL",
                      "NOT EXISTS (SELECT 1 FROM certificate_samples s WHERE s.certificate_id=c.id AND s.application_date IS NOT NULL AND TRIM(s.application_date)<>'')"]
        file_params: list[Any] = []
        if contractor != "ALL":
            file_where.append("c.contractor=?")
            file_params.append(contractor)
        file_rows = rows(
            "SELECT c.id,c.contractor,c.raw_json,cf.file_name FROM certificates c "
            "JOIN certificate_files cf ON cf.certificate_id=c.id WHERE " + " AND ".join(file_where) +
            " AND UPPER(COALESCE(cf.status,'')) NOT IN ('EXCLUIDO','SUBSTITUIDO','DUPLICADO_REMOVIDO')",
            tuple(file_params),
        )
        by_cert_files: dict[int, dict[str, Any]] = {}
        for item in file_rows:
            cid = int(item["id"])
            bucket = by_cert_files.setdefault(cid, {"contractor": item["contractor"], "raw_json": item.get("raw_json"), "names": []})
            bucket["names"].append(item.get("file_name") or "")
        for bucket in by_cert_files.values():
            try:
                raw = json.loads(bucket.get("raw_json") or "{}")
            except Exception:
                raw = {}
            if [x for x in (raw.get("service_dates") or []) if x]:
                continue
            for name in bucket["names"]:
                for d in _dates_from_certificate_filename(name):
                    covered.add((bucket["contractor"], d))
    except Exception:
        pass

    q_where = []
    q_params = []
    if contractor != "ALL":
        q_where.append("contractor=?")
        q_params.append(contractor)
    if start:
        q_where.append("date>=?")
        q_params.append(start)
    if end:
        q_where.append("date<=?")
        q_params.append(end)
    q_where.append("date IS NOT NULL")
    qw = " WHERE " + " AND ".join(q_where)
    for q in rows(f"SELECT contractor,date,raw_json FROM quality_rows{qw}", tuple(q_params)):
        if (q['contractor'], q['date']) in covered:
            continue
        if _has_vv_certificate(q.get("raw_json")):
            covered.add((q["contractor"], q["date"]))

    out = []
    for m in ms:
        if (m["contractor"], m["date"]) in covered:
            continue
        cycle = measurement_cycle(m.get("date")) or {}
        out.append({**m, **cycle, "status": "PENDENTE CERTIFICADO"})
    return out




def _kit_delivery_state_query(item: dict[str, Any]) -> tuple[str, bool]:
    explicit = norm_text(item.get("delivery_status"))
    try:
        raw = json.loads(item.get("raw_json") or "{}")
    except Exception:
        raw = {}
    has_column = raw.get("_qualimatch_entrega_coluna") is True
    raw_value = ""
    for key, value in raw.items():
        if str(key).startswith("_qualimatch_"):
            continue
        if norm_header(key) in {"ENTREGA", "STATUS ENTREGA"}:
            has_column = True
            raw_value = norm_text(value)
            break
    value = explicit or raw_value
    if value:
        has_column = True
    if value.startswith("NAO ENTREGUE") or value in {"NAO", "N ENTREGUE"}:
        return "NAO_ENTREGUE", has_column
    if value == "ENTREGUE" or ("ENTREGUE" in value and "NAO" not in value):
        return "ENTREGUE", has_column
    return "SEM_INFORMACAO", has_column

# Compatibilidade documental legado: delivery_status,raw_json,seq FROM kit_rows
def contractor_pending_measurements(contractor="ALL", start=None, end=None):
    """Pendências da Contratada, incluindo validação de Data da d.KIT.

    Regra adicional v3.8.20:
    - linha de kit sem Data Aplicação entra como pendência quando o trecho também
      não está completo;
    - se a Data estiver vazia MAS KMI e KMF estiverem preenchidos, não cria
      pendência por data (regra operacional solicitada).
    """
    base = pending_measurements(contractor, start, end)

    where = ["COALESCE(is_active,1)=1", "application_date IS NOT NULL", "TRIM(application_date)<>''"]
    params = []
    if contractor != "ALL":
        where.append("contractor=?"); params.append(contractor)
    if start:
        where.append("application_date>=?"); params.append(start)
    if end:
        where.append("application_date<=?"); params.append(end)
    kit_rows = rows(
        "SELECT contractor,application_date,delivery_status,raw_json,seq,kmi,kmf,road FROM kit_rows WHERE " + " AND ".join(where),
        tuple(params),
    ) if base else []
    by_key: dict[tuple[str,str], list[dict[str,Any]]] = {}
    for item in kit_rows:
        key=(str(item["contractor"]),str(item["application_date"])[:10])
        by_key.setdefault(key,[]).append(dict(item))

    remaining=[]
    delivery_meta: dict[tuple[str,str], dict[str,Any]] = {}
    for m in base:
        key=(str(m["contractor"]),str(m["date"])[:10])
        kits=by_key.get(key,[])
        if not kits:
            remaining.append(m)
            delivery_meta[key]={"delivery_status":"SEM KIT","kit_sequences":[]}
            continue
        infos=[_kit_delivery_state_query(k) for k in kits]
        states=[state for state,_ in infos]
        has_column=any(flag for _,flag in infos)
        delivered=(all(state=="ENTREGUE" for state in states) if has_column else True)
        delivery_meta[key]={
            "delivery_status":"ENTREGUE" if delivered else ("NÃO ENTREGUE" if "NAO_ENTREGUE" in states else "SEM INFORMAÇÃO"),
            "kit_sequences":[str(k.get("seq") or "") for k in kits if k.get("seq")],
        }
        if not delivered:
            remaining.append(m)

    grouped = {}
    for m in remaining:
        key = (m["contractor"], str(m["date"]))
        cycle = measurement_cycle(m.get("date")) or {}
        meta=delivery_meta.get((str(m["contractor"]),str(m["date"])[:10]),{})
        g = grouped.setdefault(key, {
            "contractor": m["contractor"], "date": str(m["date"]), "lines": 0,
            "roads": set(), "kmi_values": [], "kmf_values": [], "status": "PENDENTE CONTRATADA",
            "delivery_status":meta.get("delivery_status","SEM KIT"),
            "kit_sequences":meta.get("kit_sequences",[]),
            "pending_reason":"SEM_KIT_ENTREGUE",
            **cycle,
        })
        g["lines"] += 1
        if m.get("road"):
            g["roads"].add(str(m["road"]))
        if m.get("kmi") is not None:
            g["kmi_values"].append(m["kmi"])
        if m.get("kmf") is not None:
            g["kmf_values"].append(m["kmf"])

    out=[]
    for g in grouped.values():
        roads=sorted(g.pop("roads"))
        kmis=g.pop("kmi_values"); kmfs=g.pop("kmf_values")
        g["road"]=" / ".join(roads) if roads else None
        g["kmi"]=min(kmis) if kmis else None
        g["kmf"]=max(kmfs) if kmfs else None
        out.append(g)

    # Validação de preenchimento da própria d.KIT. Linha sem data é uma pendência,
    # exceto quando o trecho já está completo com KMI + KMF.
    missing_where = ["COALESCE(is_active,1)=1", "(application_date IS NULL OR TRIM(application_date)='')"]
    missing_params: list[Any] = []
    if contractor != "ALL":
        missing_where.append("contractor=?")
        missing_params.append(contractor)
    try:
        missing_rows = rows(
            "SELECT id,contractor,seq,application_date,road,kmi,kmf,delivery_status,raw_json FROM kit_rows WHERE " + " AND ".join(missing_where) + " ORDER BY source_row DESC",
            tuple(missing_params),
        )
    except Exception:
        missing_rows = []
    for k in missing_rows:
        # Defesa extra para mocks/integrações que retornem linhas fora do WHERE.
        if str(k.get("application_date") or "").strip():
            continue
        if k.get("kmi") is not None and k.get("kmf") is not None:
            continue
        out.append({
            "contractor": k.get("contractor"),
            "date": None,
            "lines": 1,
            "road": k.get("road"),
            "kmi": k.get("kmi"),
            "kmf": k.get("kmf"),
            "status": "PENDENTE CONTRATADA",
            "delivery_status": "DATA NÃO PREENCHIDA",
            "kit_sequences": [str(k.get("seq") or k.get("id") or "")],
            "measurement": None,
            "measurement_number": None,
            "measurement_start": None,
            "measurement_end": None,
            "pending_reason": "DATA_NAO_PREENCHIDA",
        })

    out.sort(key=lambda x: (x.get("date") is not None, str(x.get("date") or ""), str(x.get("contractor") or "")), reverse=True)
    return out


def pending_measurements(contractor="ALL", start=None, end=None):
    """Retorna cada linha real de medição sem cobertura por certificado.

    Diferente de pending_days(), não agrupa por dia: preserva line_measurement,
    rodovia e trecho de cada registro para a visão da Contratada.
    """
    # Reaproveita exatamente a mesma regra de cobertura já validada em pending_days.
    pending_keys = {(x["contractor"], str(x["date"])) for x in pending_days(contractor, start, end)}
    where, params = [], []
    if contractor != "ALL":
        where.append("contractor=?"); params.append(contractor)
    if start:
        where.append("date>=?"); params.append(start)
    if end:
        where.append("date<=?"); params.append(end)
    where.append("date IS NOT NULL")
    w = " WHERE " + " AND ".join(where)
    data = rows(
        f"""SELECT id,contractor,source_row,line_measurement,date,road,direction,kmi,kmf,lane,ref_measurement
               FROM measurements{w}
              ORDER BY date DESC,source_row DESC""", tuple(params)
    )
    out=[]
    for m in data:
        if (m["contractor"], str(m["date"])) not in pending_keys:
            continue
        out.append({**m, "status": "PENDENTE CERTIFICADO"})
    return out


def _measurement_filter(contractor="ALL", search="") -> tuple[str, list[Any]]:
    where = []
    params: list[Any] = []
    if contractor != "ALL":
        where.append("contractor=?")
        params.append(contractor)
    if search:
        where.append("(road LIKE ? OR ref_measurement LIKE ? OR line_measurement LIKE ? OR date LIKE ?)")
        s = f"%{search}%"
        params += [s, s, s, s]
    return (" WHERE " + " AND ".join(where) if where else ""), params


def count_measurements(contractor="ALL", search="") -> int:
    where, params = _measurement_filter(contractor, search)
    found = row(f"SELECT COUNT(*) total FROM measurements{where}", tuple(params))
    return int((found or {}).get("total") or 0)


def list_measurements(contractor="ALL", search="", limit=500, offset=0):
    where, params = _measurement_filter(contractor, search)
    return rows(
        f"SELECT * FROM measurements{where} ORDER BY date DESC,source_row DESC LIMIT ? OFFSET ?",
        tuple(params + [max(1, int(limit)), max(0, int(offset))]),
    )


def _segment_bounds(value: str) -> tuple[int | None, int | None]:
    """Lê filtros como 405+845, 405+845 a 406+100 ou Km 405."""
    txt = (value or "").strip()
    if not txt:
        return None, None
    tokens = re.findall(r"\d{1,4}\s*\+\s*\d{1,3}", txt)
    vals = [station(x) for x in tokens]
    vals = [x for x in vals if x is not None]
    if vals:
        return (vals[0], vals[0]) if len(vals) == 1 else (min(vals[0], vals[1]), max(vals[0], vals[1]))
    # Um número inteiro curto é tratado como quilômetro (ex.: 405 -> Km 405).
    m = re.search(r"(?:KM\s*)?(\d{1,4})(?![+\d])", txt, re.I)
    if m:
        km = int(m.group(1)) * 1000
        return km, km + 999
    return None, None


def _matches_segment(cert: dict[str, Any], segment_filter: str) -> bool:
    if not segment_filter:
        return True
    qroad = norm_road(segment_filter) if re.search(r"(?:BR|PR)\s*[- ]?\s*\d{2,3}", segment_filter, re.I) else ""
    if qroad and cert.get("road") != qroad:
        return False
    start, end = _segment_bounds(segment_filter)
    if start is None or end is None:
        # Se o usuário digitou só a rodovia, a comparação acima já resolveu.
        return bool(qroad)
    kmi, kmf = cert.get("kmi"), cert.get("kmf")
    if kmi is None or kmf is None:
        return False
    lo, hi = sorted((int(kmi), int(kmf)))
    return lo <= end and hi >= start


def list_certificates(
    contractor="ALL", search="", limit=300, sort="newest", cp_min: int | None = None,
    cp_max: int | None = None, status="ALL", road="", segment="", number="",
    vv_status="ALL", thickness_status="ALL", measurement: str = "",
    counterproof: str = "ALL", date_issue: str = "ALL", offset: int = 0,
    with_total: bool = False,
):
    where = ["is_active=1"]
    params: list[Any] = []
    if contractor != "ALL":
        where.append("contractor=?")
        params.append(contractor)
    if search:
        where.append("(number LIKE ? OR road LIKE ? OR service_date LIKE ? OR extraction_date LIKE ? OR trace_approved LIKE ?)")
        needle = f"%{search}%"
        params += [needle, needle, needle, needle, needle]
    if road:
        where.append("road=?")
        params.append(norm_road(road))
    if number:
        where.append("number=?")
        params.append(number)
    w = " WHERE " + " AND ".join(where)
    order = "ASC" if str(sort).lower() in {"oldest", "asc", "antigo"} else "DESC"
    raw_data = rows(
        f"""SELECT * FROM certificates{w}
             ORDER BY CASE WHEN COALESCE(extraction_date,service_date) IS NULL THEN 1 ELSE 0 END ASC,
                      COALESCE(extraction_date,service_date) {order}, number {order}, kmi {order}""",
        tuple(params),
    )

    out: list[dict[str, Any]] = []
    wanted_status = (status or "ALL").upper().strip()
    wanted_vv = (vv_status or "ALL").upper().strip()
    wanted_thickness = (thickness_status or "ALL").upper().strip()
    wanted_counterproof = (counterproof or "ALL").upper().strip()
    wanted_date_issue = (date_issue or "ALL").upper().strip()
    # Primeiro elimina por segmento (não depende de CP) e então busca os dados
    # relacionados de todos os candidatos em apenas três consultas.
    candidates = [x for x in raw_data if not segment or _matches_segment(x, segment)]
    samples_by, docs_by, matches_by = _bulk_certificate_context(candidates)
    if measurement:
        candidates = [x for x in candidates if _certificate_in_measurement(x, samples_by.get(int(x["id"]), []), measurement, docs_by.get(int(x["id"]), []))]
    for item in candidates:
        cid = int(item["id"])
        cert = _cert_stats_loaded(item, samples_by.get(cid, []), docs_by.get(cid, []), matches_by.get(cid, 0), False)
        cp_count = int(cert.get("sample_count") or 0)
        if cp_min is not None and cp_count < int(cp_min):
            continue
        if cp_max is not None and cp_count > int(cp_max):
            continue
        overall = (cert.get("overall_status") or "").upper().strip()
        if wanted_status == "APROVADO" and overall != "APROVADO":
            continue
        if wanted_status == "REPROVADO" and overall != "REPROVADO":
            continue
        if wanted_status in {"SEM_RESULTADO", "SEM RESULTADO"} and overall:
            continue

        # v3.8.9 — filtros técnicos independentes. Usam sempre a fase final
        # do certificado, portanto uma contra-prova entregue passa a comandar
        # o filtro da mesma forma que já comanda o status técnico exibido.
        cert_vv = (cert.get("status_vv") or "").upper().strip()
        cert_thickness = (cert.get("status_thickness") or "").upper().strip()
        if wanted_vv == "APROVADO" and cert_vv != "APROVADO":
            continue
        if wanted_vv == "REPROVADO" and cert_vv != "REPROVADO":
            continue
        if wanted_vv in {"SEM_RESULTADO", "SEM RESULTADO"} and cert_vv:
            continue
        if wanted_thickness == "APROVADO" and cert_thickness != "APROVADO":
            continue
        if wanted_thickness == "REPROVADO" and cert_thickness != "REPROVADO":
            continue
        if wanted_thickness in {"SEM_RESULTADO", "SEM RESULTADO"} and cert_thickness:
            continue

        # Contra-prova (CP): reaproveita o mesmo counterproof_state já usado no
        # selo "Contra-prova" exibido na listagem — ENTREGUE / PENDENTE / NÃO.
        cert_counterproof = (cert.get("counterproof_state") or "").upper().strip()
        if wanted_counterproof == "ENTREGUE" and cert_counterproof != "ENTREGUE":
            continue
        if wanted_counterproof == "PENDENTE" and cert_counterproof != "PENDENTE":
            continue
        if wanted_counterproof in {"NAO", "NÃO"} and cert_counterproof != "NÃO":
            continue

        # Datas inconsistentes: mesmo aviso já calculado em business_warnings
        # (ex.: recebimento no laboratório antes da extração dos CPs) que hoje
        # só aparecia como destaque visual na linha; agora também é filtrável.
        if wanted_date_issue in {"INCONSISTENTE", "SIM"} and not cert.get("business_warnings"):
            continue

        out.append(cert)
        if not with_total and not offset and len(out) >= max(1, int(limit)):
            break

    total = len(out)
    summary = {
        "approved": sum(x.get("overall_status") == "APROVADO" for x in out),
        "reproved": sum(x.get("overall_status") == "REPROVADO" for x in out),
        "counterproof": sum(bool(x.get("counterproof_delivered") or x.get("has_counterproof")) for x in out),
        "partial": sum(x.get("parse_status") == "PARCIAL" for x in out),
        "loaded": sum(str(x.get("parse_status") or "").upper() in {"OK", "CARREGADO"} for x in out),
        "duplicates": sum(bool(x.get("has_duplicate")) for x in out),
    }
    summary["adjustments"] = max(0, total - summary["approved"] - summary["reproved"])
    page_items = out[max(0, int(offset)):max(0, int(offset)) + max(1, int(limit))]
    dup_ctx = _number_duplicate_context(page_items)
    for item in page_items:
        item.update(dup_ctx.get(int(item["id"]), {
            "number_duplicate_count": 1, "is_latest_version": True,
            "latest_version_id": int(item["id"]), "latest_version_parsed_at": item.get("parsed_at"),
        }))

    if with_total:
        return {"items": page_items, "total": total, "summary": summary}
    return page_items


def certificate_filter_options(contractor="ALL") -> dict[str, Any]:
    where = ["c.is_active=1"]
    params: list[Any] = []
    if contractor != "ALL":
        where.append("c.contractor=?")
        params.append(contractor)
    w = " WHERE " + " AND ".join(where)
    roads_found = rows(
        f"SELECT DISTINCT c.road road FROM certificates c{w} AND COALESCE(c.road,'')<>'' ORDER BY c.road",
        tuple(params),
    )
    max_row = row(
        f"""SELECT MAX(COALESCE(x.n,0)) max_cps FROM certificates c
             LEFT JOIN (SELECT certificate_id,COUNT(*) n FROM certificate_samples GROUP BY certificate_id) x ON x.certificate_id=c.id
             {w}""",
        tuple(params),
    )
    numbers_found = rows(
        f"SELECT DISTINCT c.number number FROM certificates c{w} AND COALESCE(c.number,'')<>'' ORDER BY c.number",
        tuple(params),
    )
    return {
        "roads": [x["road"] for x in roads_found],
        "numbers": [x["number"] for x in numbers_found],
        "measurements": measurement_cycle_options(contractor),
        "max_cps": int((max_row or {}).get("max_cps") or 0),
    }


def certificate_detail(cert_id: int):
    c = row("SELECT * FROM certificates WHERE id=? AND is_active=1", (cert_id,))
    return _cert_stats(c, True) if c else None


def certificate_document(doc_id: int):
    return row("SELECT * FROM certificate_files WHERE id=?", (doc_id,))


def count_sync_logs(date_filter: str | None = None) -> int:
    if date_filter:
        found = row("SELECT COUNT(*) total FROM sync_log WHERE created_at LIKE ?", (str(date_filter)[:10] + "%",))
    else:
        found = row("SELECT COUNT(*) total FROM sync_log")
    return int((found or {}).get("total") or 0)


def sync_logs(limit=200, date_filter: str | None = None, offset: int = 0):
    if date_filter:
        return rows("SELECT * FROM sync_log WHERE created_at LIKE ? ORDER BY id DESC LIMIT ? OFFSET ?", (str(date_filter)[:10] + "%", limit, offset))
    return rows("SELECT * FROM sync_log ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset))


def diagnostics():
    data = []
    for c in ("ARENA", "PAVIDEZ"):
        s = row("SELECT * FROM quality_snapshots WHERE contractor=? ORDER BY id DESC LIMIT 1", (c,))
        if s:
            s["summary"] = _snapshot_summary(s)
            data.append(s)
    return data


def _kit_filter(contractor: str = "ALL", search: str = "", status: str = "ALL",
                road: str = "", period: str = "", service: str = "",
                start: str | None = None, end: str | None = None) -> tuple[str, list[Any]]:
    where: list[str] = ["COALESCE(is_active,1)=1"]
    params: list[Any] = []
    if contractor != "ALL":
        where.append("contractor=?"); params.append(contractor)
    if search.strip():
        q = f"%{search.strip().upper()}%"
        where.append("(UPPER(seq) LIKE ? OR UPPER(service) LIKE ? OR UPPER(mix_project) LIKE ? OR UPPER(road) LIKE ? OR UPPER(period) LIKE ? OR UPPER(status) LIKE ?)")
        params.extend([q] * 6)
    if status and status != "ALL":
        where.append("UPPER(COALESCE(status,''))=?"); params.append(status.upper())
    if road.strip():
        where.append("UPPER(COALESCE(road,''))=?"); params.append(road.strip().upper())
    if period.strip():
        where.append("UPPER(COALESCE(period,''))=?"); params.append(period.strip().upper())
    if service.strip():
        where.append("UPPER(COALESCE(service,''))=?"); params.append(service.strip().upper())
    if start:
        where.append("application_date>=?"); params.append(start)
    if end:
        where.append("application_date<=?"); params.append(end)
    return " WHERE " + " AND ".join(where), params


def count_kits(contractor: str = "ALL", search: str = "", status: str = "ALL",
               road: str = "", period: str = "", service: str = "",
               start: str | None = None, end: str | None = None) -> int:
    where, params = _kit_filter(contractor, search, status, road, period, service, start, end)
    found = row(f"SELECT COUNT(*) total FROM kit_rows{where}", tuple(params))
    return int((found or {}).get("total") or 0)


def list_kits(contractor: str = "ALL", search: str = "", limit: int = 1000,
              sort: str = "newest", status: str = "ALL", road: str = "", period: str = "",
              service: str = "", start: str | None = None, end: str | None = None,
              offset: int = 0) -> list[dict[str, Any]]:
    sql_where, params = _kit_filter(contractor, search, status, road, period, service, start, end)
    order = "ASC" if str(sort).lower()=="oldest" else "DESC"
    params.extend([max(1, int(limit)), max(0, int(offset))])
    return rows(
        f"""SELECT id,contractor,source_row,seq,service,application_date,mix_project,period,road,kmi,kmf,
                    receipt_date,delivery_status,status,status_1,status_2,status_3,status_4,status_5,status_6,status_7,status_8,sin_retro
               FROM kit_rows{sql_where}
              ORDER BY application_date {order},source_row {order} LIMIT ? OFFSET ?""",
        tuple(params),
    )


def kit_filter_options(contractor: str = "ALL") -> dict[str, list[str]]:
    """Opções estáveis dos filtros do portal Contratada.

    Situação e período são listas operacionais fechadas. Rodovias vêm da d.KIT
    já normalizadas e são consultadas diretamente no banco para não depender de
    outros campos/linhas da tabela.
    """
    where = " WHERE COALESCE(is_active,1)=1"
    params: tuple[Any, ...] = ()
    if contractor != "ALL":
        where += " AND contractor=?"
        params = (contractor,)
    road_rows = rows(f"SELECT DISTINCT road FROM kit_rows{where} ORDER BY road", params)
    roads = []
    seen = set()
    for item in road_rows:
        value = str(item.get("road") or "").strip()
        if not value or value in {"-", "—"}:
            continue
        key = value.upper()
        if key not in seen:
            seen.add(key)
            roads.append(value)
    roads.sort(key=lambda v: v.upper())
    return {
        "roads": roads,
        "statuses": ["OK", "INCOMPLETO", "PENDENTE"],
        "periods": ["DIURNO", "NOTURNO"],
    }

def kit_summary(contractor: str = "ALL") -> dict[str, Any]:
    where = " WHERE COALESCE(is_active,1)=1"
    params: tuple[Any, ...] = ()
    if contractor != "ALL":
        where += " AND contractor=?"
        params = (contractor,)
    data = rows(
        f"""SELECT contractor,application_date,receipt_date,delivery_status,status,status_1,status_2,status_3,status_4,
                    status_5,status_6,status_7,status_8,sin_retro,raw_json FROM kit_rows{where}""",
        params,
    )
    status_counts = Counter((x.get("status") or "SEM STATUS").upper() for x in data)
    dates = [x.get("application_date") for x in data if x.get("application_date")]
    controls = [f"status_{i}" for i in range(1, 9)] + ["sin_retro"]
    control_summary: dict[str, dict[str, int]] = {}
    for field in controls:
        vals = [str(x.get(field) or "").strip().upper() for x in data]
        applicable = [v for v in vals if v and v not in {"N/A", "NA", "N.A."}]
        control_summary[field] = {
            "ok": sum(v == "OK" for v in applicable),
            "pending": sum(v != "OK" for v in applicable),
            "applicable": len(applicable),
        }
    by_contractor = Counter(x.get("contractor") or "" for x in data)
    # Entregas são agregadas por mês. Data Recebimento é preferencial; quando
    # a contratada não a preenche (caso observado na Pavidez), Data Aplicação
    # entra como fallback para que a entrega não desapareça do gráfico.
    delivery_months = Counter()
    delivery_date_sources = Counter()
    for x in data:
        delivery_state, has_delivery_column = _kit_delivery_state_query(dict(x))
        # Se a fonte possui a coluna ENTREGA, o gráfico de entregas só conta
        # linhas realmente marcadas como Entregue. Planilhas antigas preservam
        # o comportamento histórico por data de recebimento/aplicação.
        if has_delivery_column and delivery_state != "ENTREGUE":
            continue
        d = str(x.get("receipt_date") or x.get("application_date") or "")
        if len(d) >= 7:
            delivery_months[d[:7]] += 1
            delivery_date_sources["receipt" if x.get("receipt_date") else "application"] += 1

    # v3.8.18 — a visão geral da Contratada não usa uma meta artificial.
    # O gráfico apresenta somente o que foi efetivamente entregue em cada mês.
    months = sorted(delivery_months)
    deliveries_monthly = [
        {"month": m, "count": delivery_months.get(m, 0)}
        for m in months
    ]
    # "Recebidos" representa linhas efetivamente preenchidas da d.KIT.
    # Não usamos Data Recebimento como critério operacional porque esse campo
    # pode ficar em branco mesmo quando o kit já foi recebido/processado.
    filled_rows = sum(
        1 for x in data
        if any(x.get(k) not in (None, "") for k in (
            "application_date", "status", "status_1", "status_2", "status_3",
            "status_4", "status_5", "status_6", "status_7", "status_8", "sin_retro"
        ))
    )
    return {
        "total": len(data),
        "received": filled_rows,
        "filled_rows": filled_rows,
        # Mantido apenas como diagnóstico/compatibilidade. Não alimenta o card Recebidos.
        "without_receipt": sum(1 for x in data if not x.get("receipt_date")),
        "ok": status_counts.get("OK", 0),
        "incomplete": status_counts.get("INCOMPLETO", 0),
        "pending": status_counts.get("PENDENTE", 0),
        "error": status_counts.get("ERRO", 0),
        "last_application_date": max(dates) if dates else None,
        "by_contractor": dict(by_contractor),
        "controls": control_summary,
        "deliveries": deliveries_monthly,
        "delivery_date_sources": dict(delivery_date_sources),
    }



def _bv_doc_where(contractor: str = "ALL", search: str = "", extension: str = "") -> tuple[list[str], list[Any]]:
    where=["COALESCE(d.is_active,1)=1"]
    params: list[Any]=[]
    if contractor != "ALL":
        where.append("d.contractor=?"); params.append(contractor)
    if search.strip():
        q=f"%{search.strip().upper()}%"
        where.append("(UPPER(d.file_name) LIKE ? OR UPPER(d.relative_path) LIKE ? OR UPPER(d.measurement_label) LIKE ?)")
        params += [q,q,q]
    if extension.strip():
        ext=extension.strip().lower(); ext=ext if ext.startswith('.') else '.'+ext
        where.append("LOWER(d.extension)=?"); params.append(ext)
    return where, params


def bv_document_groups(contractor: str = "ALL", search: str = "", extension: str = "") -> list[dict[str, Any]]:
    where, params = _bv_doc_where(contractor, search, extension)
    w=" WHERE "+" AND ".join(where)
    grouped=rows(
        f"""SELECT d.measurement_label,d.top_folder,COUNT(*) count
               FROM bv_documents d{w}
              GROUP BY d.measurement_label,d.top_folder""", tuple(params)
    )
    counts: dict[str,int]={}
    for x in grouped:
        key=str(x.get('measurement_label') or x.get('top_folder') or '(sem medição)')
        counts[key]=counts.get(key,0)+int(x.get('count') or 0)
    return [{"group":k,"count":counts[k]} for k in sorted(counts, key=lambda x: x.upper())]


BV_REPORT_CATEGORIES = ("VV/ESP", "CA", "LIGANTE", "DUI", "AGREGADOS", "OUTROS")


def _bv_report_category(file_name: str, relative_path: str) -> str:
    name = norm_header(file_name or "")
    path = norm_header(relative_path or "")
    if "DANO POR UMIDADE INDUZIDA" in path or re.search(r"(?:^|\W)07\.?\s+.*(?:DUI|UMIDADE INDUZIDA)", path): return "DUI"
    if re.search(r"(?:^|\W)DUI(?:\W|$)", name): return "DUI"
    if re.search(r"(?:^|\W)(?:AGREG\w*|AGRE|GRAN\w*)(?:\W|$)", name): return "AGREGADOS"
    if "CARACTERIZACAO AGREGADOS" in path and re.search(r"(?:^|\W)ME(?:\W|$)", name): return "AGREGADOS"
    if re.search(r"(?:^|\W)(?:LIG\w*|CAP\w*)(?:\W|$)", name): return "LIGANTE"
    if re.search(r"(?:^|\W)CA(?:\W|$)", name): return "CA"
    if "04.0 VV - CERTIFICADOS" in path and any(token in name for token in ("BI330", "BI 330", "VV", "VAZIO", "ESPESSURA")): return "VV/ESP"
    return "OUTROS"


def bv_general_report(contractor: str = "ALL") -> dict[str, Any]:
    """Consolida todos os arquivos recebidos da BV por medição e tipo."""
    where, params = ["1=1"], []
    if contractor != "ALL":
        where.append("d.contractor=?"); params.append(contractor)
    docs = rows("SELECT id,contractor,file_path,file_name,relative_path,measurement_label,top_folder,extension,size FROM bv_documents d WHERE " + " AND ".join(where) + " ORDER BY relative_path", tuple(params))
    grouped: dict[str, dict[str, Any]] = {}
    totals = {category: 0 for category in BV_REPORT_CATEGORIES}
    for doc in docs:
        file_path = str(doc.get("file_path") or "")
        if file_path and not _path_is_file(file_path):
            continue
        relative = norm_header(str(doc.get("relative_path") or ""))
        if str(doc.get("extension") or "").lower() != ".pdf" or "FICHAS FISICAS" in relative:
            continue
        measurement = str(doc.get("measurement_label") or doc.get("top_folder") or "(sem medição)")
        if not re.fullmatch(r"M\s*0*\d+", measurement, re.I):
            continue
        category = _bv_report_category(str(doc.get("file_name") or ""), str(doc.get("relative_path") or ""))
        if category == "OUTROS":
            continue
        item = grouped.setdefault(measurement, {"measurement": measurement, "total": 0, "counts": {name: 0 for name in BV_REPORT_CATEGORIES}, "files": {name: [] for name in BV_REPORT_CATEGORIES}})
        if any(str(existing.get("relative_path")) == str(doc.get("relative_path")) for existing in item["files"][category]):
            continue
        item["total"] += 1; item["counts"][category] += 1; item["files"][category].append(doc); totals[category] += 1
    def measurement_key(item: dict[str, Any]) -> tuple[int, str]:
        match = re.fullmatch(r"M\s*0*(\d+)", item["measurement"], re.I)
        return (int(match.group(1)) if match else -1, item["measurement"].upper())
    return {"categories": list(BV_REPORT_CATEGORIES), "totals": totals, "total": sum(totals.values()), "measurements": sorted(grouped.values(), key=measurement_key, reverse=True)}


def count_bv_documents(contractor: str = "ALL", search: str = "", measurement: str = "", extension: str = "") -> int:
    where, params = _bv_doc_where(contractor, search, extension)
    if measurement.strip():
        where.append("UPPER(COALESCE(NULLIF(d.measurement_label,''),NULLIF(d.top_folder,''),'(SEM MEDIÇÃO)'))=?")
        params.append(measurement.strip().upper())
    found = row("SELECT COUNT(*) total FROM bv_documents d WHERE " + " AND ".join(where), tuple(params))
    return int((found or {}).get("total") or 0)


def list_bv_documents(contractor: str = "ALL", search: str = "", measurement: str = "", extension: str = "", limit: int = 3000, offset: int = 0) -> list[dict[str, Any]]:
    where, params = _bv_doc_where(contractor, search, extension)
    if measurement.strip():
        where.append("UPPER(COALESCE(NULLIF(d.measurement_label,''),NULLIF(d.top_folder,''),'(SEM MEDIÇÃO)'))=?")
        params.append(measurement.strip().upper())
    w=" WHERE "+" AND ".join(where)
    params.extend([min(max(int(limit),1),5000), max(0, int(offset))])
    return rows(
        f"""SELECT d.*,cf.status certificate_status,cf.certificate_id,c.number certificate_number
               FROM bv_documents d
               LEFT JOIN certificate_files cf ON cf.contractor=d.contractor AND cf.file_path=d.file_path
               LEFT JOIN certificates c ON c.id=cf.certificate_id
               {w}
              ORDER BY d.relative_path LIMIT ? OFFSET ?""", tuple(params)
    )


def bv_document(doc_id: int, include_archived: bool = False) -> dict[str, Any] | None:
    if include_archived:
        return row("SELECT * FROM bv_documents WHERE id=?", (doc_id,))
    return row("SELECT * FROM bv_documents WHERE id=? AND COALESCE(is_active,1)=1", (doc_id,))


def archive_bv_document(doc_id: int, user_id: int | None = None) -> dict[str, Any] | None:
    current=bv_document(doc_id, include_archived=True)
    if not current:
        return None
    with transaction() as con:
        con.execute(
            """UPDATE bv_documents SET is_active=0,manual_override=1,archived_at=?,archived_by=? WHERE id=?""",
            (datetime.now().isoformat(timespec='seconds'), user_id, doc_id),
        )
        # Se o item arquivado era apenas uma cópia duplicada, a ocorrência deixa
        # de colorir o certificado de roxo. Certificados válidos continuam intactos.
        con.execute(
            "DELETE FROM certificate_files WHERE contractor=? AND file_path=? AND UPPER(status)='DUPLICADO'",
            (current.get('contractor'), current.get('file_path')),
        )
    return current


def remove_duplicate_certificate_files(contractor: str = "ALL", user_id: int | None = None) -> dict[str, Any]:
    """Remove da aba Certificados as cópias técnicas já marcadas como DUPLICADO.

    A detecção de duplicidade já ocorreu no importador por hash/fingerprint do
    conteúdo técnico. Portanto esta rotina NÃO compara apenas o número BI330:
    certificados que reutilizam o mesmo número em outra data/trecho continuam
    válidos. A ocorrência canônica em ``certificates`` é sempre preservada.

    A cópia removida fica registrada em ``certificate_files`` com
    ``DUPLICADO_REMOVIDO`` e sem vínculo ao certificado canônico. Isso impede
    que uma sincronização comum (ou forçada, enquanto o arquivo não mudar) a
    faça reaparecer. O arquivo físico nunca é apagado.
    """
    contractor = str(contractor or "ALL").upper().strip()
    if contractor not in {"ALL", "ARENA", "PAVIDEZ"}:
        raise ValueError("Contratada inválida")

    where = ["UPPER(COALESCE(cf.status,''))='DUPLICADO'"]
    params: list[Any] = []
    if contractor != "ALL":
        where.append("cf.contractor=?")
        params.append(contractor)
    duplicates = rows(
        """SELECT cf.id,cf.contractor,cf.certificate_id,cf.file_path,cf.file_name,
                  c.number certificate_number
             FROM certificate_files cf
             LEFT JOIN certificates c ON c.id=cf.certificate_id
            WHERE """ + " AND ".join(where) + " ORDER BY cf.contractor,cf.id",
        tuple(params),
    )
    if not duplicates:
        return {"removed": 0, "by_contractor": {}, "canonical_certificates": 0, "files": []}

    now = datetime.now().isoformat(timespec="seconds")
    by_contractor: Counter[str] = Counter()
    canonical_ids: set[int] = set()
    with transaction() as con:
        for d in duplicates:
            cid = d.get("certificate_id")
            if cid is not None:
                canonical_ids.add(int(cid))
            # Preserva o registro do caminho para que a sincronização saiba que
            # esta cópia foi removida manualmente, mas tira o vínculo da aba.
            con.execute(
                """UPDATE certificate_files
                      SET certificate_id=NULL,status='DUPLICADO_REMOVIDO',
                          error=CASE WHEN COALESCE(error,'')='' THEN 'Cópia duplicada removida manualmente da aba Certificados' ELSE error END
                    WHERE id=? AND UPPER(COALESCE(status,''))='DUPLICADO'""",
                (int(d["id"]),),
            )
            # Se a mesma cópia também estiver no navegador BV, arquiva somente
            # a visualização. O arquivo original SharePoint/OneDrive permanece.
            con.execute(
                """UPDATE bv_documents
                      SET is_active=0,manual_override=1,archived_at=?,archived_by=?
                    WHERE contractor=? AND file_path=? AND COALESCE(is_active,1)=1""",
                (now, user_id, d.get("contractor"), d.get("file_path")),
            )
            by_contractor[str(d.get("contractor") or "")] += 1

    return {
        "removed": len(duplicates),
        "by_contractor": dict(by_contractor),
        "canonical_certificates": len(canonical_ids),
        "files": [
            {
                "id": d.get("id"), "contractor": d.get("contractor"),
                "file_name": d.get("file_name"), "certificate_number": d.get("certificate_number"),
            }
            for d in duplicates
        ],
    }


def archive_duplicate_bv_documents(contractor: str = "ALL", user_id: int | None = None) -> dict[str, Any]:
    """Arquiva em lote ocorrências BV já marcadas como DUPLICADO.

    A ocorrência canônica do certificado não é alterada. Somente os arquivos
    adicionais cujo ``certificate_files.status`` é DUPLICADO saem da
    visualização. O arquivo físico no SharePoint/OneDrive nunca é removido.
    """
    contractor = str(contractor or "ALL").upper().strip()
    if contractor not in {"ALL", "ARENA", "PAVIDEZ"}:
        raise ValueError("Contratada inválida")
    where = ["COALESCE(d.is_active,1)=1", "UPPER(COALESCE(cf.status,''))='DUPLICADO'"]
    params: list[Any] = []
    if contractor != "ALL":
        where.append("d.contractor=?")
        params.append(contractor)
    duplicates = rows(
        """SELECT d.id,d.contractor,d.file_path,d.file_name,d.relative_path,cf.certificate_id
             FROM bv_documents d
             JOIN certificate_files cf ON cf.contractor=d.contractor AND cf.file_path=d.file_path
            WHERE """ + " AND ".join(where) + " ORDER BY d.contractor,d.id",
        tuple(params),
    )
    if not duplicates:
        return {"removed": 0, "by_contractor": {}, "documents": []}

    now = datetime.now().isoformat(timespec="seconds")
    by_contractor: Counter[str] = Counter()
    with transaction() as con:
        for d in duplicates:
            con.execute(
                "UPDATE bv_documents SET is_active=0,manual_override=1,archived_at=?,archived_by=? WHERE id=? AND COALESCE(is_active,1)=1",
                (now, user_id, int(d["id"])),
            )
            con.execute(
                "DELETE FROM certificate_files WHERE contractor=? AND file_path=? AND UPPER(COALESCE(status,''))='DUPLICADO'",
                (d.get("contractor"), d.get("file_path")),
            )
            by_contractor[str(d.get("contractor") or "")] += 1
    return {
        "removed": len(duplicates),
        "by_contractor": dict(by_contractor),
        "documents": [
            {"id": d.get("id"), "contractor": d.get("contractor"), "file_name": d.get("file_name"), "relative_path": d.get("relative_path")}
            for d in duplicates
        ],
    }


def kit_detail(kit_id: int) -> dict[str, Any] | None:
    return row(
        """SELECT id,contractor,source_row,seq,service,application_date,mix_project,period,road,kmi,kmf,
                  receipt_date,status,status_1,status_2,status_3,status_4,status_5,status_6,status_7,status_8,sin_retro,
                  COALESCE(is_active,1) is_active,COALESCE(manual_override,0) manual_override,updated_at,updated_by
             FROM kit_rows WHERE id=?""",
        (kit_id,),
    )


def list_kit_documents(contractor: str = "ALL", kit_id: int | None = None, search: str = "", limit: int = 2000, extension: str = "", top_folder: str = "") -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if contractor != "ALL":
        where.append("d.contractor=?")
        params.append(contractor)
    if kit_id is not None:
        where.append("d.kit_id=?")
        params.append(int(kit_id))
    if search.strip():
        q = f"%{search.strip().upper()}%"
        where.append("(UPPER(d.file_name) LIKE ? OR UPPER(d.relative_path) LIKE ? OR UPPER(d.seq_guess) LIKE ?)")
        params.extend([q,q,q])
    if extension.strip():
        ext = extension.strip().lower()
        if not ext.startswith("."):
            ext = "." + ext
        where.append("LOWER(d.extension)=?")
        params.append(ext)
    if top_folder.strip():
        # Normaliza a barra antes de comparar: no Postgres, "\" dentro de um
        # padrão LIKE é o caractere de escape por padrão, então um valor como
        # "M01\%" (caminho do Windows) era interpretado como o literal "M01%"
        # em vez de "M01" + qualquer coisa — a pasta nunca batia e a lista de
        # arquivos voltava vazia mesmo com a contagem da pasta correta.
        folder = top_folder.strip().strip("/\\")
        if folder == "(raiz)":
            where.append("REPLACE(d.relative_path,'\\','/') NOT LIKE ?")
            params.append("%/%")
        else:
            where.append("REPLACE(d.relative_path,'\\','/') LIKE ?")
            params.append(folder + "/%")
    w = " WHERE " + " AND ".join(where) if where else ""
    params.append(int(limit))
    return rows(
        f"""SELECT d.id,d.contractor,d.kit_id,d.file_name,d.relative_path,d.folder,d.extension,d.size,d.seq_guess,d.synced_at,
                    k.seq kit_seq,k.service kit_service,k.application_date kit_date
               FROM kit_documents d LEFT JOIN kit_rows k ON k.id=d.kit_id
               {w} ORDER BY d.contractor,d.relative_path LIMIT ?""",
        tuple(params),
    )


def kit_document(doc_id: int) -> dict[str, Any] | None:
    return row("SELECT * FROM kit_documents WHERE id=?", (doc_id,))
