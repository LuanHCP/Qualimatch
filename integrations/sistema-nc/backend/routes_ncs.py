"""Registros de NC/AC-AP: emissão, resposta da contratada, análise técnica,
verificação de eficácia, encerramento e evidências.

Todas as transições de status validam o perfil no backend (nunca apenas
oculta o botão na tela) e sempre gravam uma entrada correspondente em
nc_historico — preservando a mesma trilha de auditoria por registro que o
protótipo original mantinha embutida no documento.
"""
import os
import shutil
import uuid
import datetime

from flask import Blueprint, request, jsonify, g, send_from_directory
from werkzeug.utils import secure_filename

import config
import db
import audit
import permissions as perm
import serializers as ser
import nc_rules
from auth_mw import login_required, csrf_required, permission_required, get_client_ip

bp = Blueprint("ncs", __name__, url_prefix="/api/ncs")

DISPOSICAO_LABEL = {"concessao": "Concessão", "reparo": "Reparo", "retrabalho": "Retrabalho", "reprovacao": "Reprovação"}


def _load_full(nc_id):
    row = db.fetchone(f"SELECT * FROM ncs WHERE id = {db.lit(nc_id)};")
    if not row:
        return None
    hist = db.fetchall(f"SELECT * FROM nc_historico WHERE nc_id = {db.lit(nc_id)} ORDER BY data_hora ASC;")
    anexos = db.fetchall(f"SELECT * FROM nc_anexos WHERE nc_id = {db.lit(nc_id)} ORDER BY created_at ASC;")
    row = dict(row)
    row["historico"] = [{
        "dataHora": str(h["data_hora"]), "usuarioNome": h.get("usuario_nome"),
        "statusAnterior": h.get("status_anterior"), "statusNovo": h.get("status_novo"), "comentario": h.get("comentario"),
    } for h in hist]
    row["anexos"] = [{
        "id": a["id"], "tipo": a["tipo"], "nomeArquivo": a.get("nome_arquivo"), "legenda": a.get("legenda"),
        "dataFoto": str(a["data_foto"]) if a.get("data_foto") else None, "km": a.get("km"), "pista": a.get("pista"),
        "faixa": a.get("faixa"), "url": f"/api/ncs/{nc_id}/anexos/{a['id']}/arquivo",
    } for a in anexos]
    return row


def _add_historico(nc_id, user, status_anterior, status_novo, comentario):
    db.execute(f"""
        INSERT INTO nc_historico (nc_id, usuario_id, usuario_nome, status_anterior, status_novo, comentario)
        VALUES ({db.lit(nc_id)}, {db.lit(user['id'])}, {db.lit(user['nome'])},
                {db.lit(status_anterior)}, {db.lit(status_novo)}, {db.lit(comentario)});
    """)


def _sede_row(sede_id):
    return db.fetchone(f"SELECT * FROM sedes WHERE id = {db.lit(sede_id)};")


