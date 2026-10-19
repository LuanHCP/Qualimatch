from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
import hashlib
import re
from typing import Any

from pypdf import PdfReader

from .normalizers import norm_direction, norm_lane, norm_road, number, station, text, to_date

DATE_RE = r"\d{2}[./-]\d{2}[./-]\d{2,4}"
PARSER_VERSION = "3.8.14"


@dataclass(slots=True)
class Sample:
    phase: str
    cp_number: str
    application_date: date | None
    counterproof: bool
    direction: str
    lane: str
    station: int | None
    position: str
    thickness_exec_cm: float | None
    thickness_project_cm: float | None
    ratio_ab_pct: float | None
    gmb: float | None
    voids_pct: float | None
    rice_gmm: float | None = None


@dataclass(slots=True)
class Certificate:
    contractor: str
    number: str
    file_path: str
    file_hash: str
    service_date: date | None
    extraction_date: date | None
    road: str
    kmi: int | None
    kmf: int | None
    trace_approved: str
    routine_result: str
    counterproof_result: str
    has_counterproof: bool
    samples: list[Sample]
    raw: dict[str, Any]


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _result(text_page: str) -> str:
    up = text_page.upper()
    if "O TRECHO NÃO ATENDE" in up or "O TRECHO NAO ATENDE" in up or "REPROVADO POR ANÁLISE ESTATÍSTICA" in up or "REPROVADO POR ANALISE ESTATISTICA" in up:
        return "REPROVADO"
    if "O TRECHO ATENDE" in up:
        return "APROVADO"
    # O BI330 normalmente traz resultados individuais de VV e espessura. O status
    # estatístico detalhado é calculado separadamente no serviço de consultas.
    return ""


def _normalize_date_token(item: str) -> str | None:
    d = to_date(item)
    return d.isoformat() if d else None


def _date_tokens(txt: str, max_dates: int = 8) -> list[str]:
    out: list[str] = []
    for item in re.findall(DATE_RE, txt):
        d = _normalize_date_token(item)
        if d and d not in out:
            out.append(d)
    return out[:max_dates]


def _dates_between(txt: str, start_label: str, end_label: str | None, max_dates: int = 8) -> list[str]:
    low = txt.lower()
    i = low.find(start_label.lower())
    if i < 0:
        return []
    chunk = txt[i + len(start_label):]
    if end_label:
        j = chunk.lower().find(end_label.lower())
        if j >= 0:
            chunk = chunk[:j]
    return _date_tokens(chunk, max_dates)


def _service_dates_from_page(txt: str, max_dates: int = 8) -> list[str]:
    """Extrai todas as Datas ex. serviço mesmo quando o PDF embaralha a ordem.

    Alguns BI330 antigos têm a célula "Datas ex. serviço" visualmente correta,
    mas o texto extraído pelo PDF fica assim:
        25/08/2025 Data Ext. dos CP's: 04/12/2025 ...
    e o rótulo "Datas ex. serviço:" aparece somente no fim da página. Nesses
    casos, procurar apenas texto *depois* do rótulo devolvia vazio.
    """
    direct = _dates_between(txt, "Datas ex. serviço:", "Data Ext. dos CP's:", max_dates)

    # Layout com a(s) data(s) de execução imediatamente ANTES do rótulo da
    # extração dos CPs. Funciona para 1 ou vários dias de execução.
    before_ext: list[str] = []
    pattern = rf"((?:{DATE_RE}\s*){{1,{max_dates}}})\s*Data\s+Ext\.?\s+dos\s+CP['’]?s\s*:"
    m = re.search(pattern, txt, re.I)
    if m:
        before_ext = _date_tokens(m.group(1), max_dates)

    out: list[str] = []
    for d in direct + before_ext:
        if d not in out:
            out.append(d)
    return out[:max_dates]


def _extraction_dates_from_page(txt: str, max_dates: int = 8) -> list[str]:
    """Extrai a Data Ext. dos CPs tolerando apóstrofos e variações de layout."""
    patterns = [
        r"Data\s+Ext\.?\s+dos\s+CP(?:['’´`]?s)?\s*:?",
        r"Data\s+Extra[cç][aã]o\s+dos\s+CP(?:['’´`]?s)?\s*:?",
    ]
    out: list[str] = []
    for pattern in patterns:
        m = re.search(pattern, txt, re.I)
        if not m:
            continue
        chunk = txt[m.end():]
        end = re.search(r"\b(?:Turno|Data\s+ensaios|Data\s+Rec\.?\s+em\s+Lab\.?|Usina)\b", chunk, re.I)
        if end:
            chunk = chunk[:end.start()]
        for d in _date_tokens(chunk, max_dates):
            if d not in out:
                out.append(d)
        if out:
            break
    return out[:max_dates]



