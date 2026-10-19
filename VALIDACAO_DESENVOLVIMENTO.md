# Validação — QualiMatch v2.1.0

Validação feita em 13/08/2026 usando exatamente os arquivos enviados nesta rodada.

## Arena — qualidade

- `RELATÓRIO!O11`: **R$ 44.723.981,07**
- soma completa de `BD_QUALI[TOTAL SERVIÇO (R$)]`: **R$ 44.723.981,07**
- linhas válidas BD_QUALI: **2.265**
- extensão: **221.128 m**
- volume massa: **39.770,788 m³**
- CBUQ: **102.371,548 t**
- CAP: **5.272,064 t**
- aprovado: **R$ 26.511.351,92**
- pendente: **R$ 17.026.820,98**
- reprovado: **R$ 666.341,49**

## Pavidez — qualidade

- `RELATÓRIO!O11`: **R$ 115.438.471,81**
- soma completa de `BD_QUALI[TOTAL SERVIÇO (R$)]`: **R$ 115.438.471,81**
- `BD_QUALI!AV10` (SUBTOTAL filtrado): **R$ 4.183.292,78**
- linhas válidas BD_QUALI: **3.676**
- linhas visíveis no estado salvo do XLSX: **155**
- extensão: **395.052,4 m**
- volume massa: **66.238,792 m³**
- CBUQ: **167.065,09 t**
- aprovado: **R$ 84.172.454,51**
- pendente: **R$ 28.378.572,86**
- reprovado: **R$ 2.887.444,44**

O antigo valor em torno de R$ 4 milhões não era o total histórico: era apenas o SUBTOTAL do conjunto visível após filtro.

### CAP Pavidez

`RELATÓRIO!O15` traz **70.182.846,509 t**, valor impossível frente a 167.065,09 t de CBUQ. Foram encontradas também linhas da BD_QUALI com quantidade zero e CAP positivo de dezenas de milhares de toneladas. Por isso o fallback validado usa `QUANT PROJETO × TEOR ÓTIMO` por linha, totalizando **8.151,532844 t**.

## Medições

- Arena: **2.300** linhas válidas em `RDO_RESTAURA`.
- Pavidez: **3.617** linhas válidas em `RDO_RESTAURA`.

## Certificados reais

Foram processados os 15 PDFs enviados: **14 eventos de certificado** distintos, **15 documentos** e **191 linhas de amostra/fase**.

O número do BI330 se repete em eventos diferentes, por isso `(contratada, número)` não é uma chave válida. Exemplos encontrados:

- Arena BI330-0001: 11/07/2025 e 11/09/2025;
- Arena BI330-0003: 17/07/2025 e 13/08/2025;
- Pavidez BI330-0016: PR-090 em 27/08/2025 e BR-376 em 05/09/2025;
- Pavidez BI330-0021: 16/08/2025 (com contra-prova) e 22/08/2025.

O BI330-0021 de 16/08 foi validado com **23 amostras na rotina + 23 na fase de contra-prova**, preservando as duas fases no mesmo evento.

## Desempenho / idempotência

Teste ponta a ponta com 4 XLSX + 15 PDFs:

- primeira sincronização: ~**22,95 s**;
- segunda sincronização sem alterações: ~**0,004 s**;
- segunda sincronização: **0 registros reprocessados**;
- contagens e totais permaneceram idênticos.

## Testes automáticos

- Python compile: OK
- JavaScript syntax: OK
- pytest: **19 passed**
- FastAPI `/api/health`: HTTP 200
- Dashboard Arena: HTTP 200
- Dashboard Pavidez: HTTP 200

## Pendências v2.0.2
- ARENA: 16 dias pendentes
- PAVIDEZ: 15 dias pendentes
- Total: 31 dias
- 15/07/2025: reconhecido como atendido quando há certificado na mesma data de execução.
- Testes automatizados: 19 aprovados.


## Validação v2.1.0 — Data Ext. dos CPs / parser

- `certificates.extraction_date` criado e migrado automaticamente a partir de `raw_json.extraction_dates`.
- Lista e cards recentes ordenam/exibem `Data Ext. dos CPs`; filtros de período de certificados usam essa data.
- Matching e Pendências continuam usando datas de execução, nunca `extraction_date`.
- Banco incluso após migração: Arena **325/328** certificados com Data Ext. disponível; Pavidez **434/437**.
- Pendências permaneceram estáveis: Arena **16**, Pavidez **15**, total **31**.
- PDF de regressão BI330-0063: execução **29/09/2025**, Data Ext. CPs **01/10/2025**, BR-376, 15 CPs, leitura **OK**.
- `pytest`: **19 passed**.


## Validação v2.1.1 — Trecho / Segmento Ensaiado

- Parser de trecho padrão BR: OK.
- Parser PR com sufixo `- PR`: OK.
- Cabeçalho quebrado em linhas / modo layout: OK.
- Estacas com espaços (`552 + 980`): OK.
- Segmento em sentido decrescente (`315+960 a 314+970`): preservado.
- Fallback por CPs somente quando o cabeçalho falha: OK, marcado como estimado.
- Reprocessamento de parsers antigos sem origem do segmento: habilitado.
- Pendências após alteração: ARENA 16 / PAVIDEZ 15 / TOTAL 31.
- Suite: 24 testes aprovados.


## Validação v2.2.0 — gestão de certificados

- 27/27 testes automatizados aprovados.
- Migração adiciona `is_active`, `deleted_at`, `deleted_reason` e `manual_override` sem apagar registros existentes.
- Substituição validada com PDF real: mantém o ID e a contagem total; documentos anteriores viram `SUBSTITUIDO`.
- Exclusão lógica validada: remove somente o certificado selecionado das estatísticas/listas e preserva o registro no SQLite.
- `force=True` na sincronização não ressuscita um certificado excluído manualmente.
- Endpoints `/api/health`, `/api/dashboard`, `/api/certificates` e `/api/pending` retornaram HTTP 200.
- Pendências mantidas: ARENA = 16; PAVIDEZ = 15; total = 31.


## Validação v2.3.0 — filtros, rodovia/trecho e pizza

- `pytest -q`: **30 passed**.
- `node --check frontend/static/app.js`: sem erros.
- `python -m compileall`: sem erros.
- HTTP 200: `/`, `/api/health`, `/api/dashboard`, `/api/certificates-filter-options`, `/api/certificates` com filtros e `/api/pending`.
- Migração de rodovia no banco incluso: 581 certificados ativos sem rodovia antes da correção; **4** permanecem sem BR/PR após a migração porque o nome salvo não contém rodovia.
- Pendências após a alteração: **ARENA 16 / PAVIDEZ 15 / TOTAL 31**.
- Total de certificados ativos preservado: **765**.
