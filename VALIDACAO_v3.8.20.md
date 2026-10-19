# Validação — QualiMatch v3.8.20

## Escopo
Validação focada nas alterações solicitadas sobre a cópia personalizada da v3.8.19 enviada em 24/08/2026.

## Medições Mxx
- `M14` → 11/08/2026 a 10/09/2026: OK.
- `M13` → 11/07/2026 a 10/08/2026: OK.
- `M1` → 11/07/2025 a 10/08/2025: OK.
- Filtro disponível no Dashboard e em BV > Certificados: OK.

## BI330-0169 / Pendências BV
A validação do banco foi executada em modo somente leitura. Com a nova cobertura legado:
- ARENA, 29/11/2025 a 02/12/2025: nenhuma das datas verificadas do BI330-0169 permaneceu pendente.
- PAVIDEZ, 08/08/2025: não permaneceu pendente.
- PAVIDEZ, 25/11/2025: não permaneceu pendente.

A correção considera primeiro datas técnicas/vínculos/BD_QUALI e usa data presente no nome do PDF somente como fallback para registros legados sem Data ex. serviço e sem Data Aplicação dos CPs.

## Pendências da Contratada
- Data Aplicação vazia + KMI/KMF incompletos → pendência: OK.
- Data Aplicação vazia + KMI e KMF preenchidos → não gera pendência por data: OK.
- Linhas datadas existentes continuam seguindo a regra da coluna Entrega: OK.

## Histórico
- `sync_log` aceita filtro por prefixo ISO `YYYY-MM-DD`: OK.
- `change_history` aceita o mesmo filtro de data: OK.
- Interface possui Pesquisar/Limpar: OK.

## Front-end
- Árvores no background: OK.
- Cena personalizada de céu, avião, rodovia, pedágio e veículos preservada: OK.
- JavaScript validado com `node --check`: OK.

## Testes
- Testes focados da v3.8.20 + regressões de medição/pendências/duplicados: **22 aprovados**.
- Conjunto ampliado relacionado: **52 aprovados e 1 teste histórico incompatível com a customização do usuário**, pois esse teste antigo exige o painel `dashboard-financial-monthly`, removido propositalmente na versão personalizada enviada como base. O painel não foi reintroduzido.

## Banco
SHA-256 antes e depois da validação:
`30df10ae14d04e0b3cfe7f625c86ba4cbbf0ccbd0b964966fea7f0fd08cfeefe`

Nenhuma alteração no arquivo `data/qualimatch.db` durante a montagem/validação.