def _merge_date_lists(target: list[str], values: list[str]) -> None:
    for value in values:
        if value and value not in target:
            target.append(value)


def _select_extraction_date(extraction_dates: list[str], service_dates: list[str], receipt_dates: list[str], assay_dates: list[str]) -> date | None:
    """Escolhe a Data Ext. mais coerente quando os dois modos de extração discordam."""
    candidates = [to_date(x) for x in extraction_dates]
    candidates = [x for x in candidates if x]
    if not candidates:
        return None
    services = [to_date(x) for x in service_dates]; services = [x for x in services if x]
    receipts = [to_date(x) for x in receipt_dates]; receipts = [x for x in receipts if x]
    assays = [to_date(x) for x in assay_dates]; assays = [x for x in assays if x]
    lo = max(services) if services else None
    hi_receipt = min(receipts) if receipts else None
    hi_assay = min(assays) if assays else None

    def score(d: date) -> int:
        value = 0
        if lo:
            value += 3 if d >= lo else -4
        if hi_receipt:
            value += 4 if d <= hi_receipt else -5
        if hi_assay:
            value += 2 if d <= hi_assay else -3
        return value

    return max(enumerate(candidates), key=lambda x: (score(x[1]), -x[0]))[1]

def _page_text_variants(page) -> tuple[str, str]:
    plain = page.extract_text() or ""
    try:
        layout = page.extract_text(extraction_mode="layout") or ""
    except (TypeError, ValueError, NotImplementedError):
        layout = ""
    return plain, layout


def _samples_from_text(page_text: str) -> list[Sample]:
    """Extrai CPs em layouts BV antigos/novos, inclusive linhas quebradas."""
    raw_lines = [re.sub(r"\s+", " ", line.strip()) for line in page_text.splitlines() if line.strip()]
    out: list[Sample] = []
    sample_start = re.compile(
        rf"^\d+(?:\s+\d+)?\s+{DATE_RE}(?:\s*[-_.]?\s*[A-Z]+\d+(?:\.[A-Z]+\d+)*)?\s+(?:SIM|N[ÃA]O)\b",
        re.I,
    )

    for i, line in enumerate(raw_lines):
        s = _parse_sample_line(line)
        if s:
            out.append(s)
            continue
        if not sample_start.search(line):
            continue
        combined = line
        for j in range(i + 1, min(len(raw_lines), i + 5)):
            if sample_start.search(raw_lines[j]):
                break
            if re.match(r"^(?:Limites|Xm[ií]n|Resultado|M[ÉE]DIA|DESVIO|%\s*REPROVA)", raw_lines[j], re.I):
                break
            combined += " " + raw_lines[j]
            s = _parse_sample_line(combined)
            if s:
                out.append(s)
                break

    # Fallback para PDFs em que uma linha visual inteira foi repartida pelo
    # extrator de texto. Compacta a página e recorta cada CP pelo início do próximo.
    compact = re.sub(r"\s+", " ", page_text)
    starts = list(re.finditer(
        rf"(?<!\d)(?:\d+\s+)?\d+\s+{DATE_RE}(?:\s*[-_.]?\s*[A-Z]+\d+(?:\.[A-Z]+\d+)*)?\s+(?:SIM|N[ÃA]O)\b",
        compact, re.I,
    ))
    seen = {(x.cp_number, x.application_date, x.station, x.counterproof) for x in out}
    for idx, m in enumerate(starts):
        stop = starts[idx + 1].start() if idx + 1 < len(starts) else min(len(compact), m.start() + 650)
        chunk = compact[m.start():stop]
        boundary = re.search(r"\b(?:Limites|Resultado|M[ÉE]DIA|DESVIO\s+PADR[ÃA]O)\b", chunk, re.I)
        if boundary:
            chunk = chunk[:boundary.start()]
        sample = _parse_sample_line(chunk)
        if sample:
            key = (sample.cp_number, sample.application_date, sample.station, sample.counterproof)
            if key not in seen:
                out.append(sample); seen.add(key)
    return out


