# Validação v3.8.11

## Objetivo
Garantir compatibilidade do parser com revisões antigas e novas dos certificados BI330 da Bureau Veritas.

## Casos reais validados
- **BI330-0446 / PAVIDEZ / PR-323**: layout antigo, `Faixa adicional`, 6 CPs (4036–4041). Resultado: **CARREGADO**, 6/6 CPs.
- **BI330-0471 / PAVIDEZ / BR-369**: layout novo, `Faixa 1/2` e coluna adicional de VV com filme, 6 CPs (4279–4284). Resultado: **CARREGADO**, 6/6 CPs.

## Campos conferidos
Número do CP, data de aplicação, pista, faixa, estaca, posição, espessuras A/B, relação A/B, Rice (Gmm), Gmb e Volume de Vazios (%).

## Regressão
`pytest -q tests/test_pdf_parser.py tests/test_real_variants.py tests/test_rice_gmm_v327.py` → **10 passed**.

## Banco de dados
A correção é exclusiva do parser. Não exige alteração de schema nem migração.