@bp.get("")
@login_required
def list_ncs():
    sede_id = request.args.get("sedeId")
    if not sede_id:
        return jsonify(error="Parâmetro sedeId é obrigatório."), 400
    where = [f"sede_id = {db.lit(sede_id)}"]
    for param, column in (("status", "status_atual"), ("contratoId", "contrato_id"), ("contratadaId", "contratada_id"), ("categoria", "categoria"), ("classificacao", "classificacao")):
        if request.args.get(param):
            where.append(f"{column} = {db.lit(request.args[param])}")
    if request.args.get("dataDe"):
        where.append(f"data_emissao >= {db.lit(request.args['dataDe'])}::date")
    if request.args.get("dataAte"):
        where.append(f"data_emissao <= {db.lit(request.args['dataAte'])}::date")
    situacao = request.args.get("situacao")
    if situacao == "abertas":
        # A visão deve refletir literalmente a situação da planilha. Antes,
        # qualquer etapa ainda não encerrada (inclusive "Em Tratamento" e
        # "A encerrar") era agrupada como "Em aberto".
        where.append("lower(btrim(COALESCE(situacao_planilha_raw, ''))) IN ('aberta', 'em aberto')")
    elif situacao == "encerradas":
        # Não misturar "Cancelada", "Inexistente" nem "Encerrada com
        # ressalva" quando o usuário pede somente as encerradas.
        where.append("lower(btrim(COALESCE(situacao_planilha_raw, ''))) IN ('encerrada', 'encerradas')")
    elif situacao == "vencidas":
        where.append("status_atual NOT IN ('eficaz', 'encerrada') AND prazo_resposta < now()")
    elif situacao == "breve":
        where.append("status_atual NOT IN ('eficaz', 'encerrada') AND prazo_resposta >= now() AND prazo_resposta <= now() + interval '3 days'")
    if request.args.get("busca"):
        term = "%" + request.args["busca"].strip() + "%"
        where.append(f"(codigo_formatado ILIKE {db.lit(term)} OR descricao ILIKE {db.lit(term)} OR categoria ILIKE {db.lit(term)} OR rodovia ILIKE {db.lit(term)} OR EXISTS (SELECT 1 FROM contratadas c WHERE c.id = ncs.contratada_id AND c.razao_social ILIKE {db.lit(term)}))")
    clause = " AND ".join(where)
    page_arg, page_size_arg = request.args.get("page"), request.args.get("pageSize")
    if page_arg and page_arg.isdigit():
        page = max(int(page_arg), 1)
        page_size = min(max(int(page_size_arg or 15), 5), 100)
        sort_map = {"emissao":"data_emissao DESC", "prazo":"prazo_resposta ASC NULLS LAST", "codigo":"codigo_formatado ASC", "retencao":"COALESCE(valor_retencao_efetivo, valor_retencao_proposto, 0) DESC"}
        order = sort_map.get(request.args.get("sort"), "data_emissao DESC, created_at DESC")
        total = int(db.fetchone(f"SELECT count(*) AS n FROM ncs WHERE {clause};")["n"])
        offset = (page - 1) * page_size
        rows = db.fetchall(f"SELECT * FROM ncs WHERE {clause} ORDER BY {order} LIMIT {page_size} OFFSET {offset};")
        out = []
        for r in rows:
            r = dict(r); r["historico"] = []; r["anexos"] = []; out.append(ser.nc_out(r))
        return jsonify(items=out, total=total, page=page, pageSize=page_size)
    limit = request.args.get("limit")
    limit_sql = f" LIMIT {min(max(int(limit), 1), 500)}" if limit and limit.isdigit() else ""
    rows = db.fetchall(f"SELECT * FROM ncs WHERE {clause} ORDER BY created_at DESC{limit_sql};")
    out = []
    for r in rows:
        r = dict(r)
        r["historico"] = []
        r["anexos"] = []
        out.append(ser.nc_out(r))
    return jsonify(out)


@bp.get("/resumo")
@login_required
def resumo_ncs():
    sede_id = request.args.get("sedeId")
    if not sede_id:
        return jsonify(error="Parâmetro sedeId é obrigatório."), 400
    row = db.fetchone(f"""
        SELECT count(*) AS total,
          count(*) FILTER (WHERE lower(btrim(COALESCE(situacao_planilha_raw, ''))) IN ('aberta', 'em aberto')) AS abertas,
          count(*) FILTER (WHERE status_atual NOT IN ('eficaz', 'encerrada') AND prazo_resposta < now()) AS vencidas,
          count(*) FILTER (WHERE status_atual NOT IN ('eficaz', 'encerrada') AND prazo_resposta >= now() AND prazo_resposta <= now() + interval '3 days') AS vencem_breve,
          count(*) FILTER (WHERE lower(btrim(COALESCE(situacao_planilha_raw, ''))) IN ('encerrada', 'encerradas')) AS encerradas,
          COALESCE(sum(COALESCE(valor_retencao_efetivo, valor_retencao_proposto, 0)), 0) AS retencao
        FROM ncs WHERE sede_id = {db.lit(sede_id)};
    """)
    return jsonify({k: float(v) if k == "retencao" else int(v) for k, v in row.items()})


