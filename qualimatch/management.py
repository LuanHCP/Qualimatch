from __future__ import annotations

import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .config import DATA_DIR
from .database import row, rows, transaction, json_dumps, backend_name
from .normalizers import norm_header, norm_text
from .version import APP_VERSION
from .queries import (
    measurement_cycle, measurement_cycle_bounds, pending_days, certificate_detail, list_certificates,
)


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _today() -> date:
    return date.today()


def _cert_covered_dates(contractor: str = "ALL") -> set[tuple[str, str]]:
    params: list[Any] = []
    where = ["c.is_active=1"]
    if contractor != "ALL":
        where.append("c.contractor=?")
        params.append(contractor)
    w = " WHERE " + " AND ".join(where)
    covered: set[tuple[str, str]] = set()
    for c in rows(f"SELECT c.id,c.contractor,c.service_date,c.raw_json FROM certificates c{w}", tuple(params)):
        dates: list[str] = []
        if c.get("service_date"):
            dates.append(str(c["service_date"])[:10])
        try:
            raw = json.loads(c.get("raw_json") or "{}")
        except Exception:
            raw = {}
        dates += [str(x)[:10] for x in (raw.get("service_dates") or []) if x]
        for d in dates:
            covered.add((str(c["contractor"]), d))
    sample_where = ["c.is_active=1", "s.application_date IS NOT NULL", "TRIM(s.application_date)<>''"]
    sample_params: list[Any] = []
    if contractor != "ALL":
        sample_where.append("c.contractor=?")
        sample_params.append(contractor)
    for s in rows(
        "SELECT DISTINCT c.contractor,s.application_date FROM certificate_samples s JOIN certificates c ON c.id=s.certificate_id WHERE " + " AND ".join(sample_where),
        tuple(sample_params),
    ):
        covered.add((str(s["contractor"]), str(s["application_date"])[:10]))
    return covered




def _kit_delivery_info(item: dict[str, Any]) -> tuple[str, bool]:
    """Retorna (estado, coluna_existe) a partir da coluna ENTREGA da d.KIT.

    Estados normalizados:
    - ENTREGUE
    - NAO_ENTREGUE
    - SEM_INFORMACAO

    Bancos antigos ainda podem não ter ``delivery_status`` preenchido. Nesse caso
    o raw_json é consultado e, se a planilha nem possuía a coluna ENTREGA, o
    chamador pode preservar o comportamento legado baseado na existência do kit.
    """
    explicit = norm_text(item.get("delivery_status"))
    has_column = False
    try:
        raw = json.loads(item.get("raw_json") or "{}")
    except Exception:
        raw = {}
    if raw.get("_qualimatch_entrega_coluna") is True:
        has_column = True
    raw_value = ""
    for key, value in raw.items():
        if str(key).startswith("_qualimatch_"):
            continue
        nk = norm_header(key)
        if nk in {"ENTREGA", "STATUS ENTREGA"}:
            has_column = True
            raw_value = norm_text(value)
            break
    value = explicit or raw_value
    if value:
        has_column = True
    if value.startswith("NAO ENTREGUE") or value in {"NAO", "N ENTREGUE", "NÃO ENTREGUE"}:
        return "NAO_ENTREGUE", has_column
    if value == "ENTREGUE" or ("ENTREGUE" in value and "NAO" not in value):
        return "ENTREGUE", has_column
    return "SEM_INFORMACAO", has_column


def _delivery_responsibility(kits: list[dict[str, Any]]) -> tuple[str, list[str], bool]:
    """Classifica a responsabilidade de uma data de execução.

    Quando a planilha possui a coluna ENTREGA, a responsabilidade só passa para
    a BV quando TODOS os kits daquele dia estão explicitamente ``Entregue``.
    Qualquer ``Não entregue`` ou célula vazia permanece com a Contratada.

    Se a planilha é legada e não possui a coluna, mantém o comportamento antigo
    para não transformar bases históricas inteiras em pendência da Contratada.
    """
    if not kits:
        return "CONTRATADA", [], False
    infos = [_kit_delivery_info(dict(k)) for k in kits]
    states = [state for state, _ in infos]
    has_delivery_column = any(flag for _, flag in infos)
    if has_delivery_column:
        delivered = bool(states) and all(state == "ENTREGUE" for state in states)
        return ("BV" if delivered else "CONTRATADA"), states, True
    # Compatibilidade: sem a coluna ENTREGA na fonte, a simples presença do kit
    # continua representando entrega, como nas versões anteriores.
    return "BV", states, False

