# Validação v3.8.8

- 144 testes automatizados aprovados.
- `python -m py_compile` aprovado para app, runner e módulos QualiMatch.
- `node --check frontend/static/app.js` aprovado.
- Migração validada sobre cópia real do banco empacotado na v3.8.7: coluna `kit_rows.delivery_status` criada sem perda de dados.
- Escrita de espelho d.KIT validada com `delivery_status=Entregue`.
- Leitura de XLSX sintético com aba d.KIT e coluna `ENTREGA` validada.
- Smoke do Dashboard no banco empacotado: total de certificados = soma exata de Aprovados + Reprovados + Ajustes/sem resultado.
- BI330-0046 do banco de teste: rotina REPROVADO + contra-prova APROVADO => status final APROVADO, fase final CONTRA_PROVA.
