"""Importação e exportação de planilhas (.xlsx/.xlsm/.xls) da aba NC.

Fluxo de importação (seção 5 do pedido): upload -> prévia classificada
(válidos / duplicados / atualizações / rejeitados / erros) -> confirmação
explícita -> gravação transacional -> registro em import_logs (usuário,
data, arquivo, resultado). Nenhuma linha é gravada antes da confirmação.
"""
import io
import os
import inspect
import csv
import uuid
import datetime
import shutil

from flask import Blueprint, request, jsonify, g, send_file
from werkzeug.datastructures import FileStorage, ImmutableMultiDict

import db
import audit
import permissions as perm
import serializers as ser
import xlsx_import as XI
import xlsx_export as XE
import config
from auth_mw import login_required, csrf_required, permission_required, get_client_ip

bp = Blueprint("import_export", __name__, url_prefix="/api")

MAX_FILE_MB = 20
ALLOWED_EXTS = (".xlsx", ".xlsm", ".xls")


def _sede_row(sede_id):
    return db.fetchone(f"SELECT * FROM sedes WHERE id = {db.lit(sede_id)};")


def _existing_keys(sede_id):
    rows = db.fetchall(f"""
        SELECT id, unidade_planilha, numero_emissao_planilha, contrato_planilha_raw,
               COALESCE(planilha_ocorrencia, 1) AS planilha_ocorrencia,
               situacao_planilha_raw, descricao, valor_retencao_proposto, valor_retencao_efetivo, status_atual
        FROM ncs WHERE sede_id = {db.lit(sede_id)} AND numero_emissao_planilha IS NOT NULL;
    """)
    idx = {}
    for r in rows:
        key = _key(
            r.get("unidade_planilha"), r.get("numero_emissao_planilha"),
            r.get("contrato_planilha_raw"), r.get("planilha_ocorrencia") or 1,
        )
        idx[key] = r
    return idx


def _base_key(unidade, numero_emissao, contrato):
    return (
        (unidade or "").strip().lower(),
        (numero_emissao or "").strip().lower(),
        (contrato or "").strip().lower(),
    )


def _key(unidade, numero_emissao, contrato, ocorrencia=1):
    return _base_key(unidade, numero_emissao, contrato) + (int(ocorrencia or 1),)


