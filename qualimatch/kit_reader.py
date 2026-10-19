from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any
from zipfile import ZipFile
import xml.etree.ElementTree as ET

from .normalizers import norm_header, norm_road, station, text, to_date
from .xlsx_xml import NS_MAIN, cell_value, row_cells, shared_strings, sheet_path


@dataclass(slots=True)
class KitRow:
    source_row: int
    seq: str
    service: str
    application_date: date | None
    mix_project: str
    period: str
    road: str
    kmi: int | None
    kmf: int | None
    receipt_date: date | None
    delivery_status: str
    status: str
    status_1: str
    status_2: str
    status_3: str
    status_4: str
    status_5: str
    status_6: str
    status_7: str
    status_8: str
    sin_retro: str
    raw: dict[str, Any]


def read_kits(path: str | Path, worksheet: str = "d.KIT") -> list[KitRow]:
    """Lê a tabela operacional de kits da contratada diretamente do XLSX.

    A leitura usa os valores já calculados/cacheados pelo Excel, portanto funciona
    mesmo com fórmulas estruturadas na planilha (ex.: STATUS e prazo de entrega).
    """
    path = Path(path)
    out: list[KitRow] = []
    hmap: dict[str, int] = {}
    originals: dict[int, str] = {}
    header: int | None = None

    with ZipFile(path) as z:
        strings = shared_strings(z)
        sp = sheet_path(z, worksheet)
        with z.open(sp) as f:
            for _, row in ET.iterparse(f, events=("end",)):
                if row.tag != f"{{{NS_MAIN}}}row":
                    continue
                nr = int(row.attrib.get("r", "0"))
                cells = row_cells(row)

                if header is None:
                    hm: dict[str, int] = {}
                    orig: dict[int, str] = {}
                    for col, c in cells.items():
                        v = cell_value(c, strings)
                        if v not in (None, ""):
                            hm[norm_header(v)] = col
                            orig[col] = text(v)
                    required = {
                        norm_header("# SEQ"),
                        norm_header("SERVIÇO"),
                        norm_header("DATA APLICAÇÃO"),
                        norm_header("PROJETO MISTURA"),
                        norm_header("RODOVIA"),
                    }
                    if nr <= 30 and required.issubset(hm):
                        header = nr
                        hmap = hm
                        originals = orig
                    row.clear()
                    continue

                def col(*names: str) -> int | None:
                    for name in names:
                        c = hmap.get(norm_header(name))
                        if c:
                            return c
                    return None

                def get(*names: str):
                    c = col(*names)
                    return cell_value(cells.get(c), strings) if c else None

                seq = text(get("# SEQ", "SEQ #", "SEQ"))
                service = text(get("SERVIÇO"))
                application = to_date(get("DATA APLICAÇÃO"))
                mix_project = text(get("PROJETO MISTURA"))
                road = norm_road(get("RODOVIA"))
                overall = text(get("STATUS"))

                # A tabela possui duas linhas-formulário no fim com apenas SEQ.
                # Elas não são kits reais e não devem aparecer no sistema.
                if not seq or not any((service, application, mix_project, road, overall)):
                    row.clear()
                    continue

                raw: dict[str, Any] = {}
                for idx, name in originals.items():
                    v = cell_value(cells.get(idx), strings)
                    if v not in (None, ""):
                        raw[name] = v
                # Permite diferenciar "planilha antiga sem coluna ENTREGA" de
                # "coluna ENTREGA existente, porém ainda vazia". Essa distinção
                # é usada para definir de quem é a responsabilidade da pendência.
                raw["_qualimatch_entrega_coluna"] = bool(col("ENTREGA", "STATUS ENTREGA"))

                out.append(
                    KitRow(
                        source_row=nr,
                        seq=seq,
                        service=service,
                        application_date=application,
                        mix_project=mix_project,
                        period=text(get("PERÍODO", "PERIODO")),
                        road=road,
                        kmi=station(get("KM INICIAL", "KMI")),
                        kmf=station(get("KM FINAL", "KMF")),
                        receipt_date=to_date(get("DATA RECEBIMENTO")),
                        delivery_status=text(get("ENTREGA", "STATUS ENTREGA")),
                        status=overall,
                        status_1=text(get("1.CTRL APLICAÇÃO", "1 CTRL APLICAÇÃO")),
                        status_2=text(get("2. CTRL USINAGEM", "2 CTRL USINAGEM")),
                        status_3=text(get("3.CTRL Vv", "3 CTRL VV")),
                        status_4=text(get("4.CTRL TAXA", "4 CTRL TAXA")),
                        status_5=text(get("5.CTRL LIGANTE", "5 CTRL LIGANTE")),
                        status_6=text(get("6. CTRL MANCHA DE AREIA", "6 CTRL MANCHA DE AREIA")),
                        status_7=text(get("7.CTRL PENDULO", "7 CTRL PÊNDULO", "7 CTRL PENDULO")),
                        status_8=text(get("8.SIN ESP ÚMIDA", "8 SIN ESP ÚMIDA", "8 SIN ESP UMIDA")),
                        sin_retro=text(get("SIN. - RETRO", "SIN - RETRO", "SIN. RETRO")),
                        raw=raw,
                    )
                )
                row.clear()

    if header is None:
        raise ValueError(
            f"Cabeçalho da tabela de kits não localizado na aba {worksheet!r}. "
            "Esperado: # SEQ, SERVIÇO, DATA APLICAÇÃO, PROJETO MISTURA e RODOVIA."
        )
    return out


def row_to_dict(r: KitRow) -> dict[str, Any]:
    d = asdict(r)
    d["application_date"] = r.application_date.isoformat() if r.application_date else None
    d["receipt_date"] = r.receipt_date.isoformat() if r.receipt_date else None
    return d
