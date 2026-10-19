# Validação v3.7.2

- 96 testes automatizados aprovados.
- `python -m compileall`: OK.
- `node --check frontend/static/app.js`: OK.
- Importação do FastAPI: versão 3.7.2 carregada; endpoints de edição registrados.
- Revisão manual da ferramenta: `REVISAR` expõe candidatos e override transforma o vínculo em `VINCULADO`.
- Edição manual: status de VV/espessura pode sobrescrever o cálculo exibido quando explicitamente definido.
- Segurança do Excel mantida: novas linhas são anexadas ao fim da tabela; atualização de certificados existentes permanece in-place; original nunca é sobrescrito pela ferramenta.
