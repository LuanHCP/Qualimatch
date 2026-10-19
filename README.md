# QualiMatch V2 — edição demonstrativa publicável

Esta é uma cópia independente do sistema completo. Interface, abas, permissões,
relatórios, ferramentas e integrações foram preservados, mas nenhum banco,
anexo, caminho pessoal, sessão ou credencial da instalação original foi incluído.

Na primeira execução são criados automaticamente **200 registros fictícios por
área operacional**: usuários, medições, dados financeiros, certificados, kits,
documentos BV/Contratada, sincronizações, eventos, auditoria, traços e não
conformidades. Os registros são determinísticos e podem ser recriados a qualquer
momento com `RECRIAR_DADOS_DEMO.bat`.

## Execução rápida

1. Execute `INICIAR_V2_DEMO.bat`.
2. Entre com `admin@qualimatch.local` e senha `Demo@2026`.
3. Para preparar os módulos incorporados de Traços e NC, execute uma vez
   `PREPARAR_INTEGRACOES.bat`. O Controle de Traços funciona também em modo local;
   o Sistema de NC requer PostgreSQL, conforme o instalador incluído.

O modo demonstração desativa monitores de SharePoint, envio de e-mail e
sincronizações automáticas para impedir qualquer acesso acidental a fontes reais.
Para uma instalação produtiva, copie `.env.example` para `.env`, defina
`QUALIMATCH_DEMO=false` e configure apenas fontes autorizadas.

## Publicação no Git

O `.gitignore` exclui `.env`, bancos, PDFs gerados, uploads, sessões, chaves,
caches, ambientes virtuais e dependências instaladas. Antes do primeiro push,
execute `python scripts/verify_public_release.py` para confirmar que não existem
artefatos locais ou caminhos pessoais rastreáveis.

---

# Histórico da base funcional

Consultas PostgreSQL reaproveitam até oito conexões por processo. A autenticação
e o processamento de PDFs não bloqueiam a fila HTTP. Cartões de arquivos abrem
PDFs somente ao clicar em Visualizar; atualizações de certificados não recarregam
o dashboard oculto. Requisições GET simultâneas idênticas são unificadas, sem cache
persistente de respostas. Estatísticas reutilizam somente cálculos com os mesmos
valores e coeficiente; uma edição altera a chave automaticamente.

Atualização: execute `.venv\Scripts\python.exe -m pip install -r requirements.txt`
e reinicie o servidor. A nova dependência é `psycopg-pool`. Instalações sem ela
continuam funcionando com conexões individuais, mas sem esse ganho de desempenho.

Diagnóstico de consultas (somente leitura, sem imprimir documentos):
`.venv\Scripts\python.exe scripts/profile_requests.py --profile`.

## Histórico — Auto-reparo do ambiente Python


## Novidade v3.8.1 — importação automática local

A v3.8.1 adiciona um monitor de arquivos para as bibliotecas do SharePoint/OneDrive já sincronizadas no Windows do servidor. Ele funciona sem Microsoft Graph e sem configuração do TI.

- **BV:** monitora as fontes `certificados` de ARENA e PAVIDEZ. Quando um PDF BI330 novo ou alterado aparece, o arquivo é aguardado até estabilizar, processado pelo parser, gravado no banco e o matching é recalculado.
- **Contratada:** monitora a planilha `d.KIT` e a árvore `Entrega Contratada` (`kit_documentos`) de ARENA e PAVIDEZ. Arquivos novos/alterados/removidos são reindexados automaticamente.
- **Catch-up:** se o PC estiver desligado/suspenso, não há leitura da pasta local. Ao ligar o PC e iniciar o QualiMatch, o monitor compara a pasta com o banco e processa o que chegou enquanto estava offline.
- **Painel ADMIN:** em Administração → Sincronização existe o cartão “Monitor SharePoint / OneDrive”, com liga/desliga, BV, Contratada, intervalo de 10 s a 2 min, botão “Verificar agora” e histórico por arquivo.
- **Fila de eventos:** cada detecção registra NOVO/ALTERADO/REMOVIDO e o resultado CARREGADO/PARCIAL/INDEXADO/ERRO. Falhas recentes também aparecem no sino do ADMIN.

