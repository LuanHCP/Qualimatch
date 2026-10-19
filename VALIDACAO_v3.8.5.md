# Validação v3.8.5

- Hotfix da migração `bv_documents`: colunas novas são garantidas antes da criação do índice que as utiliza.
- Migração validada usando banco SQLite real da v3.8.3: `is_active`, `manual_override` e `idx_bv_documents_active` foram criados com sucesso.
- `iniciar.bat` agora mantém a janela aberta quando o servidor encerra com erro de runtime.
- 132 testes automatizados aprovados.
- Python compilado sem erros.
- JavaScript validado com `node --check`.
