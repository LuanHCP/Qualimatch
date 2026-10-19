from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from html import escape as xml_escape, unescape as xml_unescape
from io import BytesIO
import json
from pathlib import Path
import os
import shutil
import re
from typing import Any
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET

from .database import row, rows
from .config import BACKUP_DIR
from .normalizers import norm_header
from .xlsx_xml import NS_MAIN, NS_PKG, sheet_path, shared_strings


CERT_RE = re.compile(r"BI330\s*[-_]?\s*0*(\d{1,5})", re.I)
DATE_FIELDS = {
    "DATA EXTRAÇÃO", "DATA RECEBIMENTO LABORATÓRIO",
    "DATA EXTRAÇÃO CP", "DATA RECEBIMENTO LABORATÓRIO CP",
}

# Somente campos que no BD_QUALI real são entradas do certificado. Campos
# calculados (K, % reprovação, média em cm, retenções, resumo etc.) ficam com
# as fórmulas do próprio Excel.
ROUTINE_INPUT_FIELDS = [
    "Nº CERTIFICADO Vv", "DATA EXTRAÇÃO", "DATA RECEBIMENTO LABORATÓRIO",
    "DENSIDADE RICE", "Vv médio %", "DESVIO PAD (%) Vv rotina",
    "Xmin (%)", "Xmáx (%)", "TOTAL CPs", "Vv REPROVADOS (un)",
    "STATUS Vv rotina", "MEDIA (%)", "DESVIO PAD (%) Esp rotina",
    "Xmin (>95%)", "ESP REPROV (<90%) (un) rotina", "STATUS ESPESSURA rotina",
]
COUNTER_INPUT_FIELDS = [
    "Nº CERTIFICADO Vv CP", "DATA EXTRAÇÃO CP", "DATA RECEBIMENTO LABORATÓRIO CP",
    "Vv médio (%) CP", "DESVIO PAD (%)Vv CP", "Vvmin (%) CP", "Vvmáx (%) CP",
    "Vv REPROVADOS CP (un)", "STATUS Vv CP", "MEDIA (%) CP",
    "DESVIO PAD (%)CPesp", "Xmin (>95%) CP", "CP REPROVADOS (<90%) (un) CP",
    "STATUS ESPESSURA CP",
]
CLEAR_INPUT_FIELDS = ROUTINE_INPUT_FIELDS + COUNTER_INPUT_FIELDS + ["STATUS FINAL"]


@dataclass
class GeneratedFile:
    contractor: str
    file_name: str
    content: bytes
    rows_written: int
    certificates: int
    updated_rows: int
    appended_rows: int
    source_path: str
    source_sha256: str
    output_sha256: str
    target_rows: list[int]
    filters_cleared: bool


def _cert_numeric(value: Any) -> int | None:
    m = CERT_RE.search(str(value or ""))
    if m:
        return int(m.group(1))
    try:
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return None


def _raw_cert_number(raw_json: str | None) -> int | None:
    try:
        raw = json.loads(raw_json or "{}")
    except Exception:
        return None
    return _cert_numeric(raw.get("Nº CERTIFICADO Vv"))


def _existing_rows_for_cert(contractor: str, cert_number: Any) -> list[dict[str, Any]]:
    numeric = _cert_numeric(cert_number)
    if numeric is None:
        return []
    out = []
    for r in rows(
        "SELECT source_row,line_measurement,date,road,direction,lane,raw_json FROM quality_rows WHERE contractor=? ORDER BY source_row",
        (contractor,),
    ):
        if _raw_cert_number(r.get("raw_json")) == numeric:
            out.append(dict(r))
    return out


def _template_candidates(contractor: str, line_measurements: set[str]) -> dict[str, list[dict[str, Any]]]:
    if not line_measurements:
        return {}
    placeholders = ",".join("?" for _ in line_measurements)
    result = defaultdict(list)
    vals = sorted(line_measurements)
    for r in rows(
        f"SELECT source_row,line_measurement,date,road,direction,lane,raw_json FROM quality_rows WHERE contractor=? AND line_measurement IN ({placeholders}) ORDER BY source_row",
        tuple([contractor] + vals),
    ):
        d = dict(r)
        # Linhas sem certificado são templates preferenciais, mas uma linha da
        # mesma medição com certificado também serve: os campos Vv serão limpos.
        d["has_certificate"] = _raw_cert_number(d.get("raw_json")) is not None
        result[str(d.get("line_measurement") or "")].append(d)
    for key in result:
        result[key].sort(key=lambda x: (bool(x["has_certificate"]), int(x["source_row"])))
    return dict(result)




def _measurement_snapshot(measurement_id: Any) -> dict[str, Any] | None:
    """Retorna um snapshot completo da medição usada no matching.

    O fallback estrutural da v3.8.10 precisa reconstruir os campos-base da
    BD_QUALI quando ainda não existe uma linha daquela medição na planilha.
    Mantemos o raw_json original para reaproveitar os mesmos cabeçalhos do RDO.
    """
    try:
        mid = int(measurement_id)
    except Exception:
        return None
    data = row("SELECT * FROM measurements WHERE id=?", (mid,))
    if not data:
        return None
    out = dict(data)
    try:
        out["raw"] = json.loads(out.get("raw_json") or "{}")
    except Exception:
        out["raw"] = {}
    return out