O intervalo padrão é **15 segundos**. O monitor exige que os caminhos locais das fontes estejam configurados em Administração → Sincronização.

Esta versão parte da **v3.8.0** e adiciona a camada de gestão necessária para o QualiMatch funcionar como sistema operacional de acompanhamento, e não apenas como consulta de dados.

## Principais novidades

### Central de Revisões
Em **Administração → Revisões**, o ADMIN encontra em uma fila única certificados com leitura parcial/data inconsistente, kits fora de OK e pendências classificadas por responsabilidade. Avisos do mesmo certificado são agrupados para evitar ruído.

### Medições Mxx + SLA
A BV ganhou **Gestão Mxx**. Cada ciclo (M1, M2, ..., M14...) consolida dias de execução, dias com kit, dias com certificado, cobertura %, pendências da Contratada, itens no prazo, pendências de certificado e prazos médios. Cada Mxx pode ser exportada em **Excel** com resumo, pendências e execuções.

A regra de responsabilidade da Pendência BV fica:
- sem kit para a data de aplicação: **PENDENTE CONTRATADA**;
- kit entregue e ainda dentro de 3 dias: **NO PRAZO**;
- mais de 3 dias após a entrega, sem certificado: **PENDENTE CERTIFICADO**.

### Medição → Kit → Certificado
Na aba **Medições**, o botão **Ver fluxo** abre a rastreabilidade visual da execução, mostrando a Medição, os kits encontrados naquela data e os certificados vinculados.

### Busca global e notificações
O cabeçalho possui busca por BI330, linha/medição, BR, kit e documento, respeitando os acessos do usuário. O sino de notificações reúne itens que precisam de atenção e atualiza periodicamente.

### Histórico + Antes × Depois + Desfazer
Edições de kits, CPs e certificados passam a registrar snapshot anterior e posterior. O ADMIN pode abrir **Antes × Depois** e, quando suportado, usar **Desfazer**.

### Perfis Visualizador / Editor / Administrador
Além dos portais BV/Arena/Pavidez, o usuário recebe um nível operacional:
- **Visualizador**: consulta sem edição;
- **Editor**: pode editar/importar dentro dos portais que recebeu;
- **Administrador**: acesso total, permissões, backups e gestão.

O isolamento **Arena × Pavidez** continua aplicado no backend.

### Backups com restauração
O painel de Backups agora permite **Restaurar**. A restauração exige a confirmação `RESTAURAR` e cria um backup do estado atual antes de voltar no tempo. SQLite usa a Backup API; PostgreSQL usa snapshot lógico e recompõe IDs/relacionamentos.

### Saúde do sistema
Em **Administração → Saúde do sistema**, o ADMIN acompanha banco, fontes locais, último sync, erros, quantidade de certificados/kits/usuários e último backup.

## Atualização a partir da v3.7.5
1. Extraia esta versão em uma pasta nova.
2. Copie o arquivo `.env` da versão que já está funcionando.
3. Execute `iniciar.bat` ou `iniciar_rede.bat`.
4. O `init_db()` cria automaticamente `change_history` e `permission_level`; **não é necessário migrar certificados novamente**.
5. Usuários aprovados que já existiam antes da v3.8 recebem nível **EDITOR** na primeira migração para não perderem funções. Novos usuários começam como **VIEWER** e sem portal até o ADMIN liberar.

> O rodapé permanece com **Desenvolvido por Luan**.

---

# QualiMatch v3.7.5 — pré-visualização + edição segura dos kits

## v3.7.5 — Portal Contratada

