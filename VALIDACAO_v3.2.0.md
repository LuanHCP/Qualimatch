# Validação — QualiMatch v3.2.0

Data: 17/08/2026

## Testes automatizados

- `pytest -q`: **36 testes aprovados**.
- `python -m compileall`: sem erros.
- `node --check frontend/static/app.js`: sem erros.

## Base incluída

- Certificados ativos: **765**.
- Pendências Arena: **16**.
- Pendências Pavidez: **15**.
- Total de pendências: **31**.

## Leitura

A apresentação do status foi revisada:

- **CARREGADO**: todos os campos estruturais essenciais recuperados.
- **PARCIAL**: falta pelo menos um campo estrutural relevante.
- Avisos operacionais, como a regra de Data Rec. em Lab. posterior à Data Ext. dos CPs, aparecem separadamente e não alteram o status para PARCIAL.

Na base empacotada, a reavaliação atual identifica 172 certificados como CARREGADO e 593 como PARCIAL. A maior parte dos PARCIAIS antigos corresponde a registros que não possuem todos os dados técnicos/CPs armazenados na base e não a uma falha nova da v3.2.0.

## Regra BV

A regra foi implementada exatamente conforme o feedback recebido: quando pelo menos uma Data Rec. em Lab. é posterior à Data Ext. dos CPs, o detalhe do certificado mostra um alerta para envio/conferência com a BV.

Na base atual essa condição ocorre com frequência; recomenda-se validar a regra operacional em uso real caso o alerta apareça em certificados onde essa sequência de datas seja considerada normal.
