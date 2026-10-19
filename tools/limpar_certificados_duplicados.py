"""Limpeza de certificados duplicados (mesma contratada + mesmo número).

Identifica grupos de certificados com a mesma contratada + mesmo número de
BI330 com mais de um registro ATIVO — o resultado do bug de identidade já
corrigido em local_sync.py — e mantém apenas o mais recente de cada grupo,
desativando os demais pela mesma "exclusão lógica" que o resto do sistema
já usa (histórico e PDF preservados; nada é apagado do disco nem do banco).

Por padrão só MOSTRA o que seria feito (modo simulação, não muda nada).
Para aplicar de verdade:

    python tools/limpar_certificados_duplicados.py --aplicar

Opcionalmente restrinja a uma contratada:

    python tools/limpar_certificados_duplicados.py --contratada ARENA --aplicar

Faz backup completo do banco antes de aplicar qualquer mudança (o mesmo
mecanismo usado antes de excluir/substituir um certificado manualmente pela
tela). Se, dentro de um grupo, o certificado mais recente não tiver um PDF
válido no caminho salvo mas um mais antigo tiver, o grupo é PULADO e listado
à parte para revisão manual — não decide sozinho contra o arquivo existir.
"""
import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qualimatch.database import init_db, rows, automatic_backup
from qualimatch.local_sync import deactivate_certificate
from qualimatch.matching import recalculate_matches


def identificar_grupos(contratada_filtro: str) -> dict:
    todos = rows(
        "SELECT * FROM certificates WHERE is_active=1 ORDER BY contractor, number, parsed_at DESC, id DESC"
    )
    grupos = defaultdict(list)
    for c in todos:
        c = dict(c)
        if contratada_filtro != "ALL" and c["contractor"] != contratada_filtro:
            continue
        grupos[(c["contractor"], c["number"])].append(c)
    # já vem ordenado por parsed_at/id DESC dentro de cada grupo, graças ao ORDER BY acima
    return {chave: linhas for chave, linhas in grupos.items() if len(linhas) > 1}


def tem_arquivo_valido(cert: dict) -> bool:
    caminho = cert.get("file_path") or ""
    return bool(caminho) and Path(caminho).exists()


def main():
    parser = argparse.ArgumentParser(description="Limpa certificados duplicados (mesma contratada + número).")
    parser.add_argument("--aplicar", action="store_true",
                         help="Aplica de verdade. Sem essa flag, só mostra o que seria feito.")
    parser.add_argument("--contratada", default="ALL", choices=["ALL", "ARENA", "PAVIDEZ"])
    args = parser.parse_args()

    init_db()
    grupos = identificar_grupos(args.contratada)

    if not grupos:
        print("Nenhum grupo de certificados duplicados (mesma contratada + número, mais de um ativo) encontrado.")
        return

    print(f"{len(grupos)} grupo(s) de certificados duplicados encontrado(s):\n")

    precisa_revisao = []
    plano = []  # lista de (manter, [desativar...])

    for (contratada, numero), linhas in grupos.items():
        print(f"--- {contratada} / {numero} ({len(linhas)} registros ativos) ---")
        for c in linhas:
            arquivo_ok = "OK" if tem_arquivo_valido(c) else "ARQUIVO NÃO ENCONTRADO"
            print(f"   id={c['id']:<6} parsed_at={c['parsed_at']:<20} rodovia={(c.get('road') or '—'):<15} "
                  f"km {c.get('kmi')}-{c.get('kmf')}  data_serviço={(c.get('service_date') or '—'):<12} arquivo={arquivo_ok}")

        candidato = linhas[0]  # mais recente (parsed_at/id DESC)
        if not tem_arquivo_valido(candidato) and any(tem_arquivo_valido(x) for x in linhas[1:]):
            print("   >>> ATENÇÃO: o mais recente não tem PDF válido no caminho salvo, mas um mais antigo tem.\n"
                  "       Não decidi sozinho — este grupo foi PULADO para revisão manual. <<<")
            precisa_revisao.append((contratada, numero))
            print()
            continue

        manter = candidato
        desativar = linhas[1:]
        plano.append((manter, desativar))
        print(f"   => manter id={manter['id']} (mais recente); desativar {len(desativar)} registro(s) mais antigo(s)")
        print()

    total_desativar = sum(len(d) for _, d in plano)
    print(f"Resumo: manter {len(plano)} certificado(s); desativar {total_desativar} registro(s) duplicado(s) mais antigos.")
    if precisa_revisao:
        print(f"{len(precisa_revisao)} grupo(s) PULADO(S), precisam de revisão manual: "
              + ", ".join(f"{c}/{n}" for c, n in precisa_revisao))

    if not args.aplicar:
        print("\nModo simulação — nada foi alterado. Rode de novo com --aplicar para executar de verdade.")
        return

    if total_desativar == 0:
        print("\nNada a aplicar.")
        return

    print("\nFazendo backup completo do banco antes de aplicar...")
    nome_backup = automatic_backup("limpeza_duplicados", 0)
    print(f"Backup criado: {nome_backup}")

    contratadas_afetadas = set()
    for manter, desativar in plano:
        for c in desativar:
            motivo = f"DUPLICADO - SUBSTITUIDO POR CERTIFICADO MAIS RECENTE (ID {manter['id']})"
            deactivate_certificate(c["id"], motivo)
            contratadas_afetadas.add(c["contractor"])
            print(f"   desativado id={c['id']} ({c['contractor']}/{c['number']})")

    for contratada in contratadas_afetadas:
        recalculate_matches(contratada)
        print(f"Matching recalculado para {contratada}.")

    print(f"\n=== Concluído: {total_desativar} certificado(s) duplicado(s) desativado(s), "
          f"{len(plano)} mantido(s) como versão atual. Backup salvo como {nome_backup}. ===")


if __name__ == "__main__":
    main()
