"""Sedes, contratos, contratadas e textos padronizados.

Leitura: qualquer usuário autenticado (a visibilidade por SEDE é aplicada
no frontend/estado, mas nada aqui vaza dados de outras organizações —
trata-se de um único sistema multi-SEDE de uma mesma concessionária).
Escrita: exige permissão equivalente a App.perm.podeConfigurar() no
protótipo original (admin_geral ou admin_sede) — validada aqui no backend,
não apenas ocultando botões na interface.
"""
from flask import Blueprint, request, jsonify, g

import db
import audit
import permissions as perm
import serializers as ser
from auth_mw import login_required, csrf_required, permission_required, get_client_ip

bp = Blueprint("catalog", __name__, url_prefix="/api")


# --------------------------------------------------------------- sedes ----
@bp.get("/sedes")
@login_required
def list_sedes():
    rows = db.fetchall("SELECT * FROM sedes ORDER BY sigla;")
    return jsonify([ser.sede_out(r) for r in rows])


@bp.patch("/sedes/<sede_id>")
@login_required
@csrf_required
@permission_required(perm.pode_configurar)
def update_sede(sede_id):
    body = request.get_json(silent=True) or {}
    fields = {
        "sigla": body.get("sigla"), "nome": body.get("nome"), "razao_social": body.get("razaoSocial"),
        "logo_letra": body.get("logoLetra"), "cor_primaria": body.get("corPrimaria"), "cor_secundaria": body.get("corSecundaria"),
        "nomenclatura_nc": (body.get("nomenclatura") or {}).get("NC"),
        "nomenclatura_ac": (body.get("nomenclatura") or {}).get("AC"),
        "mascara_numeracao": body.get("mascaraNumeracao"), "prazo_padrao_dias": body.get("prazoPadraoDias"),
        "dias_uteis": body.get("diasUteis"), "encerramento_automatico_desconto": body.get("encerramentoAutomaticoComDesconto"),
        "planilha_local_path": body.get("planilhaLocalPath"),
        "areas": body.get("areas"), "disciplinas": body.get("disciplinas"), "classificacoes": body.get("classificacoes"),
    }
    set_clause = ", ".join(f"{k} = {db.lit(v)}" for k, v in fields.items() if v is not None)
    if not set_clause:
        return jsonify(error="Nenhum campo para atualizar."), 400
    db.execute(f"UPDATE sedes SET {set_clause} WHERE id = {db.lit(sede_id)};")
    audit.log(g.user, "sede.update", "sedes", sede_id, fields, get_client_ip())
    row = db.fetchone(f"SELECT * FROM sedes WHERE id = {db.lit(sede_id)};")
    return jsonify(ser.sede_out(row))


# ---------------------------------------------------------- contratadas ---
@bp.get("/contratadas")
@login_required
def list_contratadas():
    rows = db.fetchall("SELECT * FROM contratadas WHERE ativo ORDER BY razao_social;")
    return jsonify([ser.contratada_out(r) for r in rows])


@bp.post("/contratadas")
@login_required
@csrf_required
@permission_required(perm.pode_configurar)
def create_contratada():
    body = request.get_json(silent=True) or {}
    razao = (body.get("razaoSocial") or "").strip()
    if not razao:
        return jsonify(error="Informe a razão social."), 400
    row = db.fetchone(f"""
        INSERT INTO contratadas (razao_social, cnpj) VALUES ({db.lit(razao)}, {db.lit(body.get('cnpj') or None)})
        RETURNING *;
    """)
    audit.log(g.user, "contratada.create", "contratadas", row["id"], {"razaoSocial": razao}, get_client_ip())
    return jsonify(ser.contratada_out(row)), 201


# ------------------------------------------------------------ contratos ---
def _contrato_with_contratadas(row):
    ids = db.fetchall(f"SELECT contratada_id FROM contrato_contratadas WHERE contrato_id = {db.lit(row['id'])};")
    row = dict(row)
    row["contratada_ids"] = [x["contratada_id"] for x in ids]
    return row


@bp.get("/contratos")
@login_required
def list_contratos():
    sede_id = request.args.get("sedeId")
    where = f"WHERE sede_id = {db.lit(sede_id)}" if sede_id else ""
    rows = db.fetchall(f"SELECT * FROM contratos {where} ORDER BY numero;")
    return jsonify([ser.contrato_out(_contrato_with_contratadas(r)) for r in rows])