@bp.get("/<nc_id>")
@login_required
def get_nc(nc_id):
    row = _load_full(nc_id)
    if not row:
        return jsonify(error="Registro não encontrado."), 404
    return jsonify(ser.nc_out(row))


@bp.patch("/<nc_id>")
@login_required
@csrf_required
@permission_required(lambda perfil: perm.pode_emitir(perfil) or perm.pode_avaliar(perfil))
def update_nc(nc_id):
    current = db.fetchone(f"SELECT * FROM ncs WHERE id = {db.lit(nc_id)};")
    if not current:
        return jsonify(error="Registro não encontrado."), 404
    body = request.get_json(silent=True) or {}
    mapping = {
        "contratoId":"contrato_id", "contratadaId":"contratada_id", "dataEmissao":"data_emissao",
        "dataOcorrencia":"data_ocorrencia", "responsavelEmissaoNome":"responsavel_emissao_nome",
        "area":"area", "disciplina":"disciplina", "categoria":"categoria", "item":"item",
        "subitem":"subitem", "classificacao":"classificacao", "unidadeQuantidade":"unidade_quantidade",
        "rodovia":"rodovia", "trecho":"trecho", "kmInicial":"km_inicial", "kmFinal":"km_final",
        "pistaSentido":"pista_sentido", "faixa":"faixa", "estacaInicial":"estaca_inicial",
        "estacaFinal":"estaca_final", "comprimento":"comprimento", "largura":"largura",
        "espessura":"espessura", "quantidade":"quantidade", "descricao":"descricao",
        "observacaoCampo":"observacao_campo", "normaReferencia":"norma_referencia",
        "valorEstimado":"valor_estimado", "valorRetencaoProposto":"valor_retencao_proposto",
        "solicitaAcAp":"solicita_ac_ap",
    }
    numeric = {"kmInicial","kmFinal","comprimento","largura","espessura","quantidade","valorEstimado","valorRetencaoProposto"}
    fields = {}
    for source, column in mapping.items():
        if source in body:
            fields[column] = _num(body[source]) if source in numeric else body[source]
    if not fields:
        return jsonify(error="Nenhum campo editável foi informado."), 400
    fields["updated_by"] = g.user["id"]
    db.execute(f"UPDATE ncs SET {', '.join(f'{k} = {db.lit(v)}' for k, v in fields.items())} WHERE id = {db.lit(nc_id)};")
    _add_historico(nc_id, g.user, current["status_atual"], current["status_atual"], "Dados do registro editados.")
    audit.log(g.user, "nc.update", "ncs", nc_id, {"campos": list(fields.keys())}, get_client_ip())
    return jsonify(ser.nc_out(_load_full(nc_id)))