@bp.post("/import/preview")
@login_required
@csrf_required
@permission_required(perm.pode_configurar)
def import_preview():
    sede_id = request.form.get("sedeId")
    sede = _sede_row(sede_id) if sede_id else None
    if not sede:
        return jsonify(error="SEDE inválida."), 400
    file = request.files.get("arquivo")
    if not file or not file.filename:
        return jsonify(error="Selecione um arquivo de planilha."), 400
    if not file.filename.lower().endswith(ALLOWED_EXTS):
        return jsonify(error="Formato não suportado. Envie um arquivo .xlsx, .xlsm ou .xls."), 400

    file_bytes = file.read()
    if len(file_bytes) > MAX_FILE_MB * 1024 * 1024:
        return jsonify(error=f"Arquivo excede o limite de {MAX_FILE_MB}MB."), 400

    try:
        sheet_name, header_mapping, raw_rows = XI.read_workbook_rows(file_bytes, file.filename, sede_id)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    except Exception as e:
        return jsonify(error=f"Não foi possível ler a planilha: {e}"), 400

    aux_contratos = XI.load_contrato_aux_sheet(file_bytes, sede["sigla"])
    existing_idx = _existing_keys(sede_id)

    contratos_sede = {c["numero"].strip().lower(): c for c in db.fetchall(
        f"SELECT id, numero FROM contratos WHERE sede_id = {db.lit(sede_id)};")}
    contratadas_all = {c["razao_social"].strip().lower(): c for c in db.fetchall(
        "SELECT id, razao_social FROM contratadas;")}

    occurrence_in_file = {}
    valid, duplicate, update, rejected, error_rows = [], [], [], [], []

    for raw in raw_rows:
        try:
            m = XI.map_row(raw)
        except Exception as e:  # linha com dado corrompido/inesperado
            error_rows.append({"linha": raw.get("_linha"), "erro": f"Falha ao interpretar a linha: {e}"})
            continue

        if not m["numeroEmissao"] and not m["unidade"] and not m["contrato"]:
            continue  # linha vazia / decorativa — nunca é importada nem contada como erro

        faltando = [campo for campo, chave in (("nº Emissão", "numeroEmissao"), ("Unidade", "unidade"), ("Contrato", "contrato")) if not m[chave]]
        if faltando:
            rejected.append({**m, "motivo": "Campos obrigatórios ausentes: " + ", ".join(faltando)})
            continue

        if m["unidade"].strip().lower() != sede["sigla"].strip().lower():
            rejected.append({**m, "motivo": f"Unidade da planilha ('{m['unidade']}') não corresponde à SEDE selecionada ('{sede['sigla']}')."})
            continue

        m["statusAtual"] = XI.normalize_status(m["situacaoRaw"])
        # Normaliza a descrição (mesmo texto de reserva usado na gravação)
        # ANTES de comparar com o banco, para que uma célula vazia na
        # planilha não seja lida como "alteração" frente ao texto de
        # reserva gravado em uma importação anterior.
        if not m["descricao"]:
            m["descricao"] = f"Importado da planilha ({m['contrato']} / {m['contratada'] or '—'})."
        base_key = _base_key(m["unidade"], m["numeroEmissao"], m["contrato"])
        occurrence = occurrence_in_file.get(base_key, 0) + 1
        occurrence_in_file[base_key] = occurrence
        m["ocorrenciaPlanilha"] = occurrence
        key = _key(m["unidade"], m["numeroEmissao"], m["contrato"], occurrence)
        avisos = []

        contrato_row = contratos_sede.get(m["contrato"].strip().lower())
        if not contrato_row and m["contrato"] in aux_contratos:
            avisos.append("Contrato será cadastrado automaticamente a partir da aba 'Banco de Dados Contrato'.")
        elif not contrato_row:
            avisos.append("Contrato não localizado no sistema — registro será importado sem vínculo de contrato.")
        m["avisos"] = avisos
        m["contratoEncontrado"] = bool(contrato_row)

        existing = existing_idx.get(key)
        if existing:
            mudou = (
                existing.get("status_atual") != m["statusAtual"]
                or (existing.get("descricao") or "") != m["descricao"]
                or _differs(existing.get("valor_retencao_proposto"), m["valorRetencaoProposto"])
                or _differs(existing.get("valor_retencao_efetivo"), m["valorRetencaoEfetivo"])
            )
            if mudou:
                # O PostgreSQL devolve colunas UUID como ``uuid.UUID``. O
                # payload da prévia vai para JSONB e para o navegador.
                m["ncIdExistente"] = str(existing["id"])
                update.append(m)
            else:
                duplicate.append({**m, "motivo": "Já importado anteriormente, sem alterações."})
            continue

        valid.append(m)

    import_id = str(uuid.uuid4())
    # Na sincronização exclusiva pelo caminho local, estes registros podem
    # ser removidos na confirmação. A lista é calculada na prévia para que o
    # usuário saiba exatamente quantos itens deixarão de existir.
    file_keys = {
        _key(
            item.get("unidade"), item.get("numeroEmissao"), item.get("contrato"),
            item.get("ocorrenciaPlanilha") or 1,
        )
        for item in valid + update + duplicate
        if item.get("unidade") and item.get("numeroEmissao") and item.get("contrato")
    }
    remove = []
    for current in db.fetchall(f"""
        SELECT id, codigo_formatado, unidade_planilha, numero_emissao_planilha, contrato_planilha_raw,
               COALESCE(planilha_ocorrencia, 1) AS planilha_ocorrencia
        FROM ncs WHERE sede_id = {db.lit(sede_id)};
    """):
        current_key = _key(
            current.get("unidade_planilha"),
            current.get("numero_emissao_planilha"),
            current.get("contrato_planilha_raw"),
            current.get("planilha_ocorrencia") or 1,
        )
        if current_key not in file_keys:
            remove.append({"id": str(current["id"]), "codigo": current.get("codigo_formatado") or ""})

    payload = {
        "sedeId": sede_id, "filename": file.filename, "sheetName": sheet_name,
        "valid": valid, "update": update, "duplicate": duplicate, "rejected": rejected,
        "error": error_rows, "remove": remove,
    }
    db.execute(f"""
        INSERT INTO import_logs (id, sede_id, user_id, user_nome, filename, sheet_name, status,
                                  total_rows, valid_count, duplicate_count, update_count, rejected_count, error_count,
                                  header_mapping, preview_payload)
        VALUES ({db.lit(import_id)}, {db.lit(sede_id)}, {db.lit(g.user['id'])}, {db.lit(g.user['nome'])},
                {db.lit(file.filename)}, {db.lit(sheet_name)}, 'preview',
                {db.lit(len(raw_rows))}, {db.lit(len(valid))}, {db.lit(len(duplicate))}, {db.lit(len(update))},
                {db.lit(len(rejected))}, {db.lit(len(error_rows))},
                {db.json_lit(header_mapping)}, {db.json_lit(payload)});
    """)
    audit.log(g.user, "import.preview", "import_logs", import_id,
              {"filename": file.filename, "total": len(raw_rows)}, get_client_ip())

    def trim(lst, n=500):
        return lst[:n]

    return jsonify({
        "importId": import_id, "sheetName": sheet_name, "headerMapping": header_mapping,
        "totalRows": len(raw_rows),
        "counts": {"validos": len(valid), "duplicados": len(duplicate), "atualizacoes": len(update),
                   "rejeitados": len(rejected), "erros": len(error_rows), "remocoes": len(remove)},
        "rows": {"validos": trim(valid), "duplicados": trim(duplicate), "atualizacoes": trim(update),
                 "rejeitados": trim(rejected), "erros": trim(error_rows), "remocoes": trim(remove)},
    })


