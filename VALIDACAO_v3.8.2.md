# Validação — QualiMatch v3.8.2

## Testes automatizados

- **127/127 testes aprovados**.
- `python -m compileall -q .`: aprovado.
- `node --check frontend/static/app.js`: aprovado.

## Dias reais de execução

A meta/dias de execução passou a usar datas de calendário distintas existentes na tabela `measurements`.

- várias linhas/faixas/trechos na mesma data = **1 dia de execução**;
- na visão `ALL`, Arena e Pavidez executando na mesma data = **1 dia real**;
- smoke test na base empacotada confirmou que nenhuma medição Mxx apresenta mais dias de execução do que o próprio período comporta;
- coberturas por dias de kit/certificado permanecem <= 100% no smoke test.

Exemplo da base empacotada na visão ALL para a meta mensal:
- junho/2026: 22 dias distintos com medição;
- julho/2026: 22 dias distintos com medição;
- agosto/2026 (até a base disponível): 7 dias distintos.

## Bloqueio de certificados duplicados

A validação compara o conteúdo técnico do BI330, ignorando apenas localização/nome físico do PDF. Entram na assinatura:

- contratada e número do certificado;
- datas de serviço e Data Ext. dos CPs;
- rodovia e segmento;
- traço e resultados de rotina/contra-prova;
- resumo estatístico por fase;
- todos os CPs com data, pista/sentido, faixa, estaca, posição, espessuras, A/B, Rice, Gmb e VV.

Também há atalho por hash do PDF para cópias byte a byte.

Comportamento:
- upload manual duplicado: HTTP **409** e nenhum novo certificado é criado;
- monitor automático: arquivo fica registrado como **DUPLICADO**, vinculado apenas para auditoria ao certificado já existente, e não é reprocessado em todo ciclo;
- reprocessamento do mesmo caminho continua permitido;
- arquivo do mesmo BI com conteúdo novo (ex.: contra-prova) continua permitido.

### Smoke test real

Foi feita uma cópia temporária do banco empacotado e processado o PDF real `BI330-0388_26_ARENA_REIS_BR376_TR1516-14.07.26-18.07.26(3).pdf`.

Resultado: a nova validação reconheceu o conteúdo já existente e bloqueou a inclusão apontando para o certificado **BI330-0388 / ID 321**.