- Documentos indexados da Contratada podem ser pré-visualizados no próprio QualiMatch (PDF/imagens), sem download prévio.
- Kits de ensaio podem ser editados pelo ADMIN diretamente na interface.
- Exclusão de kit é lógica/segura: remove das telas, estatísticas, gráfico e cobertura de pendências, mas não apaga a linha original da d.KIT no SharePoint.
- Edições/exclusões manuais recebem `manual_override` e não são sobrescritas pela sincronização seguinte.
- O gráfico mensal usa `Data recebimento` e, quando ela estiver vazia, usa `Data aplicação` como fallback — corrigindo kits Pavidez que antes não apareciam no gráfico.
- Isolamento Arena/Pavidez e todas as funções anteriores permanecem.


Esta versão mantém todo o trabalho técnico da v3.2.7 e adiciona uma nova camada de navegação e controle de acesso.

## v3.7.4 — gravação direta e isolamento das contratadas

A Central de Ferramentas mantém **Gerar cópia Excel** e adiciona **Atualizar planilha principal**. A gravação oficial cria backup integral do XLSX, valida hashes antes/depois, usa arquivo temporário + troca atômica e bloqueia a operação se a planilha estiver aberta no Excel. Após a gravação, a fonte Qualidade é sincronizada novamente.

Novos usuários aprovados não recebem portal automaticamente: o ADMIN define o acesso. No portal Contratada, os acessos agora são segregados por empresa. Em Administração → Usuários, o ADMIN libera **Contratada • Arena** e/ou **Contratada • Pavidez**. O backend aplica o mesmo filtro, portanto alterar a URL ou chamar a API diretamente não permite visualizar a outra contratada. ADMIN continua vendo ambas.


## Depois do login

O usuário escolhe entre três ambientes em cards grandes:

- **BV** — ambiente atual completo: Dashboard, Certificados, Pendências BV e Medições.
- **Contratada** — novo ambiente separado. Nesta versão possui abas demonstrativas para validarmos a navegação antes de desenvolver as regras reais.
- **Administração** — usuários e acessos, sincronização, histórico e backups.

Cards sem permissão aparecem bloqueados. A proteção também existe no backend: não basta descobrir uma URL da API para acessar a BV sem autorização.

## Permissões

Na Administração, cada usuário pode receber:

- BV;
- Contratada;
- Administração.

Marcar **Administração** promove o usuário para `ADMIN`. ADMIN possui acesso aos três ambientes e pode administrar permissões de outras contas.

Por segurança:

- um administrador não pode remover sua própria permissão administrativa;
- o sistema não permite ficar sem nenhum administrador aprovado;
- usuários antigos já aprovados recebem BV automaticamente somente na primeira migração;
- usuários novos aprovados recebem BV por padrão, e o ADMIN pode alterar depois.

## Portal Contratada

As abas desta versão são protótipos funcionais de navegação:

- Visão geral;
- Certificados;
- Pendências.

Elas não exibem dados reais ainda. A ideia é desenvolver esse fluxo separadamente sem misturar regras internas da BV.

## PostgreSQL / atualização

Se você já usa a versão anterior com PostgreSQL, copie o seu `.env` para esta pasta e execute normalmente. Ao iniciar, as novas colunas de permissão são criadas automaticamente.

Não é necessário migrar novamente os certificados.

## Iniciar

Local:

`iniciar.bat`

Na rede:

`iniciar_rede.bat`

O parser dos certificados permanece na versão 3.2.7 porque esta atualização não altera a leitura dos BI330.

## v3.4.0 — Kits da Contratada

O portal **Contratada** passa a ler duas planilhas locais de kits (Arena/Pavidez), diretamente das bibliotecas SharePoint/OneDrive sincronizadas no Windows. A aba esperada é `d.KIT`.

No primeiro **Sincronizar tudo**, se o caminho de Kits estiver vazio, o sistema tenta localizar automaticamente um XLSX compatível nas pastas das fontes de Medição/Qualidade da contratada. Em **Administração → Sincronização**, o botão **Localizar** pode repetir essa busca ou o caminho pode ser colado manualmente.

A planilha permanece no SharePoint; o QualiMatch usa uma cópia estável em `data/cache` e grava apenas os campos operacionais no banco.

