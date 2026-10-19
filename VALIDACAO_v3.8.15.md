# Validação v3.8.15 — Bootstrap Python robusto

## Problema
Em alguns Windows, `instalar.bat` ainda podia exibir `failed to locate pyvenv.cfg` mesmo após apagar o `.venv` local. A causa é o `python` resolvido pelo `PATH` apontar para o executável de um ambiente virtual antigo, movido ou apagado.

## Correção
- variáveis `VIRTUAL_ENV`, `PYTHONHOME` e `PYTHONPATH` são limpas no bootstrap;
- interpretadores candidatos precisam ser Python 3.11+ e Python base (`sys.prefix == sys.base_prefix`);
- prioridade para `py -3.13`, `py -3.12`, `py -3.11` e `py -3`;
- busca por instalações absolutas comuns antes de usar `python` do PATH;
- WindowsApps e executáveis dentro de `.venv\\Scripts`/`venv\\Scripts` são ignorados;
- `.venv` inválido é removido e recriado;
- falha ao remover `.venv` interrompe a instalação para evitar estado parcial.

## Banco e parser
- `data/qualimatch.db` preservado sem leitura/escrita pela revisão.
- SHA-256 do banco no pacote: `30df10ae14d04e0b3cfe7f625c86ba4cbbf0ccbd0b964966fea7f0fd08cfeefe`.
- `PARSER_VERSION` permanece `3.8.13`.
