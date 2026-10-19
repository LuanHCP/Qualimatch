# Notificações de novos certificados por e-mail

Após atualizar os arquivos, reinicie o QualiMatch pelo inicializador habitual.
As tabelas de preferências e fila são criadas automaticamente no SQLite ou PostgreSQL,
sem alterar os certificados existentes. Nenhum usuário é inscrito automaticamente.

## Ativar

1. Entre na sua conta e abra um ambiente.
2. Clique no sino e em **Notificações por e-mail**.
3. Marque **BV — novos certificados** e salve.

É necessário ter acesso à BV. O destinatário é sempre o e-mail da própria conta.
Os avisos começam nas próximas importações de certificados novos pelas fontes
`bv_documentos` e `certificados`. A base já cadastrada, correções, releituras,
duplicados e uploads manuais não geram estes avisos. Importação não significa
aprovação técnica: PDFs com leitura parcial precisam ser conferidos no site.

## Configuração no servidor

Reutiliza as variáveis SMTP existentes em `.env`: `SMTP_HOST`, `SMTP_PORT`,
`SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_STARTTLS` e `SMTP_SSL`.
Use os dados fornecidos pela TI/provedor, sem publicar senhas no Git.
Configure `APP_BASE_URL` com o endereço do QualiMatch acessível aos destinatários
para incluir o link no e-mail. Sem esse endereço, o aviso é enviado sem link.
Reinicie o servidor após alterar essas variáveis.

## Notificações da área de trabalho

No sino do QualiMatch, abra **Configurar avisos** e escolha **Ativar neste
computador**. O navegador solicita permissão uma única vez e passa a exibir
avisos nativos do Windows para certificados BV novos. A ativação grava o último
certificado existente como ponto inicial, portanto não dispara a base antiga.

A preferência fica somente no navegador e por usuário. O QualiMatch deve
permanecer aberto em uma aba, mesmo minimizada. A API de notificações exige
`localhost` ou HTTPS; em um endereço HTTP comum da rede o navegador pode bloquear
a permissão. Clicar no aviso abre a aba de certificados.

O servidor, o monitor e o OneDrive/SharePoint precisam estar funcionando.
Não é um webhook direto do SharePoint: o aviso depende de o arquivo chegar à
pasta local e ser importado no QualiMatch. A fila é verificada a cada 30 segundos,
com até 20 e-mails por rodada. Esse intervalo não inclui o tempo do OneDrive,
da extração do PDF, de filas acumuladas ou da entrega pelo provedor.

## Falhas e cancelamento

Sem SMTP configurado, os avisos permanecem na fila sem consumir tentativas.
Falhas de envio têm até cinco tentativas com intervalos crescentes. A tela mostra
a quantidade na fila, falhas finais e o último envio. Os detalhes SMTP ficam em
Administração > Histórico. Não há botão de reenvio manual nesta primeira versão.

Desativar cancela a fila pendente, inclusive tentativas com falha. Reativar não
reenvia o histórico. Acesso à BV e situação da conta são conferidos novamente
antes do envio. Uma mensagem já entregue ao provedor não pode ser cancelada.

A fila sobrevive a reinicializações e impede duplicidade por usuário/certificado
nas releituras normais. Como SMTP não oferece confirmação transacional junto ao
banco, uma queda exatamente após o provedor aceitar o e-mail e antes de registrar
o envio pode gerar uma repetição na recuperação, após 15 minutos.

## Testes locais (sem e-mails reais)

```text
.venv\Scripts\python.exe -m pytest tests/test_email_notifications.py -q
node tests/frontend_email_notifications.cjs
```

Os testes usam banco temporário e remetente simulado. A entrega real depende da
configuração SMTP do ambiente e não é comprovada por esses testes.