## v3.5.0 — Documentos dos Kits + feedback da Contratada

### Pasta `Entrega Contratada`
Em **Administração → Sincronização** existem agora as fontes **Documentos dos Kits** para ARENA e PAVIDEZ.
Aponte o caminho para a pasta local sincronizada pelo SharePoint/OneDrive. O QualiMatch percorre a árvore inteira recursivamente, portanto as 13 pastas e qualquer quantidade de subpastas abaixo delas são lidas sem cadastro individual.

O sistema não duplica os documentos: mantém os arquivos no SharePoint/OneDrive e grava no banco somente um índice com nome, caminho relativo, pasta, tipo, tamanho e data de modificação. No portal **Contratada → Kits de ensaio**, a seção **Documentos dos kits** permite pesquisar e abrir os arquivos pelo navegador.

Quando o `#SEQ` de um kit aparece no nome ou no caminho do arquivo, o documento é vinculado automaticamente à linha correspondente da tabela `d.KIT`.

### Feedback da reunião
- Dashboard: filtro `Todos / Aprovados / Reprovados`.
- Dashboard: removido o card `Volume massa`.
- Dashboard: `Linhas qualidade` substituído por `Quantidade CPs`.
- Certificados: removidos os filtros `CPs mín.` e `CPs máx.`.
- Certificados: novo filtro suspenso pelo número/nome do certificado.

Para bancos PostgreSQL existentes, basta copiar o `.env` da versão anterior e iniciar. A nova tabela `kit_documents` e as novas fontes são criadas automaticamente pelo `init_db`.


## v3.6.0 — Evolução da Contratada

O card **Recebidos** considera linhas preenchidas da `d.KIT`, e não a confiabilidade da coluna Data Recebimento. O Dashboard da Contratada mostra o desempenho de cada controle (1–8 e SIN.-Retro). A aba **Certificados** funciona como navegador da árvore local `Entrega Contratada`, agrupando pelos diretórios principais e oferecendo prévia inline para PDF/imagens. A aba **Pendências** reutiliza a mesma cobertura por data aplicada na BV.

## v3.6.4 — Contratada
A Visão Geral passa a consolidar entregas por mês e compara com uma linha de meta baseada nos dias com medição. Os filtros de Kits foram simplificados para Situação (OK/INCOMPLETO/PENDENTE), Período (DIURNO/NOTURNO) e Rodovia, com carregamento automático das opções ao abrir a aba.

## v3.7.0 — Central de Ferramentas

A Administração ganhou a página **Ferramentas**. A primeira ferramenta funcional é **PDF → BD_QUALI (prévia)**.

Fluxo atual:
1. Administrador seleciona até 30 PDFs BI330.
2. O parser existente lê rotina e contra-prova.
3. A quantidade de linhas esperadas é definida pelos **CPs de rotina**: 1 CP = 1 linha.
4. Contra-provas complementam as mesmas linhas e não dobram a quantidade.
5. Cada CP é cruzado com `measurements` usando contratada, Data Aplicação, rodovia, estaca, faixa e sentido.
6. O sistema mostra `VINCULADO`, `REVISAR` ou `SEM MEDIÇÃO` e informa a Linha/Medição encontrada.
7. Também compara a quantidade esperada com quantas linhas do mesmo certificado já existem na `quality_rows`.
8. É possível baixar a prévia em CSV para auditoria.

**Segurança:** v3.7.0 não escreve na planilha BD_QUALI. A gravação em XLSX será a etapa seguinte, depois da validação dos vínculos e do mapeamento de fórmulas.

## v3.7.1 — Preenchimento seguro da BD_QUALI

A ferramenta **Administração → Ferramentas → PDF → BD_QUALI** passa da prévia para a geração de uma **cópia segura do Excel oficial**.