def _fallback_template_candidates(contractor: str, measurement: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Busca linhas estruturais da própria BD_QUALI para clonar fórmulas/estilo.

    Não exigimos mais uma linha da MESMA medição. Preferimos linhas recentes,
    sem certificado e parecidas com a medição (rodovia/sentido/faixa), mas uma
    linha válida da mesma contratada já serve como molde estrutural porque os
    valores constantes são limpos antes de receber os dados da nova medição.
    """
    candidates = [dict(r) for r in rows(
        "SELECT source_row,line_measurement,date,road,direction,lane,raw_json "
        "FROM quality_rows WHERE contractor=? ORDER BY source_row DESC LIMIT 250",
        (contractor,),
    )]
    if not candidates:
        return []
    measurement = measurement or {}
    mroad = str(measurement.get("road") or "").upper()
    mdir = str(measurement.get("direction") or "").upper()
    mlane = str(measurement.get("lane") or "").upper()
    mdate = str(measurement.get("date") or "")

    def score(item: dict[str, Any]) -> tuple[int, int]:
        points = 0
        if _raw_cert_number(item.get("raw_json")) is None:
            points += 100
        if mroad and str(item.get("road") or "").upper() == mroad:
            points += 25
        if mdir and str(item.get("direction") or "").upper() == mdir:
            points += 8
        if mlane and str(item.get("lane") or "").upper() == mlane:
            points += 5
        if mdate and str(item.get("date") or "") == mdate:
            points += 3
        # Em empate, usa a linha mais recente da própria tabela.
        return points, int(item.get("source_row") or 0)

    candidates.sort(key=score, reverse=True)
    return candidates

def _final_status(fields: dict[str, Any]) -> str:
    cp_num = fields.get("Nº CERTIFICADO Vv CP")
    if cp_num not in (None, "", 0, "0"):
        vv = str(fields.get("STATUS Vv CP") or "").upper()
        esp = str(fields.get("STATUS ESPESSURA CP") or "").upper()
        vv_bad = "REPROV" in vv or vv.startswith("REP")
        esp_bad = "REPROV" in esp or esp.startswith("REP")
        if not vv_bad and not esp_bad and vv and esp:
            return "APROVADO CP"
        if vv_bad and esp_bad:
            return "REP Vv/ESP"
        if vv_bad:
            return "REP Vv"
        if esp_bad:
            return "REP ESP"
        return "P. CONTRA PROVA"
    vv = str(fields.get("STATUS Vv rotina") or "").upper()
    esp = str(fields.get("STATUS ESPESSURA rotina") or "").upper()
    if vv == "APROVADO" and esp == "APROVADO":
        return "APROVADO"
    return "P. CONTRA PROVA"


def _projected_first_append_row(contractor: str) -> int | None:
    try:
        source = _source_for_contractor(contractor)
        with ZipFile(source, "r") as zin:
            ws_path = sheet_path(zin, _worksheet_for_contractor(contractor))
            table_path = _resolve_table_path(zin, ws_path)
            _, _, table_end, _, _ = _table_info(zin.read(table_path))
            return int(table_end) + 1
    except Exception:
        return None


def enrich_write_plan(analysis: dict[str, Any]) -> dict[str, Any]:
    ready = blocked = ready_rows = 0
    next_projected: dict[str, int | None] = {}
    for cert in analysis.get("certificates") or []:
        contractor = str(cert.get("contractor") or "").upper()
        lines = cert.get("lines") or []
        reasons: list[str] = []
        if str(cert.get("parse_status") or "").upper() == "PARCIAL":
            reasons.append("Leitura PARCIAL do PDF.")
        if any("Número divergente:" in str(w) for w in cert.get("warnings") or []):
            reasons.append("Número do arquivo diverge do número lido no certificado.")
        if any(str(x.get("match_status") or "") != "VINCULADO" for x in lines):
            reasons.append("Há CP(s) em REVISAR ou SEM MEDIÇÃO.")
        projected_lines = [str((x.get("measurement") or {}).get("line_measurement") or "") for x in lines]
        if any(not x for x in projected_lines):
            reasons.append("Há CP sem Linha de Medição vinculada.")

        existing = _existing_rows_for_cert(contractor, cert.get("certificate"))
        projected_counter = Counter(projected_lines)
        existing_counter = Counter(str(x.get("line_measurement") or "") for x in existing)
        assignments: list[dict[str, Any]] = []
        mode = ""

        if not reasons and existing:
            if len(existing) != len(lines):
                reasons.append(
                    f"O certificado já possui {len(existing)} linha(s) na BD_QUALI, mas o PDF projeta {len(lines)}."
                )
            else:
                # Para certificado já existente, os dados de rotina/CP são
                # resumos repetidos em todas as linhas. Se a quantidade bate,
                # atualizamos as linhas atuais sem mexer no vínculo de medição
                # que já está consolidado na BD_QUALI.
                mode = "ATUALIZAR_EXISTENTE"
                for r in existing:
                    assignments.append({
                        "target_row": int(r["source_row"]),
                        "line_measurement": str(r.get("line_measurement") or ""),
                    })

        elif not reasons:
            template_map = _template_candidates(contractor, set(projected_lines))
            mode = "ADICIONAR_NOVO"
            if contractor not in next_projected:
                next_projected[contractor] = _projected_first_append_row(contractor)
            fallback_cache: dict[int, list[dict[str, Any]]] = {}
            for x in lines:
                measurement_ref = x.get("measurement") or {}
                lm = str(measurement_ref.get("line_measurement") or "")
                measurement_id = measurement_ref.get("id")
                exact = template_map.get(lm) or []
                strategy = "EXACT_MEASUREMENT"
                if exact:
                    tpl = exact[0]
                    measurement_snapshot = None
                else:
                    measurement_snapshot = _measurement_snapshot(measurement_id)
                    cache_key = int(measurement_id) if str(measurement_id or "").isdigit() else -1
                    fallback = fallback_cache.get(cache_key)
                    if fallback is None:
                        fallback = _fallback_template_candidates(contractor, measurement_snapshot or measurement_ref)
                        fallback_cache[cache_key] = fallback
                    if not fallback:
                        reasons.append(
                            f"Sem linha estrutural válida na BD_QUALI para criar a medição {lm or '(sem linha)'}; "
                            "sincronize a fonte Qualidade e tente novamente."
                        )
                        break
                    if not measurement_snapshot:
                        reasons.append(
                            f"A medição {lm or '(sem linha)'} foi vinculada, mas os dados completos dela não estão disponíveis no banco. "
                            "Sincronize a fonte Medição e tente novamente."
                        )
                        break
                    tpl = fallback[0]
                    strategy = "STRUCTURAL_FALLBACK"
                projected = next_projected.get(contractor)
                assignments.append({
                    "template_row": int(tpl["source_row"]),
                    "template_line_measurement": str(tpl.get("line_measurement") or ""),
                    "template_strategy": strategy,
                    "measurement_id": measurement_id,
                    "line_measurement": lm,
                    "projected_row": projected,
                })
                if projected is not None:
                    next_projected[contractor] = projected + 1
            if reasons:
                mode = ""
                assignments = []

        placement = ""
        if not reasons and mode == "ATUALIZAR_EXISTENTE":
            rows_txt = [str(x.get("target_row")) for x in assignments if x.get("target_row")]
            placement = "Atualiza linha(s) existente(s): " + ", ".join(rows_txt)
        elif not reasons and mode == "ADICIONAR_NOVO":
            projected_rows = [int(x["projected_row"]) for x in assignments if x.get("projected_row") is not None]
            if projected_rows:
                placement = f"Adiciona ao fim da tabela: linhas {min(projected_rows)} a {max(projected_rows)}"
            else:
                placement = "Adiciona ao fim da tabela BD_QUALI"
            if any(str(a.get("template_strategy") or "") == "STRUCTURAL_FALLBACK" for a in assignments):
                placement += " • linha estrutural reconstruída pela medição"
        cert["excel_write"] = {
            "ready": not reasons,
            "mode": mode if not reasons else "BLOQUEADO",
            "reason": " ".join(reasons),
            "assignments": assignments if not reasons else [],
            "final_status": _final_status(cert.get("quality_fields") or {}),
            "placement": placement,
        }
        if reasons:
            blocked += 1
        else:
            ready += 1
            ready_rows += len(lines)

    summary = analysis.setdefault("summary", {})
    summary["excel_ready_certificates"] = ready
    summary["excel_blocked_certificates"] = blocked
    summary["excel_ready_rows"] = ready_rows
    analysis["mode"] = "PREVIEW_AND_SAFE_EXCEL_COPY"
    analysis["message"] = (
        "A prévia não altera a planilha. Certificados marcados como prontos podem gerar uma cópia segura da BD_QUALI."
    )
    return analysis


def _col_to_num(col: str) -> int:
    n = 0
    for ch in col:
        if "A" <= ch <= "Z":
            n = n * 26 + ord(ch) - 64
    return n


def _num_to_col(n: int) -> str:
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def _resolve_table_path(z: ZipFile, worksheet_path: str) -> str:
    rel_path = worksheet_path.rsplit("/", 1)[0] + "/_rels/" + worksheet_path.rsplit("/", 1)[1] + ".rels"
    rels = ET.fromstring(z.read(rel_path))
    for rel in rels.findall(f"{{{NS_PKG}}}Relationship"):
        if rel.attrib.get("Type", "").endswith("/table"):
            target = rel.attrib["Target"]
            if target.startswith("../"):
                return "xl/" + target.replace("../", "", 1)
            return worksheet_path.rsplit("/", 1)[0] + "/" + target
    raise ValueError("Tabela BD_QUALI não localizada na aba.")


def _table_info(table_xml: bytes) -> tuple[str, int, int, dict[str, str], dict[str, str]]:
    root = ET.fromstring(table_xml)
    ref = root.attrib["ref"]
    m = re.fullmatch(r"([A-Z]+)(\d+):([A-Z]+)(\d+)", ref)
    if not m:
        raise ValueError(f"Referência de tabela inválida: {ref}")
    start_col, header_row, end_col, end_row = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))
    start_num = _col_to_num(start_col)
    header_map: dict[str, str] = {}
    formulas: dict[str, str] = {}
    cols = root.find(f"{{{NS_MAIN}}}tableColumns")
    if cols is None:
        raise ValueError("Colunas da tabela BD_QUALI não localizadas.")
    for i, col in enumerate(cols):
        name = col.attrib.get("name", "")
        letter = _num_to_col(start_num + i)
        header_map[norm_header(name)] = letter
        formula = col.find(f"{{{NS_MAIN}}}calculatedColumnFormula")
        if formula is not None and formula.text:
            formulas[norm_header(name)] = formula.text
    return ref, header_row, end_row, header_map, formulas


def _find_row(sheet: bytes, row_num: int, start: int = 0) -> tuple[int, int, bytes] | None:
    needle = f'<row r="{row_num}"'.encode()
    pos = sheet.find(needle, start)
    if pos < 0:
        # fallback para atributos em ordem diferente
        m = re.search(rb"<row\b[^>]*\br=\"" + str(row_num).encode() + rb"\"[^>]*", sheet[start:])
        if not m:
            return None
        pos = start + m.start()
    close = sheet.find(b">", pos)
    if close < 0:
        return None
    if sheet[close - 1:close] == b"/":
        end = close + 1
    else:
        rclose = sheet.find(b"</row>", close)
        if rclose < 0:
            return None
        end = rclose + len(b"</row>")
    return pos, end, sheet[pos:end]


def _collect_rows(sheet: bytes, row_numbers: set[int]) -> dict[int, bytes]:
    out: dict[int, bytes] = {}
    cursor = 0
    for nr in sorted(row_numbers):
        found = _find_row(sheet, nr, cursor)
        if not found:
            # Pode ocorrer quando a busca com cursor ultrapassou uma linha que
            # foi solicitada fora de ordem em XML atípico; tenta do início.
            found = _find_row(sheet, nr, 0)
        if found:
            s, e, xml = found
            out[nr] = xml
            cursor = e
    return out


def _cell_pattern(col: str, row_num: int) -> re.Pattern[bytes]:
    ref = re.escape(f"{col}{row_num}".encode())
    # Importante: trata célula autocontida e célula normal em alternativas
    # separadas. O padrão antigo podia fazer backtracking em `<c .../>` e
    # consumir também a célula seguinte (inclusive fórmulas), ao substituir
    # uma entrada manual como TOTAL CPs.
    return re.compile(
        rb'(?:<c\b(?=[^>]*\br="' + ref + rb'")[^>]*?/>|<c\b(?=[^>]*\br="' + ref + rb'")[^>]*>.*?</c>)',
        re.S,
    )


def _cell_style(cell_xml: bytes | None) -> str:
    if not cell_xml:
        return ""
    m = re.search(rb'\bs="([^"]+)"', cell_xml)
    return m.group(1).decode() if m else ""


def _style_from_row(row_xml: bytes, col: str, row_num: int) -> str:
    m = _cell_pattern(col, row_num).search(row_xml)
    return _cell_style(m.group(0) if m else None)


def _serialize_cell(ref: str, style: str, value: Any = None, formula: str | None = None) -> bytes:
    s_attr = f' s="{style}"' if style else ""
    if formula is not None:
        return f'<c r="{ref}"{s_attr}><f>{xml_escape(formula, quote=False)}</f></c>'.encode("utf-8")
    if value is None or value == "":
        return f'<c r="{ref}"{s_attr}/>'.encode("utf-8")
    if isinstance(value, bool):
        return f'<c r="{ref}"{s_attr} t="b"><v>{1 if value else 0}</v></c>'.encode()
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{s_attr}><v>{value}</v></c>'.encode()
    text = xml_escape(str(value), quote=False)
    return f'<c r="{ref}"{s_attr} t="inlineStr"><is><t>{text}</t></is></c>'.encode("utf-8")


def _insert_cell_sorted(row_xml: bytes, cell_xml: bytes, col: str) -> bytes:
    target = _col_to_num(col)
    for m in re.finditer(rb'<c\b[^>]*\br="([A-Z]+)\d+"', row_xml):
        current = _col_to_num(m.group(1).decode())
        if current > target:
            return row_xml[:m.start()] + cell_xml + row_xml[m.start():]
    close = row_xml.rfind(b"</row>")
    if close >= 0:
        return row_xml[:close] + cell_xml + row_xml[close:]
    # transforma row autocontida em row normal
    if row_xml.rstrip().endswith(b"/>"):
        return row_xml.rstrip()[:-2] + b">" + cell_xml + b"</row>"
    return row_xml


def _set_cell(row_xml: bytes, col: str, row_num: int, value: Any = None, formula: str | None = None) -> bytes:
    pat = _cell_pattern(col, row_num)
    m = pat.search(row_xml)
    style = _cell_style(m.group(0) if m else None)
    new_cell = _serialize_cell(f"{col}{row_num}", style, value=value, formula=formula)
    if m:
        return row_xml[:m.start()] + new_cell + row_xml[m.end():]
    return _insert_cell_sorted(row_xml, new_cell, col)


def _cell_numeric_text(row_xml: bytes, col: str, row_num: int) -> str:
    """Lê um valor simples/numerado de uma célula da linha sem regravar o Excel."""
    m = _cell_pattern(col, row_num).search(row_xml)
    if not m:
        return ""
    vm = re.search(rb'<v>(.*?)</v>', m.group(0), re.S)
    if not vm:
        return ""
    try:
        value = vm.group(1).decode("utf-8").strip()
        # LINHA MEDIÇÃO costuma ser numérica; normaliza 2258.0 -> 2258.
        if re.fullmatch(r"-?\d+(?:\.0+)?", value):
            return str(int(float(value)))
        return value
    except Exception:
        return ""


def _validate_input_headers(header_map: dict[str, str], fields: dict[str, Any]) -> None:
    allowed = {norm_header(x) for x in ROUTINE_INPUT_FIELDS + COUNTER_INPUT_FIELDS}
    missing = []
    for field, value in fields.items():
        key = norm_header(field)
        if key in allowed and value not in (None, "") and key not in header_map:
            missing.append(field)
    if norm_header("STATUS FINAL") not in header_map:
        missing.append("STATUS FINAL")
    if missing:
        raise ValueError(
            "A estrutura da BD_QUALI não corresponde ao modelo validado. Coluna(s) não localizada(s): "
            + ", ".join(sorted(set(missing)))
        )


def _shift_formula_rows(formula: str, delta: int) -> str:
    """Replica o comportamento de copiar uma fórmula para outra linha.

    Referências A1 com linha relativa são deslocadas pelo delta; linhas com `$`
    permanecem fixas. Referências estruturadas (BD_QUALI[[#This Row],...]) não
    são afetadas.
    """
    if not delta:
        return formula
    pat = re.compile(r"(?<![A-Za-z0-9_])(?P<col>\$?[A-Z]{1,3})(?P<abs>\$?)(?P<row>\d+)")

    def repl(m: re.Match[str]) -> str:
        if m.group("abs") == "$":
            return m.group(0)
        row_num = max(1, int(m.group("row")) + delta)
        return f'{m.group("col")}{row_num}'

    return pat.sub(repl, formula)


def _shared_formula_masters(sheet_xml: bytes) -> dict[str, tuple[int, str]]:
    """Lê somente as fórmulas-mestre reais de grupos `t=shared`.

    Não usamos um regex `<f ...>(.*?)</f>` direto porque uma fórmula-filho
    autocontida (`<f t="shared" si="..."/>`) poderia ser confundida com uma
    abertura e capturar células inteiras até o próximo `</f>`.
    """
    out: dict[str, tuple[int, str]] = {}
    for tag_m in re.finditer(rb'<f\b[^>]*>', sheet_xml):
        tag = tag_m.group(0)
        if tag.rstrip().endswith(b'/>'):
            continue
        if b't="shared"' not in tag:
            continue
        si_m = re.search(rb'\bsi="(\d+)"', tag)
        if not si_m:
            continue
        close = sheet_xml.find(b'</f>', tag_m.end())
        if close < 0:
            continue
        # Uma fórmula não pode atravessar o fechamento da própria célula.
        cell_close = sheet_xml.find(b'</c>', tag_m.end())
        if cell_close >= 0 and close > cell_close:
            continue
        cpos = sheet_xml.rfind(b'<c', 0, tag_m.start())
        if cpos < 0:
            continue
        cend = sheet_xml.find(b'>', cpos, tag_m.start())
        if cend < 0:
            continue
        cm = re.search(rb'\br="[A-Z]+(\d+)"', sheet_xml[cpos:cend + 1])
        if not cm:
            continue
        try:
            master_row = int(cm.group(1))
            formula = xml_unescape(sheet_xml[tag_m.end():close].decode("utf-8"))
            out[si_m.group(1).decode()] = (master_row, formula)
        except Exception:
            continue
    return out


def _clone_row(
    row_xml: bytes,
    source_row: int,
    target_row: int,
    shared_formulas: dict[str, tuple[int, str]] | None = None,
) -> bytes:
    text = row_xml.decode("utf-8")
    text = re.sub(rf'(<row\b[^>]*\br="){source_row}(\")', rf'\g<1>{target_row}\2', text, count=1)
    text = re.sub(rf'(<c\b[^>]*\br="[A-Z]+){source_row}(\")', rf'\g<1>{target_row}\2', text)
    shared_formulas = shared_formulas or {}

    # Protege primeiro fórmulas shared autocontidas. Sem isso, um regex de
    # fórmula normal poderia começar em <f .../> e atravessar células até o
    # próximo </f>, corrompendo a linha.
    protected: list[tuple[str, str]] = []

    def protect_shared(m: re.Match[str]) -> str:
        attrs = m.group(1) or ""
        token = f"__QM_SHARED_FORMULA_{len(protected)}__"
        protected.append((token, attrs))
        return token

    text = re.sub(
        r'<f((?=[^>]*\bt="shared")(?=[^>]*\bsi="\d+")[^>]*)/>',
        protect_shared,
        text,
    )

    # Fórmulas com corpo (normais ou mestres de um grupo shared) viram fórmulas
    # independentes e são deslocadas como ocorreria ao copiar a linha no Excel.
    def full_formula(m: re.Match[str]) -> str:
        attrs, body = m.group(1), m.group(2)
        raw = xml_unescape(body)
        if 't="shared"' in attrs:
            attrs = re.sub(r'\s+t="shared"', '', attrs)
            attrs = re.sub(r'\s+si="[^"]+"', '', attrs)
            attrs = re.sub(r'\s+ref="[^"]+"', '', attrs)
        else:
            # Fórmulas array/dynamic podem carregar `ref="AN3690"`; ao
            # clonar a linha esse intervalo precisa acompanhar o deslocamento.
            def shift_ref(a: re.Match[str]) -> str:
                return a.group(1) + _shift_formula_rows(a.group(2), target_row - source_row) + a.group(3)
            attrs = re.sub(r'(\bref=")([^"]+)(")', shift_ref, attrs)
        translated = _shift_formula_rows(raw, target_row - source_row)
        return f'<f{attrs}>{xml_escape(translated, quote=False)}</f>'

    text = re.sub(r'<f([^>/]*?(?:"[^"]*"[^>/]*)*)>(.*?)</f>', full_formula, text, flags=re.S)

    # Materializa os filhos shared usando a fórmula-mestre do grupo.
    for token, attrs in protected:
        si_m = re.search(r'\bsi="(\d+)"', attrs)
        replacement = f'<f{attrs}/>'
        if si_m:
            master = shared_formulas.get(si_m.group(1))
            if master:
                master_row, formula = master
                translated = _shift_formula_rows(formula, target_row - master_row)
                replacement = f'<f>{xml_escape(translated, quote=False)}</f>'
        text = text.replace(token, replacement, 1)

    return text.encode("utf-8")


def _excel_serial(value: str) -> float:
    d = date.fromisoformat(value[:10])
    return float((d - date(1899, 12, 30)).days)


def _field_value(field: str, value: Any) -> Any:
    if value in (None, ""):
        return None
    if field in DATE_FIELDS and isinstance(value, str) and re.match(r"\d{4}-\d{2}-\d{2}", value):
        return _excel_serial(value)
    return value




_PT_MONTHS = {
    1: "JANEIRO", 2: "FEVEREIRO", 3: "MARÇO", 4: "ABRIL",
    5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO",
    9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO",
}


def _cell_has_formula(row_xml: bytes, col: str, row_num: int) -> bool:
    m = _cell_pattern(col, row_num).search(row_xml)
    return bool(m and b"<f" in m.group(0))


def _clear_non_formula_cells(row_xml: bytes, row_num: int) -> bytes:
    """Transforma uma linha existente em molde estrutural seguro.

    Fórmulas/estilos são preservados; qualquer valor constante da medição antiga
    (kit, certificados, RNC, valores manuais etc.) é apagado para não vazar para
    a nova linha criada a partir de um template genérico.
    """
    pattern = re.compile(
        rb'(?:<c\b(?=[^>]*\br="[A-Z]+' + str(row_num).encode() + rb'")[^>]*?/>|'
        rb'<c\b(?=[^>]*\br="[A-Z]+' + str(row_num).encode() + rb'")[^>]*>.*?</c>)',
        re.S,
    )

    def repl(m: re.Match[bytes]) -> bytes:
        cell = m.group(0)
        if b"<f" in cell:
            return cell
        ref_m = re.search(rb'\br="([A-Z]+)' + str(row_num).encode() + rb'"', cell)
        if not ref_m:
            return cell
        col = ref_m.group(1).decode()
        return _serialize_cell(f"{col}{row_num}", _cell_style(cell), None)

    return pattern.sub(repl, row_xml)


def _measurement_excel_values(contractor: str, measurement: dict[str, Any]) -> dict[str, Any]:
    """Converte o registro de `measurements` para entradas da área-base BD_QUALI."""
    raw = measurement.get("raw")
    if not isinstance(raw, dict):
        try:
            raw = json.loads(measurement.get("raw_json") or "{}")
        except Exception:
            raw = {}
    raw_norm = {norm_header(k): v for k, v in raw.items() if str(k).strip()}

    def raw_value(*names: str) -> Any:
        for name in names:
            key = norm_header(name)
            if key in raw_norm and raw_norm[key] not in (None, ""):
                return raw_norm[key]
        return None

    date_value = str(measurement.get("date") or "")
    month_value = raw_value("MÊS", "MES")
    year_value = raw_value("ANO")
    if date_value:
        try:
            dt = date.fromisoformat(date_value[:10])
            month_value = month_value if month_value not in (None, "") else _PT_MONTHS.get(dt.month)
            year_value = year_value if year_value not in (None, "") else dt.year
        except Exception:
            pass

    thickness_raw = raw_value("ESPESSURA (cm)", "ESPESSURA (CM)")
    if thickness_raw in (None, ""):
        tm = measurement.get("thickness_m")
        if tm not in (None, ""):
            try:
                num = float(tm)
                thickness_raw = num * 100.0 if abs(num) <= 1.0 else num
            except Exception:
                thickness_raw = tm

    values: dict[str, Any] = {
        "EMPRESA": contractor,
        "LINHA MEDIÇÃO": measurement.get("line_measurement"),
        "REF MEDIÇÃO": measurement.get("ref_measurement"),
        "EQUIPE": measurement.get("team") or raw_value("EQUIPE"),
        "TURNO": raw_value("TURNO", "PERÍODO", "PERIODO"),
        "FISCAL": measurement.get("inspector") or raw_value("FISCAL"),
        "DATA": measurement.get("date") or raw_value("DATA"),
        "MÊS": month_value,
        "ANO": year_value,
        "RODOVIA": measurement.get("road") or raw_value("RODOVIA"),
        "SENTIDO": measurement.get("direction") or raw_value("SENTIDO"),
        "KMI": raw_value("KMI") if raw_value("KMI") not in (None, "") else measurement.get("kmi"),
        "KMF": raw_value("KMF") if raw_value("KMF") not in (None, "") else measurement.get("kmf"),
        "FAIXA": measurement.get("lane") or raw_value("FAIXA"),
        "ESCOPO": raw_value("ESCOPO") or measurement.get("scope"),
        "EXTENSÃO (m)": raw_value("EXTENSÃO (m)", "EXTENSAO (m)") or measurement.get("extension_m"),
        "LARGURA (m)": raw_value("LARGURA (m)") or measurement.get("width_m"),
        "ESPESSURA (cm)": thickness_raw,
        "TIPO": raw_value("TIPO") or measurement.get("scope"),
        "DMT FRESADO (km)": raw_value("DMT FRESADO (km)", "DMT FRESADO (KM)") or measurement.get("dmt_milled_km"),
        "AREA MED (m²)": raw_value("AREA MED (m²)", "ÁREA MED (m²)", "AREA (m²)", "ÁREA (m²)") or measurement.get("area_m2"),
        "VOLUME MASSA (m³)": raw_value("VOLUME MASSA (m³)") or measurement.get("volume_mass_m3"),
        "VOLUME FRESADO (m³)": raw_value("VOLUME FRESADO (m³)") or measurement.get("volume_milled_m3"),
        "QUANT PROJETO (ton)": raw_value("QUANT PROJETO (ton)", "QUANT (ton)", "QUANTIDADE (ton)") or measurement.get("quantity_t"),
    }
    # Campos com o mesmo cabeçalho nas duas planilhas (NOTAS, CÓDIGO TRAÇO,
    # PEP, preços, volumes auxiliares etc.) entram automaticamente. O writer
    # limita a aplicação ao bloco-base, antes de KIT ID.
    for raw_header, value in raw.items():
        if value not in (None, ""):
            values.setdefault(str(raw_header), value)
    return {k: v for k, v in values.items() if v not in (None, "")}


def _measurement_field_value(field: str, value: Any) -> Any:
    if value in (None, ""):
        return None
    if norm_header(field) == norm_header("DATA"):
        if isinstance(value, str) and re.match(r"\d{4}-\d{2}-\d{2}", value):
            return _excel_serial(value)
    return value


def _apply_measurement_fields(
    row_xml: bytes,
    row_num: int,
    header_map: dict[str, str],
    contractor: str,
    measurement: dict[str, Any],
) -> bytes:
    values = _measurement_excel_values(contractor, measurement)
    kit_col = header_map.get(norm_header("KIT ID"))
    kit_num = _col_to_num(kit_col) if kit_col else 10**9
    protected = {norm_header("ID")}
    for field, value in values.items():
        key = norm_header(field)
        col = header_map.get(key)
        if not col or key in protected or _col_to_num(col) >= kit_num:
            continue
        # Se a planilha-modelo já possui fórmula nessa coluna (ex.: DIA
        # APLICAÇÃO), mantém a fórmula em vez de trocar por valor fixo.
        if _cell_has_formula(row_xml, col, row_num):
            continue
        row_xml = _set_cell(row_xml, col, row_num, _measurement_field_value(field, value))
    return row_xml

def _apply_certificate_fields(row_xml: bytes, row_num: int, header_map: dict[str, str], fields: dict[str, Any], final_status: str) -> bytes:
    # Limpa entradas antigas do Vv/CP antes de aplicar o novo certificado.
    for field in CLEAR_INPUT_FIELDS:
        col = header_map.get(norm_header(field))
        if col:
            row_xml = _set_cell(row_xml, col, row_num, None)
    for field, value in fields.items():
        col = header_map.get(norm_header(field))
        if col and norm_header(field) in {norm_header(x) for x in (ROUTINE_INPUT_FIELDS + COUNTER_INPUT_FIELDS)}:
            row_xml = _set_cell(row_xml, col, row_num, _field_value(field, value))
    final_col = header_map.get(norm_header("STATUS FINAL"))
    if final_col:
        row_xml = _set_cell(row_xml, final_col, row_num, final_status)
    return row_xml


def _max_quality_id(contractor: str) -> int:
    best = 0
    for r in rows("SELECT raw_json FROM quality_rows WHERE contractor=?", (contractor,)):
        try:
            raw = json.loads(r.get("raw_json") or "{}")
            v = raw.get("ID")
            if v not in (None, ""):
                best = max(best, int(float(str(v).replace(",", "."))))
        except Exception:
            pass
    return best


def _replace_rows(sheet: bytes, replacements: dict[int, bytes], append_missing: bool = True) -> bytes:
    if not replacements:
        return sheet
    pieces: list[bytes] = []
    cursor = 0
    missing: list[tuple[int, bytes]] = []
    for nr, repl in sorted(replacements.items()):
        found = _find_row(sheet, nr, cursor)
        if not found:
            found = _find_row(sheet, nr, 0)
        if found:
            s, e, _ = found
            pieces.append(sheet[cursor:s])
            pieces.append(repl)
            cursor = e
        else:
            missing.append((nr, repl))
    pieces.append(sheet[cursor:])
    out = b"".join(pieces)
    if missing and append_missing:
        marker = b"</sheetData>"
        pos = out.find(marker)
        if pos < 0:
            raise ValueError("Fim de sheetData não localizado.")
        payload = b"".join(x[1] for x in sorted(missing))
        out = out[:pos] + payload + out[pos:]
    elif missing:
        raise ValueError("Linha(s) existente(s) não localizada(s): " + ", ".join(str(x[0]) for x in missing[:8]))
    return out


def _table_has_active_filter(table_xml: bytes) -> bool:
    """Retorna True somente quando a tabela possui critério de filtro ativo."""
    try:
        root = ET.fromstring(table_xml)
        af = root.find(f"{{{NS_MAIN}}}autoFilter")
        return af is not None and any(child.tag == f"{{{NS_MAIN}}}filterColumn" for child in af)
    except Exception:
        return False


def _clear_table_filters(table_xml: bytes) -> bytes:
    """Remove apenas critérios ativos da tabela, preservando o botão de filtro e a referência."""
    try:
        root = ET.fromstring(table_xml)
        af = root.find(f"{{{NS_MAIN}}}autoFilter")
        if af is None:
            return table_xml
        for child in list(af):
            if child.tag == f"{{{NS_MAIN}}}filterColumn":
                af.remove(child)
        # ET reescreveria namespaces; fazemos remoção textual dos filterColumn para preservar o XML.
        text = table_xml.decode('utf-8')
        text = re.sub(r'<filterColumn\b[^>]*>.*?</filterColumn>', '', text, flags=re.S)
        text = re.sub(r'<filterColumn\b[^>]*/>', '', text)
        return text.encode('utf-8')
    except Exception:
        return table_xml


def _unhide_table_rows(sheet_xml: bytes, first_data_row: int, last_data_row: int) -> bytes:
    """Desfaz ocultação causada por AutoFilter apenas dentro das linhas da tabela."""
    def repl(m: re.Match[bytes]) -> bytes:
        tag = m.group(0)
        rn = re.search(rb'\br="(\d+)"', tag)
        if not rn:
            return tag
        nr = int(rn.group(1))
        if nr < first_data_row or nr > last_data_row:
            return tag
        tag = re.sub(rb'\s+hidden="1"', b'', tag)
        return tag
    return re.sub(rb'<row\b[^>]*>', repl, sheet_xml)


def _make_row_visible(row_xml: bytes) -> bytes:
    """Linha clonada de uma tabela filtrada não deve herdar hidden=1 na cópia de revisão."""
    close = row_xml.find(b'>')
    if close < 0:
        return row_xml
    head = re.sub(rb'\s+hidden="1"', b'', row_xml[:close])
    return head + row_xml[close:]


def _read_simple_cell(row_xml: bytes, col: str, row_num: int) -> str:
    m = _cell_pattern(col, row_num).search(row_xml)
    if not m:
        return ''
    cell = m.group(0)
    inline = re.search(rb'<t[^>]*>(.*?)</t>', cell, re.S)
    if inline:
        try:
            return xml_unescape(inline.group(1).decode('utf-8')).strip()
        except Exception:
            return ''
    vm = re.search(rb'<v>(.*?)</v>', cell, re.S)
    if vm:
        try:
            return vm.group(1).decode('utf-8').strip()
        except Exception:
            return ''
    return ''


def _verify_output_rows(content: bytes, contractor: str, expected: list[tuple[int, Any]]) -> None:
    """Confirma no XLSX final que as linhas realmente receberam o Nº CERTIFICADO Vv.

    Isso evita entregar uma cópia que foi baixada sem os valores escritos por alguma
    particularidade do arquivo Excel.
    """
    if not expected:
        return
    with ZipFile(BytesIO(content), 'r') as z:
        ws_path = sheet_path(z, _worksheet_for_contractor(contractor))
        table_path = _resolve_table_path(z, ws_path)
        sheet_xml = z.read(ws_path)
        _, _, _, header_map, _ = _table_info(z.read(table_path))
        cert_col = header_map.get(norm_header('Nº CERTIFICADO Vv'))
        if not cert_col:
            raise ValueError('Validação pós-gravação: coluna Nº CERTIFICADO Vv não localizada.')
        failed=[]
        for row_num, cert_number in expected:
            found=_find_row(sheet_xml, int(row_num), 0)
            if not found:
                failed.append(f'linha {row_num} ausente')
                continue
            actual=_read_simple_cell(found[2], cert_col, int(row_num))
            expected_num=_cert_numeric(cert_number)
            actual_num=_cert_numeric(actual)
            if expected_num is None or actual_num != expected_num:
                failed.append(f'linha {row_num}: esperado {cert_number}, encontrado {actual or "vazio"}')
        if failed:
            raise ValueError('A cópia foi criada, mas a validação dos novos dados falhou: ' + '; '.join(failed[:8]))


def _patch_table_ref(table_xml: bytes, new_end_row: int) -> bytes:
    root = ET.fromstring(table_xml)
    old_ref = root.attrib["ref"]
    new_ref = re.sub(r"\d+$", str(new_end_row), old_ref)
    # Substituição textual preserva namespaces/ordem originais do XML.
    out = table_xml.replace(f'ref="{old_ref}"'.encode(), f'ref="{new_ref}"'.encode(), 1)
    # autoFilter costuma repetir a referência.
    out = out.replace(f'ref="{old_ref}"'.encode(), f'ref="{new_ref}"'.encode(), 1)
    return out


def _patch_dimension(sheet_xml: bytes, new_end_row: int) -> bytes:
    m = re.search(rb'<dimension\s+ref="([A-Z]+)(\d+):([A-Z]+)(\d+)"\s*/>', sheet_xml)
    if not m:
        return sheet_xml
    current_end = int(m.group(4))
    if new_end_row <= current_end:
        return sheet_xml
    new = (
        b'<dimension ref="' + m.group(1) + m.group(2) + b':' + m.group(3) + str(new_end_row).encode() + b'"/>'
    )
    return sheet_xml[:m.start()] + new + sheet_xml[m.end():]


def _force_recalc(workbook_xml: bytes) -> bytes:
    text = workbook_xml.decode("utf-8")
    m = re.search(r'<calcPr\b([^>]*)/>', text)
    if m:
        attrs = m.group(1)
        for name, value in (("calcMode", "auto"), ("fullCalcOnLoad", "1"), ("forceFullCalc", "1")):
            if re.search(rf'\b{name}="[^"]*"', attrs):
                attrs = re.sub(rf'\b{name}="[^"]*"', f'{name}="{value}"', attrs)
            else:
                attrs += f' {name}="{value}"'
        text = text[:m.start()] + f'<calcPr{attrs}/>' + text[m.end():]
    else:
        pos = text.rfind("</workbook>")
        if pos >= 0:
            text = text[:pos] + '<calcPr calcMode="auto" fullCalcOnLoad="1" forceFullCalc="1"/>' + text[pos:]
    return text.encode("utf-8")


def _validate_source(source_path: Path, contractor: str) -> None:
    if not source_path.exists() or not source_path.is_file():
        raise ValueError(f"Fonte Qualidade {contractor} não encontrada: {source_path}")
    if source_path.suffix.lower() != ".xlsx":
        raise ValueError(f"Fonte Qualidade {contractor} precisa ser .xlsx")


def _recover_append_template(spec: dict[str, Any], current_line_measurement: str) -> bool:
    """Converte um molde deslocado em fallback estrutural seguro."""
    expected = str(spec.get("template_line_measurement") or "")
    current = str(current_line_measurement or "")
    if not expected or not current or current == expected:
        return True
    if str(spec.get("template_strategy") or "") == "STRUCTURAL_FALLBACK":
        return True
    if not _measurement_snapshot(spec.get("measurement_id")):
        return False
    spec["template_strategy"] = "STRUCTURAL_FALLBACK"
    return True


def _recover_append_template(spec: dict[str, Any], current_line_measurement: str) -> bool:
    """Converte um molde deslocado em fallback estrutural seguro."""
    expected = str(spec.get("template_line_measurement") or "")
    current = str(current_line_measurement or "")
    if not expected or not current or current == expected:
        return True
    if str(spec.get("template_strategy") or "") == "STRUCTURAL_FALLBACK":
        return True
    if not _measurement_snapshot(spec.get("measurement_id")):
        return False
    spec["template_strategy"] = "STRUCTURAL_FALLBACK"
    return True


def _source_for_contractor(contractor: str) -> Path:
    s = row("SELECT path FROM sources WHERE contractor=? AND kind='qualidade'", (contractor,))
    if not s or not s.get("path"):
        raise ValueError(f"Fonte Qualidade {contractor} não configurada em Administração → Sincronização.")
    p = Path(s["path"])
    _validate_source(p, contractor)
    return p


def _worksheet_for_contractor(contractor: str) -> str:
    """Nome da aba configurada em Administração → Sincronização para a fonte Qualidade.

    Antes, a gravação sempre procurava uma aba chamada literalmente "BD_QUALI",
    mesmo quando o admin configurou outro nome de aba para essa fonte (o mesmo
    campo que a sincronização usa em local_sync.py). Se a planilha tiver mais de
    uma aba parecida, isso fazia a gravação ler/validar uma aba diferente da que
    foi sincronizada — gerando um "esperado X, encontrado Y" que nenhuma
    sincronização resolvia, porque a sincronização nunca estava olhando para a
    aba errada; só a gravação estava. Mantém "BD_QUALI" como padrão quando o
    campo não foi customizado, então o comportamento não muda para quem já usa
    o nome padrão.
    """
    s = row("SELECT worksheet FROM sources WHERE contractor=? AND kind='qualidade'", (contractor,))
    return str((s or {}).get("worksheet") or "").strip() or "BD_QUALI"


def patch_quality_workbook(source_path: Path, contractor: str, certificates: list[dict[str, Any]]) -> GeneratedFile:
    source_bytes = source_path.read_bytes()
    source_hash = sha256(source_bytes).hexdigest()
    with ZipFile(BytesIO(source_bytes), "r") as zin:
        ws_path = sheet_path(zin, _worksheet_for_contractor(contractor))
        table_path = _resolve_table_path(zin, ws_path)
        sheet_xml = zin.read(ws_path)
        table_xml = zin.read(table_path)
        workbook_xml = zin.read("xl/workbook.xml")
        _, header_row, table_end, header_map, _ = _table_info(table_xml)
        active_filters = _table_has_active_filter(table_xml)
        shared_formulas = _shared_formula_masters(sheet_xml)
        if header_row != 11:
            raise ValueError(f"Cabeçalho BD_QUALI inesperado na linha {header_row}; esperado 11.")

        existing_targets: dict[int, tuple[dict[str, Any], str, str]] = {}
        append_specs: list[dict[str, Any]] = []
        templates: set[int] = set()
        updated_rows = appended_rows = 0
        next_row = table_end + 1
        next_id = _max_quality_id(contractor) + 1
        written_expected: list[tuple[int, Any]] = []

        for cert in certificates:
            plan = cert.get("excel_write") or {}
            if not plan.get("ready"):
                continue
            fields = cert.get("quality_fields") or {}
            final_status = str(plan.get("final_status") or _final_status(fields))
            assignments = plan.get("assignments") or []
            if plan.get("mode") == "ATUALIZAR_EXISTENTE":
                for a in assignments:
                    target = int(a["target_row"])
                    existing_targets[target] = (fields, final_status, str(a.get("line_measurement") or ""))
                    updated_rows += 1
            elif plan.get("mode") == "ADICIONAR_NOVO":
                for a in assignments:
                    template = int(a["template_row"])
                    templates.add(template)
                    append_specs.append({
                        "template_row": template,
                        "template_line_measurement": str(a.get("template_line_measurement") or a.get("line_measurement") or ""),
                        "template_strategy": str(a.get("template_strategy") or "EXACT_MEASUREMENT"),
                        "measurement_id": a.get("measurement_id"),
                        "line_measurement": str(a.get("line_measurement") or ""),
                        "fields": fields,
                        "final_status": final_status,
                    })
                    appended_rows += 1

        if not existing_targets and not append_specs:
            raise ValueError("Nenhum certificado está pronto para geração do Excel.")

        row_need = set(existing_targets) | templates
        source_rows = _collect_rows(sheet_xml, row_need)
        missing_existing = sorted(set(existing_targets) - set(source_rows))
        missing_tpl = sorted(templates - set(source_rows))
        if missing_existing or missing_tpl:
            raise ValueError(
                "A BD_QUALI mudou desde a última sincronização. Sincronize novamente antes de gerar a cópia. "
                + (f"Linhas ausentes: {missing_existing + missing_tpl}" if (missing_existing or missing_tpl) else "")
            )

        line_col = header_map.get(norm_header("LINHA MEDIÇÃO"))
        if not line_col:
            raise ValueError("Coluna LINHA MEDIÇÃO não localizada na BD_QUALI.")
        # Garante que o arquivo local ainda está alinhado ao banco que fez o
        # matching. Se alguém reordenou/alterou a planilha após a sincronização,
        # abortamos em vez de escrever na linha errada.
        line_errors = []
        for target, (_, _, expected_lm) in existing_targets.items():
            current = _cell_numeric_text(source_rows[target], line_col, target)
            if expected_lm and current and current != str(expected_lm):
                line_errors.append(f"linha {target}: esperado {expected_lm}, encontrado {current}")
        for spec in append_specs:
            template = int(spec["template_row"])
            expected_template_lm = str(spec.get("template_line_measurement") or "")
            current = _cell_numeric_text(source_rows[template], line_col, template)
            if expected_template_lm and current and current != expected_template_lm:
                if not _recover_append_template(spec, current):
                    line_errors.append(
                        f"modelo {template}: esperado linha-modelo {expected_template_lm}, encontrado {current}"
                    )
        if line_errors:
            raise ValueError(
                "A BD_QUALI foi alterada depois da última sincronização. Sincronize novamente. "
                + "; ".join(line_errors[:8])
            )

        replacements: dict[int, bytes] = {}
        # Atualiza certificados já existentes sem alterar a quantidade/posição das linhas.
        for target, (fields, final_status, _) in existing_targets.items():
            _validate_input_headers(header_map, fields)
            rxml = source_rows[target]
            replacements[target] = _apply_certificate_fields(rxml, target, header_map, fields, final_status)
            written_expected.append((target, fields.get("Nº CERTIFICADO Vv")))

        # Certificados novos são adicionados ao fim da própria tabela, clonando a
        # linha da medição correspondente. Isso evita inserir linhas no meio do
        # arquivo e mantém referências, gráficos e demais abas intactos.
        id_col = header_map.get(norm_header("ID"))
        for spec in append_specs:
            template = int(spec["template_row"])
            fields = spec["fields"]
            final_status = str(spec["final_status"])
            strategy = str(spec.get("template_strategy") or "EXACT_MEASUREMENT")
            _validate_input_headers(header_map, fields)
            target = next_row
            next_row += 1
            rxml = _clone_row(source_rows[template], template, target, shared_formulas)
            rxml = _make_row_visible(rxml)
            if strategy == "STRUCTURAL_FALLBACK":
                measurement = _measurement_snapshot(spec.get("measurement_id"))
                if not measurement:
                    raise ValueError(
                        f"A medição {spec.get('line_measurement') or ''} não está mais disponível no banco. "
                        "Sincronize Medição e tente novamente."
                    )
                # Um template genérico serve apenas como estrutura. Apagamos os
                # valores da linha antiga para nunca carregar kit/RNC/certificado
                # de outra medição e depois reconstruímos o bloco-base.
                rxml = _clear_non_formula_cells(rxml, target)
                rxml = _apply_measurement_fields(rxml, target, header_map, contractor, measurement)
            rxml = _apply_certificate_fields(rxml, target, header_map, fields, final_status)
            if id_col:
                rxml = _set_cell(rxml, id_col, target, next_id)
                next_id += 1
            replacements[target] = rxml
            written_expected.append((target, fields.get("Nº CERTIFICADO Vv")))

        new_table_end = table_end + appended_rows
        sheet_xml = _replace_rows(sheet_xml, replacements, append_missing=True)
        sheet_xml = _patch_dimension(sheet_xml, new_table_end)
        table_xml = _patch_table_ref(table_xml, new_table_end) if appended_rows else table_xml
        # Uma BD_QUALI filtrada (ex.: PAVIDEZ em M01) escondia as linhas clonadas.
        # Na CÓPIA de revisão limpamos apenas o filtro ativo e reexibimos as linhas da tabela;
        # o arquivo oficial continua intocado.
        if active_filters:
            table_xml = _clear_table_filters(table_xml)
            sheet_xml = _unhide_table_rows(sheet_xml, header_row + 1, new_table_end)
        workbook_xml = _force_recalc(workbook_xml)

        out_buf = BytesIO()
        with ZipFile(out_buf, "w") as zout:
            for info in zin.infolist():
                if info.filename == ws_path:
                    data = sheet_xml
                elif info.filename == table_path:
                    data = table_xml
                elif info.filename == "xl/workbook.xml":
                    data = workbook_xml
                else:
                    data = zin.read(info.filename)
                zout.writestr(info, data)

    content = out_buf.getvalue()
    _verify_output_rows(content, contractor, written_expected)
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"{source_path.stem}_QUALIMATCH_{suffix}.xlsx"
    return GeneratedFile(
        contractor=contractor,
        file_name=name,
        content=content,
        rows_written=updated_rows + appended_rows,
        certificates=len(certificates),
        updated_rows=updated_rows,
        appended_rows=appended_rows,
        source_path=str(source_path),
        source_sha256=source_hash,
        output_sha256=sha256(content).hexdigest(),
        target_rows=sorted(row_num for row_num, _ in written_expected),
        filters_cleared=bool(active_filters),
    )


def generate_excel_export(analysis: dict[str, Any]) -> tuple[str, str, bytes, dict[str, Any]]:
    ready_by_contractor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    blocked: list[dict[str, Any]] = []
    for cert in analysis.get("certificates") or []:
        plan = cert.get("excel_write") or {}
        if plan.get("ready"):
            ready_by_contractor[str(cert.get("contractor") or "").upper()].append(cert)
        else:
            blocked.append({
                "certificate": cert.get("certificate"),
                "contractor": cert.get("contractor"),
                "reason": plan.get("reason") or "Bloqueado",
            })
    if not ready_by_contractor:
        raise ValueError("Nenhum certificado está pronto para gerar a cópia Excel.")

    generated: list[GeneratedFile] = []
    for contractor, certs in ready_by_contractor.items():
        generated.append(patch_quality_workbook(_source_for_contractor(contractor), contractor, certs))

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "SAFE_COPY_ONLY",
        "original_files_changed": False,
        "files": [
            {
                "contractor": g.contractor,
                "file_name": g.file_name,
                "rows_written": g.rows_written,
                "updated_rows": g.updated_rows,
                "appended_rows": g.appended_rows,
                "certificates": g.certificates,
                "source_path": g.source_path,
                "source_sha256": g.source_sha256,
                "output_sha256": g.output_sha256,
                "target_rows": g.target_rows,
                "filters_cleared": g.filters_cleared,
            }
            for g in generated
        ],
        "blocked": blocked,
        "note": "Abra a cópia no Excel para recalcular as fórmulas. O arquivo original não é alterado. Filtros ativos da BD_QUALI são limpos somente na cópia para que as linhas geradas fiquem visíveis.",
    }

    if len(generated) == 1:
        g = generated[0]
        return g.file_name, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", g.content, report

    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as z:
        for g in generated:
            z.writestr(g.file_name, g.content)
        lines = [
            "QualiMatch — Relatório de geração segura",
            f"Gerado em: {report['generated_at']}",
            "O(s) arquivo(s) original(is) NÃO foram alterados.",
            "",
        ]
        for f in report["files"]:
            lines.extend([
                f"[{f['contractor']}] {f['file_name']}",
                f"  Certificados: {f['certificates']}",
                f"  Linhas atualizadas: {f['updated_rows']}",
                f"  Linhas adicionadas: {f['appended_rows']}",
                f"  Origem: {f['source_path']}",
                "",
            ])
        if blocked:
            lines.append("Certificados bloqueados e não gravados:")
            for b in blocked:
                lines.append(f"- {b['contractor']} {b['certificate']}: {b['reason']}")
        z.writestr("RELATORIO_IMPORTACAO.txt", "\n".join(lines).encode("utf-8"))
        z.writestr("RELATORIO_IMPORTACAO.json", json.dumps(report, ensure_ascii=False, indent=2).encode("utf-8"))
    name = f"QualiMatch_BD_QUALI_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    return name, "application/zip", buf.getvalue(), report



def write_excel_to_main_sources(analysis: dict[str, Any]) -> dict[str, Any]:
    """Grava os certificados prontos diretamente nas BD_QUALI configuradas.

    A escrita é deliberadamente conservadora:
    1. gera e valida TODAS as planilhas em memória antes de tocar nos originais;
    2. confere se o arquivo não mudou desde a geração;
    3. cria backup integral de cada XLSX;
    4. escreve em arquivo temporário na mesma pasta e troca via os.replace;
    5. em falha durante o commit, tenta restaurar todos os arquivos já trocados.
    """
    ready_by_contractor: dict[str, list[dict[str, Any]]] = defaultdict(list)
    blocked: list[dict[str, Any]] = []
    for cert in analysis.get("certificates") or []:
        plan = cert.get("excel_write") or {}
        if plan.get("ready"):
            ready_by_contractor[str(cert.get("contractor") or "").upper()].append(cert)
        else:
            blocked.append({
                "certificate": cert.get("certificate"),
                "contractor": cert.get("contractor"),
                "reason": plan.get("reason") or "Bloqueado",
            })
    if not ready_by_contractor:
        raise ValueError("Nenhum certificado está pronto para atualizar a BD_QUALI principal.")

    # Fase 1: produz e valida todos os arquivos sem alterar os originais.
    generated: list[GeneratedFile] = []
    for contractor, certs in ready_by_contractor.items():
        source = _source_for_contractor(contractor)
        generated.append(patch_quality_workbook(source, contractor, certs))

    # Garante que ninguém (Excel/OneDrive/outro usuário) alterou o arquivo entre
    # a leitura e o momento imediatamente anterior ao commit.
    for g in generated:
        source = Path(g.source_path)
        current_hash = sha256(source.read_bytes()).hexdigest()
        if current_hash != g.source_sha256:
            raise ValueError(
                f"A BD_QUALI {g.contractor} mudou durante a preparação. "
                "Sincronize novamente e refaça a prévia antes de gravar."
            )

    backup_dir = BACKUP_DIR / "bd_quali"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    prepared: list[dict[str, Any]] = []
    try:
        # Fase 2: backup + temporário na MESMA pasta (necessário para troca atômica).
        for g in generated:
            source = Path(g.source_path)
            backup = backup_dir / f"{g.contractor}_{source.stem}_{stamp}_{g.source_sha256[:8]}.xlsx"
            shutil.copy2(source, backup)
            tmp = source.with_name(f".{source.stem}.qualimatch_{stamp}_{os.getpid()}.tmp.xlsx")
            with tmp.open("wb") as f:
                f.write(g.content)
                f.flush()
                os.fsync(f.fileno())
            if sha256(tmp.read_bytes()).hexdigest() != g.output_sha256:
                raise ValueError(f"Falha ao validar o arquivo temporário da {g.contractor}.")
            prepared.append({"generated": g, "source": source, "backup": backup, "tmp": tmp, "committed": False})

        # Fase 3: commit. Se o Excel estiver mantendo o arquivo bloqueado no Windows,
        # os.replace falha antes de corromper o original e mostramos uma mensagem clara.
        for item in prepared:
            try:
                os.replace(item["tmp"], item["source"])
            except PermissionError as exc:
                raise ValueError(
                    f"A BD_QUALI {item['generated'].contractor} está aberta/bloqueada. "
                    "Feche a planilha no Excel e tente novamente."
                ) from exc
            item["committed"] = True

        # Fase 4: valida o que foi realmente gravado no caminho oficial.
        for item in prepared:
            g: GeneratedFile = item["generated"]
            content = item["source"].read_bytes()
            if sha256(content).hexdigest() != g.output_sha256:
                raise ValueError(f"A validação pós-gravação falhou para {g.contractor}.")
    except Exception:
        # Rollback best-effort de qualquer arquivo já substituído.
        for item in reversed(prepared):
            try:
                if item.get("committed") and Path(item["backup"]).exists():
                    restore_tmp = item["source"].with_name(f".{item['source'].stem}.qualimatch_restore_{os.getpid()}.tmp.xlsx")
                    shutil.copy2(item["backup"], restore_tmp)
                    os.replace(restore_tmp, item["source"])
                Path(item.get("tmp") or "").unlink(missing_ok=True)
            except Exception:
                pass
        raise
    finally:
        for item in prepared:
            try:
                Path(item.get("tmp") or "").unlink(missing_ok=True)
            except Exception:
                pass

    report = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "WRITE_MAIN_WITH_BACKUP",
        "original_files_changed": True,
        "files": [],
        "blocked": blocked,
        "note": (
            "As BD_QUALI principais foram atualizadas com backup e troca atômica. "
            "O Excel foi marcado para recalcular fórmulas na próxima abertura."
        ),
    }
    for item in prepared:
        g: GeneratedFile = item["generated"]
        report["files"].append({
            "contractor": g.contractor,
            "source_path": g.source_path,
            "backup_path": str(item["backup"]),
            "rows_written": g.rows_written,
            "updated_rows": g.updated_rows,
            "appended_rows": g.appended_rows,
            "certificates": g.certificates,
            "target_rows": g.target_rows,
            "filters_cleared": g.filters_cleared,
            "source_sha256_before": g.source_sha256,
            "source_sha256_after": g.output_sha256,
        })
    return report