def _road_from_filename(name: str) -> str:
    m = re.search(r"(?<![A-Z0-9])(BR|PR)\s*[-_/ ]?\s*(\d{2,3})(?!\d)", name, re.I)
    return norm_road(f"{m.group(1)}-{m.group(2)}") if m else ""


ROAD_TOKEN = r"(?:BR|PR)\s*[-/]?\s*\d{2,3}(?:\s*[-/]\s*PR)?"
STATION_TOKEN = r"\d{1,4}\s*\+\s*\d{1,3}"


def _segment_from_text(value: str) -> tuple[str, int | None, int | None]:
    """Extrai Trecho/Rodovia e Segmento Ensaiado do cabeçalho do BI330.

    Os PDFs do BI330 são planilhas convertidas para PDF. Dependendo da versão do
    arquivo, o pypdf pode devolver o cabeçalho em uma única linha ou quebrar
    "Trecho", "Km" e "Segmento Ensaiado" em colunas/linhas diferentes.
    Por isso a leitura é feita por partes e não depende de uma única regex rígida.
    """
    if not value:
        return "", None, None

    # Normaliza somente espaços invisíveis; mantém quebras como whitespace para as regexes.
    txt = value.replace("\xa0", " ").replace("–", "-").replace("—", "-")

    road = ""
    kmi = kmf = None

    # Rodovia: preferencialmente o valor após o rótulo Trecho. Limita a janela para
    # não capturar uma rodovia citada muito depois na página.
    m_trecho = re.search(r"Trecho\s*:?\s*", txt, re.I)
    if m_trecho:
        road_window = txt[m_trecho.end():m_trecho.end() + 180]
        m_road = re.search(ROAD_TOKEN, road_window, re.I)
        if m_road:
            road = norm_road(m_road.group(0))

    # Segmento ensaiado: aceita quebras de linha, espaços dentro da estaca e
    # separadores 'a', 'até' ou hífen.
    m_seg_label = re.search(r"Segmento\s+Ensaiado\s*:?", txt, re.I)
    if m_seg_label:
        seg_window = txt[m_seg_label.end():m_seg_label.end() + 260]
        m_st = re.search(
            rf"(?P<ini>{STATION_TOKEN})\s*(?:a|at[eé]|-)\s*(?P<fim>{STATION_TOKEN})",
            seg_window,
            re.I,
        )
        if m_st:
            kmi = station(m_st.group("ini"))
            kmf = station(m_st.group("fim"))

    # Fallback para layouts em que o rótulo 'Segmento Ensaiado' é perdido, mas
    # 'Trecho: <rodovia> Km' e as duas estacas continuam próximas no cabeçalho.
    if kmi is None or kmf is None:
        m_head = re.search(
            rf"Trecho\s*:?\s*(?P<road>{ROAD_TOKEN}).{{0,240}}?"
            rf"(?P<ini>{STATION_TOKEN})\s*(?:a|at[eé]|-)\s*(?P<fim>{STATION_TOKEN})",
            txt,
            re.I | re.S,
        )
        if m_head:
            road = road or norm_road(m_head.group("road"))
            kmi = station(m_head.group("ini"))
            kmf = station(m_head.group("fim"))

    return road, kmi, kmf


def _segment_from_candidates(candidates: list[str]) -> tuple[str, int | None, int | None, str]:
    """Procura o trecho em TODAS as variantes de extração do cabeçalho.

    Retorna a melhor combinação e a origem usada, evitando o bug em que a versão
    mais longa do texto era escolhida mesmo quando justamente ela quebrava as
    células do cabeçalho.
    """
    best: tuple[str, int | None, int | None, str] = ("", None, None, "")
    best_score = -1
    for idx, candidate in enumerate(candidates):
        road, kmi, kmf = _segment_from_text(candidate)
        score = (3 if road else 0) + (4 if kmi is not None and kmf is not None else 0)
        # Desempate favorece a primeira leitura (texto corrido), que costuma
        # representar melhor a ordem visual do cabeçalho.
        if score > best_score:
            best = (road, kmi, kmf, "TEXTO" if idx == 0 else "LAYOUT")
            best_score = score
        if score == 7:
            break
    return best


