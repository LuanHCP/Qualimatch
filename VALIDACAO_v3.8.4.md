# Validação v3.8.4

- `pytest -q`: **132 testes aprovados**.
- Python: `py_compile` aprovado.
- JavaScript: `node --check` aprovado.
- Smoke test com BI330-0388 real colocado em `M14`: arquivo foi indexado em `bv_documents`, detectado como candidato BI330 e tratado como `DUPLICADO`, apontando para o certificado já existente ID 321, sem criar novo certificado.
- Smoke test de arquivamento: arquivo comum foi indexado, arquivado pelo banco e continuou oculto após nova sincronização, mesmo permanecendo fisicamente na pasta origem.
- Banco empacotado restaurado para a base limpa da v3.8.3 e migrado apenas com as novas colunas de compatibilidade; mantém 765 certificados.
