# Sistema de Gestão de NC/RNC/AC-AP — Relatório de Entrega

Reconstrução completa do protótipo (localStorage + login sem senha) em uma
aplicação real: backend Flask + PostgreSQL, autenticação com hash de senha,
importação/exportação de planilha validadas contra o arquivo real, e
correção de todos os problemas de contraste/acessibilidade encontrados.

Tudo abaixo foi **implementado e validado** contra um PostgreSQL real e um
navegador real (Playwright/Chromium) rodando a aplicação de ponta a ponta —
não são apenas recomendações.

---

## 1. Arquitetura

```
Navegador (SPA JS puro, hash-router)
   │  fetch() + cookie de sessão + header X-CSRF-Token
   ▼
Flask (backend/app.py) ── blueprints: auth, admin, catalog, ncs, import_export
   │  psycopg3 (ou psql como transporte, ver nota abaixo)
   ▼
PostgreSQL 16 (migrations versionadas em backend/migrations/)
```

- **Frontend**: mantido vanilla JS (sem framework/build step, como no
  original), mas todo acesso a dados agora passa por `assets/js/api.js`
  (wrapper fetch com CSRF) em vez de localStorage. `assets/js/db.js` só
  guarda mais o helper de download de arquivo no navegador.
- **Backend**: Flask puro (não Node) — o ambiente de desenvolvimento usado
  bloqueia `registry.npmjs.org`; Flask permitiu implementar e validar tudo
  de verdade em vez de escrever um backend Node não testável aqui. Não há
  nada em Node vs. Python que o requisito exigisse; a escolha foi só para
  poder *validar* de fato, conforme pedido.
- **Banco**: PostgreSQL 16, 17 tabelas, `backend/migrations/*.sql` aplicadas
  por `backend/migrate.py` (idempotente, controla versão em
  `schema_migrations`).
- **Nota sobre o driver do banco**: `backend/db.py` usa `psycopg` (psycopg3)
  quando disponível. No sandbox de desenvolvimento usado para construir e
  validar isso, o PyPI estava bloqueado, então existe um adaptador de
  fallback que fala com o Postgres via `psql` (parametrização seura por
  dollar-quoting com tag aleatória — sem risco de SQL injection). Em
  produção, com `pip install -r requirements.txt` funcionando normalmente
  (é o caso do Docker Compose entregue), `psycopg[binary]` é instalado e
  usado automaticamente — nenhuma rota depende de qual dos dois está ativo.

---

## 2. O que mudou — lista de arquivos

### Backend (novo, `backend/`)
`app.py`, `config.py`, `db.py`, `security.py` (hash bcrypt), `auth_mw.py`
(sessão+CSRF+permissões), `permissions.py`, `audit.py`, `nc_rules.py`,
`serializers.py`, `routes_auth.py`, `routes_admin.py`, `routes_catalog.py`,
`routes_ncs.py`, `routes_import_export.py`, `xlsx_import.py`,
`xlsx_export.py`, `bootstrap_admin.py`, `migrate.py`,
`migrations/0001_init.sql` … `0004_import_extra_columns.sql`,
`tests/test_backend.py` (26 testes), `requirements.txt`.

### Frontend (reescrito para falar com a API em vez de localStorage)
`assets/js/api.js` (novo), `assets/js/pages/change-password.js` (novo),
`assets/js/db.js`, `assets/js/app.js`, `assets/js/router.js`,
`assets/js/pages/login.js`, `assets/js/pages/usuarios.js` (virou a tela de
Administração completa), `assets/js/pages/import-export.js`,
`assets/js/pages/registro-form.js`, `assets/js/pages/registro-detail.js`,
`assets/js/pages/contratos.js`, `assets/js/pages/textos.js`,
`assets/js/pages/configuracao.js`, `assets/js/pdf.js`,
`assets/js/pages/dashboard.js`, `assets/js/pages/registros.js`,
`index.html`.

### CSS (acessibilidade/contraste)
`assets/css/variables.css`, `assets/css/components.css`,
`assets/css/layout.css`.