@bp.post("")
@login_required
@csrf_required
@permission_required(perm.pode_emitir)
def create_nc():
    body = request.get_json(silent=True) or {}
    sede_id = body.get("sedeId")
    sede = _sede_row(sede_id) if sede_id else None
    if not sede:
        return jsonify(error="SEDE inválida."), 400
    for campo, msg in [("contratoId", "Selecione o contrato."), ("dataEmissao", "Informe a data de emissão."),
                        ("responsavelEmissaoNome", "Informe o responsável pela emissão."),
                        ("categoria", "Selecione a categoria."), ("rodovia", "Informe a rodovia."),
                        ("descricao", "Informe a descrição da ocorrência.")]:
        if not body.get(campo):
            return jsonify(error=msg, field=campo), 400

    tipo_core = body.get("tipoCore") or "NC"
    data_emissao = body["dataEmissao"]
    ano = int(data_emissao[:4])
    seq = nc_rules.proximo_numero(sede_id, tipo_core, ano)
    codigo = nc_rules.gerar_codigo(sede, tipo_core, seq, ano)
    prazo_dias = int(body.get("prazoDias") or sede.get("prazo_padrao_dias") or 3)
    prazo_resposta = nc_rules.add_dias(data_emissao, prazo_dias, sede.get("dias_uteis"))

    cols = {
        "sede_id": sede_id, "tipo_core": tipo_core, "contrato_id": body.get("contratoId"),
        "contratada_id": body.get("contratadaId") or None, "numero_sequencial": seq, "ano": ano,
        "codigo_formatado": codigo, "data_emissao": data_emissao, "data_ocorrencia": body.get("dataOcorrencia") or None,
        "responsavel_emissao_nome": body.get("responsavelEmissaoNome"), "area": body.get("area"),
        "disciplina": body.get("disciplina"), "categoria": body.get("categoria"), "item": body.get("item"),
        "subitem": body.get("subitem"), "classificacao": body.get("classificacao"),
        "unidade_quantidade": body.get("unidadeQuantidade"), "rodovia": body.get("rodovia"), "trecho": body.get("trecho"),
        "km_inicial": _num(body.get("kmInicial")), "km_final": _num(body.get("kmFinal")),
        "pista_sentido": body.get("pistaSentido"), "faixa": body.get("faixa"),
        "estaca_inicial": body.get("estacaInicial"), "estaca_final": body.get("estacaFinal"),
        "comprimento": _num(body.get("comprimento")), "largura": _num(body.get("largura")),
        "espessura": _num(body.get("espessura")), "quantidade": _num(body.get("quantidade")),
        "descricao": body.get("descricao"), "observacao_campo": body.get("observacaoCampo"),
        "norma_referencia": body.get("normaReferencia"), "valor_estimado": _num(body.get("valorEstimado")),
        "valor_retencao_proposto": _num(body.get("valorRetencaoProposto")), "prazo_resposta": prazo_resposta,
        "solicita_ac_ap": bool(body.get("solicitaAcAp")), "status_atual": "aguardando_resposta",
        "created_by": g.user["id"], "updated_by": g.user["id"],
    }
    collist = ", ".join(cols.keys())
    vallist = ", ".join(db.lit(v) for v in cols.values())
    row = db.fetchone(f"INSERT INTO ncs ({collist}) VALUES ({vallist}) RETURNING *;")
    for status in ("emitida", "protocolada", "aguardando_resposta"):
        _add_historico(row["id"], g.user, None if status == "emitida" else "emitida" if status == "protocolada" else "protocolada", status,
                        {"emitida": "Registro emitido.", "protocolada": "Protocolado automaticamente.",
                         "aguardando_resposta": f"Aguardando resposta da contratada até {prazo_resposta}."}[status])
    audit.log(g.user, "nc.create", "ncs", row["id"], {"codigo": codigo}, get_client_ip())
    return jsonify(ser.nc_out(_load_full(row["id"]))), 201


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


@bp.post("/<nc_id>/resposta")
@login_required
@csrf_required
@permission_required(perm.pode_responder)
def responder(nc_id):
    nc = db.fetchone(f"SELECT * FROM ncs WHERE id = {db.lit(nc_id)};")
    if not nc:
        return jsonify(error="Registro não encontrado."), 404
    if perm.STATUS_GROUP.get(nc["status_atual"]) == "encerrado":
        return jsonify(error="Este registro já está encerrado."), 409
    body = request.get_json(silent=True) or {}
    responsavel = (body.get("responsavel") or "").strip()
    prazo = body.get("prazoImplementacao")
    disposicao = body.get("disposicaoSolicitada")
    if not responsavel or not prazo or disposicao not in DISPOSICAO_LABEL:
        return jsonify(error="Preencha responsável, prazo de implementação e disposição solicitada."), 400
    resposta = {
        "analiseCausa": body.get("analiseCausa", ""), "correcaoImediata": body.get("correcaoImediata", ""),
        "acaoCorretiva": body.get("acaoCorretiva", ""), "acaoPreventiva": body.get("acaoPreventiva", ""),
        "planoDeAcao": body.get("planoDeAcao", ""), "conclusao": body.get("conclusao", ""),
        "responsavel": responsavel, "prazoImplementacao": prazo, "disposicaoSolicitada": disposicao,
    }
    db.execute(f"""
        UPDATE ncs SET resposta_contratada = {db.json_lit(resposta)}, status_atual = 'em_analise', updated_by = {db.lit(g.user['id'])}
        WHERE id = {db.lit(nc_id)};
    """)
    _add_historico(nc_id, g.user, nc["status_atual"], "respondida", f"Contratada enviou resposta e disposição: {DISPOSICAO_LABEL[disposicao]}.")
    _add_historico(nc_id, g.user, "respondida", "em_analise", "Aguardando análise da concessionária.")
    audit.log(g.user, "nc.resposta", "ncs", nc_id, {"disposicao": disposicao}, get_client_ip())
    return jsonify(ser.nc_out(_load_full(nc_id)))