@bp.post("/import/preview-local")
@login_required
@csrf_required
@permission_required(perm.pode_configurar)
def import_preview_local():
    body = request.get_json(silent=True) or {}
    sede_id = body.get("sedeId")
    caminho = os.path.expandvars(os.path.expanduser((body.get("caminho") or "").strip()))
    if not sede_id or not _sede_row(sede_id):
        return jsonify(error="SEDE inválida."), 400
    if not caminho or not os.path.isabs(caminho):
        return jsonify(error="Informe o caminho completo da planilha."), 400
    if not caminho.lower().endswith(ALLOWED_EXTS):
        return jsonify(error="Formato não suportado. Use .xlsx, .xlsm ou .xls."), 400
    if not os.path.isfile(caminho):
        return jsonify(error="Planilha não encontrada nesse caminho."), 404
    if os.path.getsize(caminho) > MAX_FILE_MB * 1024 * 1024:
        return jsonify(error=f"Arquivo excede o limite de {MAX_FILE_MB}MB."), 400
    with open(caminho, "rb") as stream:
        file_bytes = stream.read()
    req = request._get_current_object()
    req.__dict__["form"] = ImmutableMultiDict({"sedeId": sede_id})
    req.__dict__["files"] = ImmutableMultiDict({"arquivo": FileStorage(stream=io.BytesIO(file_bytes), filename=os.path.basename(caminho))})
    return inspect.unwrap(import_preview)()

def _differs(a, b):
    if a is None and b is None:
        return False
    try:
        return round(float(a or 0), 2) != round(float(b or 0), 2)
    except (TypeError, ValueError):
        return str(a) != str(b)


@bp.get("/import/<import_id>/erros.csv")
@login_required
@permission_required(perm.pode_configurar)
def import_error_report(import_id):
    row = db.fetchone(f"SELECT * FROM import_logs WHERE id = {db.lit(import_id)};")
    if not row:
        return jsonify(error="Importação não encontrada."), 404
    payload = row.get("preview_payload") or {}
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Linha", "Unidade", "nº Emissão", "Contrato", "Contratada", "Categoria", "Motivo"])
    for r in (payload.get("rejeitados") or payload.get("rejected") or []):
        writer.writerow([r.get("linha"), r.get("unidade"), r.get("numeroEmissao"), r.get("contrato"),
                          r.get("contratada"), r.get("categoria"), r.get("motivo")])
    for r in (payload.get("erros") or payload.get("error") or []):
        writer.writerow([r.get("linha"), "", "", "", "", "", r.get("erro")])
    mem = io.BytesIO(buf.getvalue().encode("utf-8-sig"))
    return send_file(mem, mimetype="text/csv", as_attachment=True,
                      download_name=f"erros-importacao-{import_id[:8]}.csv")