def _clean_trace(value: str) -> str:
    value = (value or "").strip()
    # No modo layout, outras colunas da mesma linha podem vir anexadas ao traço.
    value = re.split(r"\s{4,}|\bQuant\.?\s*CP['’]?s\s*=|\bDensidade\s+[áa]gua|\bData\s+Aprova[cç][aã]o", value, maxsplit=1, flags=re.I)[0].strip()
    value = re.sub(r"\s+\d+\s+[\d.,]+\s*$", "", value).strip()
    compact = re.sub(r"\s+", " ", value).upper()
    bad = {"DIA 1 DIA 2 USINA", "DIA 1 DIA 2", "USINA", "PEDREIRA"}
    if compact in bad or ("DIA 1" in compact and "DIA 2" in compact and len(compact) < 40):
        return ""
    return value


def _parse_health(
    extraction_date: date | None, service_dates: list[str], road: str,
    kmi: int | None, kmf: int | None, trace: str, samples: list[Sample],
    receipt_dates: list[str] | None = None, assay_dates: list[str] | None = None,
) -> tuple[str, list[str], list[str]]:
    """Separa qualidade da extração de alertas operacionais.

    PARCIAL significa que faltou dado relevante na leitura automática. Quando todos
    os campos essenciais foram recuperados, o estado é CARREGADO. Inconsistências
    de datas são alertas de negócio e não rebaixam uma leitura completa para PARCIAL.
    """
    parse_warnings: list[str] = []
    validation_warnings: list[str] = []
    if extraction_date is None:
        parse_warnings.append("Data Ext. dos CP's não encontrada")
    if not service_dates and not any(s.application_date for s in samples):
        parse_warnings.append("Data ex. serviço não identificada")
    if not road:
        parse_warnings.append("Rodovia não identificada")
    if kmi is None or kmf is None:
        parse_warnings.append("Segmento ensaiado não identificado")
    if not trace:
        parse_warnings.append("Traço aprovado não identificado")
    if not samples:
        parse_warnings.append("Nenhum corpo de prova extraído")

    if extraction_date:
        receipt_parsed = [to_date(x) for x in (receipt_dates or [])]
        receipt_parsed = [x for x in receipt_parsed if x]
        # Regra operacional: o recebimento no laboratório não pode anteceder
        # a Data Ext. dos CPs. Quando isso ocorrer, destacar para conferência/BV.
        if any(d < extraction_date for d in receipt_parsed):
            validation_warnings.append(
                "Data de recebimento em laboratório anterior à Data Ext. dos CPs — enviar para a BV"
            )

    status = "CARREGADO" if not parse_warnings else "PARCIAL"
    return status, parse_warnings, validation_warnings


def _printed_summary(page_text: str) -> dict[str, float | None]:
    """Extrai os valores do quadro estatístico impresso no BI330 quando disponíveis.

    O PDF normalmente apresenta duas colunas no quadro: relação A/B (espessura)
    e volume de vazios. Usamos esses números impressos para exibição, porque são
    os valores que o usuário enxerga no certificado. Os cálculos internos continuam
    disponíveis como fallback quando a extração textual não encontra o quadro.
    """
    out: dict[str, float | None] = {
        "k": None,
        "ratio_mean_pct": None,
        "ratio_std_pct": None,
        "ratio_xmin_pct": None,
        "ratio_xmax_pct": None,
        "vv_mean_pct": None,
        "vv_std_pct": None,
        "vv_xmin_pct": None,
        "vv_xmax_pct": None,
    }
    mk = re.search(r"\bk\s*=\s*([\d,.]+)", page_text, re.I)
    if mk:
        out["k"] = number(mk.group(1))

    # Ex.: MÉDIA 116,0% MÉDIA 5,2%
    m = re.search(r"M[ÉE]DIA\s+([\d,.]+)%\s+M[ÉE]DIA\s+([\d,.]+)%", page_text, re.I)
    if m:
        out["ratio_mean_pct"] = number(m.group(1)); out["vv_mean_pct"] = number(m.group(2))
    m = re.search(r"DESVIO\s+PADR[ÃA]O\s+([\d,.]+)%\s+DESVIO\s+PADR[ÃA]O\s+([\d,.]+)%", page_text, re.I)
    if m:
        out["ratio_std_pct"] = number(m.group(1)); out["vv_std_pct"] = number(m.group(2))
    mins = re.findall(r"X(?:m[ií]n|MIN)\s+([\d,.]+)%\s+X(?:m[ií]n|MIN)\s+([\d,.]+)%", page_text, re.I)
    if mins:
        # A primeira ocorrência costuma ser o limite normativo (95% / 3,5%).
        # A última é o Xmin estatístico calculado no quadro do certificado.
        out["ratio_xmin_pct"] = number(mins[-1][0]); out["vv_xmin_pct"] = number(mins[-1][1])
    maxs = re.findall(r"Xm[áa]x\s+([\d,.]+)%\s+Xmax\s+([\d,.]+)%", page_text, re.I)
    if maxs:
        out["ratio_xmax_pct"] = number(maxs[-1][0]); out["vv_xmax_pct"] = number(maxs[-1][1])
    return out


