# Validação — QualiMatch v3.7.4

## Automatizada
- `pytest -q`: **103 testes aprovados**.
- `python -m py_compile`: app/auth/database/writer sem erros.
- `node --check frontend/static/app.js`: JavaScript válido.

## Gravação direta em XLSX real
Teste feito em **cópia temporária** de `BD.QUALIDADE_PAVIDEZ_v01(4).xlsx`, usando o PDF real `BI330-0468-PAVIDEZ_ICA_BR369_TR1537-10.07.26 (1)(1).pdf`.

Resultado:
- BI330-0468 reconhecido como pronto para atualização existente.
- **11 linhas atualizadas**.
- Linhas Excel confirmadas: **3550 a 3560**.
- Backup integral criado antes da troca.
- Arquivo principal temporário substituído e validado pelo hash esperado.

Nenhum arquivo original enviado pelo usuário foi alterado durante a validação.

## Isolamento Arena/Pavidez
Teste em banco SQLite temporário:
- usuário com `Contratada • Arena` recebe somente `ARENA`;
- pedido `contractor=ALL` é reduzido para `ARENA`;
- pedido explícito `PAVIDEZ` retorna HTTP 403;
- ADMIN continua com `ARENA` + `PAVIDEZ`.

## Observação sobre fórmulas
A escrita preserva as fórmulas da BD_QUALI e marca o workbook para recálculo automático. Fórmulas do Excel são recalculadas pelo Excel na próxima abertura do arquivo. O QualiMatch não substitui as fórmulas por valores fixos.
