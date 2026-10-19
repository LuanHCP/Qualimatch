"""Regras de numeração e prazo — espelham exatamente App.gerarCodigo /
App.util.addDias / App.proximoNumero do frontend original (assets/js/app.js),
agora como fonte da verdade no backend."""
import datetime

import db

TIPO_LABEL_PADRAO = {"NC": "RNC", "AC": "RACP"}


def tipo_label(sede, tipo_core):
    nomenclatura = {"NC": sede.get("nomenclatura_nc"), "AC": sede.get("nomenclatura_ac")}
    return nomenclatura.get(tipo_core) or TIPO_LABEL_PADRAO.get(tipo_core, tipo_core)


def proximo_numero(sede_id, tipo_core, ano):
    row = db.fetchone(f"""
        SELECT count(*) AS n FROM ncs
        WHERE sede_id = {db.lit(sede_id)} AND tipo_core = {db.lit(tipo_core)} AND ano = {db.lit(ano)}
              AND origem = 'manual';
    """)
    return int(row["n"]) + 1


def gerar_codigo(sede, tipo_core, seq, ano):
    label = tipo_label(sede, tipo_core)
    mask = sede.get("mascara_numeracao") or "{SIGLA}_{TIPO}_{SEQ}_{ANO}"
    seq_str = str(seq).zfill(3)
    return (mask.replace("{SIGLA}", sede.get("sigla") or "")
                .replace("{TIPO}", label)
                .replace("{SEQ}", seq_str)
                .replace("{ANO}", str(ano)))


def add_dias(data_iso, dias, dias_uteis):
    d = datetime.date.fromisoformat(data_iso[:10])
    if not dias_uteis:
        d = d + datetime.timedelta(days=dias)
        return datetime.datetime.combine(d, datetime.time(0, 0)).isoformat() + "Z"
    added = 0
    while added < dias:
        d = d + datetime.timedelta(days=1)
        if d.weekday() < 5:
            added += 1
    return datetime.datetime.combine(d, datetime.time(0, 0)).isoformat() + "Z"


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
