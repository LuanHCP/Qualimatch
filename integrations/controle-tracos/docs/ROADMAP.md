# Próximas evoluções

## Integração com SharePoint (pasta local sincronizada) — implementado

Mesmo padrão já usado no QualiMatch: um campo de configuração com o
caminho local da pasta sincronizada pelo OneDrive/SharePoint, lido e
escrito pelo servidor local (sem chamada externa nenhuma).

- campo "Caminho local sincronizado" na aba Ferramentas, acima da lista de
  traços;
- os anexos da carta traço e do checklist agora são salvos de verdade no
  servidor local (`uploads/<id>/`), não só o nome do arquivo;
- ao mudar o status de um traço, os arquivos são movidos para a subpasta
  correspondente ao novo status (`.../Aprovado/`, `.../Não conforme/`,
  etc.), saindo da subpasta do status anterior;
- versão futura, se fizer sentido: também importar automaticamente novas
  cartas-traço que apareçam numa subpasta de entrada da mesma pasta
  sincronizada.

## Selos de status — parcialmente implementado

Pedido: usar os selos reais da empresa nos carimbos, em vez do ícone
genérico de escudo.

- selos recebidos até agora: **Aprovado** (CONFORME, verde), **Não
  conforme** (vermelho) e **Restrito** (amarelo) — recortados do PDF
  enviado, com fundo transparente, e já em uso nos botões de carimbo da
  aba Ferramentas (`public/selos/`, mapeamento em `statusSeals` no
  `lib/trace-data.ts`);
- pendente: selos de **Cancelado**, **Em análise** e **Solicitado** —
  continuam com o ícone genérico de escudo até o usuário enviar as
  imagens correspondentes.

## Ferramenta de carimbo visual no PDF — implementado (2ª tentativa, mais segura)

Pedido: em vez de só mudar o status no site, poder abrir o PDF da carta
traço e posicionar visualmente o selo/carimbo (imagem) no lugar desejado
da página, com pré-visualização ao vivo.

- primeira tentativa (revertida): carregava pdf.js e pdf-lib via `<script>`
  de CDN dentro do componente — quebrou a renderização do app inteiro (erro
  genérico "internal error" do vinext em toda requisição, até na tela de
  login); a causa mais provável, olhando com mais calma, não foi a CDN em
  si, e sim uma tag JSX sem fechamento correto introduzida naquela edição —
  como todas as telas do app vivem no mesmo arquivo `app/page.tsx`, um erro
  de sintaxe em qualquer parte dele quebra a compilação da página inteira,
  inclusive o login, o que bate exatamente com o sintoma observado;
- segunda tentativa (esta): `pdfjs-dist` e `pdf-lib` agora são dependências
  normais do `package.json` (instaladas via `npm install`, sem CDN); o
  carregamento das duas libs acontece por `import()` dinâmico só quando o
  usuário realmente clica para carimbar um status com selo real, nunca no
  carregamento inicial da página; o worker do pdf.js foi copiado como
  arquivo estático (`public/pdf.worker.min.mjs`) para não depender de
  nenhuma configuração especial de empacotador;
- desta vez o arquivo `app/page.tsx` foi validado com o compilador do
  TypeScript (checagem de sintaxe/JSX real, não só contagem de
  parênteses/chaves) antes de enviar, para pegar exatamente o tipo de erro
  que causou o problema anterior;
- como usar: na aba Ferramentas, ao clicar num status que já tem selo real
  (Aprovado/Não conforme/Restrito), abre a pré-visualização com a página 1
  do PDF anexado e o selo arrastável/redimensionável por cima; "Confirmar
  carimbo" gera uma cópia carimbada (`carimbado-<nome>.pdf`) via pdf-lib,
  salva no servidor local e só então muda o status; se não houver PDF
  anexado ao traço, ou se algo falhar ao carregar, aparece a opção
  "Carimbar sem posicionar" (comportamento antigo, instantâneo);
- se o app quebrar de novo ao usar essa ferramenta, me avise com o print do
  erro (F12 → Console, ou o texto que aparece na tela) para eu investigar
  com essa pista em mãos.

Nenhuma conexão ou publicação no SharePoint foi implementada nesta versão.
