# Validação v3.0.0

Validação local realizada antes do empacotamento:

- 30/30 testes automatizados existentes aprovados.
- `python -m compileall` aprovado para aplicação, módulos e ferramentas.
- Endpoints testados com SQLite de fallback: `/api/health`, `/api/dashboard`, `/api/certificates`, `/api/pending` e `/api/certificates-filter-options` retornando HTTP 200.
- Banco incluído preservou as contagens da v2.3.0:
  - measurements: 5917
  - quality_rows: 5941
  - certificates: 765
  - certificate_files: 949
  - certificate_samples: 3078
  - matches: 5917
- Certificados ativos: ARENA 328 / PAVIDEZ 437.
- Pendências mantidas: ARENA 16 / PAVIDEZ 15.
- Listagem de 300 certificados no backend SQLite otimizado: ~0,03 s no ambiente de validação.
- Dashboard completo: ~0,42 s no ambiente de validação.

## PostgreSQL

A conexão PostgreSQL do computador do usuário não é acessível pelo ambiente de desenvolvimento. Por isso a etapa final de integração é feita pelo `migrar_para_postgres.bat` no próprio PC: ele cria a estrutura, copia cada tabela, reajusta as sequences e compara as contagens SQLite/PostgreSQL antes de marcar a migração como concluída.
