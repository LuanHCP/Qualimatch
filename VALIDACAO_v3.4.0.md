# Validação — QualiMatch v3.4.0 Kits da Contratada

Data: 17/08/2026

## Escopo

- Nova fonte `kits` para ARENA e PAVIDEZ.
- Leitura da aba `d.KIT` de XLSX local sincronizado pelo SharePoint/OneDrive.
- Persistência em `kit_rows` (SQLite/PostgreSQL).
- Portal Contratada com visão geral e tabela de Kits de ensaio.
- Administração → Sincronização com fonte `Tabela de Kits` e botão `Localizar`.
- Descoberta automática no primeiro sync quando o caminho ainda estiver vazio.

## Validação com a planilha fornecida

Arquivo usado somente para teste local: `BD_ARENA_FRESA(1).xlsx`.

- Aba detectada: `d.KIT`.
- Kits reais lidos: **428**.
- Linhas-formulário vazias no final: ignoradas corretamente.
- Status geral: **406 OK**, **20 INCOMPLETO**, **2 PENDENTE**.
- Sem Data Recebimento: **55**.
- Primeiro kit: #SEQ 1, FRESAGEM, 11/07/2025, BR-376, 552+240 a 552+990.
- Último kit: #SEQ 428, FRESAGEM, 04/08/2026, BR-376.
- Smoke test de sincronização local: **428 registros gravados em ~0,3 s**.

## Campos validados

`#SEQ`, `SERVIÇO`, `DATA APLICAÇÃO`, `PROJETO MISTURA`, `PERÍODO`, `RODOVIA`, `KM INICIAL`, `KM FINAL`, `DATA RECEBIMENTO`, `STATUS`, controles 1 a 8 e `SIN. - RETRO`.

A coluna `DUI` permanece preservada no `raw_json` da linha para uma futura evolução, mas não é exibida nesta primeira versão porque não foi solicitada na visão inicial.

## Regressão

- `pytest`: 60 testes aprovados.
- Python compilado sem erros.
- JavaScript validado com `node --check`.
- Banco fallback final não contém a planilha de teste importada; apenas a nova estrutura/fonte vazia. A operação real lê o arquivo local configurado no PC do servidor.