### Infraestrutura (novo)
`Dockerfile`, `docker-compose.yml`, `docker-entrypoint.sh`, `.env.example`.

---

## 3. Login e segurança (seção 2 do pedido)

- Tela de login pública **não lista mais usuários** — é e-mail + senha.
- Senhas com **bcrypt** (`backend/security.py`), nunca texto puro; nunca
  retornadas por nenhuma rota da API (validado por teste automatizado
  `test_password_never_returned_by_api`).
- Sessão via cookie `httpOnly` (`nc_session`) + cookie legível
  `nc_csrf` — padrão *double-submit* CSRF, checado em todo POST/PATCH/DELETE
  (`test_csrf_required_for_mutations`).
- Expiração deslizante (8h) + limite absoluto (24h), configuráveis por env.
- Rate limiting de login: 5 tentativas / 15 min → bloqueio de 15 min
  (`test_account_lockout_after_max_failed_attempts`) — **confirmado
  funcionando de verdade**, inclusive descobri isso na prática quando meus
  próprios testes automatizados dispararam o bloqueio.
- Autorização checada **no backend**, não só escondida na UI: cada rota
  valida perfil/permissão antes de executar
  (`test_admin_endpoints_forbidden_for_non_admin_profile`,
  `test_non_emitting_profile_cannot_create_nc`,
  `test_consulta_profile_is_read_only`).
- Último `admin_geral` do sistema não pode ser bloqueado, excluído nem
  rebaixado (3 testes dedicados).
- Troca de senha obrigatória no primeiro acesso
  (`assets/js/pages/change-password.js` + rota
  `/api/auth/change-password`), incluindo para o admin de bootstrap.

---

## 4. Banco de dados (seção 3)

17 tabelas: `users`, `sedes`, `contratos`, `contratadas`,
`contrato_contratadas`, `user_sedes`, `user_contratos`, `ncs`,
`nc_historico`, `nc_anexos`, `textos_padrao`, `header_aliases`,
`import_logs`, `audit_log`, `login_attempts`, `sessions`,
`schema_migrations`. Constraints de FK, índices em colunas de filtro
frequente (sede/contrato/status/data), triggers de auditoria
(`0002_triggers.sql`), tudo versionado em migrations SQL puras aplicadas por
`backend/migrate.py` (idempotente — pode rodar seguro em todo deploy).
Credenciais só via variáveis de ambiente (`PGHOST/PGPORT/PGDATABASE/PGUSER/
PGPASSWORD`), nunca hardcoded.

---

## 5. Administração local (seção 4)

Rota `/#/usuarios` → tela **Administração** com 4 abas:
- **Usuários**: CRUD, ativar/desativar, bloquear/desbloquear, redefinir
  senha (gera senha provisória exibida uma única vez em modal), controle de
  perfil/sedes/contratos.
- **Auditoria**: log de ações administrativas.
- **Importações**: histórico de importações (usuário, data, arquivo,
  resultado).
- **Aliases**: cadastro dos apelidos de cabeçalho de planilha por
  administrador.

Bootstrap do admin inicial: `backend/bootstrap_admin.py`
(`BOOTSTRAP_ADMIN_EMAIL`/`BOOTSTRAP_ADMIN_PASSWORD`/`BOOTSTRAP_ADMIN_NOME`
via env ou `--email/--senha/--nome`), força troca de senha no primeiro
login, e **recusa** criar um segundo `admin_geral` se já existir um ativo
(evita duplicação silenciosa a cada deploy). No Docker Compose isso roda
sozinho no entrypoint se as variáveis estiverem no `.env`.

---

## 6. Importação de planilha (seção 5) — testada contra o arquivo real

`backend/xlsx_import.py` foi validado contra
`CONTROLE_NC_PV_Pavimentos_Leon (1).xlsm` de verdade (não um arquivo
sintético) — teste automatizado
`test_real_reference_workbook_import_matches_expected_counts`, mais um
ciclo completo `test_export_then_reimport_no_duplication` e
`test_reimporting_confirmed_data_yields_only_duplicates`.