def bv_pending_workflow(contractor: str = "ALL", start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
    """Pendências sem certificado, classificadas por responsabilidade real.

    Fonte primária de responsabilidade: coluna ``ENTREGA`` da planilha da
    construtora (d.KIT).

    - sem kit: CONTRATADA;
    - ENTREGA = Não entregue / vazio: CONTRATADA;
    - todos os kits da data com ENTREGA = Entregue: BV;
    - planilhas históricas sem a coluna ENTREGA preservam o comportamento legado.

    Para itens da BV, ``status`` continua distinguindo o SLA de 3 dias:
    ``NO PRAZO`` ou ``PENDENTE CERTIFICADO``. O campo ``responsibility`` é o que
    define em qual portal o item aparece.
    """
    base = pending_days(contractor, start, end)
    if not base:
        return []
    where = ["COALESCE(is_active,1)=1", "application_date IS NOT NULL", "TRIM(application_date)<>''"]
    params: list[Any] = []
    if contractor != "ALL":
        where.append("contractor=?"); params.append(contractor)
    if start:
        where.append("application_date>=?"); params.append(start)
    if end:
        where.append("application_date<=?"); params.append(end)
    kit_rows = rows(
        "SELECT contractor,application_date,receipt_date,delivery_status,status,seq,raw_json FROM kit_rows WHERE " + " AND ".join(where),
        tuple(params),
    )
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for k in kit_rows:
        by_key[(str(k["contractor"]), str(k["application_date"])[:10])].append(dict(k))
    today = _today()
    out: list[dict[str, Any]] = []
    for item in base:
        key = (str(item["contractor"]), str(item["date"])[:10])
        kits = by_key.get(key, [])
        responsibility, delivery_states, has_delivery_column = _delivery_responsibility(kits)
        delivery_candidates = [_as_date(x.get("receipt_date")) for x in kits]
        delivery_candidates = [x for x in delivery_candidates if x]
        delivery_date = max(delivery_candidates) if delivery_candidates else None
        days_since = (today - delivery_date).days if delivery_date else None

        if responsibility == "CONTRATADA":
            status = "PENDENTE CONTRATADA"
            sla_status = None
        else:
            # Entrega confirmada: a responsabilidade já é da BV imediatamente.
            # O SLA é mostrado separadamente e não interfere no roteamento.
            if days_since is None:
                status = "PENDENTE CERTIFICADO"
                sla_status = "SEM DATA RECEBIMENTO"
            elif days_since <= 3:
                status = "NO PRAZO"
                sla_status = "NO PRAZO"
            else:
                status = "PENDENTE CERTIFICADO"
                sla_status = "ATRASADO"

        out.append({
            **item,
            "status": status,
            "responsibility": responsibility,
            "sla_status": sla_status,
            "kit_count": len(kits),
            "kit_sequences": [str(x.get("seq") or "") for x in kits if x.get("seq")],
            "kit_delivery_date": delivery_date.isoformat() if delivery_date else None,
            "days_since_kit": days_since,
            "delivery_states": delivery_states,
            "delivery_column": has_delivery_column,
        })
    return out


def bv_certificate_pending(contractor: str = "ALL", start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
    """Itens sem certificado cuja responsabilidade já está com a BV.

    A coluna ENTREGA é a autoridade operacional. Por isso um kit marcado como
    ``Entregue`` aparece na BV mesmo que ainda esteja dentro dos 3 dias de SLA.
    """
    out = []
    for item in bv_pending_workflow(contractor, start, end):
        responsibility = str(item.get("responsibility") or "").upper()
        if responsibility == "BV":
            out.append(item)
        elif not responsibility and str(item.get("status") or "").upper() == "PENDENTE CERTIFICADO":
            # Compatibilidade com registros/integrações anteriores à v3.8.8.
            out.append(item)
    return out


def _quality_counterproof_reproved_numbers(contractor: str, measurement: str) -> set[str]:
    """Certificados cuja contra-prova já consta reprovada na BD_QUALI."""
    where = ["status_final IS NOT NULL"]
    params: list[Any] = []
    if contractor != "ALL":
        where.append("contractor=?"); params.append(contractor)
    bounds = measurement_cycle_bounds(measurement) if measurement != "ALL" else None
    if bounds:
        where.extend(["date>=?", "date<=?"])
        params.extend([bounds["measurement_start"], bounds["measurement_end"]])
    found: set[str] = set()
    try:
        data = rows("SELECT status_final,raw_json FROM quality_rows WHERE " + " AND ".join(where), tuple(params))
    except Exception:
        return found
    for item in data:
        status = norm_text(item.get("status_final"))
        if "REP" not in status and "RETRAB" not in status:
            continue
        try:
            raw = json.loads(item.get("raw_json") or "{}")
        except Exception:
            raw = {}
        for key, value in raw.items():
            header = norm_header(key)
            if "CERTIFICADO" not in header or "VV" not in header or not re.search(r"(?:^|\s)CP(?:\s|$)", header):
                continue
            digits = re.findall(r"\d+", str(value or ""))
            if digits:
                found.add(str(int(digits[-1])))
    return found


def bv_kpi_dashboard(contractor: str = "ALL", measurement: str = "ALL") -> dict[str, Any]:
    """Indicadores BV sem misturar a base de certificados com pendências diárias."""
    selected_measurement = str(measurement or "ALL").upper().strip()
    quality_cp_reproved_numbers = _quality_counterproof_reproved_numbers(contractor, selected_measurement)
    cert_result = list_certificates(contractor=contractor, limit=100000, with_total=True)
    certificates = list(cert_result.get("items") or [])

    def cycle_label(value: Any) -> str:
        cycle = measurement_cycle(str(value or "")[:10])
        return str((cycle or {}).get("measurement") or "")

    def certificate_measurements(cert: dict[str, Any]) -> list[str]:
        labels = [cycle_label(value) for value in (cert.get("execution_dates") or [])]
        labels = list(dict.fromkeys(x for x in labels if x))
        if labels:
            return labels
        for key in ("service_date", "application_date", "extraction_date", "certificate_date"):
            label = cycle_label(cert.get(key))
            if label:
                return [label]
        return []

    certificate_rows: list[dict[str, Any]] = []
    for cert in certificates:
        labels = certificate_measurements(cert)
        if selected_measurement != "ALL":
            labels = [selected_measurement] if selected_measurement in labels else []
        elif not labels:
            labels = ["—"]
        if not labels:
            continue
        overall = str(cert.get("overall_status") or "").upper().strip()
        counterproof = str(cert.get("counterproof_state") or "").upper().strip()
        has_counterproof = bool(cert.get("counterproof_delivered") or cert.get("has_counterproof") or counterproof == "ENTREGUE")
        cert_digits = re.findall(r"\d+", str(cert.get("number") or ""))
        quality_cp_reproved = bool(cert_digits and str(int(cert_digits[-1])) in quality_cp_reproved_numbers)
        if quality_cp_reproved:
            has_counterproof = True
            overall = "REPROVADO"
        # Categorias executivas são exclusivas. Uma reprovação de rotina ainda
        # não é reprovação final: enquanto não chega a contra-prova ela pertence
        # à fila PENDENTE CONTRA-PROVA. REPROVADO só existe após a fase de
        # contra-prova também encerrar reprovada.
        if has_counterproof and overall == "REPROVADO":
            category = "REPROVADO"
        elif overall == "APROVADO":
            # O parecer estatístico oficial da fase final prevalece. A inspeção
            # dos CPs individuais alimenta o cálculo estatístico e os avisos,
            # mas não transforma uma rotina estatisticamente APROVADA em
            # pendência de contra-prova.
            category = "APROVADO"
        elif not has_counterproof and overall == "REPROVADO":
            category = "PENDENTE_CONTRAPROVA"
        else:
            category = "SEM_RESULTADO"
        for label in labels:
            certificate_rows.append({
                "type": category,
                "contractor": cert.get("contractor"), "measurement": label or "—",
                "date": cert.get("service_date") or cert.get("extraction_date"), "road": cert.get("road"),
                "reference": cert.get("number") or f"Certificado #{cert.get('id')}",
                "status": "PENDENTE CONTRA-PROVA" if category == "PENDENTE_CONTRAPROVA" else category.replace("_", " "),
                "certificate_id": cert.get("id"),
            })

    pending_rows: list[dict[str, Any]] = []
    for item in bv_pending_workflow(contractor):
        label = cycle_label(item.get("date"))
        if selected_measurement != "ALL" and label != selected_measurement:
            continue
        is_bv = str(item.get("responsibility") or "").upper() == "BV"
        pending_type = "PENDENTE_CERTIFICADO" if is_bv else "PENDENTE_EXTRACAO"
        pending_rows.append({
            "type": pending_type, "contractor": item.get("contractor"), "measurement": label or "—",
            "date": item.get("date"), "road": item.get("road"),
            "reference": f"{int(item.get('lines') or 0)} linha(s) de medição",
            "status": "PENDENTE CERTIFICADO" if is_bv else "PENDENTE EXTRAÇÃO",
            "sla_status": item.get("sla_status"), "delivery_date": item.get("kit_delivery_date"),
            "days_since": item.get("days_since_kit"),
        })

    # Um mesmo BI330 pode ter datas em mais de uma medição. Ele aparece em cada
    # ciclo pertinente na tabela, mas no consolidado geral só pode contar uma vez.
    summary_certificate_rows = list({x.get("certificate_id"): x for x in certificate_rows}.values())
    certificate_total = len(summary_certificate_rows)
    classified_total = sum(x["type"] in {"APROVADO", "REPROVADO", "PENDENTE_CONTRAPROVA"} for x in summary_certificate_rows)
    approved = sum(x["type"] == "APROVADO" for x in summary_certificate_rows)
    reproved = sum(x["type"] == "REPROVADO" for x in summary_certificate_rows)
    counterproof_pending = sum(x["type"] == "PENDENTE_CONTRAPROVA" for x in summary_certificate_rows)
    extraction_pending = sum(x["type"] == "PENDENTE_EXTRACAO" for x in pending_rows)
    certificate_pending = sum(x["type"] == "PENDENTE_CERTIFICADO" for x in pending_rows)
    pending_total = extraction_pending + certificate_pending
    # Todos os percentuais da tela usam a mesma base visível de certificados
    # avaliados (ex.: 12/830), conforme a leitura executiva solicitada.
    obligation_total = classified_total
    # Para pendências operacionais, a base precisa incluir o que já chegou e o
    # que ainda falta. Ex.: 5 certificados + 5 extrações pendentes = 10 itens;
    # pendente extração é 5/10, não 5/5.
    operational_total = classified_total + pending_total

    def percentage(value: int, total: int) -> float:
        return round(value * 100 / total, 1) if total else 0.0

    measurements: dict[str, dict[str, Any]] = {}
    for item in certificate_rows + pending_rows:
        label = str(item.get("measurement") or "—")
        group = measurements.setdefault(label, {"measurement": label, "certificates": 0, "approved": 0,
            "reproved": 0, "counterproof_pending": 0, "extraction_pending": 0, "certificate_pending": 0})
        kind = item.get("type")
        if kind in {"APROVADO", "REPROVADO", "SEM_RESULTADO", "PENDENTE_CONTRAPROVA"}: group["certificates"] += 1
        if kind == "APROVADO": group["approved"] += 1
        if kind == "REPROVADO": group["reproved"] += 1
        if kind == "PENDENTE_CONTRAPROVA": group["counterproof_pending"] += 1
        if kind == "PENDENTE_EXTRACAO": group["extraction_pending"] += 1
        if kind == "PENDENTE_CERTIFICADO": group["certificate_pending"] += 1

    def measurement_sort(item: dict[str, Any]) -> int:
        digits = "".join(ch for ch in str(item.get("measurement") or "") if ch.isdigit())
        return int(digits or -1)

    detail = [x for x in certificate_rows if x["type"] == "PENDENTE_CONTRAPROVA"] + pending_rows
    detail.sort(key=lambda x: (str(x.get("date") or ""), str(x.get("contractor") or "")), reverse=True)
    approved_metric = {"count": approved, "percent": percentage(approved, operational_total)}
    reproved_metric = {"count": reproved, "percent": percentage(reproved, operational_total)}
    counterproof_metric = {"count": counterproof_pending, "percent": percentage(counterproof_pending, operational_total)}
    return {"contractor": contractor, "measurement": selected_measurement,
        "summary": {"certificate_total": certificate_total, "classified_total": classified_total, "pending_total": pending_total,
            "obligation_total": obligation_total, "operational_total": operational_total,
            "approved": approved_metric,
            "reproved": reproved_metric,
            "counterproof_pending": counterproof_metric,
            "extraction_pending": {"count": extraction_pending, "percent": percentage(extraction_pending, operational_total)},
            "certificate_pending": {"count": certificate_pending, "percent": percentage(certificate_pending, operational_total)}},
        "measurements": sorted(measurements.values(), key=measurement_sort, reverse=True), "details": detail}


def measurement_cycle_dashboard(contractor: str = "ALL", limit: int = 14) -> dict[str, Any]:
    params: list[Any] = []
    mw = ["date IS NOT NULL", "TRIM(date)<>''"]
    if contractor != "ALL":
        mw.append("contractor=?"); params.append(contractor)
    measurement_rows = rows("SELECT DISTINCT contractor,date FROM measurements WHERE " + " AND ".join(mw), tuple(params))
    cycles: dict[str, dict[str, Any]] = {}
    # Dias de execução = datas de calendário distintas com pelo menos uma linha de medição.
    # Na visão ALL, Arena e Pavidez executando no mesmo dia continuam sendo 1 dia real.
    #
    # Exceção: dia 10 é o dia de FECHAMENTO/PAGAMENTO da medição (planilha lança
    # o lote ali, mesmo sem execução real naquela data), não um dia de execução de
    # fato. Contar esse dia inflava a meta de VV/ESP (expected = execution_days) e
    # gerava "dívida" artificial no Relatório Geral para algo que nunca foi
    # executado — por isso ele não entra nessa contagem.
    execution_dates: set[str] = set()
    for m in measurement_rows:
        d = str(m.get("date") or "")[:10]
        if d[8:10] == "10":
            continue
        cyc = measurement_cycle(d)
        if not cyc:
            continue
        if d in execution_dates:
            continue
        execution_dates.add(d)
        key = cyc["measurement"]
        g = cycles.setdefault(key, {**cyc, "execution_days": 0, "kit_days": 0, "certificate_days": 0,
                                     "kits": 0, "certificates": 0, "pending_contractor": 0,
                                     "pending_certificate": 0, "on_time": 0, "kit_lead_days": [], "certificate_lead_days": []})
        g["execution_days"] += 1

    kparams: list[Any] = []
    kw = ["COALESCE(is_active,1)=1", "application_date IS NOT NULL", "TRIM(application_date)<>''"]
    if contractor != "ALL":
        kw.append("contractor=?"); kparams.append(contractor)
    kit_rows = rows("SELECT contractor,application_date,receipt_date FROM kit_rows WHERE " + " AND ".join(kw), tuple(kparams))
    kit_day_keys: set[str] = set()
    for k in kit_rows:
        d = str(k.get("application_date") or "")[:10]
        cyc = measurement_cycle(d)
        if not cyc:
            continue
        key = cyc["measurement"]
        if key not in cycles:
            cycles[key] = {**cyc, "execution_days": 0, "kit_days": 0, "certificate_days": 0,
                           "kits": 0, "certificates": 0, "pending_contractor": 0,
                           "pending_certificate": 0, "on_time": 0, "kit_lead_days": [], "certificate_lead_days": []}
        g = cycles[key]
        g["kits"] += 1
        if d not in kit_day_keys:
            kit_day_keys.add(d); g["kit_days"] += 1
        app = _as_date(k.get("application_date")); rec = _as_date(k.get("receipt_date"))
        if app and rec:
            g["kit_lead_days"].append((rec-app).days)

    cparams: list[Any] = []
    cw = ["is_active=1"]
    if contractor != "ALL":
        cw.append("contractor=?"); cparams.append(contractor)
    certs = rows("SELECT id,contractor,service_date,extraction_date,raw_json FROM certificates WHERE " + " AND ".join(cw), tuple(cparams))
    cert_day_keys: set[str] = set()
    for c in certs:
        service_dates: list[str] = []
        if c.get("service_date"):
            service_dates.append(str(c["service_date"])[:10])
        try:
            raw = json.loads(c.get("raw_json") or "{}")
        except Exception:
            raw = {}
        service_dates += [str(x)[:10] for x in (raw.get("service_dates") or []) if x]
        if not service_dates:
            sample_dates = rows("SELECT DISTINCT application_date FROM certificate_samples WHERE certificate_id=? AND application_date IS NOT NULL", (c["id"],))
            service_dates += [str(x["application_date"])[:10] for x in sample_dates]
        seen_for_cert: set[str] = set()
        for d in service_dates:
            if d in seen_for_cert:
                continue
            seen_for_cert.add(d)
            cyc = measurement_cycle(d)
            if not cyc:
                continue
            key = cyc["measurement"]
            if key not in cycles:
                cycles[key] = {**cyc, "execution_days": 0, "kit_days": 0, "certificate_days": 0,
                               "kits": 0, "certificates": 0, "pending_contractor": 0,
                               "pending_certificate": 0, "on_time": 0, "kit_lead_days": [], "certificate_lead_days": []}
            if d not in cert_day_keys:
                cert_day_keys.add(d); cycles[key]["certificate_days"] += 1
        first_service = min((_as_date(x) for x in service_dates if _as_date(x)), default=None)
        ext = _as_date(c.get("extraction_date"))
        if first_service and ext:
            cyc = measurement_cycle(first_service)
            if cyc:
                cycles[cyc["measurement"]]["certificate_lead_days"].append((ext-first_service).days)
        if service_dates:
            cyc = measurement_cycle(service_dates[0])
            if cyc:
                cycles[cyc["measurement"]]["certificates"] += 1

    for p in bv_pending_workflow(contractor):
        cyc = measurement_cycle(p.get("date"))
        if not cyc:
            continue
        g = cycles.setdefault(cyc["measurement"], {**cyc, "execution_days": 0, "kit_days": 0, "certificate_days": 0,
                                                   "kits": 0, "certificates": 0, "pending_contractor": 0,
                                                   "pending_certificate": 0, "on_time": 0, "kit_lead_days": [], "certificate_lead_days": []})
        if p["status"] == "PENDENTE CONTRATADA": g["pending_contractor"] += 1
        elif p["status"] == "PENDENTE CERTIFICADO": g["pending_certificate"] += 1
        elif p["status"] == "NO PRAZO": g["on_time"] += 1

    out = []
    for g in cycles.values():
        exec_days = int(g["execution_days"] or 0)
        kit_days = int(g["kit_days"] or 0)
        cert_days = int(g["certificate_days"] or 0)
        kit_leads = g.pop("kit_lead_days")
        cert_leads = g.pop("certificate_lead_days")
        g["kit_coverage_pct"] = (kit_days/exec_days*100) if exec_days else 0.0
        g["certificate_coverage_pct"] = (cert_days/exec_days*100) if exec_days else 0.0
        g["attendance_pct"] = (min(exec_days, cert_days)/exec_days*100) if exec_days else 0.0
        g["avg_kit_lead_days"] = round(sum(kit_leads)/len(kit_leads), 1) if kit_leads else None
        g["avg_certificate_lead_days"] = round(sum(cert_leads)/len(cert_leads), 1) if cert_leads else None
        out.append(g)
    out.sort(key=lambda x: int(x.get("measurement_number") or 0), reverse=True)
    out = out[:max(1, int(limit))]
    return {"contractor": contractor, "cycles": out}


def review_queue(
    contractor: str = "ALL",
    limit: int = 500,
    severity: str = "ALL",
    item_type: str = "ALL",
    search: str = "",
    offset: int = 0,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    # Certificados parciais / datas inconsistentes. Agrupa os avisos por
    # certificado para a central não virar milhares de linhas repetidas.
    for c in list_certificates(contractor=contractor, limit=5000):
        parse_warnings = [str(x) for x in (c.get("parse_warnings") or []) if x]
        business_warnings = [str(x) for x in (c.get("business_warnings") or []) if x]
        if parse_warnings:
            items.append({"severity":"warning","type":"CERTIFICADO_PARCIAL","contractor":c.get("contractor"),
                          "title":f"{c.get('number')} precisa revisão", "detail":" • ".join(parse_warnings),
                          "entity_type":"certificate","entity_id":str(c.get("id")),"page":"certificates"})
        if business_warnings:
            items.append({"severity":"warning","type":"DATA_INCONSISTENTE","contractor":c.get("contractor"),
                          "title":f"{c.get('number')} com data inconsistente", "detail":" • ".join(business_warnings),
                          "entity_type":"certificate","entity_id":str(c.get("id")),"page":"certificates"})
    # Kits fora de OK.
    kw = ["COALESCE(is_active,1)=1", "UPPER(COALESCE(status,''))<>'OK'"]
    kp: list[Any] = []
    if contractor != "ALL": kw.append("contractor=?"); kp.append(contractor)
    for k in rows("SELECT id,contractor,seq,status,application_date,road FROM kit_rows WHERE " + " AND ".join(kw) + " ORDER BY application_date DESC LIMIT 1000", tuple(kp)):
        sev = "danger" if str(k.get("status") or "").upper() == "PENDENTE" else "warning"
        items.append({"severity":sev,"type":"KIT_ATENCAO","contractor":k.get("contractor"),
                      "title":f"Kit {k.get('seq') or k.get('id')} • {k.get('status') or 'SEM STATUS'}",
                      "detail":f"{k.get('application_date') or 'Sem data'} • {k.get('road') or 'Sem rodovia'}",
                      "entity_type":"kit","entity_id":str(k.get("id")),"page":"contractor-kits"})
    # Pendências por responsabilidade.
    for p in bv_pending_workflow(contractor):
        sev = "danger" if p["status"] != "NO PRAZO" else "info"
        items.append({"severity":sev,"type":p["status"].replace(" ","_"),"contractor":p.get("contractor"),
                      "title":f"{p.get('measurement') or ''} • {p.get('status')}",
                      "detail":f"Execução {p.get('date')} • {p.get('road') or 'rodovia não identificada'}",
                      "entity_type":"pending","entity_id":f"{p.get('contractor')}:{p.get('date')}","page":"pending"})
    available_types = sorted({str(x.get("type") or "") for x in items if x.get("type")})
    severity = str(severity or "ALL").lower().strip()
    item_type = str(item_type or "ALL").upper().strip()
    needle = norm_text(search)
    if severity not in {"all", "danger", "warning", "info"}:
        severity = "all"
    if severity != "all":
        items = [x for x in items if str(x.get("severity") or "").lower() == severity]
    if item_type != "ALL":
        items = [x for x in items if str(x.get("type") or "").upper() == item_type]
    if needle:
        items = [
            x for x in items
            if needle in norm_text(" ".join(str(x.get(key) or "") for key in ("type", "contractor", "title", "detail")))
        ]
    counts = Counter(x["type"] for x in items)
    sev_counts = Counter(x["severity"] for x in items)
    items.sort(key=lambda x: ({"danger":0,"warning":1,"info":2}.get(x["severity"],3), x.get("title") or ""))
    return {
        "total": len(items),
        "counts": dict(counts),
        "severity": dict(sev_counts),
        "available_types": available_types,
        "items": items[max(0, int(offset)):max(0, int(offset)) + max(1, int(limit))],
    }


def notification_summary(user: dict[str, Any]) -> dict[str, Any]:
    admin = str(user.get("role") or "").upper() == "ADMIN"
    allowed: list[str] = ["ARENA","PAVIDEZ"] if admin else []
    if not admin:
        if int(user.get("access_arena") or 0): allowed.append("ARENA")
        if int(user.get("access_pavidez") or 0): allowed.append("PAVIDEZ")
    contractor = "ALL" if len(allowed) > 1 else (allowed[0] if allowed else "ALL")
    queue = review_queue(contractor=contractor, limit=20) if (admin or int(user.get("access_bv") or 0) or allowed) else {"total":0,"items":[]}
    items = list(queue.get("items") or [])
    if not admin:
        if allowed:
            items = [x for x in items if x.get("contractor") in allowed]
        if not int(user.get('access_bv') or 0):
            # Usuário da Contratada não recebe metadados de certificados BV.
            items = [x for x in items if x.get('page') in {'contractor-kits','contractor-pending','contractor-certificates'} or x.get('type')=='KIT_ATENCAO']
    if admin:
        pending_users = rows("SELECT id,name,email,created_at FROM users WHERE status='PENDING' ORDER BY created_at DESC")
        for u in pending_users:
            items.insert(0,{"severity":"info","type":"CADASTRO_PENDENTE","title":f"Cadastro aguardando: {u['name']}",
                            "detail":u["email"],"entity_type":"user","entity_id":str(u["id"]),"page":"admin"})
        # v3.8.1 — falha em arquivo detectado automaticamente aparece no sino
        # do ADMIN para permitir correção/reprocessamento sem vigiar a pasta.
        try:
            monitor_errors = rows("SELECT id,contractor,portal,file_name,message,detected_at FROM auto_import_events WHERE status='ERRO' ORDER BY id DESC LIMIT 5")
        except Exception:
            monitor_errors = []
        for e in reversed(monitor_errors):
            items.insert(0,{"severity":"danger","type":"IMPORTACAO_AUTOMATICA_ERRO",
                            "title":f"Falha na importação automática: {e.get('file_name') or 'arquivo'}",
                            "detail":f"{e.get('contractor') or ''} • {e.get('message') or 'Verifique a sincronização.'}",
                            "entity_type":"auto_import","entity_id":str(e.get('id') or ''),"page":"sync"})
    return {"count":len(items),"items":items[:20]}


def global_search(term: str, user: dict[str, Any], limit: int = 30) -> list[dict[str, Any]]:
    q = (term or "").strip()
    if len(q) < 2:
        return []
    like = f"%{q.upper()}%"
    out: list[dict[str, Any]] = []
    admin = str(user.get("role") or "").upper() == "ADMIN"
    if admin or int(user.get("access_bv") or 0):
        for c in rows("SELECT id,contractor,number,road,service_date,extraction_date FROM certificates WHERE is_active=1 AND (UPPER(number) LIKE ? OR UPPER(road) LIKE ? OR UPPER(trace_approved) LIKE ?) ORDER BY id DESC LIMIT ?", (like,like,like,limit)):
            out.append({"type":"CERTIFICADO","title":c["number"],"subtitle":f"{c['contractor']} • {c.get('road') or 'sem rodovia'}", "page":"certificates","entity_id":c["id"],"contractor":c["contractor"]})
        for m in rows("SELECT id,contractor,line_measurement,ref_measurement,date,road FROM measurements WHERE UPPER(COALESCE(line_measurement,'')) LIKE ? OR UPPER(COALESCE(ref_measurement,'')) LIKE ? OR UPPER(COALESCE(road,'')) LIKE ? OR UPPER(COALESCE(date,'')) LIKE ? ORDER BY id DESC LIMIT ?", (like,like,like,like,limit)):
            out.append({"type":"MEDIÇÃO","title":m.get("line_measurement") or m.get("ref_measurement") or f"Medição {m['id']}","subtitle":f"{m['contractor']} • {m.get('date') or ''} • {m.get('road') or ''}","page":"measurements","entity_id":m["id"],"contractor":m["contractor"]})
    allowed = ["ARENA","PAVIDEZ"] if admin else [x for x in ("ARENA","PAVIDEZ") if int(user.get(f"access_{x.lower()}") or 0)]
    if allowed:
        placeholders = ",".join("?" for _ in allowed)
        params = tuple(allowed) + (like,like,like,like,limit)
        for k in rows(f"SELECT id,contractor,seq,application_date,road,status FROM kit_rows WHERE COALESCE(is_active,1)=1 AND contractor IN ({placeholders}) AND (UPPER(seq) LIKE ? OR UPPER(road) LIKE ? OR UPPER(mix_project) LIKE ? OR UPPER(status) LIKE ?) ORDER BY id DESC LIMIT ?", params):
            out.append({"type":"KIT","title":f"Kit {k.get('seq') or k['id']}","subtitle":f"{k['contractor']} • {k.get('application_date') or ''} • {k.get('road') or ''}","page":"contractor-kits","entity_id":k["id"],"contractor":k["contractor"]})
        dparams = tuple(allowed) + (like,like,limit)
        for d in rows(f"SELECT id,contractor,file_name,relative_path FROM kit_documents WHERE contractor IN ({placeholders}) AND (UPPER(file_name) LIKE ? OR UPPER(relative_path) LIKE ?) ORDER BY id DESC LIMIT ?", dparams):
            out.append({"type":"DOCUMENTO","title":d["file_name"],"subtitle":f"{d['contractor']} • {d.get('relative_path') or ''}","page":"contractor-certificates","entity_id":d["id"],"contractor":d["contractor"]})
    return out[:max(1,int(limit))]


def traceability(measurement_id: int) -> dict[str, Any] | None:
    m = row("SELECT * FROM measurements WHERE id=?", (measurement_id,))
    if not m:
        return None
    kits = rows("SELECT id,seq,contractor,application_date,receipt_date,road,kmi,kmf,status FROM kit_rows WHERE COALESCE(is_active,1)=1 AND contractor=? AND application_date=? ORDER BY id", (m["contractor"],m["date"]))
    # Prioriza o vínculo formal; se não existir, procura certificados pela data dos CPs.
    certs = rows("SELECT c.id,c.number,c.contractor,c.extraction_date,c.road,c.kmi,c.kmf,c.routine_result,c.counterproof_result FROM matches x JOIN certificates c ON c.id=x.certificate_id WHERE x.measurement_id=? AND c.is_active=1", (measurement_id,))
    if not certs:
        certs = rows("SELECT DISTINCT c.id,c.number,c.contractor,c.extraction_date,c.road,c.kmi,c.kmf,c.routine_result,c.counterproof_result FROM certificate_samples s JOIN certificates c ON c.id=s.certificate_id WHERE c.is_active=1 AND c.contractor=? AND s.application_date=? ORDER BY c.id", (m["contractor"],m["date"]))
    return {"measurement":{**m, **(measurement_cycle(m.get("date")) or {})},"kits":kits,"certificates":certs}


def record_change(user_id: int | None, action: str, entity_type: str, entity_id: str | int,
                  before: Any, after: Any, path=None) -> int:
    now = datetime.now().isoformat(timespec="seconds")
    try:
        with transaction(path) as con:
            cur = con.execute("INSERT INTO change_history(user_id,action,entity_type,entity_id,before_json,after_json,created_at) VALUES(?,?,?,?,?,?,?)",
                              (user_id,action[:80],entity_type[:40],str(entity_id),json_dumps(before or {}),json_dumps(after or {}),now))
            if getattr(cur, "lastrowid", None):
                return int(cur.lastrowid)
        rec = row("SELECT id FROM change_history WHERE user_id=? AND action=? AND entity_type=? AND entity_id=? AND created_at=? ORDER BY id DESC LIMIT 1",
                  (user_id,action[:80],entity_type[:40],str(entity_id),now), path)
        return int(rec["id"]) if rec else 0
    except Exception:
        # Compatibilidade com bancos de teste/legados ainda não migrados.
        return 0


def count_changes(path=None, date_filter: str | None = None) -> int:
    where = ""
    params: tuple[Any, ...] = ()
    if date_filter:
        where = " WHERE created_at LIKE ?"
        params = (str(date_filter)[:10] + "%",)
    found = row(f"SELECT COUNT(*) total FROM change_history{where}", params, path)
    return int((found or {}).get("total") or 0)


def list_changes(limit: int = 100, path=None, date_filter: str | None = None, offset: int = 0) -> list[dict[str, Any]]:
    limit = max(1,min(int(limit),500))
    where = ""
    params: tuple[Any, ...] = ()
    if date_filter:
        # created_at é ISO (YYYY-MM-DDTHH:MM:SS); filtrar pelo prefixo mantém
        # compatibilidade com SQLite e PostgreSQL sem depender de DATE().
        where = " WHERE ch.created_at LIKE ?"
        params = (str(date_filter)[:10] + "%",)
    offset = max(0, int(offset))
    if not offset:
        # Preserva a forma histórica da consulta da primeira página para manter
        # compatibilidade com integrações/testes que inspecionam os parâmetros.
        return rows(
            f"SELECT ch.*,u.name user_name FROM change_history ch LEFT JOIN users u ON u.id=ch.user_id{where} ORDER BY ch.id DESC LIMIT {limit}",
            params, path
        )
    return rows(
        f"SELECT ch.*,u.name user_name FROM change_history ch LEFT JOIN users u ON u.id=ch.user_id{where} ORDER BY ch.id DESC LIMIT ? OFFSET ?",
        params + (limit, offset), path
    )


def undo_change(change_id: int, admin_id: int, path=None) -> dict[str, Any]:
    ch = row("SELECT * FROM change_history WHERE id=?", (change_id,), path)
    if not ch:
        raise ValueError("Alteração não encontrada.")
    if ch.get("undone_at"):
        raise ValueError("Esta alteração já foi desfeita.")
    try:
        before = json.loads(ch.get("before_json") or "{}")
    except Exception:
        before = {}
    et = str(ch.get("entity_type") or "").lower()
    eid = int(ch.get("entity_id") or 0)
    with transaction(path) as con:
        if et == "kit":
            allowed = ["seq","service","application_date","mix_project","period","road","kmi","kmf","receipt_date","status","status_1","status_2","status_3","status_4","status_5","status_6","status_7","status_8","sin_retro","is_active","manual_override","updated_at","updated_by"]
            vals = {k:before.get(k) for k in allowed if k in before}
            if not vals: raise ValueError("Snapshot anterior do kit não está disponível.")
            set_sql = ",".join(f"{k}=?" for k in vals)
            con.execute(f"UPDATE kit_rows SET {set_sql} WHERE id=?", tuple(vals.values())+(eid,))
        elif et == "certificate_sample":
            allowed = ["application_date","direction","lane","station","position","thickness_exec_cm","thickness_project_cm","ratio_ab_pct","rice_gmm","gmb","voids_pct"]
            vals = {k:before.get(k) for k in allowed if k in before}
            set_sql = ",".join(f"{k}=?" for k in vals)
            con.execute(f"UPDATE certificate_samples SET {set_sql} WHERE id=?", tuple(vals.values())+(eid,))
        elif et == "certificate":
            allowed = ["routine_result","counterproof_result","raw_json","is_active","deleted_at","deleted_reason","manual_override"]
            vals = {k:before.get(k) for k in allowed if k in before}
            if not vals: raise ValueError("Snapshot anterior do certificado não está disponível.")
            set_sql = ",".join(f"{k}=?" for k in vals)
            con.execute(f"UPDATE certificates SET {set_sql} WHERE id=?", tuple(vals.values())+(eid,))
        else:
            raise ValueError("Esse tipo de alteração ainda não possui desfazer automático.")
        con.execute("UPDATE change_history SET undone_at=?,undone_by=? WHERE id=?", (datetime.now().isoformat(timespec="seconds"),admin_id,change_id))
    return {"ok":True,"change_id":change_id,"entity_type":et,"entity_id":eid}


def system_health() -> dict[str, Any]:
    sources = rows("SELECT contractor,kind,last_sync,last_status,last_error,path FROM sources WHERE enabled=1 ORDER BY contractor,kind")
    now = datetime.now()
    latest_sync: datetime | None = None
    failed_sources = 0
    stale_sources = 0
    for source in sources:
        status = str(source.get("last_status") or "NUNCA").upper()
        source["health"] = "OK" if status == "OK" else ("NUNCA" if status == "NUNCA" else "ATENCAO")
        if status not in {"OK", "NUNCA"}:
            failed_sources += 1
        try:
            synced = datetime.fromisoformat(str(source.get("last_sync") or ""))
        except Exception:
            synced = None
        if synced:
            latest_sync = max(latest_sync, synced) if latest_sync else synced
            age_minutes = max(0, int((now - synced).total_seconds() // 60))
            source["age_minutes"] = age_minutes
            if age_minutes > 360:
                source["health"] = "DESATUALIZADO"
                stale_sources += 1
        else:
            source["age_minutes"] = None
    backups = []
    try:
        from .config import BACKUP_DIR
        files = list(BACKUP_DIR.glob("*.db"))+[p for p in BACKUP_DIR.glob("*.json.gz") if not p.name.startswith("logs_arquivados_")]
        if files:
            p=max(files,key=lambda x:x.stat().st_mtime)
            backups=[{"name":p.name,"modified":datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),"size":p.stat().st_size}]
    except Exception:
        pass
    counts = {
        "measurements": int((row("SELECT COUNT(*) n FROM measurements") or {"n":0})["n"]),
        "certificates": int((row("SELECT COUNT(*) n FROM certificates WHERE is_active=1") or {"n":0})["n"]),
        "kits": int((row("SELECT COUNT(*) n FROM kit_rows WHERE COALESCE(is_active,1)=1") or {"n":0})["n"]),
        "users": int((row("SELECT COUNT(*) n FROM users WHERE status='APPROVED'") or {"n":0})["n"]),
    }
    warnings=[]
    for s in sources:
        if str(s.get("last_status") or "").upper() not in {"OK","NUNCA"}:
            warnings.append(f"{s.get('contractor')} / {s.get('kind')}: {s.get('last_status')}")
        if s.get("health") == "DESATUALIZADO":
            warnings.append(f"{s.get('contractor')} / {s.get('kind')}: sem sincronização há mais de 6 horas")
    if not backups:
        warnings.append("Nenhum backup disponível.")
    try:
        usage = shutil.disk_usage(DATA_DIR)
        disk = {
            "free_gb": round(usage.free / (1024 ** 3), 1),
            "total_gb": round(usage.total / (1024 ** 3), 1),
            "used_pct": round((usage.used / usage.total) * 100, 1) if usage.total else 0,
        }
        if usage.free < 2 * 1024 ** 3:
            warnings.append("Espaço livre abaixo de 2 GB no disco de dados.")
    except Exception:
        disk = {"free_gb": None, "total_gb": None, "used_pct": None}
    return {
        "database": backend_name(),
        "sources": sources,
        "last_backup": backups[0] if backups else None,
        "counts": counts,
        "warnings": warnings,
        "latest_sync": latest_sync.isoformat(timespec="seconds") if latest_sync else None,
        "failed_sources": failed_sources,
        "stale_sources": stale_sources,
        "disk": disk,
        "runtime": {
            "version": APP_VERSION,
            "python": ".".join(str(x) for x in sys.version_info[:3]),
            "data_dir": str(Path(DATA_DIR)),
        },
    }