### Regra de escrita
- A fonte continua sendo a planilha `Qualidade` configurada para ARENA/PAVIDEZ em Administração → Sincronização.
- **O arquivo oficial nunca é sobrescrito nesta versão.** O botão `Gerar cópia Excel` devolve um novo `.xlsx` (ou um `.zip` com Arena + Pavidez).
- O QualiMatch usa a própria linha da `BD_QUALI` ligada à Medição como molde, preservando estrutura, estilos, fórmulas e demais abas.
- São preenchidos somente os campos de entrada do certificado: número, datas, Rice, estatísticas de Vv, estatísticas de espessura/A-B, totais de CPs, quantidades reprovadas, status e campos equivalentes de contra-prova.
- Campos calculados como **K, % de reprovação, média em cm, volumes/valores de retenção e resumo de status permanecem fórmulas do Excel**.
- Ao abrir a cópia no Excel, o arquivo é marcado para recálculo completo das fórmulas.

### Certificado já existente
Se a quantidade de linhas existentes na BD_QUALI for exatamente igual à quantidade de CPs projetada, a cópia atualiza apenas os campos do certificado nessas linhas, sem alterar o vínculo de Medição já consolidado.

Se a quantidade divergir, a escrita é bloqueada e o certificado fica para revisão. Isso evita completar ou apagar linhas silenciosamente.

### Certificado novo
Cada CP vinculado clona uma linha-modelo da mesma `LINHA MEDIÇÃO` e a nova linha é adicionada **ao final da tabela BD_QUALI**, em vez de inserir no meio da planilha. A linha clonada mantém os dados da medição e suas fórmulas; os campos Vv/CP antigos são limpos e recebem os dados do novo BI330.

### Proteções
A geração é bloqueada quando:
- o PDF ficou `PARCIAL`;
- há CP em `REVISAR`/`SEM MEDIÇÃO`;
- o número no nome do PDF diverge do número interno;
- a quantidade de linhas já existente diverge da quantidade de CPs;
- não existe linha-modelo para a medição;
- o Excel local foi alterado/reordenado após a última sincronização;
- a estrutura esperada da BD_QUALI não possui as colunas de entrada necessárias.

Esta etapa foi desenhada propositalmente para validar cópias antes de habilitar qualquer escrita direta no arquivo SharePoint oficial.

## v3.7.2 — revisão e edição manual

Na ferramenta PDF → BD_QUALI, novos certificados são adicionados ao fim da tabela `BD_QUALI` para não deslocar fórmulas/referências; a prévia informa as linhas projetadas. Itens `REVISAR` podem ser resolvidos escolhendo manualmente uma medição candidata.

Administradores também podem editar resumo/status de cada fase e valores individuais dos CPs. Toda edição cria backup, auditoria e protege o certificado contra sobrescrita automática. O rodapé identifica o projeto como **Desenvolvido por Luan**.


## v3.7.3 — cópia Excel visível e validada

- A cópia da BD_QUALI agora detecta filtros ativos no Excel. Na cópia gerada, os critérios são limpos e as linhas da tabela são reexibidas para que novos registros não fiquem ocultos. O arquivo oficial permanece intocado.
- Linhas novas não herdam mais `hidden=1` da linha-modelo.
- Depois de montar o XLSX, o QualiMatch abre internamente a cópia e confirma que `Nº CERTIFICADO Vv` foi gravado nas linhas previstas; se não estiver, o download é bloqueado com erro.
- O aviso após o download informa a faixa de linhas efetivamente escrita.
- Certificados BV com recebimento em laboratório anterior à Data Ext. dos CPs aparecem em amarelo na listagem.


## v3.8.2
Dias de execução agora são datas distintas da Medição. A importação de BI330 também possui validação de conteúdo duplicado antes de criar/mesclar registros.

## v3.8.3 — Arquivos BV por Medição
Em Administração → Sincronização configure **Arquivos BV por medição** apontando para a pasta local sincronizada do SharePoint/OneDrive. A leitura é recursiva e a aba **BV → Arquivos BV** agrupa automaticamente documentos por pastas Mxx quando o padrão é reconhecido. O monitor automático da BV também atualiza esse índice.