@bp.post("/contratos")
@login_required
@csrf_required
@permission_required(perm.pode_configurar)
def create_contrato():
    body = request.get_json(silent=True) or {}
    numero = (body.get("numero") or "").strip()
    sede_id = body.get("sedeId")
    if not numero or not sede_id:
        return jsonify(error="Informe SEDE e número do contrato."), 400
    row = db.fetchone(f"""
        INSERT INTO contratos (sede_id, numero, descricao_obra, vigencia_inicio, vigencia_fim)
        VALUES ({db.lit(sede_id)}, {db.lit(numero)}, {db.lit(body.get('descricaoObra'))},
                {db.lit(body.get('vigenciaInicio') or None)}::date, {db.lit(body.get('vigenciaFim') or None)}::date)
        RETURNING *;
    """)
    for cid in (body.get("contratadaIds") or []):
        db.execute(f"INSERT INTO contrato_contratadas (contrato_id, contratada_id) VALUES ({db.lit(row['id'])}, {db.lit(cid)}) ON CONFLICT DO NOTHING;")
    audit.log(g.user, "contrato.create", "contratos", row["id"], {"numero": numero}, get_client_ip())
    return jsonify(ser.contrato_out(_contrato_with_contratadas(row))), 201


@bp.patch("/contratos/<contrato_id>")
@login_required
@csrf_required
@permission_required(perm.pode_configurar)
def update_contrato(contrato_id):
    body = request.get_json(silent=True) or {}
    fields = {
        "numero": body.get("numero"), "descricao_obra": body.get("descricaoObra"),
        "vigencia_inicio": body.get("vigenciaInicio") or None,
        "vigencia_fim": body.get("vigenciaFim") or None,
    }
    set_clause = ", ".join(f"{k} = {db.lit(v)}" + ("::date" if k.startswith("vigencia_") and v else "") for k, v in fields.items() if v is not None)
    if set_clause:
        db.execute(f"UPDATE contratos SET {set_clause} WHERE id = {db.lit(contrato_id)};")
    if "contratadaIds" in body:
        db.execute(f"DELETE FROM contrato_contratadas WHERE contrato_id = {db.lit(contrato_id)};")
        for cid in (body.get("contratadaIds") or []):
            db.execute(f"INSERT INTO contrato_contratadas (contrato_id, contratada_id) VALUES ({db.lit(contrato_id)}, {db.lit(cid)}) ON CONFLICT DO NOTHING;")
    row = db.fetchone(f"SELECT * FROM contratos WHERE id = {db.lit(contrato_id)};")
    if not row:
        return jsonify(error="Contrato não encontrado."), 404
    audit.log(g.user, "contrato.update", "contratos", contrato_id, fields, get_client_ip())
    return jsonify(ser.contrato_out(_contrato_with_contratadas(row)))


# --------------------------------------------------------- textos padrão --
@bp.get("/textos")
@login_required
def list_textos():
    sede_id = request.args.get("sedeId")
    where = f"WHERE sede_id = {db.lit(sede_id)} OR sede_id IS NULL" if sede_id else ""
    rows = db.fetchall(f"SELECT * FROM textos_padrao {where} ORDER BY categoria, item;")
    return jsonify([ser.texto_out(r) for r in rows])


@bp.post("/textos")
@login_required
@csrf_required
@permission_required(perm.pode_configurar)
def create_texto():
    body = request.get_json(silent=True) or {}
    categoria = (body.get("categoria") or "").strip()
    item = (body.get("item") or "").strip()
    texto = (body.get("texto") or "").strip()
    if not categoria or not item or not texto:
        return jsonify(error="Informe categoria, item e texto."), 400
    sede_id = body.get("sedeId")
    sede_id = None if sede_id in (None, "GLOBAL", "") else sede_id
    row = db.fetchone(f"""
        INSERT INTO textos_padrao (sede_id, categoria, item, subitem, texto)
        VALUES ({db.lit(sede_id)}, {db.lit(categoria)}, {db.lit(item)}, {db.lit(body.get('subitem') or '')}, {db.lit(texto)})
        RETURNING *;
    """)
    audit.log(g.user, "texto.create", "textos_padrao", row["id"], {"categoria": categoria, "item": item}, get_client_ip())
    return jsonify(ser.texto_out(row)), 201


@bp.patch("/textos/<texto_id>")
@login_required
@csrf_required
@permission_required(perm.pode_configurar)
def update_texto(texto_id):
    body = request.get_json(silent=True) or {}
    fields = {"categoria": body.get("categoria"), "item": body.get("item"), "subitem": body.get("subitem"), "texto": body.get("texto")}
    set_clause = ", ".join(f"{k} = {db.lit(v)}" for k, v in fields.items() if v is not None)
    if not set_clause:
        return jsonify(error="Nenhum campo para atualizar."), 400
    db.execute(f"UPDATE textos_padrao SET {set_clause} WHERE id = {db.lit(texto_id)};")
    audit.log(g.user, "texto.update", "textos_padrao", texto_id, fields, get_client_ip())
    row = db.fetchone(f"SELECT * FROM textos_padrao WHERE id = {db.lit(texto_id)};")
    return jsonify(ser.texto_out(row))
