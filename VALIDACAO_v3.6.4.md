# Validação — QualiMatch v3.6.4

## Escopo
- Gráfico mensal de entregas da Contratada.
- Linha de meta baseada em dias reais de medição por mês.
- Filtros de Kits simplificados e corrigidos.

## Regras validadas
- Entregas são agrupadas por `receipt_date` no formato AAAA-MM.
- Meta mensal considera dias distintos de `measurements.date` por contratada.
- Situações disponíveis: `OK`, `INCOMPLETO`, `PENDENTE`.
- Períodos disponíveis: `DIURNO`, `NOTURNO`.
- Filtro Serviço removido da interface.
- Rodovias são buscadas diretamente via `SELECT DISTINCT road FROM kit_rows`.
- `loadKitFilterOptions()` roda ao entrar em Kits de ensaio, evitando o select de Rodovia vazio na primeira abertura.

## Amostra Arena enviada
A leitura de `BD_ARENA_FRESA(1).xlsx` identificou rodovias reais como `BR-376` e `BR-373`, confirmando que existem valores para alimentar o filtro.

## Testes
- 79 testes automatizados aprovados.
- `node --check frontend/static/app.js`: OK.
- `python -m compileall`: OK.