Na aba Certificados, a legenda visual é: verde = aprovado, vermelho = reprovado, amarelo = ajustes/inconsistências e roxo = duplicado. O roxo indica que outro arquivo tecnicamente idêntico foi detectado; somente o certificado original participa das estatísticas.

## v3.8.4 — Arquivos BV como fonte de certificados + carregamento leve

A fonte **Arquivos BV por medição** passa a ter duas funções ao mesmo tempo:

1. indexar a árvore operacional da BV por Mxx para navegação; e
2. importar automaticamente PDFs BI330 encontrados nessa árvore pelo mesmo pipeline técnico da fonte de certificados.

PDFs comuns continuam somente no índice de Arquivos BV. Um BI330 novo alimenta `certificates`, `certificate_samples`, matching, Dashboard e Pendências. Se o conteúdo técnico já existir, o arquivo é registrado como `DUPLICADO` e não dobra as estatísticas.

### Carregamento sob demanda

A página **BV → Arquivos BV** não cria mais dezenas/centenas de `iframe` de PDFs ao abrir. Primeiro são carregados apenas os grupos/pastas e metadados. Os bytes do PDF/imagem são buscados somente quando o usuário clicar em **Pré-visualizar** ou **Abrir**. Cada grupo começa com até 100 itens e oferece `Carregar mais` quando necessário.

### Excluir da visualização

Perfis com permissão de edição podem clicar em **Excluir** em Arquivos BV. A exclusão é lógica: o item some do QualiMatch e não volta nas sincronizações seguintes, mas o arquivo original no SharePoint/OneDrive não é apagado. Se o item era apenas uma ocorrência duplicada, essa ocorrência deixa de manter o certificado original marcado como roxo.


## v3.8.6 — Responsabilidade das pendências

- **BV → Pendências BV:** somente `PENDENTE CERTIFICADO`.
- **Contratada → Pendências:** somente execuções sem kit/data de aplicação, `PENDENTE CONTRATADA`.
- `NO PRAZO` continua disponível na Gestão Mxx/indicadores, mas não aparece como pendência operacional.
- Rodapé: versão curta (`v3.8.6`) + autoria separada.


## v3.8.7 — Preenchimento automático da BD_QUALI

- O monitor SharePoint/OneDrive pode preencher a BD_QUALI automaticamente quando reconhece um BI330 novo ou alterado.
- Reutiliza o mesmo pipeline seguro da Central de Ferramentas: CP de rotina → linha da medição → campos manuais do certificado; fórmulas e formatação da BD_QUALI continuam sendo do próprio Excel.
- Só grava quando todos os CPs estão `VINCULADO` e o plano Excel está `PRONTO`; ambiguidades ficam como `REVISAR` e não são escritas.
- Antes de alterar a planilha principal, mantém backup, validação do arquivo e troca atômica. Depois da gravação, a fonte Qualidade é ressincronizada para atualizar Dashboard e Pendências.
- PDFs duplicados/erro/substituídos não entram no preenchimento automático.
- Alterações reais do mesmo BI (por exemplo, contra-prova adicionada) podem atualizar as linhas já existentes, sem criar novas linhas duplicadas.
- Administração → Sincronização ganhou a opção **Preencher BD_QUALI**, que pode ser desligada sem desativar o restante do monitor.
- Upload manual e sincronização manual de certificados também acionam a reconciliação automática.


## v3.8.8 — Status final + coluna Entrega

- O Dashboard deixa explícito que **contra-prova é subconjunto do total**, e não uma terceira situação somada a Aprovado/Reprovado.
- A classificação fecha em **Aprovados + Reprovados + Ajustes/sem resultado = Total**.
- Quando há CPs reais na fase `CONTRA_PROVA`, essa fase passa a ser a fonte do status final do certificado.
- A planilha `d.KIT` passa a extrair a coluna **Entrega**. `Entregue` transfere a responsabilidade para a BV; `Não entregue` ou vazio mantém a pendência com a Contratada.
- Quando existem vários kits na mesma data, a responsabilidade só passa para a BV se **todos** estiverem como Entregue.
- O SLA de 3 dias continua calculado, mas separado da responsabilidade: itens entregues podem aparecer na BV como `NO PRAZO` ou `PENDENTE CERTIFICADO`.
- Planilhas antigas sem a coluna Entrega continuam funcionando pelo comportamento legado até serem atualizadas.


