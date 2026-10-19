# Validação — QualiMatch v3.8.0

## Automatizada

- **117 testes aprovados** (`python -m pytest -q`).
- `python -m py_compile app.py qualimatch/*.py`: aprovado.
- `node --check frontend/static/app.js`: aprovado.

## Testes específicos adicionados na v3.8.0

- migração/permissões VIEWER → EDITOR → ADMIN;
- classificação da Pendência BV em PENDENTE CONTRATADA / NO PRAZO / PENDENTE CERTIFICADO;
- consolidação M14 e percentuais de cobertura;
- rastreabilidade Medição → Kit → Certificado;
- busca global limitada ao escopo Arena/Pavidez do usuário;
- registro e desfazer de alteração de kit em banco temporário;
- geração e abertura do relatório XLSX de Medição;
- restauração SQLite com backup de segurança;
- presença das novas telas/controles no frontend.

## Smoke test com a base empacotada

- 5.917 medições disponíveis;
- 765 certificados ativos;
- Gestão Mxx retornou ciclos reais da base;
- Central de Revisões retornou dados reais e avisos agrupados por certificado;
- Rastreabilidade executada sobre uma medição real;
- relatório de Medição foi gerado e reaberto como XLSX válido;
- Saúde do sistema detectou corretamente fontes locais indisponíveis no ambiente de desenvolvimento.

> A base empacotada não contém os kits do PostgreSQL do usuário. Ao copiar o `.env`, a aplicação usa a base PostgreSQL real, onde os kits sincronizados permanecem.
