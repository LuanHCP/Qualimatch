"""
Regras de permissão — espelham exatamente assets/js/permissions.js do
frontend, mas aqui são a fonte da verdade: toda rota que altera dados
valida a permissão no backend, independente do que a interface envia.
"""

PERFIS = {
    "admin_geral": "Administrador geral",
    "admin_sede": "Administrador da SEDE",
    "qualidade": "Qualidade",
    "fiscalizacao": "Fiscalização / Engenharia",
    "gestor_contrato": "Gestor do contrato",
    "contratada": "Contratada",
    "consulta": "Consulta / Auditoria",
}

STATUS_GROUP = {
    "rascunho": "aberto", "emitida": "aberto", "protocolada": "aberto",
    "aguardando_resposta": "aberto", "respondida": "aberto", "em_analise": "aberto",
    "disposicao_aprovada": "aberto", "disposicao_recusada": "aberto",
    "em_execucao": "aberto", "aguardando_verificacao": "aberto",
    "eficaz": "encerrado", "nao_eficaz": "aberto", "encerrada": "encerrado",
}


def pode_emitir(perfil):
    return perfil in ("admin_geral", "admin_sede", "qualidade", "fiscalizacao")


def pode_responder(perfil):
    return perfil in ("contratada", "admin_geral")


def pode_avaliar(perfil):
    return perfil in ("admin_geral", "admin_sede", "qualidade", "fiscalizacao", "gestor_contrato")


def pode_configurar(perfil):
    return perfil in ("admin_geral", "admin_sede")


def pode_adm_usuarios(perfil):
    return perfil in ("admin_geral", "admin_sede")


def is_admin_geral(perfil):
    return perfil == "admin_geral"


def contratos_visiveis_perfis():
    return ("admin_geral", "admin_sede", "qualidade", "fiscalizacao", "consulta")
