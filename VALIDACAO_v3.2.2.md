# Validação — QualiMatch v3.2.2

## Dashboard

- Avisos renderizados no botão amarelo do cabeçalho e ocultos quando não existem avisos ou quando o usuário sai do Dashboard.
- Tooltip de avisos acessível por hover e foco.
- Tendências financeiras disponibilizadas para Total serviço, Aprovado, Pendente e Reprovado.
- Fallback validado entre as duas datas mais recentes da BD_QUALI.
- Layout inferior redistribuído: painel de certificados recentes mais compacto e donut/legenda maiores, sem truncamento obrigatório do texto.

## Regressão

- `pytest`: 39 testes aprovados.
- `py_compile qualimatch/queries.py`: OK.
- `node --check frontend/static/app.js`: OK.
- Base SQLite empacotada: 765 certificados ativos.
- Pendências: Arena 16, Pavidez 15, total 31.
- Tendência da base empacotada (Arena + Pavidez) usa fallback diário entre 31/07/2026 e 03/08/2026 enquanto não houver dois snapshots oficiais por contratada.
