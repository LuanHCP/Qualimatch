from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from .normalizers import norm_header, norm_road, norm_direction, norm_lane, number, station, text, to_date
from .report_reader import read_report_summary
from .xlsx_xml import NS_MAIN, cell_value, row_cells, shared_strings, sheet_path

TARGETS = {
    "total_service": ["TOTAL SERVIÇO (R$)"],
    "extension_m": ["EXTENSÃO (m)", "EXTENSÃO (M)"],
    "volume_mass_m3": ["VOLUME MASSA (m³)", "VOLUME MASSA (M³)"],
    "quantity_t": ["QUANT PROJETO (ton)", "QUANT PROJETO (TON)"],
    "cap_project_t": ["CAP PROJETO (ton)", "CAP PROJETO (TON)"],
    "proposed_retention": ["VALOR DE RETENÇÃO PROPOSTO"],
}


@dataclass(slots=True)
class QualityRow:
    source_row: int
    visible_excel: bool
    line_measurement: str
    ref_measurement: str
    date: date | None
    road: str
    direction: str
    kmi: int | None
    kmf: int | None
    lane: str
    trace_code: str
    status_final: str
    status_summary: str
    extension_m: float | None
    volume_mass_m3: float | None
    quantity_t: float | None
    cap_project_t: float | None
    total_service: float | None
    proposed_retention: float | None
    raw: dict[str, Any]


@dataclass(slots=True)
class QualitySummary:
    total_service: float | None
    total_service_visible_sum: float
    total_difference: float | None
    total_source_cell: str
    extension_m: float | None
    volume_mass_m3: float | None
    quantity_t: float | None
    cap_project_t: float | None
    proposed_retention: float | None
    visible_records: int
    total_records: int
    warning: str
    # auditoria v2
    total_service_all_rows: float = 0.0
    subtotal_excel: float | None = None
    subtotal_source_cell: str = ""
    summary_source: str = ""
    approved_value: float | None = None
    pending_value: float | None = None
    reproved_value: float | None = None
    unclassified_value: float | None = None
    period_start: str | None = None
    period_end: str | None = None
    cap_source: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _header_map(cells, strings):
    out = {}
    orig = {}
    for col, c in cells.items():
        v = cell_value(c, strings)
        if v not in (None, ""):
            out[norm_header(v)] = col
            orig[col] = text(v)
    return out, orig


def _col(h, *names):
    for n in names:
        if norm_header(n) in h:
            return h[norm_header(n)]
    return None


def _binder_fraction(v: Any) -> float | None:
    n = number(v)
    if n is None or n < 0:
        return None
    if n > 1:
        n /= 100.0
    return n if 0 <= n <= 0.25 else None


def _correct_cap(raw_cap: float | None, quantity: float | None, binder: float | None) -> tuple[float | None, str]:
    """Corrige o erro conhecido da planilha Pavidez em CAP PROJETO.

    Nos arquivos enviados, o CAP da Arena já está coerente, porém a Pavidez traz
    valores como 23.262 t de CAP para apenas 76,565 t de mistura. Quando o valor
    bruto é fisicamente incompatível, usa QUANT PROJETO × TEOR ÓTIMO, ambos da
    própria BD_QUALI.
    """
    derived = quantity * binder if quantity is not None and binder is not None else None
    if raw_cap is None:
        return derived, "BD_QUALI[QUANT PROJETO × TEOR ÓTIMO]"
    if quantity is not None:
        # Se a quantidade é zero, qualquer CAP positivo é estruturalmente inválido.
        # Nos arquivos Pavidez existem exatamente essas linhas (quantidade=0 com
        # dezenas de milhares de toneladas em CAP).
        if quantity <= 0:
            return (derived if derived is not None else 0.0), "BD_QUALI[QUANT PROJETO × TEOR ÓTIMO]"
        # CAP normalmente é uma fração pequena da massa total. Limite amplo (20%)
        # apenas para detectar erro estrutural, sem alterar pequenas diferenças.
        if raw_cap > quantity * 0.20:
            return derived, "BD_QUALI[QUANT PROJETO × TEOR ÓTIMO]"
    return raw_cap, "BD_QUALI[CAP PROJETO (ton)]"