@bp.post("/import/<import_id>/confirmar")
@login_required
@csrf_required
@permission_required(perm.pode_configurar)
def import_confirmar(import_id):
    body = request.get_json(silent=True) or {}
    aplicar_atualizacoes = bool(body.get("aplicarAtualizacoes", True))
    somente_planilha = bool(body.get("somentePlanilha", False))

    row = db.fetchone(f"SELECT * FROM import_logs WHERE id = {db.lit(import_id)};")
    if not row:
        return jsonify(error="Importação não encontrada."), 404
    if row["status"] != "preview":
        return jsonify(error="Esta importação já foi confirmada anteriormente."), 409

    payload = row["preview_payload"] or {}
    sede_id = payload["sedeId"]
    sede = _sede_row(sede_id)
    valid_rows = payload.get("valid") or []
    update_rows = (payload.get("update") or []) if aplicar_atualizacoes else []
    remove_rows = (payload.get("remove") or []) if somente_planilha else []
    aux_contratos = {}
    try:
        # o arquivo original não é mantido em disco entre preview e confirmação
        # (não persistimos uploads brutos por padrão) — o vínculo de contrato já
        # resolvido/planejado na prévia (avisos) é reaplicado a partir do payload.
        pass
    except Exception:
        pass

    # 1) garante contratos/contratadas referenciados (idempotente, fora da
    #    transação principal — criação de catálogo não é destrutiva).
    contrato_cache = {}
    for m in valid_rows + update_rows:
        numero = m["contrato"].strip()
        key = numero.lower()
        if key in contrato_cache:
            continue
        existing = db.fetchone(f"SELECT id FROM contratos WHERE sede_id = {db.lit(sede_id)} AND lower(numero) = {db.lit(key)};")
        if existing:
            contrato_cache[key] = existing["id"]
            continue
        if not m.get("contratoEncontrado"):
            contratada_id = None
            if m.get("contratada"):
                crow = db.fetchone(f"SELECT id FROM contratadas WHERE lower(razao_social) = {db.lit(m['contratada'].strip().lower())};")
                if not crow:
                    crow = db.fetchone(f"INSERT INTO contratadas (razao_social) VALUES ({db.lit(m['contratada'].strip())}) ON CONFLICT DO NOTHING RETURNING id;")
                    if not crow:
                        crow = db.fetchone(f"SELECT id FROM contratadas WHERE lower(razao_social) = {db.lit(m['contratada'].strip().lower())};")
                contratada_id = crow["id"] if crow else None
            newc = db.fetchone(f"""
                INSERT INTO contratos (sede_id, numero, descricao_obra)
                VALUES ({db.lit(sede_id)}, {db.lit(numero)}, {db.lit('Criado automaticamente na importação de ' + row['filename'])})
                ON CONFLICT (sede_id, numero) DO UPDATE SET numero = EXCLUDED.numero
                RETURNING id;
            """)
            contrato_cache[key] = newc["id"]
            if contratada_id:
                db.execute(f"INSERT INTO contrato_contratadas (contrato_id, contratada_id) VALUES ({db.lit(newc['id'])}, {db.lit(contratada_id)}) ON CONFLICT DO NOTHING;")

    contratada_cache = {}

    def resolve_contratada(nome):
        if not nome:
            return None
        key = nome.strip().lower()
        if key in contratada_cache:
            return contratada_cache[key]
        r = db.fetchone(f"SELECT id FROM contratadas WHERE lower(razao_social) = {db.lit(key)};")
        if not r:
            r = db.fetchone(f"INSERT INTO contratadas (razao_social) VALUES ({db.lit(nome.strip())}) ON CONFLICT DO NOTHING RETURNING id;")
            if not r:
                r = db.fetchone(f"SELECT id FROM contratadas WHERE lower(razao_social) = {db.lit(key)};")
        contratada_cache[key] = r["id"] if r else None
        return contratada_cache[key]

    # 2) monta o script de inserção/atualização das NCs em uma única transação.
    statements = []
    for m in valid_rows:
        contrato_id = contrato_cache.get(m["contrato"].strip().lower())
        contratada_id = resolve_contratada(m["contratada"])
        nc_id = str(uuid.uuid4())
        cols = {
            "id": nc_id, "sede_id": sede_id, "tipo_core": "NC", "contrato_id": contrato_id,
            "contratada_id": contratada_id, "codigo_formatado": m["numeroEmissao"],
            "data_emissao": m["dataEmissao"], "responsavel_emissao_nome": g.user["nome"],
            "categoria": m["categoria"] or None, "disciplina": m["disciplina"] or None,
            "classificacao": m["classificacao"], "descricao": m["descricao"] or f"Importado da planilha ({m['contrato']} / {m['contratada']}).",
            "valor_retencao_proposto": m["valorRetencaoProposto"], "valor_retencao_efetivo": m["valorRetencaoEfetivo"],
            "prazo_resposta": (m["prazoResposta"] + "T00:00:00") if m["prazoResposta"] else None,
            "status_atual": m["statusAtual"], "origem": "importacao", "import_id": import_id,
            "numero_emissao_planilha": m["numeroEmissao"], "unidade_planilha": m["unidade"],
            "contrato_planilha_raw": m["contrato"], "situacao_planilha_raw": m["situacaoRaw"],
            "planilha_ocorrencia": m.get("ocorrenciaPlanilha") or 1,
            "tipo_planilha_raw": m["tipoRaw"], "rodovia": m["rodovia"] or None,
            "km_inicial": m["kmInicial"], "km_final": m["kmFinal"],
            "data_encerramento": (m["dataEncerramento"] + "T00:00:00") if m["dataEncerramento"] else None,
            "created_by": g.user["id"], "updated_by": g.user["id"],
        }
        resposta = {}
        if m.get("propostaAcao"):
            resposta["planoDeAcao"] = m["propostaAcao"]
            resposta["disposicaoSolicitada"] = ""
        avaliacao = {}
        if m.get("parecerSupervisao"):
            avaliacao["parecerTecnico"] = m["parecerSupervisao"]
            disp = XI.normalize_disposicao(m["parecerSupervisao"])
            if disp:
                avaliacao["disposicaoStatus"] = disp
        if m.get("eficaciaRaw"):
            ef = XI.normalize_eficacia(m["eficaciaRaw"])
            if ef:
                avaliacao["resultadoEficacia"] = ef
        if resposta:
            cols["resposta_contratada"] = resposta
        if avaliacao:
            cols["avaliacao_concessionaria"] = avaliacao

        collist = ", ".join(cols.keys())
        vallist = ", ".join(db.lit(v) if not isinstance(v, dict) else db.json_lit(v) for v in cols.values())
        statements.append(f"INSERT INTO ncs ({collist}) VALUES ({vallist});")
        statements.append(f"""
            INSERT INTO nc_historico (nc_id, usuario_id, usuario_nome, status_anterior, status_novo, comentario)
            VALUES ({db.lit(nc_id)}, {db.lit(g.user['id'])}, {db.lit(g.user['nome'])}, NULL, {db.lit(m['statusAtual'])},
                    {db.lit('Importado da planilha ' + row['filename'] + ' (' + m['contrato'] + ' / ' + (m['contratada'] or '—') + ').')});
        """)

    for m in update_rows:
        nc_id = m["ncIdExistente"]
        set_parts = [
            f"status_atual = {db.lit(m['statusAtual'])}",
            f"descricao = {db.lit(m['descricao'] or None)}",
            f"valor_retencao_proposto = {db.lit(m['valorRetencaoProposto'])}",
            f"valor_retencao_efetivo = {db.lit(m['valorRetencaoEfetivo'])}",
            f"situacao_planilha_raw = {db.lit(m['situacaoRaw'])}",
            f"import_id = {db.lit(import_id)}",
            f"updated_by = {db.lit(g.user['id'])}",
        ]
        statements.append(f"UPDATE ncs SET {', '.join(set_parts)} WHERE id = {db.lit(nc_id)};")
        statements.append(f"""
            INSERT INTO nc_historico (nc_id, usuario_id, usuario_nome, status_anterior, status_novo, comentario)
            VALUES ({db.lit(nc_id)}, {db.lit(g.user['id'])}, {db.lit(g.user['nome'])}, NULL, {db.lit(m['statusAtual'])},
                    {db.lit('Atualizado por reimportação da planilha ' + row['filename'] + '.')});
        """)

    if remove_rows:
        remove_ids = [str(item.get("id") or "") for item in remove_rows if item.get("id")]
        if remove_ids:
            ids_sql = ", ".join(db.lit(item_id) for item_id in remove_ids)
            statements.append(
                f"DELETE FROM ncs WHERE sede_id = {db.lit(sede_id)} AND id IN ({ids_sql});"
            )

    statements.append(f"""
        UPDATE import_logs SET status = 'committed', finished_at = now()
        WHERE id = {db.lit(import_id)};
    """)

    if statements:
        db.execute_script(statements, single_transaction=True)
    else:
        db.execute(f"UPDATE import_logs SET status = 'committed', finished_at = now() WHERE id = {db.lit(import_id)};")

    cleanup_errors = []
    if remove_rows:
        upload_root = os.path.realpath(os.path.join(config.UPLOAD_DIR, "nc"))
        for item in remove_rows:
            nc_id = str(item.get("id") or "")
            expected_dir = os.path.realpath(os.path.join(upload_root, nc_id))
            try:
                if nc_id and os.path.commonpath([expected_dir, upload_root]) == upload_root and os.path.isdir(expected_dir):
                    shutil.rmtree(expected_dir)
            except (OSError, ValueError) as exc:
                cleanup_errors.append({"id": nc_id, "erro": str(exc)})

    audit.log(g.user, "import.confirm", "import_logs", import_id,
              {"validos": len(valid_rows), "atualizacoes": len(update_rows),
               "removidos": len(remove_rows), "falhasLimpeza": cleanup_errors}, get_client_ip())

    final = db.fetchone(f"SELECT * FROM import_logs WHERE id = {db.lit(import_id)};")
    result = ser.import_log_out(final)
    result["removedCount"] = len(remove_rows)
    result["cleanupComplete"] = not cleanup_errors
    return jsonify(result)


