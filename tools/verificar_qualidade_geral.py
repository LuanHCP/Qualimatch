"""Verificação somente-leitura do módulo de Qualidade Geral (Traços + NCs).

Lê as planilhas a partir dos caminhos já configurados (os mesmos que a
aplicação usa) e imprime um resumo — útil para conferir rapidamente, pelo
terminal, se os números batem com o que a tela está mostrando, sem precisar
abrir o navegador.

Uso:
    python tools/verificar_qualidade_geral.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qualimatch.database import init_db
from qualimatch.general_quality import (
    _qg_path, _qg_load_nc, _qg_nc_summary,
    _qg_load_traces, _qg_trace_summary,
    _QG_NC_SETTING, _QG_NC_DEFAULT, _QG_TRACE_SETTING, _QG_TRACE_DEFAULT,
)

init_db()

print("=== Não Conformidades ===")
caminho_nc = _qg_path(_QG_NC_SETTING, _QG_NC_DEFAULT)
print(f"Fonte: {caminho_nc}")
if not caminho_nc.exists():
    print("  (arquivo não encontrado neste computador)")
else:
    itens = _qg_load_nc()
    resumo = _qg_nc_summary(itens)
    print(f"  RNCs lidas:      {len(itens)}")
    print(f"  Abertas:         {resumo['open']}")
    print(f"  Em tratamento:   {resumo['treatment']}")
    print(f"  Encerradas:      {resumo['closed']}")
    print(f"  Canceladas:      {resumo['cancelled']}")
    print(f"  RETENÇÃO:        R$ {resumo['proposed_retention']:,.2f}")
    print(f"  RETIDO DE FATO:  R$ {resumo['real_retained']:,.2f}")

print()
print("=== Traços ===")
caminho_tracos = _qg_path(_QG_TRACE_SETTING, _QG_TRACE_DEFAULT)
print(f"Fonte: {caminho_tracos}")
if not caminho_tracos.exists():
    print("  (arquivo não encontrado neste computador)")
else:
    itens = _qg_load_traces()
    resumo = _qg_trace_summary(itens)
    print(f"  Traços lidos:    {len(itens)}")
    print(f"  Aprovados:       {resumo['approved']}")
    print(f"  Vencidos:        {resumo['expired']}")
    print(f"  Vencendo em 30d: {resumo['expiring_30d']}")
