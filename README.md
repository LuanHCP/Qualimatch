# QualiMatch — Portfolio Edition

> Edição pública e sanitizada de um sistema de gestão da qualidade aplicado a obras de infraestrutura.

Esta versão foi preparada exclusivamente para portfólio. Ela **não contém dados reais, credenciais, PDFs, planilhas, caminhos corporativos, nomes de clientes/fornecedores nem histórico do ambiente de produção**.

## O que a demonstração mostra

- Dashboard executivo com indicadores técnicos
- Gestão e consulta de certificados de laboratório
- Regras configuráveis de aprovação por Vv e relação A/B
- Pendências de documentação
- Medições com filtros e paginação
- Ciclos operacionais mensais
- API REST com FastAPI
- Frontend responsivo em HTML/CSS/JavaScript
- Dados sintéticos para execução local
- Testes automatizados

## Stack

- Python 3.12+
- FastAPI
- Uvicorn
- HTML / CSS / JavaScript
- Pytest

## Executar

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Abra `http://127.0.0.1:8000`.

## Estrutura

```
app.py              API e entrega do frontend
domain.py           regras técnicas e ciclos
demo_data.py        base sintética
frontend/           interface
tests/              testes unitários
docs/ARCHITECTURE.md
```

## Sobre a sanitização

O repositório de desenvolvimento real permanece privado. Esta edição pública foi criada como uma base independente e sem histórico operacional.

Projeto desenvolvido para demonstrar arquitetura, automação, análise de dados e desenvolvimento de sistemas de qualidade.
