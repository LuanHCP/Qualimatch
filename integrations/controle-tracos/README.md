# Controle de Traço — protótipo local

Protótipo para recebimento, análise e organização de cartas-traço. Funciona somente no computador local e não está publicado.

## Rodar o protótipo

### Opção rápida (um clique)

Dê duplo clique em `iniciar.bat`. O script detecta o Node.js instalado,
instala as dependências na primeira vez, abre o navegador automaticamente
em http://localhost:3000 e inicia o servidor local. Deixe a janela aberta
enquanto estiver usando o sistema; para parar, feche a janela.

### Opção manual

Requisitos: Node.js 22.13 ou superior.

```powershell
npm install
npm run dev
```

Abra http://localhost:3000 e use:

- E-mail: `admin@qualimatch.local`
- Senha: `Demo@2026`

Sem PostgreSQL configurado, os dados do fluxo ficam no armazenamento local do
navegador e os anexos continuam sendo gravados na pasta local `uploads/` pela
API. O editor de PDF funciona normalmente nesse modo.

## Ativar PostgreSQL / pgAdmin 4

### Opção rápida (um clique)

Dê duplo clique em `criar_banco.bat`. O script pede a senha do usuário
`postgres`, cria o banco `tracos_teste`, roda `database/setup.sql` e já
grava o `.env.local`. Depois é só rodar `npm run dev` de novo.

### Opção manual

1. No pgAdmin 4, crie um banco chamado `tracos_teste`.
2. Selecione esse banco, abra **Query Tool** e execute todo o arquivo `database/setup.sql`.
3. Copie `.env.example` para `.env.local` e troque `SUA_SENHA` pela senha local do usuário `postgres`.
4. Reinicie `npm run dev`.

A interface indicará **Banco PostgreSQL** quando a conexão estiver ativa. A API local roda em http://127.0.0.1:3001.

## Funcionalidades do protótipo

- Login com sessão local e autenticação via PostgreSQL quando configurado,
  com telas de "Esqueci minha senha" e "Solicitar cadastro" (simuladas).
- Tema escuro com paleta roxa/ciano no mesmo espírito do QualiMatch.
- Seletor de módulos no topo, no padrão de navegação do QualiMatch:
  **Análise de Traços** (dashboard, todos os traços, relatórios e responsáveis)
  e **Ferramentas** (editor de PDF e configuração da pasta sincronizada).
- Dashboard, Todos os traços, Relatórios e Responsáveis.
- Busca e filtros em menus suspensos.
- Cadastro, visualização, atribuição de responsável e mudança de status.
- Anexos reais: a carta traço e o checklist de análise enviados no
  formulário "Nova solicitação" são salvos de fato no servidor local (pasta
  `uploads/`, ignorada pelo Git), não apenas o nome do arquivo.
- Documentos acessíveis no detalhe de cada análise, com download, reposição e
  atalho direto para o editor.
- Editor multipágina para posicionar, redimensionar e aplicar no PDF os selos
  **Aprovado**, **Restrito** e **Não conforme**, com data escolhida pelo usuário.
  A versão carimbada é salva no histórico de anexos e também baixada.
- Pasta sincronizada (SharePoint/OneDrive): em **Ferramentas**, é possível
  informar o caminho local da pasta sincronizada; ao mudar o status de um
  traço, os anexos são movidos automaticamente para a subpasta
  correspondente ao novo status.
- Relatório por status/categoria/responsável e exportação CSV.
- Persistência local automática como fallback.

## Observação

As credenciais são exclusivamente de demonstração. Antes de qualquer uso real, configure usuários e senhas próprios.
