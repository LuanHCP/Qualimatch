# Validação v3.6.0

- 70 testes automatizados aprovados.
- Python compilado sem erros.
- JavaScript validado com `node --check`.
- `BD_ARENA_FRESA(1).xlsx`: 428 kits lidos; 373 possuem Data Recebimento, mas **Recebidos = 428** pela nova regra de linhas preenchidas.
- Status geral da amostra: 406 OK, 20 INCOMPLETO, 2 PENDENTE.
- Controles OK da amostra: 1=426/428; 2=426/428; 3=422/428; 4=414/428; 5=426/428; 6=417/428; 7=417/428; 8=29/338 aplicáveis; SIN.-Retro=75/428.
- Navegador de pastas usa os documentos já indexados pela fonte Documentos dos Kits e não duplica arquivos.
- Endpoint `/api/contractor/pending` reutiliza diretamente `pending_days`, preservando a regra validada da BV.
