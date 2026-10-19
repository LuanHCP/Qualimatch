# Validação v3.8.12

## Motivo da correção
O BI330-0093 usa uma variação antiga da planilha BV em que a célula **Data Aplicação** inclui o marcador da etapa imediatamente após a data (`09/10/2025-E3` / `09/10/2025-E1`). O parser anterior esperava espaço logo após a data e rejeitava todas as linhas de CP.

## Caso real validado
- **BI330-0093 / PAVIDEZ / BR-376**
- CPs esperados: 10
- CPs extraídos: **10** (736–743, 751–752)
- Status do parser: **CARREGADO**
- Data de aplicação normalizada: **09/10/2025**
- Rice: **2,671** nos 10 CPs
- Gmb e Vv conferidos com o PDF.

## Regressão real
- **BI330-0446**: CARREGADO, 6/6 CPs
- **BI330-0471**: CARREGADO, 6/6 CPs

## Testes
`pytest -q tests/test_pdf_parser.py tests/test_real_variants.py tests/test_rice_gmm_v327.py` → **12 passed**.

## Banco de dados
A alteração é exclusiva do parser e não requer migração de schema.
