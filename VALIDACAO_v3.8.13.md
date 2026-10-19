# Validação v3.8.13 — Revalidação BV “Sem resultado”

## Auditoria do banco empacotado

A auditoria foi feita com SQLite em `mode=ro`, sem executar `init_db`, migração ou rotina de sincronização.

- Certificados ativos: **765**
- **APROVADO:** 116
- **REPROVADO:** 82
- **SEM RESULTADO:** **567**
  - PAVIDEZ: **336**
  - ARENA: **231**
- Os **567** certificados Sem resultado têm **0 CPs** registrados.
- 552/567 não tinham `service_date` na leitura legada.
- 557/567 não tinham segmento (`kmi/kmf`) completo na leitura legada.
- Os 949 registros de `certificate_files` do banco empacotado possuem `parser_version` vazio; portanto foram carregados antes do controle de versão atual do parser.
- `parsed_at` dos certificados ativos está concentrado em **13/08/2026**, confirmando que a Situação atual representa uma carga legada, e não uma tentativa com os parsers 3.8.11/3.8.12.

## Casos reais executados com o parser 3.8.13

| Certificado | Resultado | CPs | Observação |
|---|---|---:|---|
| BI330-0093 | APROVADO / CARREGADO | 10/10 | Datas de aplicação com `-E1`/`-E3` |
| BI330-0446 | APROVADO / CARREGADO | 6/6 | Faixa `Faixa adicional` |
| BI330-0471 | APROVADO / CARREGADO | 6/6 | Layout novo com Vv com filme |

Nos três casos, Rice, Gmb e Vv foram extraídos em suas colunas corretas.

## Cobertura de parser

Testes focados:

```text
pytest -q tests/test_pdf_parser.py tests/test_real_variants.py tests/test_rice_gmm_v327.py tests/test_v3813_semresultado_parser.py
16 passed
```

A v3.8.13 adiciona cobertura explícita para:

- faixa vazia;
- faixa textual/múltiplas palavras;
- etapa anexada ou separada da data de aplicação;
- linha visual de CP quebrada em múltiplas linhas de texto;
- layout com dois percentuais de Vv no final.

## Suíte geral

Em cópia isolada do projeto, a suíte geral passou em **153 testes** e apresentou 4 falhas preexistentes: 3 eram asserts de versão antiga (`v3.8.10`) e foram atualizados para a versão corrente; 1 depende do fixture externo `/mnt/data/BD.QUALIDADE_ARENA_v02(5).xlsx`, que não está incluído neste ambiente. Após a atualização dos asserts de versão, a única indisponibilidade esperada é esse fixture externo.

## Revalidação em lote

Foi incluída a rotina `reprocess_no_result_certificates()` e o botão **Validar sem resultado**. Ela:

1. filtra exatamente os certificados BV com `overall_status` vazio;
2. localiza os PDFs ativos já vinculados;
3. força a leitura desses PDFs com o `PARSER_VERSION = 3.8.13`;
4. atualiza apenas certificado/CPs/status técnico;
5. não chama a rotina de preenchimento automático da BD_QUALI;
6. ao final, mostra quantos foram corrigidos e quais permaneceram sem resultado.

## Limitação da validação neste ambiente

O ZIP guarda no banco os caminhos Windows/OneDrive dos PDFs, mas **não inclui fisicamente os 567 PDFs originais**. Por isso, não é possível executar aqui um dry-run real de todos os 567 arquivos. O lote completo será executado no computador operacional, onde esses caminhos existem, ao clicar em **Validar sem resultado** ou na próxima sincronização.

Isso é diferente de assumir que todos serão corrigidos: os que continuarem em Sem resultado após a revalidação serão as exceções reais que ainda exigem uma regra específica de parser ou revisão do próprio PDF.

## Integridade do banco

SHA-256 da v3.8.12 e da cópia usada na v3.8.13:

`30df10ae14d04e0b3cfe7f625c86ba4cbbf0ccbd0b964966fea7f0fd08cfeefe`

Nenhuma migração de schema é necessária.
