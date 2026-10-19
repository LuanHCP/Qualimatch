# Validação — QualiMatch v3.8.1

## Testes automatizados

- **122/122 testes aprovados**.
- `python -m py_compile app.py qualimatch/*.py`: aprovado.
- `node --check frontend/static/app.js`: aprovado.

## Smoke test real do monitor

Foi usado um banco SQLite temporário, sem alterar a base empacotada. O monitor recebeu simultaneamente:

1. um BI330 real na pasta de certificados ARENA;
2. a `BD_ARENA_FRESA(1).xlsx` como fonte `d.KIT`;
3. um PDF dentro de uma subpasta da árvore `Entrega Contratada`.

Resultado:

- 3 alterações detectadas;
- 3 processadas;
- 0 erros;
- 1 certificado BI330 carregado;
- 428 kits importados;
- 1 documento da Contratada indexado;
- eventos registrados como `BV / certificados / CARREGADO`, `CONTRATADA / kits / CARREGADO` e `CONTRATADA / kit_documentos / INDEXADO`.

## Comportamento offline

O monitor depende das pastas locais sincronizadas, portanto não roda durante suspensão/desligamento do PC. Ao iniciar novamente o QualiMatch, a comparação com o banco identifica arquivos que chegaram no SharePoint durante o período offline e faz o catch-up.