# -------------------------------------------------------------- export ---
@bp.get("/export/ncs.xlsx")
@login_required
def export_ncs():
    sede_id = request.args.get("sedeId")
    if not sede_id:
        return jsonify(error="Parâmetro sedeId é obrigatório."), 400
    sede = _sede_row(sede_id)
    if not sede:
        return jsonify(error="SEDE inválida."), 400

    where = [f"n.sede_id = {db.lit(sede_id)}"]
    if request.args.get("contratoId"):
        where.append(f"n.contrato_id = {db.lit(request.args['contratoId'])}")
    if request.args.get("status"):
        where.append(f"n.status_atual = {db.lit(request.args['status'])}")
    if request.args.get("dataInicio"):
        where.append(f"n.data_emissao >= {db.lit(request.args['dataInicio'])}::date")
    if request.args.get("dataFim"):
        where.append(f"n.data_emissao <= {db.lit(request.args['dataFim'])}::date")

    rows = db.fetchall(f"""
        SELECT n.*, c.numero AS contrato_numero, k.razao_social AS contratada_nome
        FROM ncs n
        LEFT JOIN contratos c ON c.id = n.contrato_id
        LEFT JOIN contratadas k ON k.id = n.contratada_id
        WHERE {' AND '.join(where)}
        ORDER BY n.data_emissao DESC NULLS LAST, n.created_at DESC;
    """)
    xlsx_bytes = XE.build_export(rows, sede["sigla"])
    audit.log(g.user, "export.ncs", "ncs", None, {"sedeId": sede_id, "total": len(rows)}, get_client_ip())
    mem = io.BytesIO(xlsx_bytes)
    return send_file(mem, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                      as_attachment=True, download_name=f"export-{sede['sigla']}-{datetime.date.today().isoformat()}.xlsx")