- Aceita `.xlsx`/`.xlsm`/`.xls`; lê apenas dados (openpyxl/xlrd), **nunca
  executa macros**.
- Lê a aba "NC" com cabeçalhos na linha 2, ignora linhas vazias, linhas de
  total e fórmulas de resumo.
- Datas do Excel, moeda em `R$`, acentuação e variações de cabeçalho
  tratadas via `header_aliases` (tabela abaixo), configurável por
  administrador sem alterar código.
- Duplicidade detectada por (nº de emissão + unidade + contrato).
- Fluxo: **preview** (abas válidos/atualizações/duplicados/rejeitados/erros)
  → **confirmação transacional** → relatório de erro baixável em CSV → log
  de usuário/data/arquivo/resultado em `import_logs`.

### Tabela de mapeamento planilha → sistema (aliases padrão)

| Campo do sistema | Cabeçalhos aceitos na planilha |
|---|---|
| unidade | Unidade, SEDE |
| tipo_obra | Tipo de Obra |
| numero_emissao | nº Emissão, N° Emissão, NC nº., NC nº, Numero, Número |
| situacao_final | Situação Final (Status), Status Da RNC, Status |
| assunto / contrato / contratada / obra / lote / trecho | (nome direto) |
| descricao | Descrição Detalhada, Descrição Padrão, Descrição |
| data_emissao | Data de Emissão, Data emissão, Data Emissão |
| valor_retencao_proposto | Valor para Retenção, Valor Retenção Proposto |
| valor_retencao_efetivo | Valor Real Retido, Valor retenção efetivo |
| rodovia / km_inicial / km_final / disciplina / classificação | (nome direto) |
| *(+ ~20 outros campos administrativos/de fluxo)* | ver `backend/migrations/0003_seed_header_aliases.sql` |

Novos aliases (ex.: variações que apareçam em outra planilha) são
cadastráveis pela aba **Aliases** da Administração, sem deploy.

---

## 7. Exportação (seção 6)

`GET /api/export/ncs.xlsx` — filtros por sede/contrato/período/status,
colunas compatíveis com a planilha de referência, tipos preservados
(datas como data, valores como número). Ciclo completo
**importar → exportar → reimportar** testado automaticamente sem duplicar
nem corromper dados.

---

## 8. Acessibilidade/contraste — bugs reais encontrados e corrigidos

Validação feita com auditoria de contraste WCAG (fórmula de luminância
relativa) + Playwright renderizando a aplicação de verdade em claro e
escuro, 1440px/390px. Três problemas **reais** (não hipotéticos) foram
encontrados e corrigidos:

1. **Tela de login no tema escuro quase ilegível** — o painel de marca usava
   variáveis de cor que viram quase-branco no tema escuro, com texto branco
   por cima (contraste medido em ~1.13:1). Corrigido com tokens de cor fixos
   (`--brand-panel-1/2/3`), agora 5.75–13.4:1.
2. **Botões/badges com texto branco fixo sobre fundo que vira claro no tema
   escuro** (`.btn.danger:hover`, indicadores de fluxo concluído/atual) —
   contraste medido 1.98–2.64:1. Corrigido com tokens `--ink-on-danger`/
   `--ink-on-success`, agora 6.6–8.9:1.
3. **Atributo `hidden` sendo ignorado** por uma regra CSS de mesma
   especificidade declarada depois (`.alert-banner{display:flex}`) — banners
   de erro apareciam vazios/visíveis quando deveriam estar ocultos.
   Corrigido com `[hidden]{display:none!important;}` global.
4. Cor de fundo de sede definida pelo administrador (hex arbitrário) agora
   escolhe automaticamente texto preto ou branco por luminância
   (`App.util.idealTextColor`), evitando texto ilegível sobre uma cor clara
   escolhida pelo admin.

---

## 9. Bugs reais encontrados só por testar de ponta a ponta (não visíveis por leitura de código)