@bp.post("/<nc_id>/analise")
@login_required
@csrf_required
@permission_required(perm.pode_avaliar)
def analisar(nc_id):
    nc = db.fetchone(f"SELECT * FROM ncs WHERE id = {db.lit(nc_id)};")
    if not nc:
        return jsonify(error="Registro não encontrado."), 404
    if nc["status_atual"] != "em_analise":
        return jsonify(error="Este registro não está aguardando análise."), 409
    body = request.get_json(silent=True) or {}
    decisao = body.get("decisao")
    if decisao not in ("aprovada", "recusada"):
        return jsonify(error="Decisão inválida."), 400
    parecer = body.get("parecer") or ""
    novo = "em_execucao" if decisao == "aprovada" else "aguardando_resposta"
    avaliacao = dict(nc.get("avaliacao_concessionaria") or {})
    avaliacao.update({"parecerTecnico": parecer, "disposicaoStatus": decisao})
    db.execute(f"""
        UPDATE ncs SET status_atual = {db.lit(novo)}, avaliacao_concessionaria = {db.json_lit(avaliacao)},
               updated_by = {db.lit(g.user['id'])}
        WHERE id = {db.lit(nc_id)};
    """)
    intermed = "disposicao_aprovada" if decisao == "aprovada" else "disposicao_recusada"
    _add_historico(nc_id, g.user, "em_analise", intermed, parecer or f"Disposição {decisao}.")
    if decisao == "aprovada":
        _add_historico(nc_id, g.user, "disposicao_aprovada", "em_execucao", "Ação corretiva/preventiva liberada para execução.")
    audit.log(g.user, "nc.analise", "ncs", nc_id, {"decisao": decisao}, get_client_ip())
    return jsonify(ser.nc_out(_load_full(nc_id)))


@bp.post("/<nc_id>/solicitar-verificacao")
@login_required
@csrf_required
@permission_required(perm.pode_avaliar)
def solicitar_verificacao(nc_id):
    nc = db.fetchone(f"SELECT * FROM ncs WHERE id = {db.lit(nc_id)};")
    if not nc:
        return jsonify(error="Registro não encontrado."), 404
    if nc["status_atual"] not in ("em_execucao", "disposicao_aprovada"):
        return jsonify(error="Registro não está em execução."), 409
    db.execute(f"UPDATE ncs SET status_atual = 'aguardando_verificacao', updated_by = {db.lit(g.user['id'])} WHERE id = {db.lit(nc_id)};")
    _add_historico(nc_id, g.user, nc["status_atual"], "aguardando_verificacao", "Verificação de eficácia solicitada.")
    audit.log(g.user, "nc.solicitar_verificacao", "ncs", nc_id, None, get_client_ip())
    return jsonify(ser.nc_out(_load_full(nc_id)))


