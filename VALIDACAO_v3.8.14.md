# Validação v3.8.14 — Auto-reparo do ambiente Python

## Problema corrigido
Ao atualizar o QualiMatch sobrescrevendo uma pasta já existente, uma pasta `.venv` antiga/incompleta podia permanecer. Se `.venv\Scripts\python.exe` existisse mas `.venv\pyvenv.cfg` não, o launcher tentava executar esse Python e o Windows retornava `failed to locate pyvenv.cfg`.

## Correção
`iniciar.bat` e `iniciar_preparar.bat` agora:
1. verificam a existência de `.venv\pyvenv.cfg`;
2. testam se o Python interno do venv consegue iniciar;
3. removem somente `.venv` quando o ambiente estiver inválido;
4. recriam o ambiente com o Python instalado no Windows;
5. reinstalam dependências quando necessário.

## Banco
Nenhum código de banco foi alterado. O arquivo `data/qualimatch.db` foi apenas transportado no pacote, sem migração ou edição.

## Parser
`PARSER_VERSION` permanece `3.8.13`, pois esta revisão é somente de inicialização/ambiente.