## v3.8.9 — Filtros técnicos BV

- BV → Certificados ganhou filtros independentes para **Volume de vazios (Vv)** e **Espessura**.
- Cada filtro aceita Todos, Aprovado, Reprovado e Sem resultado.
- Os filtros são combináveis entre si e com contratada, situação geral, rodovia, trecho, número e busca.
- A avaliação usa a fase final do certificado; quando existe contra-prova efetivamente entregue, o resultado final dela é usado.



## v3.8.13 — Revalidação BV “Sem resultado”

- Auditoria do banco operacional identifica certificados com **Situação = Sem resultado** a partir da ausência de fase/CP técnico.
- Novo botão **Validar sem resultado** em BV → Certificados (ADMIN): reabre somente os PDFs vinculados aos registros sem resultado e os reprocessa com o parser atual.
- A rotina em lote **não grava na BD_QUALI**; limita-se ao cadastro dos certificados/CPs e ao recálculo dos vínculos após o lote.
- Parser de linhas de CP reforçado para aceitar faixa vazia, faixa com múltiplas palavras, datas com etapa (`-E1`, `-E3`), linhas quebradas no texto do PDF e layouts BV antigos/novos com coluna adicional de Vv com filme.
- Mudança de `PARSER_VERSION` para **3.8.13** faz a sincronização comum reprocessar automaticamente registros incompletos de versões antigas; registros tecnicamente completos continuam usando o upgrade inteligente.
- Incluído diagnóstico somente leitura em `tools/diagnosticar_sem_resultado_bv.py`.

## v3.8.12 — Parser BV com etapas E1/E3

- Corrige certificados BV em que a **Data Aplicação** possui um identificador de etapa anexado à data, como `09/10/2025-E3` e `09/10/2025-E1`.
- O sufixo de etapa é aceito na leitura da linha do CP, enquanto a data civil continua sendo gravada como `09/10/2025` para matching e pendências.
- Validado com o **BI330-0093 / PAVIDEZ / BR-376**, que passa de 0 CPs para **10/10 CPs carregados** (736–743, 751–752).
- Mantém as correções da v3.8.11 para `Faixa adicional` e para o layout BV novo com VV em filme.
- Nenhuma alteração de schema ou migração de banco de dados.

## v3.8.11 — Parser BV multiversão

- Corrige certificados BV antigos com faixa textual, como **Faixa adicional**, que antes não geravam nenhum CP.
- Mantém compatibilidade com faixas numéricas (`1`, `Faixa 1`, `Faixa 2`, etc.).
- Corrige leitura de **Gmb** em certificados BV novos que possuem a coluna adicional `Volume de Vazios com Plástico Filme (%)`.
- O parser passa a localizar o bloco final de VV pelo padrão dos percentuais, em vez de assumir que Gmb/VV são sempre as duas últimas células.
- Validado com BI330-0446 (layout antigo) e BI330-0471 (layout novo), ambos com 6 CPs carregados.
- Nenhuma alteração de schema ou migração de banco de dados.

## v3.8.10 — Linha estrutural automática BD_QUALI

- Corrige o bloqueio **“Sem linha-modelo na BD_QUALI”** quando o CP está corretamente vinculado a uma medição que ainda não possui linha na BD_QUALI.
- Ordem de criação de novas linhas: linha exata da medição → linha estrutural segura da própria BD_QUALI da contratada.
- No fallback estrutural, o QualiMatch clona fórmulas/estilos, apaga valores constantes da linha antiga e reconstrói o bloco-base com os dados da medição antes de aplicar o certificado.
- KIT, certificado, RNC e demais dados manuais da linha usada como molde **não são transportados** para a nova medição.
- Mantém backup, troca atômica, validação pós-gravação, fórmulas e formatação já existentes no fluxo PDF → BD_QUALI.
- Se não houver nenhuma linha estrutural válida na planilha, o sistema continua bloqueando a escrita para evitar criar uma linha sem fórmulas/estrutura.