@bp.post("/<nc_id>/eficacia")
@login_required
@csrf_required
@permission_required(perm.pode_avaliar)
def eficacia(nc_id):
    nc = db.fetchone(f"SELECT * FROM ncs WHERE id = {db.lit(nc_id)};")
    if not nc:
        return jsonify(error="Registro não encontrado."), 404
    if nc["status_atual"] != "aguardando_verificacao":
        return jsonify(error="Registro não está aguardando verificação de eficácia."), 409
    body = request.get_json(silent=True) or {}
    resultado = body.get("resultado")
    if resultado not in ("eficaz", "nao_eficaz"):
        return jsonify(error="Resultado inválido."), 400
    valor = _num(body.get("valor"))
    parecer = body.get("parecer") or ""
    avaliacao = dict(nc.get("avaliacao_concessionaria") or {})
    parecer_anterior = avaliacao.get("parecerTecnico") or ""
    avaliacao.update({"resultadoEficacia": resultado, "valorRetidoFinal": valor,
                       "parecerTecnico": (parecer_anterior + " | " + parecer) if parecer_anterior else parecer})
    novo_status = "encerrada" if resultado == "eficaz" else "em_execucao"
    set_extra = ", data_encerramento = now()" if novo_status == "encerrada" else ""
    valor_clause = f", valor_retencao_efetivo = {db.lit(valor)}" if valor is not None else ""
    db.execute(f"""
        UPDATE ncs SET status_atual = {db.lit(novo_status)}, avaliacao_concessionaria = {db.json_lit(avaliacao)}
               {valor_clause}{set_extra}, updated_by = {db.lit(g.user['id'])}
        WHERE id = {db.lit(nc_id)};
    """)
    _add_historico(nc_id, g.user, "aguardando_verificacao", resultado, parecer)
    if novo_status == "encerrada":
        _add_historico(nc_id, g.user, "eficaz", "encerrada", "Registro encerrado.")
    audit.log(g.user, "nc.eficacia", "ncs", nc_id, {"resultado": resultado}, get_client_ip())
    return jsonify(ser.nc_out(_load_full(nc_id)))


@bp.post("/<nc_id>/encerrar-vencido")
@login_required
@csrf_required
@permission_required(perm.pode_avaliar)
def encerrar_vencido(nc_id):
    nc = db.fetchone(f"SELECT * FROM ncs WHERE id = {db.lit(nc_id)};")
    if not nc:
        return jsonify(error="Registro não encontrado."), 404
    sede = _sede_row(nc["sede_id"])
    vencido = (nc["status_atual"] == "aguardando_resposta" and nc["prazo_resposta"]
               and str(nc["prazo_resposta"]) < nc_rules.now_iso())
    if not vencido or not sede.get("encerramento_automatico_desconto"):
        return jsonify(error="Este registro não pode ser encerrado automaticamente por prazo vencido nesta SEDE."), 409
    db.execute(f"""
        UPDATE ncs SET status_atual = 'encerrada', data_encerramento = now(),
               valor_retencao_efetivo = valor_retencao_proposto, updated_by = {db.lit(g.user['id'])}
        WHERE id = {db.lit(nc_id)};
    """)
    _add_historico(nc_id, g.user, nc["status_atual"], "encerrada",
                    "Encerrado automaticamente por prazo vencido, com aplicação da retenção proposta (regra da SEDE).")
    audit.log(g.user, "nc.encerrar_vencido", "ncs", nc_id, None, get_client_ip())
    return jsonify(ser.nc_out(_load_full(nc_id)))


