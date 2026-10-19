# QualiMatch v3.8.17 — Bootstrap Python Install Manager robusto

## Problema corrigido
Em alguns Windows 11 com o novo **Python Install Manager**, `py install 3.12` confirma que o Python 3.12.10 já está instalado, porém o processo de bootstrap não consegue validar imediatamente `py -3.12` ou o alias genérico `python.exe`.

O próprio manager informa que o runtime será exposto por aliases como `python3.12[-64].exe`. O runtime real normalmente fica em `%LocalAppData%\Python\pythoncore-3.12-64\python.exe`.

## Correção
- Prioriza o executável real do runtime gerenciado, sem depender de PATH ou alias.
- Procura `%LocalAppData%\Python\pythoncore-3.12*\python.exe` por wildcard.
- Procura aliases versionados, como `%LocalAppData%\Python\bin\python3.12.exe`.
- Mantém fallback para `py -3.12` e acrescenta `py -V:3.12`.
- Após `py install 3.12`, executa novamente toda a descoberta de runtime.
- Simplifica o probe de Python, evitando falso negativo por `sys.prefix == sys.base_prefix`.
- Mantém suporte a instalações clássicas do python.org.
- Nenhuma alteração de parser/BD_QUALI/schema.

## Banco
`data/qualimatch.db` preservado byte a byte em relação à v3.8.16.
SHA-256 esperado: `30df10ae14d04e0b3cfe7f625c86ba4cbbf0ccbd0b964966fea7f0fd08cfeefe`.

## Parser
`PARSER_VERSION` permanece `3.8.13`.