## v3.8.14 — Auto-reparo do ambiente Python

O launcher agora detecta `.venv` incompleto/quebrado (inclusive ausência de `pyvenv.cfg`) e recria automaticamente o ambiente virtual antes de iniciar. O parser permanece na versão 3.8.13.

## v3.8.15 — Inicialização em Windows
Se `instalar.bat` encontrar um Python quebrado no PATH (por exemplo, executável de um `.venv` antigo que perdeu `pyvenv.cfg`), ele agora ignora esse executável e procura uma instalação base válida do Python 3.11+ antes de recriar o `.venv` do QualiMatch.

## v3.8.16 — Bootstrap Python Install Manager
O instalador valida a execução real do runtime Python antes de criar `.venv` e pode instalar Python 3.12 automaticamente via `py install 3.12` quando o novo Python Install Manager estiver presente sem runtimes instalados.

## v3.8.17 — Bootstrap Python Install Manager
Correção de inicialização para Windows onde `py install 3.12` instala o runtime em `%LocalAppData%\Python\pythoncore-3.12-64`, mas os aliases/launcher não são detectados imediatamente. O bootstrap agora usa diretamente o executável real instalado.

## v3.8.18 — Duplicados + Dashboard mensal + Contratada sem meta
- BV > Arquivos por medição: botão **Remover duplicados** arquiva em lote as ocorrências marcadas como DUPLICADO, preservando uma ocorrência original e sem apagar arquivos físicos do SharePoint/OneDrive.
- Dashboard BV: nova **Visão financeira por mês** e tendências dos cards calculadas mês contra mês.
- Contratada > Visão geral: gráfico mensal de entregas sem linha de meta.
- Sem migração de banco; parser BI330 permanece 3.8.13; bootstrap da v3.8.17 preservado.


## v3.8.19 — Remoção de duplicados em BV > Certificados

O atalho **Remover duplicados** agora fica na própria aba **BV > Certificados**. Ele remove em lote apenas cópias que já foram classificadas tecnicamente como `DUPLICADO`, preserva a ocorrência canônica e não usa somente o número do certificado como critério. A cópia removida fica registrada como `DUPLICADO_REMOVIDO`, evitando reaparecer em sincronizações enquanto o arquivo não for alterado.

## v3.8.20 — Filtros Mxx, pendências e árvores

A v3.8.20 parte da cópia personalizada da v3.8.19 enviada pelo usuário e preserva as alterações visuais já aplicadas nela.

- Dashboard e BV > Certificados agora possuem filtro por medição Mxx, usando ciclo do dia 11 ao dia 10 do mês seguinte.
- Pendências BV ganharam cobertura adicional para certificados legados, incluindo vínculos formais e fallback conservador por data no nome do PDF; isso corrige o falso pendente observado no BI330-0169.
- Contratada > Pendências passa a apontar linhas da d.KIT sem Data Aplicação, exceto quando KMI e KMF estiverem ambos preenchidos.
- Administração > Histórico permite pesquisar sincronizações e alterações manuais por data.
- O fundo ganhou árvores discretas integradas à paisagem existente.
- O banco empacotado não exige migração e foi preservado sem alteração.

## v3.11.1 — Monitor BV sem bloqueio da BD_QUALI

- Certificados novos ou corrigidos no SharePoint são importados e disponibilizados no site antes do processamento da planilha `BD_QUALI`.
- A atualização automática da `BD_QUALI` passa a usar uma fila independente, evitando que um Excel lento ou bloqueado interrompa a leitura da ARENA ou da PAVIDEZ.
- O status exibido pelo monitor passa a considerar sempre o processamento mais recente de cada arquivo.
