from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from .normalizers import number, text, to_date
from .xlsx_xml import NS_MAIN, cell_value, row_cells, shared_strings, sheet_path


@dataclass(slots=True)
class ReportSummary:
    available: bool = False
    contractor: str = ""
    total_service: float | None = None
    extension_m: float | None = None
    volume_mass_m3: float | None = None
    quantity_t: float | None = None
    cap_project_t: float | None = None
    approved_value: float | None = None
    pending_value: float | None = None
    reproved_value: float | None = None
    unclassified_value: float | None = None
    period_start: date | None = None
    period_end: date | None = None
    source_cells: dict[str, str] | None = None
    warning: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.period_start:
            d["period_start"] = self.period_start.isoformat()
        if self.period_end:
            d["period_end"] = self.period_end.isoformat()
        return d


def _top_cells(path: Path, worksheet: str = "RELATÓRIO", max_row: int = 20) -> dict[str, Any]:
    """Lê somente o topo do RELATÓRIO usando os valores em cache do XLSX.

    Isso é muito mais rápido do que carregar a planilha inteira e, principalmente,
    independe do filtro que esteja ativo visualmente na aba BD_QUALI.
    """
    out: dict[str, Any] = {}
    with ZipFile(path) as z:
        strings = shared_strings(z)
        sp = sheet_path(z, worksheet)
        with z.open(sp) as f:
            for _, row in ET.iterparse(f, events=("end",)):
                if row.tag != f"{{{NS_MAIN}}}row":
                    continue
                nr = int(row.attrib.get("r", "0") or 0)
                if nr > max_row:
                    row.clear()
                    break
                for c in row_cells(row).values():
                    ref = c.attrib.get("r", "")
                    out[ref] = cell_value(c, strings)
                row.clear()
    return out


def read_report_summary(path: str | Path, worksheet: str = "RELATÓRIO") -> ReportSummary:
    path = Path(path)
    try:
        c = _top_cells(path, worksheet)
    except Exception as e:
        return ReportSummary(available=False, warning=f"RELATÓRIO não pôde ser lido: {type(e).__name__}: {e}")

    # Validação mínima da estrutura usada nas duas planilhas oficiais fornecidas.
    label_total = text(c.get("M11")).upper()
    total = number(c.get("O11"))
    if "TOTAL SERVI" not in label_total or total is None:
        return ReportSummary(available=False, warning="RELATÓRIO encontrado, mas o bloco consolidado M11:O15 não foi reconhecido.")

    approved = number(c.get("R11"))
    pending = number(c.get("V11"))
    reproved = number(c.get("AA11"))
    classified = sum(v or 0.0 for v in (approved, pending, reproved))
    unclassified = total - classified
    if abs(unclassified) < 0.01:
        unclassified = 0.0

    return ReportSummary(
        available=True,
        contractor=text(c.get("G10")).upper(),
        total_service=total,
        extension_m=number(c.get("O12")),
        volume_mass_m3=number(c.get("O13")),
        quantity_t=number(c.get("O14")),
        cap_project_t=number(c.get("O15")),
        approved_value=approved,
        pending_value=pending,
        reproved_value=reproved,
        unclassified_value=unclassified,
        period_start=to_date(c.get("H13")),
        period_end=to_date(c.get("K13")),
        source_cells={
            "total_service": f"{worksheet}!O11",
            "extension_m": f"{worksheet}!O12",
            "volume_mass_m3": f"{worksheet}!O13",
            "quantity_t": f"{worksheet}!O14",
            "cap_project_t": f"{worksheet}!O15",
            "approved_value": f"{worksheet}!R11",
            "pending_value": f"{worksheet}!V11",
            "reproved_value": f"{worksheet}!AA11",
        },
    )
