"""Exportação de registros de NC para .xlsx, com colunas compatíveis com a
planilha de referência (mesmos nomes de cabeçalho da aba NC) e tipos
nativos preservados (datas como data, valores como número/moeda, textos
como texto) — para que o arquivo gerado possa ser reaberto no Excel e
reimportado sem perda ou duplicação."""
import io
import datetime
import openpyxl
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

COLUMNS = [
    ("Unidade", "sede_sigla"), ("nº Emissão", "codigo_ou_planilha"), ("Contrato", "contrato_numero"),
    ("Contratada", "contratada_nome"), ("Situação Final (Status)", "status_label"),
    ("Assunto", "categoria"), ("Descrição Detalhada", "descricao"), ("Data de Emissão", "data_emissao"),
    ("Disciplina", "disciplina"), ("CLASSIFICAÇÃO", "classificacao"),
    ("Valor para Retenção", "valor_retencao_proposto"), ("Valor Real Retido", "valor_retencao_efetivo"),
    ("Prazo de Resposta", "prazo_resposta"), ("Data de Encerramento", "data_encerramento"),
    ("Rodovia", "rodovia"), ("Km Inicial", "km_inicial"), ("Km Final", "km_final"),
    ("Tipo de Registro", "tipo_core"), ("ID Sistema", "id"),
]

STATUS_LABEL = {
    "rascunho": "Rascunho", "emitida": "Emitida", "protocolada": "Protocolada",
    "aguardando_resposta": "Aguard. resposta da contratada", "respondida": "Respondida",
    "em_analise": "Em análise pela concessionária", "disposicao_aprovada": "Disposição aprovada",
    "disposicao_recusada": "Disposição recusada", "em_execucao": "Em execução",
    "aguardando_verificacao": "Aguard. verificação de eficácia", "eficaz": "Eficaz",
    "nao_eficaz": "Não eficaz", "encerrada": "Encerrada",
}


def build_export(rows, sede_sigla):
    """rows: lista de dicts (linhas da tabela ncs, já com contrato_numero e
    contratada_nome resolvidos pela consulta).

    Os cabeçalhos são escritos na LINHA 2 (linha 1 fica livre para um
    título/metadado) — o mesmo layout da planilha de referência (aba NC)
    e o mesmo que o importador espera (`header_row=2`). Isso é o que
    permite reimportar o próprio arquivo exportado sem qualquer ajuste
    manual: o ciclo importar → exportar → reimportar não duplica nem
    corrompe registros (mesma chave de deduplicação nº emissão + unidade
    + contrato é preservada na coluna "nº Emissão")."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "NC"
    ws.cell(row=1, column=1, value=f"Exportação — SEDE {sede_sigla} — {datetime.date.today().isoformat()} — {len(rows)} registro(s)")
    header_font = Font(bold=True)
    for c_idx, (label, _) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=2, column=c_idx, value=label)
        cell.font = header_font

    for r_idx, row in enumerate(rows, start=3):
        values = {
            "sede_sigla": sede_sigla,
            "codigo_ou_planilha": row.get("numero_emissao_planilha") or row.get("codigo_formatado"),
            "contrato_numero": row.get("contrato_numero") or row.get("contrato_planilha_raw"),
            "contratada_nome": row.get("contratada_nome"),
            "status_label": STATUS_LABEL.get(row.get("status_atual"), row.get("status_atual")),
            "categoria": row.get("categoria"),
            "descricao": row.get("descricao"),
            "data_emissao": _to_date(row.get("data_emissao")),
            "disciplina": row.get("disciplina"),
            "classificacao": row.get("classificacao"),
            "valor_retencao_proposto": _to_number(row.get("valor_retencao_proposto")),
            "valor_retencao_efetivo": _to_number(row.get("valor_retencao_efetivo")),
            "prazo_resposta": _to_date(row.get("prazo_resposta")),
            "data_encerramento": _to_date(row.get("data_encerramento")),
            "rodovia": row.get("rodovia"),
            "km_inicial": _to_number(row.get("km_inicial")),
            "km_final": _to_number(row.get("km_final")),
            "tipo_core": row.get("tipo_core"),
            "id": row.get("id"),
        }
        for c_idx, (_, key) in enumerate(COLUMNS, start=1):
            cell = ws.cell(row=r_idx, column=c_idx, value=values.get(key))
            if key in ("data_emissao", "prazo_resposta", "data_encerramento") and values.get(key):
                cell.number_format = "DD/MM/YYYY"
            if key in ("valor_retencao_proposto", "valor_retencao_efetivo"):
                cell.number_format = '"R$" #,##0.00'

    for c_idx, (label, _) in enumerate(COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(c_idx)].width = max(12, min(40, len(label) + 4))
    ws.freeze_panes = "A3"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def _to_date(v):
    if not v:
        return None
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v
    s = str(v)[:10]
    try:
        return datetime.date.fromisoformat(s)
    except ValueError:
        return None


def _to_number(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
