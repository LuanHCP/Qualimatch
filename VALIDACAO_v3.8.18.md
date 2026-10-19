# QualiMatch v3.8.18 — Duplicados, Dashboard mensal e Contratada sem meta

## Escopo
Baseado na v3.8.17, sem alteração do parser BI330 ou do bootstrap Python.

## Validações executadas
- Limpeza em lote de duplicados testada em banco temporário: 2 cópias DUPLICADO arquivadas e 1 ocorrência original preservada.
- `certificate_files` das cópias removidas deixa de manter o status DUPLICADO, sem alterar o certificado canônico.
- Filtro por contratada preservado na API de limpeza.
- Interface contém atalho `Remover duplicados` e confirmação antes da ação.
- Dashboard expõe `financial_monthly` e renderiza a visão financeira por mês.
- Tendências financeiras dos cards comparam os dois meses mais recentes disponíveis.
- Gráfico da Contratada não contém mais linha de meta e exibe somente entregas mensais.

## Testes
- Testes focados relacionados: **10 aprovados**.
- Suíte completa: **159 aprovados e 1 falha externa**.
- A única falha depende do fixture `/mnt/data/BD.QUALIDADE_ARENA_v02(5).xlsx`, ausente no ambiente de validação; não está relacionada às alterações da v3.8.18.

## Banco
- `data/qualimatch.db` preservado sem alteração durante a montagem da versão.
- SHA-256 verificado: `30df10ae14d04e0b3cfe7f625c86ba4cbbf0ccbd0b964966fea7f0fd08cfeefe`.
- Nenhuma migração/schema novo necessário.

## Observação sobre "Remover duplicados"
A rotina remove os duplicados **da visualização/índice do QualiMatch**, mantendo o arquivo físico no SharePoint/OneDrive. Isso evita uma exclusão destrutiva em massa da fonte documental.