# ---------------------------------------------------- aliases de cabeçalho
@bp.get("/header-aliases")
@login_required
@permission_required(perm.pode_configurar)
def list_header_aliases():
    rows = db.fetchall("SELECT * FROM header_aliases ORDER BY campo_sistema, alias;")
    return jsonify([{"id": r["id"], "campoSistema": r["campo_sistema"], "alias": r["alias"], "sedeId": r.get("sede_id")} for r in rows])


@bp.post("/header-aliases")
@login_required
@csrf_required
@permission_required(perm.pode_configurar)
def create_header_alias():
    body = request.get_json(silent=True) or {}
    campo = (body.get("campoSistema") or "").strip()
    alias = (body.get("alias") or "").strip()
    if not campo or not alias:
        return jsonify(error="Informe o campo do sistema e o alias."), 400
    sede_id = body.get("sedeId") or None
    row = db.fetchone(f"""
        INSERT INTO header_aliases (campo_sistema, alias, sede_id) VALUES ({db.lit(campo)}, {db.lit(alias)}, {db.lit(sede_id)})
        ON CONFLICT DO NOTHING RETURNING *;
    """)
    if not row:
        return jsonify(error="Este alias já existe para este campo/SEDE."), 409
    audit.log(g.user, "header_alias.create", "header_aliases", row["id"], body, get_client_ip())
    return jsonify({"id": row["id"], "campoSistema": row["campo_sistema"], "alias": row["alias"], "sedeId": row.get("sede_id")}), 201