def _parse_sample_line(line: str, phase: str = "ROTINA") -> Sample | None:
    """Extrai uma linha de CP usando data/estaca/percentual como âncoras estáveis."""
    line = re.sub(r"\s+", " ", line.strip())
    head = re.match(
        rf"^(?P<ids>\d+(?:\s+\d+)?)\s+"
        rf"(?P<date>{DATE_RE})(?:\s*[-_.]?\s*[A-Z]+\d+(?:\.[A-Z]+\d+)*)?\s+"
        r"(?P<flag>SIM|N[ÃA]O)\s+(?P<body>.+)$",
        line, re.I,
    )
    if not head:
        return None

    body = head.group("body")
    sm = re.search(r"(?P<station>\d{1,4}\s*\+\s*\d{1,3})", body)
    if not sm:
        return None
    loc_prefix = body[:sm.start()].strip()
    after_station = body[sm.end():].strip()
    loc_tokens = loc_prefix.split()
    if not loc_tokens:
        return None
    direction = loc_tokens[0]
    lane = " ".join(loc_tokens[1:])  # pode ser vazio em alguns BI330

    # Depois da estaca, procura o primeiro bloco Esp.Exec / Esp.Proj / A/B.
    triple = re.search(
        r"(?P<position>.*?)\s*(?P<a>[-+]?\d+(?:[.,]\d+)?)\s+"
        r"(?P<b>[-+]?\d+(?:[.,]\d+)?)\s+"
        r"(?P<ratio>[-+]?\d+(?:[.,]\d+)?%)\s+(?P<rest>.+)$",
        after_station, re.I,
    )
    if not triple:
        return None
    position = triple.group("position").strip() or ""
    rest = triple.group("rest").split()
    if len(rest) < 3:
        return None

    # Rice: normalmente vem após o diâmetro; procura o primeiro valor fisicamente
    # plausível entre os primeiros campos, evitando depender de posição absoluta.
    rice_gmm = None
    for tok in rest[:5]:
        val = number(tok)
        if val is not None and 1.5 <= val <= 3.5:
            rice_gmm = val
            break

    pct_positions = [i for i,tok in enumerate(rest) if tok.endswith('%') and number(tok) is not None]
    if not pct_positions:
        return None

    # Ordem esperada no BI330:
    #   ... Gmb | Volume de Vazios (%) | Volume de Vazios com Plástico Filme (%)
    #
    # Regra de negócio:
    # - quando "Volume de Vazios com Plástico Filme (%)" estiver preenchido,
    #   ele é o Vv verdadeiro do CP;
    # - quando estiver vazio, usa "Volume de Vazios (%)".
    #
    # No texto extraído, quando os dois últimos campos são percentuais, o último
    # corresponde ao Vv com plástico filme e o penúltimo ao Vv convencional.
    # O Gmb continua sendo o campo imediatamente anterior aos dois percentuais.
    has_plastic_film_vv = (
        len(rest) >= 3
        and rest[-1].endswith('%')
        and number(rest[-1]) is not None
        and rest[-2].endswith('%')
        and number(rest[-2]) is not None
    )
    if has_plastic_film_vv:
        vv_idx = len(rest) - 1
        gmb_idx = len(rest) - 3
    else:
        vv_idx = pct_positions[-1]
        gmb_idx = vv_idx - 1

    vv = number(rest[vv_idx])
    gmb = number(rest[gmb_idx]) if gmb_idx >= 0 else None
    if gmb is not None and not (1.5 <= gmb <= 3.5):
        gmb = None

    ids = head.group("ids").split()
    flag = head.group("flag").upper().replace("Ã", "A")
    return Sample(
        phase=phase,
        cp_number=ids[-1],
        application_date=to_date(head.group("date")),
        counterproof=flag == "SIM",
        direction=norm_direction(direction),
        lane=norm_lane(lane),
        station=station(sm.group("station")),
        position=text(position).upper(),
        thickness_exec_cm=number(triple.group("a")),
        thickness_project_cm=number(triple.group("b")),
        ratio_ab_pct=number(triple.group("ratio")),
        gmb=gmb,
        voids_pct=vv,
        rice_gmm=rice_gmm,
    )


