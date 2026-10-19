# Validação v3.7.0 — Central de Ferramentas

## Testes automatizados
- 87 testes aprovados.
- `python -m py_compile app.py qualimatch/*.py`: OK.
- `node --check frontend/static/app.js`: OK.
- Rota `/api/admin/tools/pdf-quality/analyze`: registrada.

## Validação com os PDFs fornecidos para desenvolvimento
Foram processados 6 BI330 reais contra a base de Medições incluída no projeto:

- Total projetado: 65 linhas (CPs de rotina).
- 47 vínculos automáticos.
- 18 casos marcados para revisão.
- 0 CPs sem qualquer medição candidata na data.

Casos relevantes:
- BI330-0058 (Pavidez): 9 linhas esperadas, apesar de o PDF também conter 9 CPs de contra-prova. A contra-prova foi ligada aos mesmos CPs, sem gerar 18 linhas.
- BI330-0235 (Arena): 12 CPs → 12 linhas esperadas; os 12 localizaram medição.
- BI330-0346 (Pavidez): 17 CPs → 17 linhas esperadas. O PDF foi lido como BR-323 enquanto as medições compatíveis estão em PR-323; os 17 casos foram corretamente marcados como REVISAR, não gravados silenciosamente.
- BI330-0388 (Arena): 9 CPs distribuídos entre 14/07/2026 e 18/07/2026 → 9 vínculos automáticos; a Data Aplicação de cada CP foi usada individualmente.
- BI330-0468 (Pavidez): 11 CPs → 11 vínculos automáticos.
- Arquivo nomeado BI330-0060: o conteúdo interno do PDF apresenta BI330-0058; a ferramenta emite aviso de divergência de número.

## Conferência de mapeamento com BD_QUALI
Para BI330-0388, os valores projetados pela ferramenta coincidiram com a planilha de referência para Rice, VV médio, desvio padrão VV, Xmin/Xmax, total de CPs, média A/B, desvio de espessura, Xmin de espessura e status.

Para BI330-0058, os valores de rotina e contra-prova também coincidiram nos campos estatísticos. Quando a rotina reprova, a prévia prepara `P CONTRA PROVA` como status de rotina, preservando a lógica operacional da BD_QUALI; a fase de contra-prova recebe APROVADO/REPROVADO conforme o resultado final.

## Escopo propositalmente não implementado
A v3.7.0 é PREVIEW_ONLY. Ainda não insere/copía linhas no XLSX. A etapa seguinte deverá:
1. abrir uma cópia da planilha oficial;
2. duplicar linha-base da Medição para cada CP;
3. preservar fórmulas/estilos/tabela estruturada;
4. preencher somente os campos de entrada do certificado;
5. validar duplicidade e quantidade antes de salvar;
6. produzir arquivo novo ou, mediante confirmação, atualizar a fonte sincronizada.
