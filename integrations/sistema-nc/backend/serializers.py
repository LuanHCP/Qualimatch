"""Conversão de linhas do banco (snake_case) para o formato usado pelo
frontend (camelCase, mesmos nomes de campo do protótipo original), e
vice-versa. Mantém a reescrita do frontend mínima."""


def sede_out(r):
    return {
        "id": r["id"], "sigla": r["sigla"], "nome": r["nome"], "razaoSocial": r.get("razao_social"),
        "logoLetra": r.get("logo_letra"), "corPrimaria": r.get("cor_primaria"), "corSecundaria": r.get("cor_secundaria"),
        "nomenclatura": {"NC": r.get("nomenclatura_nc"), "AC": r.get("nomenclatura_ac")},
        "mascaraNumeracao": r.get("mascara_numeracao"), "prazoPadraoDias": r.get("prazo_padrao_dias"),
        "diasUteis": r.get("dias_uteis"), "encerramentoAutomaticoComDesconto": r.get("encerramento_automatico_desconto"),
        "planilhaLocalPath": r.get("planilha_local_path") or "",
        "areas": r.get("areas") or [], "disciplinas": r.get("disciplinas") or [],
        "classificacoes": r.get("classificacoes") or [], "ativo": r.get("ativo", True),
    }


def contratada_out(r):
    return {"id": r["id"], "razaoSocial": r["razao_social"], "cnpj": r.get("cnpj"), "ativo": r.get("ativo", True)}


def contrato_out(r):
    return {
        "id": r["id"], "sedeId": r["sede_id"], "numero": r["numero"], "descricaoObra": r.get("descricao_obra"),
        "tipoObra": r.get("tipo_obra"), "ano": r.get("ano"), "lote": r.get("lote"), "gerente": r.get("gerente"),
        "gestorObra": r.get("gestor_obra"), "vigenciaInicio": r.get("vigencia_inicio"), "vigenciaFim": r.get("vigencia_fim"),
        "situacao": r.get("situacao"), "contratadaIds": r.get("contratada_ids") or [],
    }


def usuario_out(r):
    return {
        "id": r["id"], "nome": r["nome"], "email": r["email"], "perfil": r["perfil"],
        "ativo": r.get("ativo", True), "bloqueado": r.get("bloqueado", False),
        "mustChangePassword": r.get("must_change_password", False),
        "approvalStatus": r.get("approval_status", "aprovado"), "requestedAt": _iso(r.get("requested_at")),
        "sedeIds": r.get("sede_ids") or [], "contratoIds": r.get("contrato_ids") or [],
        "lastLoginAt": _iso(r.get("last_login_at")), "createdAt": _iso(r.get("created_at")),
    }


def texto_out(r):
    return {
        "id": r["id"], "sedeId": r.get("sede_id") or "GLOBAL", "categoria": r["categoria"],
        "item": r["item"], "subitem": r.get("subitem") or "", "texto": r["texto"],
    }


def _iso(v):
    if v is None:
        return None
    return str(v)


def nc_out(r):
    return {
        "id": r["id"], "sedeId": r["sede_id"], "tipoCore": r["tipo_core"],
        "contratoId": r.get("contrato_id"), "contratadaId": r.get("contratada_id"),
        "numeroSequencial": r.get("numero_sequencial"), "ano": r.get("ano"), "codigoFormatado": r["codigo_formatado"],
        "dataEmissao": _iso(r.get("data_emissao")), "dataOcorrencia": _iso(r.get("data_ocorrencia")),
        "responsavelEmissaoNome": r.get("responsavel_emissao_nome"),
        "area": r.get("area"), "disciplina": r.get("disciplina"), "categoria": r.get("categoria"),
        "item": r.get("item"), "subitem": r.get("subitem"), "classificacao": r.get("classificacao"),
        "unidadeQuantidade": r.get("unidade_quantidade"),
        "rodovia": r.get("rodovia"), "trecho": r.get("trecho"),
        "kmInicial": r.get("km_inicial"), "kmFinal": r.get("km_final"),
        "pistaSentido": r.get("pista_sentido"), "faixa": r.get("faixa"),
        "estacaInicial": r.get("estaca_inicial"), "estacaFinal": r.get("estaca_final"),
        "comprimento": r.get("comprimento"), "largura": r.get("largura"), "espessura": r.get("espessura"),
        "quantidade": r.get("quantidade"),
        "descricao": r.get("descricao"), "observacaoCampo": r.get("observacao_campo"), "normaReferencia": r.get("norma_referencia"),
        "valorEstimado": r.get("valor_estimado"), "valorRetencaoProposto": r.get("valor_retencao_proposto"),
        "valorRetencaoEfetivo": r.get("valor_retencao_efetivo"),
        "prazoResposta": _iso(r.get("prazo_resposta")), "solicitaAcAp": r.get("solicita_ac_ap"),
        "statusAtual": r["status_atual"], "dataEncerramento": _iso(r.get("data_encerramento")),
        "respostaContratada": r.get("resposta_contratada"), "avaliacaoConcessionaria": r.get("avaliacao_concessionaria"),
        "origem": r.get("origem"), "anexos": r.get("anexos") or [], "historico": r.get("historico") or [],
    }


def import_log_out(r):
    return {
        "id": r["id"], "sedeId": r["sede_id"], "userNome": r.get("user_nome"), "filename": r["filename"],
        "sheetName": r.get("sheet_name"), "status": r["status"], "totalRows": r.get("total_rows"),
        "validCount": r.get("valid_count"), "duplicateCount": r.get("duplicate_count"),
        "updateCount": r.get("update_count"), "rejectedCount": r.get("rejected_count"),
        "errorCount": r.get("error_count"), "startedAt": _iso(r.get("started_at")), "finishedAt": _iso(r.get("finished_at")),
    }
