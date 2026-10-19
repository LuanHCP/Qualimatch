# Validação v3.7.5

- `pytest -q`: **108 passed**.
- `python -m py_compile app.py qualimatch/*.py`: OK.
- `node --check frontend/static/app.js`: OK.
- Teste unitário confirma fallback `receipt_date -> application_date` no gráfico Pavidez.
- Teste confirma normalização de rodovia e estacas na edição de kit.
- Sincronizador preserva linhas com `manual_override=1`.
- Consultas operacionais ignoram `is_active=0`.
