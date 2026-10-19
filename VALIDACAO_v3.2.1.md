# Validação — QualiMatch v3.2.1

## Alterações validadas

- Alerta BV invertido conforme regra operacional: Recebimento em laboratório **anterior** à Data Ext. dos CPs.
- Recebimento posterior à extração não gera alerta BV.
- K exibido no cabeçalho da fase.
- Desvio padrão exibido imediatamente ao lado de VV médio.
- Parser permanece em 3.2.0 para não forçar reprocessamento desnecessário dos PDFs.

## Testes

- `pytest`: 37 testes aprovados.
- `py_compile`: OK.
- `node --check frontend/static/app.js`: OK.
- Base SQLite empacotada: 18 alertas BV em ARENA e 33 em PAVIDEZ pela nova condição.
