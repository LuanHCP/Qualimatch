# Validação — QualiMatch v3.3.0

- 56 testes automatizados aprovados.
- Python compilado sem erros.
- JavaScript validado com `node --check`.
- Base empacotada preservada: 765 certificados ativos.
- Pendências preservadas: Arena 16 / Pavidez 15.
- Migração de usuários legados validada: usuários aprovados anteriores recebem acesso BV apenas na primeira migração.
- Revogação de BV permanece revogada após reinicialização.
- ADMIN possui acesso aos três ambientes e não consegue remover a própria administração.
- Usuário comum pode receber BV e Contratada de forma independente.
- Tela de seleção contém os três cards e o portal Contratada possui três abas de protótipo.
- Smoke test FastAPI: login USER somente Contratada = HTTP 200; `/api/dashboard` = HTTP 403; `/api/auth/me` reporta permissões corretas; ADMIN acessa `/api/admin/users` = HTTP 200; página raiz = HTTP 200.