def read_quality(path: str | Path, worksheet: str = "BD_QUALI"):
    path = Path(path)
    out: list[QualityRow] = []
    subtotal_candidates: list[tuple[int, int, str, str, float]] = []
    hmap: dict[str, int] = {}
    originals: dict[int, str] = {}
    header_row = None

    with ZipFile(path) as z:
        strings = shared_strings(z)
        sp = sheet_path(z, worksheet)
        with z.open(sp) as f:
            for _, row in ET.iterparse(f, events=("end",)):
                if row.tag != f"{{{NS_MAIN}}}row":
                    continue
                nr = int(row.attrib.get("r", "0"))
                cells = row_cells(row)

                # SUBTOTAL costuma ficar acima do cabeçalho da tabela.
                if header_row is None:
                    hm, orig = _header_map(cells, strings)
                    for col, c in cells.items():
                        fe = c.find(f"{{{NS_MAIN}}}f")
                        if fe is not None and fe.text and "SUBTOTAL" in fe.text.upper():
                            v = number(cell_value(c, strings))
                            if v is not None:
                                subtotal_candidates.append((nr, col, c.attrib.get("r", ""), fe.text, v))
                    if nr <= 80 and {norm_header("DATA"), norm_header("TOTAL SERVIÇO (R$)")}.issubset(hm):
                        header_row = nr
                        hmap = hm
                        originals = orig
                    row.clear()
                    continue

                def get(*names):
                    p = _col(hmap, *names)
                    return cell_value(cells.get(p), strings) if p else None

                d = to_date(get("DATA"))
                if d:
                    raw: dict[str, Any] = {}
                    for idx, name in originals.items():
                        v = cell_value(cells.get(idx), strings)
                        if v not in (None, ""):
                            raw[name] = v

                    quantity = number(get("QUANT PROJETO (ton)", "QUANT PROJETO (TON)"))
                    raw_cap = number(get("CAP PROJETO (ton)", "CAP PROJETO (TON)"))
                    binder = _binder_fraction(get("TEOR ÓTIMO", "TEOR OTIMO"))
                    cap, _ = _correct_cap(raw_cap, quantity, binder)

                    out.append(
                        QualityRow(
                            nr,
                            row.attrib.get("hidden") not in {"1", "true"},
                            text(get("LINHA MEDIÇÃO", "LINHA")),
                            text(get("REF MEDIÇÃO")),
                            d,
                            norm_road(get("RODOVIA")),
                            norm_direction(get("SENTIDO")),
                            station(get("KMI")),
                            station(get("KMF")),
                            norm_lane(get("FAIXA")),
                            text(get("CÓDIGO TRAÇO", "CODIGO TRAÇO", "CÓDIGO DO TRAÇO")),
                            text(get("STATUS FINAL")).upper(),
                            text(get("RESUMO STATUS", "STATUS RESUMO")).upper(),
                            number(get("EXTENSÃO (m)", "EXTENSÃO (M)")),
                            number(get("VOLUME MASSA (m³)", "VOLUME MASSA (M³)")),
                            quantity,
                            cap,
                            number(get("TOTAL SERVIÇO (R$)")),
                            number(get("VALOR DE RETENÇÃO PROPOSTO")),
                            raw,
                        )
                    )
                row.clear()

    if header_row is None:
        raise ValueError("Cabeçalho da BD_QUALI não localizado.")

    subs = {k: None for k in TARGETS}
    sources: dict[str, str] = {}
    for key, aliases in TARGETS.items():
        exp = _col(hmap, *aliases)
        cand = []
        for r, c, ref, formula, val in subtotal_candidates:
            nf = norm_header(formula)
            if any(norm_header(a) in nf for a in aliases):
                cand.append((r, c, ref, val))
        if cand:
            pref = [x for x in cand if x[1] == exp] or cand
            ch = max(pref, key=lambda x: x[0])
            subs[key] = ch[3]
            sources[key] = f"{worksheet}!{ch[2]}"

    vis = [x for x in out if x.visible_excel]

    def sm(items, field):
        return float(sum((getattr(x, field) or 0.0) for x in items))

    all_total = sm(out, "total_service")
    visible_total = sm(vis, "total_service")
    all_extension = sm(out, "extension_m")
    all_volume = sm(out, "volume_mass_m3")
    all_quantity = sm(out, "quantity_t")
    all_cap = sm(out, "cap_project_t")
    all_retention = sm(out, "proposed_retention")

    report = read_report_summary(path, "RELATÓRIO")
    warnings: list[str] = []

    # Se o CAP consolidado do RELATÓRIO for estruturalmente impossível, o problema
    # não é pontual: a coluna CAP da própria BD_QUALI também contém fórmulas/valores
    # corrompidos em parte das linhas. Nessa situação, normaliza TODAS as linhas a
    # partir das duas entradas oficiais da BD_QUALI: QUANT PROJETO × TEOR ÓTIMO.
    report_cap_probe = report.cap_project_t if report.available else None
    report_qty_probe = report.quantity_t if report.available else None
    cap_report_invalid = bool(
        report_cap_probe is not None and report_qty_probe is not None and
        report_qty_probe >= 0 and report_cap_probe > report_qty_probe * 0.20
    )
    if cap_report_invalid:
        strict_cap = 0.0
        for r in out:
            binder = None
            for key, value in r.raw.items():
                if norm_header(key) == norm_header("TEOR ÓTIMO"):
                    binder = _binder_fraction(value)
                    break
            derived = (r.quantity_t * binder) if r.quantity_t is not None and binder is not None else 0.0
            r.cap_project_t = derived
            strict_cap += derived
        all_cap = strict_cap

    subtotal = subs["total_service"]
    subtotal_ref = sources.get("total_service", "")

    # Usa o RELATÓRIO somente quando o consolidado é compatível com a base.
    # Fórmulas/cache quebrados nessa aba não podem derrubar o total do Dashboard.
    report_total = report.total_service if report.available else None
    report_total_plausible = bool(
        report_total is not None
        and report_total >= 0
        and (abs(all_total) < 0.01 or abs(report_total - all_total) <= max(1.0, abs(all_total) * 0.20))
    )
    if report_total_plausible:
        official_total = report.total_service
        source_cell = (report.source_cells or {}).get("total_service", "RELATÓRIO!O11")
        summary_source = "RELATÓRIO"
    else:
        official_total = all_total
        source_cell = "BD_QUALI[TOTAL SERVIÇO (R$)] • soma de todas as linhas"
        summary_source = "BD_QUALI"
        if report_total is not None:
            warnings.append(
                f"Total do RELATÓRIO ({report_total:.2f}) incompatível com a soma da BD_QUALI ({all_total:.2f}); "
                "o Dashboard usou a soma completa das linhas."
            )
        if report.warning:
            warnings.append(report.warning)

    if subtotal is not None and official_total is not None:
        delta = subtotal - official_total
        if abs(delta) > max(0.05, abs(official_total) * 1e-6):
            warnings.append(
                f"O SUBTOTAL filtrado ({subtotal:.2f} em {subtotal_ref}) difere do consolidado ({official_total:.2f}). "
                "Isso ocorre quando a BD_QUALI está com filtro/linhas ocultas; o Dashboard usa o RELATÓRIO/soma completa."
            )

    # CAP: o relatório Pavidez enviado contém valor incompatível. Usa o valor do
    # relatório somente quando plausível; caso contrário, usa a própria BD_QUALI
    # (QUANT PROJETO × TEOR ÓTIMO), já corrigida linha a linha acima.
    report_cap = report.cap_project_t if report.available else None
    report_qty = report.quantity_t if report.available else None
    if report_cap is not None and report_qty and 0 <= report_cap <= report_qty * 0.20:
        cap_total = report_cap
        cap_source = (report.source_cells or {}).get("cap_project_t", "RELATÓRIO!O15")
    else:
        cap_total = all_cap
        cap_source = "BD_QUALI[QUANT PROJETO × TEOR ÓTIMO / CAP válido]"
        if report_cap is not None and report_qty and report_cap > report_qty * 0.20:
            warnings.append(
                f"CAP do RELATÓRIO ({report_cap:.2f} t) é incompatível com a quantidade ({report_qty:.2f} t). "
                f"Foi usado o CAP derivado da própria BD_QUALI ({all_cap:.2f} t)."
            )

    extension = report.extension_m if report_total_plausible and report.extension_m is not None else all_extension
    volume = report.volume_mass_m3 if report_total_plausible and report.volume_mass_m3 is not None else all_volume
    quantity = report.quantity_t if report_total_plausible and report.quantity_t is not None else all_quantity

    row_financial = {"approved": 0.0, "pending": 0.0, "reproved": 0.0, "unclassified": 0.0}
    for item in out:
        value = float(item.total_service or 0.0)
        item_status = str(item.status_final or "").upper().strip()
        if item_status.startswith("APROVADO"):
            row_financial["approved"] += value
        elif item_status.startswith("P.") or "PEND" in item_status:
            row_financial["pending"] += value
        elif "REP" in item_status or "RETRAB" in item_status:
            row_financial["reproved"] += value
        else:
            row_financial["unclassified"] += value

    diff = (official_total - all_total) if official_total is not None else None
    if diff is not None and abs(diff) > max(0.05, abs(official_total or 0) * 1e-6):
        warnings.append(
            f"Consolidado ({official_total:.2f}) difere da soma de todas as linhas da BD_QUALI ({all_total:.2f}) em {diff:.2f}."
        )

    summary = QualitySummary(
        official_total,
        visible_total,
        diff,
        source_cell,
        extension,
        volume,
        quantity,
        cap_total,
        all_retention,
        len(vis),
        len(out),
        " | ".join(warnings),
        total_service_all_rows=all_total,
        subtotal_excel=subtotal,
        subtotal_source_cell=subtotal_ref,
        summary_source=summary_source,
        approved_value=report.approved_value if report_total_plausible else row_financial["approved"],
        pending_value=report.pending_value if report_total_plausible else row_financial["pending"],
        reproved_value=report.reproved_value if report_total_plausible else row_financial["reproved"],
        unclassified_value=report.unclassified_value if report_total_plausible else row_financial["unclassified"],
        period_start=report.period_start.isoformat() if report.period_start else None,
        period_end=report.period_end.isoformat() if report.period_end else None,
        cap_source=cap_source,
    )
    return out, summary


def row_to_dict(r):
    d = asdict(r)
    d["date"] = r.date.isoformat() if r.date else None
    return d