- **Condição de corrida assíncrona**: com latência de rede real (em vez do
  localStorage síncrono do protótipo), uma navegação rápida podia deixar um
  `render()` antigo terminar depois que o DOM já tinha sido substituído,
  crashando com `Cannot set properties of null`. Corrigido com guardas
  `mount.isConnected` e um sistema de token/geração nas abas de
  Administração.
- **Overflow horizontal em mobile (390px)**: uma tabela larga empurrava a
  página inteira em vez de rolar dentro do próprio container — causa raiz
  era `main.content` (item de CSS Grid) sem `min-width:0`. Corrigido;
  overflow medido caiu de 662px para 0px em todas as rotas testadas.

---

## 10. Como rodar localmente (Docker Compose)

```bash
cp .env.example .env
# edite PGPASSWORD, APP_SECRET_KEY, BOOTSTRAP_ADMIN_EMAIL/PASSWORD no .env
docker compose up -d --build
```

Isso sobe Postgres + a aplicação (API e frontend na mesma porta 8000),
aplica as migrations automaticamente e cria o administrador inicial se as
variáveis `BOOTSTRAP_ADMIN_*` estiverem definidas. Acesse
`http://localhost:8000`, faça login com o admin de bootstrap e troque a
senha (obrigatório no primeiro acesso).

Sem Docker (dev manual): Postgres 16 rodando localmente,
`pip install -r backend/requirements.txt`, `python3 backend/migrate.py`,
`python3 backend/bootstrap_admin.py --email ... --senha ...`,
`python3 backend/app.py` (porta 8000, configurável via `PORT`).

---

## 11. Testes executados e resultado

- **Backend — 26 testes automatizados (`python3 -m unittest discover -s
  backend/tests`): 26/26 OK**, cobrindo login/sessão/CSRF/lockout,
  autorização por perfil, proteção do último admin, workflow completo de
  NC (emissão→resposta→análise→eficácia→encerramento), schema/migrations,
  e importação/exportação **contra o arquivo `.xlsm` real do usuário**
  (contagens de linhas válidas/duplicadas/rejeitadas validadas).
- **End-to-end (Playwright + Chromium real)**: login/logout, dashboard com
  321 registros reais, listagem/filtro de NCs, formulário de novo registro
  (wizard de 8 passos), tela de Administração (4 abas), criação de usuário,
  responsividade em 1440px e 390px em 6 rotas (overflow horizontal
  verificado = 0px em todas), tema escuro em tela de login/painel/lista de
  registros (contraste OK visualmente).
- Base de dados de teste: os 321 registros reais importados da planilha de
  referência permanecem no banco de desenvolvimento; o usuário de teste
  E2E (`teste.e2e@exemplo.com`) e as tentativas de login de teste foram
  removidos antes desta entrega.

---

## 12. Limitações e pendências conhecidas

- **`.xls` (formato antigo binário)**: o código usa `xlrd` para lê-lo e
  está listado em `requirements.txt`, mas não foi possível instalar/testar
  esse caminho especificamente no sandbox de desenvolvimento (rede
  restrita); `.xlsx`/`.xlsm` foram validados de ponta a ponta contra o
  arquivo real.
- Ainda não testado por clique-a-clique no navegador (só via API/testes
  automatizados de backend): as transições de workflow
  resposta→análise→eficácia→encerramento na tela de detalhe da NC. A lógica
  está coberta por `test_full_flow_emission_to_closure` no backend.
- Import/export não foi re-testado pela **UI nova** com upload real pelo
  navegador (foi validado no nível de API/backend, que é o que faz a
  validação de dados); recomendo um teste manual de upload real antes do
  primeiro uso em produção, por segurança.
- `COOKIE_SECURE` vem `false` por padrão no `.env.example` — **mude para
  `true`** ao publicar atrás de HTTPS, senão o cookie de sessão trafega sem
  a proteção de "somente HTTPS".
- Sem CI configurado — os testes existem (`backend/tests/test_backend.py`)
  mas rodam manualmente; adicionar GitHub Actions/similar é recomendado.
