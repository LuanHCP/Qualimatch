# Validação — QualiMatch v3.1.0

## Testes automatizados

- `pytest`: **33 testes aprovados**.
- `python -m compileall`: sem erros.
- `node --check frontend/static/app.js`: sem erros.

## Smoke test da API

Validado com banco SQLite temporário para isolar os dados reais:

- `/api/health` sem login: HTTP 200.
- `/api/dashboard` sem login: HTTP 401.
- login ADMIN: HTTP 200.
- painel `/api/admin/users` como ADMIN: HTTP 200.
- cadastro USER: HTTP 202 / PENDING.
- aprovação pelo ADMIN: HTTP 200.
- login USER aprovado: HTTP 200.
- dashboard como USER: HTTP 200.
- `/api/admin/users` como USER: HTTP 403.
- `/api/backups` como USER: HTTP 403.

## Base operacional incluída

Validação direta sem alteração da lógica de negócio:

- Certificados ativos/listados: **765**.
- Pendências Arena: **16**.
- Pendências Pavidez: **15**.
- Total de pendências: **31**.

## Segurança

- Hash Argon2 para senhas.
- Sessão aleatória armazenada no navegador em cookie `HttpOnly`.
- Banco guarda apenas SHA-256 do token de sessão.
- Recuperação de senha usa token aleatório com validade de 30 minutos e uso único.
- Conta PENDING/REJECTED/BLOCKED não recebe sessão.
- Operações administrativas são verificadas no backend e retornam HTTP 403 para USER.
