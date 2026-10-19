# Validação v3.8.10

- Fallback de linha estrutural quando a Linha de Medição ainda não existe em `quality_rows`.
- Validação de prioridade para linha exata quando ela existe.
- Sanitização do template estrutural: valores constantes antigos são apagados; fórmulas são preservadas.
- Reconstrução dos campos-base a partir de `measurements`/`raw_json`.
- Teste real usando `BD.QUALIDADE_ARENA_v02`: nova linha criada a partir de modelo genérico, com LINHA MEDIÇÃO e RODOVIA novas, BI330 preenchido e KIT ID antigo removido.
- Testes completos do projeto executados após a alteração: **149/149 aprovados**.
- Python compilado e JavaScript validado.
- Smoke adicional na BD.QUALIDADE_PAVIDEZ real: fallback estrutural gerou 1 nova linha válida sem erro.