def _rice_day_from_page(page_text: str) -> float | None:
    """Fallback para BI330 em que o Rice não fica alinhado na linha do CP."""
    m = re.search(r"Rice\s+do\s+Dia\s*=\s*([\d,.]+)", page_text, re.I)
    value = number(m.group(1)) if m else None
    return value if value is not None and 1.5 <= value <= 3.5 else None


def parse_pdf(path: str | Path, contractor_hint: str | None = None) -> Certificate:
    path = Path(path)
    reader = PdfReader(path)
    variants = [_page_text_variants(p) for p in reader.pages]
    page_texts = [plain for plain, _ in variants]
    layout_texts = [layout for _, layout in variants]
    if not page_texts:
        raise ValueError("PDF sem páginas.")
    full = "\n".join(page_texts + [x for x in layout_texts if x])
    if not full.strip():
        raise ValueError("PDF sem texto extraível (imagem/digitalização). Envie o PDF original com texto ou uma versão com OCR; o certificado existente não foi substituído.")

    # Mantém a identidade numérica compatível com a base antiga, inclusive nos
    # arquivos de contra-prova BI330-PG-CP-xxxx. O texto original fica no raw.
    number_match = (
        re.search(r"\bBI330\s*[-_]\s*(?:PG\s*[-_]\s*CP\s*[-_]\s*)?0*(\d{1,5})(?:\.\d{2})?\b", full, re.I)
        or re.search(r"BI330\s*[-_]\s*(?:PG\s*[-_]\s*CP\s*[-_]\s*)?0*(\d{1,5})(?:\.\d{2})?", path.name, re.I)
    )
    if not number_match:
        raise ValueError("Número BI330 não encontrado no PDF.")
    cert_number = f"BI330-{int(number_match.group(1)):04d}"
    original_number_match = re.search(r"\bBI330[-_A-Z]*[-_]?\d{3,5}(?:\.\d{2})?\b", full, re.I) or re.search(r"BI330[-_A-Z]*[-_]?\d{3,5}(?:\.\d{2})?", path.name, re.I)
    original_number = original_number_match.group(0).replace("_", "-") if original_number_match else cert_number

    contractor = (contractor_hint or "").upper().strip()
    m_con = re.search(r"(?:Construtora|Executora):\s*([^\n\r]+)", full, re.I)
    con_line = m_con.group(1).upper() if m_con else ""
    if "PAVDEZ" in con_line or "PAVIDEZ" in con_line:
        contractor = "PAVIDEZ"
    elif "ARENA" in con_line:
        contractor = "ARENA"
    if contractor not in {"ARENA", "PAVIDEZ"}:
        raise ValueError("Contratada não identificada (ARENA/PAVIDEZ).")

    # Para metadados, testa texto corrido e modo layout. O modo layout preserva
    # melhor células e colunas em várias gerações do BI330.
    first_candidates = [page_texts[0]] + ([layout_texts[0]] if layout_texts and layout_texts[0] else [])
    service_dates: list[str] = []
    extraction_dates: list[str] = []
    assay_dates: list[str] = []
    receipt_dates: list[str] = []
    for candidate in first_candidates:
        _merge_date_lists(service_dates, _service_dates_from_page(candidate))
        _merge_date_lists(extraction_dates, _extraction_dates_from_page(candidate))
        _merge_date_lists(assay_dates, _dates_between(candidate, "Data ensaios:", "Data Rec. em Lab.:"))
        _merge_date_lists(receipt_dates, _dates_between(candidate, "Data Rec. em Lab.:", "Usina"))
    service_date = to_date(service_dates[0]) if service_dates else None
    extraction_date = _select_extraction_date(extraction_dates, service_dates, receipt_dates, assay_dates)
    first = max(first_candidates, key=len)

    # TRECHO: não escolhe somente a variante de texto mais longa. Procura em
    # texto corrido + layout e guarda qual delas conseguiu ler o cabeçalho.
    road, kmi, kmf, segment_source = _segment_from_candidates(first_candidates)
    if not road:
        road = _road_from_filename(path.name)
        if road:
            segment_source = (segment_source + "+ARQUIVO").strip("+")

    trace = ""
    m_trace = re.search(r"Traço\s+Aprovado:\s*([^\n\r]+)", first, re.I)
    if m_trace:
        trace = _clean_trace(m_trace.group(1))

    samples: list[Sample] = []
    routine_result = ""
    counterproof_result = ""
    phases_seen: set[str] = set()
    phase_summaries: dict[str, dict[str, Any]] = {}

    for page_no, page_text in enumerate(page_texts, 1):
        candidates = [page_text]
        if page_no - 1 < len(layout_texts) and layout_texts[page_no - 1]:
            candidates.append(layout_texts[page_no - 1])
        parsed_candidates = [(_samples_from_text(t), t) for t in candidates]
        page_samples, page_text = max(parsed_candidates, key=lambda item: len(item[0]))
        if not page_samples:
            continue

        # O cabeçalho da tabela contém literalmente "Contra Prova?" até em páginas
        # de rotina. Portanto a fase deve ser definida pelos CPs marcados SIM.
        phase = "CONTRA_PROVA" if any(s.counterproof for s in page_samples) else "ROTINA"
        rice_day = _rice_day_from_page(page_text)
        for s in page_samples:
            s.phase = phase
            if s.rice_gmm is None and rice_day is not None:
                s.rice_gmm = rice_day
        phases_seen.add(phase)
        samples.extend(page_samples)

        ps = _printed_summary(page_text)
        ps.update({"page": page_no, "sample_count": len(page_samples)})
        phase_summaries[phase] = ps
        page_result = _result(page_text)
        if phase == "CONTRA_PROVA" and page_result:
            counterproof_result = page_result
        elif phase == "ROTINA" and page_result and not routine_result:
            routine_result = page_result

    unique: dict[tuple, Sample] = {}
    for s in samples:
        key = (s.phase, s.cp_number, s.station, s.counterproof, s.voids_pct, s.ratio_ab_pct)
        unique[key] = s
    samples = list(unique.values())

    if (kmi is None or kmf is None) and samples:
        sts = [s.station for s in samples if s.station is not None]
        if sts:
            # Último recurso: permite exibir um intervalo aproximado quando o
            # cabeçalho realmente não é extraível. O raw informa que veio dos CPs.
            kmi, kmf = min(sts), max(sts)
            segment_source = "CPS_ESTIMADO"
    if service_date is None:
        dates = [s.application_date for s in samples if s.application_date]
        if dates:
            service_date = min(dates)
            service_dates = sorted({d.isoformat() for d in dates})

    parse_status, parse_warnings, validation_warnings = _parse_health(extraction_date, service_dates, road, kmi, kmf, trace, samples, receipt_dates, assay_dates)
    if segment_source == "CPS_ESTIMADO":
        parse_warnings.append("Segmento estimado pelas estacas dos CPs; cabeçalho do PDF não identificado")
        parse_status = "PARCIAL"

    return Certificate(
        contractor=contractor,
        number=cert_number,
        file_path=str(path.resolve()),
        file_hash=file_hash(path),
        service_date=service_date,
        extraction_date=extraction_date,
        road=road,
        kmi=kmi,
        kmf=kmf,
        trace_approved=trace,
        routine_result=routine_result,
        counterproof_result=counterproof_result,
        has_counterproof="CONTRA_PROVA" in phases_seen,
        samples=samples,
        raw={
            "pages": len(page_texts),
            "parser_version": PARSER_VERSION,
            "parse_status": parse_status,
            "parse_warnings": parse_warnings,
            "validation_warnings": validation_warnings,
            "number_original": original_number,
            "contractor_line": con_line,
            "segment_source": segment_source,
            "segment_kmi": kmi,
            "segment_kmf": kmf,
            "sample_count": len(samples),
            "service_dates": service_dates,
            "extraction_dates": extraction_dates,
            "assay_dates": assay_dates,
            "receipt_dates": receipt_dates,
            "phase_summaries": phase_summaries,
        },
    )


def certificate_to_dict(c: Certificate) -> dict[str, Any]:
    d = asdict(c)
    d["service_date"] = c.service_date.isoformat() if c.service_date else None
    d["extraction_date"] = c.extraction_date.isoformat() if c.extraction_date else None
    for s in d["samples"]:
        if s.get("application_date"):
            s["application_date"] = s["application_date"].isoformat()
    return d