@bp.delete("/<nc_id>")
@login_required
@csrf_required
@permission_required(perm.pode_configurar)
def delete_nc(nc_id):
    """Exclui definitivamente uma NC e limpa seus anexos locais."""
    nc = db.fetchone(f"SELECT id, sede_id, codigo_formatado FROM ncs WHERE id = {db.lit(nc_id)};")
    if not nc:
        return jsonify(error="Registro não encontrado."), 404
    if g.user["perfil"] == "admin_sede":
        allowed = db.fetchone(f"SELECT 1 AS ok FROM user_sedes WHERE user_id = {db.lit(g.user['id'])} AND sede_id = {db.lit(nc['sede_id'])};")
        if not allowed:
            return jsonify(error="Sem permissão para excluir registros desta SEDE."), 403

    anexos = db.fetchall(f"SELECT storage_path FROM nc_anexos WHERE nc_id = {db.lit(nc_id)};")
    db.execute(f"DELETE FROM ncs WHERE id = {db.lit(nc_id)};")

    expected_dir = os.path.realpath(os.path.join(config.UPLOAD_DIR, "nc", nc_id))
    upload_root = os.path.realpath(os.path.join(config.UPLOAD_DIR, "nc"))
    cleanup_errors = []
    try:
        if os.path.commonpath([expected_dir, upload_root]) == upload_root and os.path.isdir(expected_dir):
            shutil.rmtree(expected_dir)
    except (OSError, ValueError) as exc:
        cleanup_errors.append(str(exc))

    audit.log(g.user, "nc.delete", "ncs", nc_id,
              {"codigo": nc["codigo_formatado"], "anexos": len(anexos), "falhasLimpeza": cleanup_errors},
              get_client_ip())
    return jsonify(message=f"Registro {nc['codigo_formatado']} excluído.", id=nc_id,
                   anexosRemovidos=len(anexos), limpezaCompleta=not cleanup_errors)


# --------------------------------------------------------------- anexos ---
ALLOWED_EXT = {"jpg", "jpeg", "png", "gif", "webp", "pdf"}


@bp.post("/<nc_id>/anexos")
@login_required
@csrf_required
@permission_required(lambda perfil: perm.pode_emitir(perfil) or perm.pode_avaliar(perfil))
def upload_anexo(nc_id):
    nc = db.fetchone(f"SELECT id, sede_id FROM ncs WHERE id = {db.lit(nc_id)};")
    if not nc:
        return jsonify(error="Registro não encontrado."), 404
    file = request.files.get("arquivo")
    if not file or not file.filename:
        return jsonify(error="Selecione um arquivo."), 400
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        return jsonify(error="Tipo de arquivo não permitido."), 400

    anexo_id = str(uuid.uuid4())
    folder = os.path.join(config.UPLOAD_DIR, "nc", nc_id)
    os.makedirs(folder, exist_ok=True)
    stored_name = f"{anexo_id}.{ext}"
    path = os.path.join(folder, stored_name)
    file.save(path)
    size = os.path.getsize(path)
    if size > config.MAX_UPLOAD_MB * 1024 * 1024:
        os.remove(path)
        return jsonify(error=f"Arquivo excede o limite de {config.MAX_UPLOAD_MB}MB."), 400

    safe_name = secure_filename(file.filename)
    db.execute(f"""
        INSERT INTO nc_anexos (id, nc_id, tipo, nome_arquivo, storage_path, legenda, data_foto, km, pista, faixa,
                                tamanho_bytes, content_type, uploaded_by)
        VALUES ({db.lit(anexo_id)}, {db.lit(nc_id)}, 'foto', {db.lit(safe_name)}, {db.lit(path)},
                {db.lit(request.form.get('legenda'))}, {db.lit(request.form.get('dataFoto') or None)}::date,
                {db.lit(request.form.get('km'))}, {db.lit(request.form.get('pista'))}, {db.lit(request.form.get('faixa'))},
                {db.lit(size)}, {db.lit(file.content_type)}, {db.lit(g.user['id'])});
    """)
    audit.log(g.user, "nc.anexo.upload", "ncs", nc_id, {"arquivo": safe_name}, get_client_ip())
    return jsonify(ser.nc_out(_load_full(nc_id))), 201


@bp.get("/<nc_id>/anexos/<anexo_id>/arquivo")
@login_required
def download_anexo(nc_id, anexo_id):
    row = db.fetchone(f"SELECT * FROM nc_anexos WHERE id = {db.lit(anexo_id)} AND nc_id = {db.lit(nc_id)};")
    if not row:
        return jsonify(error="Anexo não encontrado."), 404
    folder = os.path.dirname(row["storage_path"])
    filename = os.path.basename(row["storage_path"])
    return send_from_directory(folder, filename, as_attachment=False, download_name=row.get("nome_arquivo") or filename)
