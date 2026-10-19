# Validação — QualiMatch v3.7.1

## Objetivo
Validar a primeira escrita segura de BI330 na estrutura real das planilhas BD_QUALI de ARENA e PAVIDEZ, sem sobrescrever os arquivos de origem.

## Estruturas reais verificadas
- ARENA: `BD_QUALI` em tabela iniciada na linha 11, 176 colunas.
- PAVIDEZ: `BD_QUALI` em tabela iniciada na linha 11, 194 colunas.
- Todos os campos de entrada usados pela ferramenta existem nos dois modelos.
- Campos calculados do bloco Vv/espessura foram mantidos como fórmulas do próprio Excel.

## Teste de linha nova — ARENA
Uma linha real da medição foi clonada para a primeira linha após o fim da tabela.

Verificado:
- LINHA MEDIÇÃO preservada;
- Data/rodovia/trecho e dados-base da medição preservados;
- Nº CERTIFICADO, datas, Rice, Vv e estatísticas preenchidos;
- fórmulas de K/XLOOKUP, % reprovação, média em cm, reprovação individual e RESUMO STATUS preservadas;
- fórmulas compartilhadas foram convertidas em fórmulas normais equivalentes na nova linha;
- referência da tabela ampliada até a nova linha;
- ZIP/XLSX estruturalmente válido;
- original não alterado.

## Teste de linha nova — PAVIDEZ
Repetido no modelo PAVIDEZ, incluindo fórmulas shared e fórmulas array/dynamic.

Verificado:
- tabela expandida para a nova linha;
- fórmulas compartilhadas materializadas sem atravessar/corromper células;
- referências relativas deslocadas como em uma cópia de linha do Excel;
- fórmulas array mantêm referência ajustada à nova linha;
- estrutura ZIP válida.

## Proteções
- Divergência de quantidade existente × CPs esperados bloqueia escrita.
- PDF PARCIAL ou CP em REVISAR/SEM MEDIÇÃO bloqueia escrita.
- Número no arquivo diferente do número interno bloqueia escrita.
- Ausência de linha-modelo bloqueia escrita.
- LINHA MEDIÇÃO da fonte atual é conferida contra o banco antes da geração.
- Original nunca é sobrescrito nesta versão.

## Recomendação operacional
Gerar a cópia, abrir no Microsoft Excel para o recálculo completo e conferir algumas linhas antes de substituir qualquer rotina manual. A escrita direta no SharePoint deve ser uma etapa posterior à validação desta cópia.

## PDFs reais da validação
Os seis BI330 fornecidos foram reprocessados com a v3.7.1:
- 65 linhas esperadas no total;
- 47 vínculos automáticos;
- 18 vínculos para revisão;
- 2 certificados ficaram prontos para geração segura no estado atual da BD_QUALI: BI330-0388 (Arena, 9 linhas) e BI330-0468 (Pavidez, 11 linhas);
- os demais foram bloqueados por revisão, divergência de número ou divergência entre quantidade existente e quantidade de CPs.

Foram geradas cópias reais de teste das planilhas Arena e Pavidez com esses certificados prontos. Os XLSX passaram no teste estrutural ZIP e mantiveram as fórmulas críticas.

## Testes automatizados
- 93 testes `pytest` aprovados.
- JavaScript validado com `node --check`.
- Python compilado sem erros com `compileall`.
