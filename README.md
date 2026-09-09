# QualiMatch — Portfolio Edition

[![CI](https://github.com/LuanHCP/Qualimatch_portfolio/actions/workflows/ci.yml/badge.svg)](https://github.com/LuanHCP/Qualimatch_portfolio/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-REST_API-009688?logo=fastapi&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-Vanilla-F7DF1E?logo=javascript&logoColor=111)
![Status](https://img.shields.io/badge/status-portfolio-8b63e8)

Sistema web para **gestão e análise da qualidade em obras de infraestrutura**, com foco em certificados laboratoriais, medições, pendências documentais e indicadores técnicos.

> Esta é uma edição pública e sanitizada para portfólio. Todos os dados utilizados são sintéticos e não representam empresas, contratos, documentos ou operações reais.

---

## Visão geral

O **QualiMatch** nasceu como uma solução para centralizar informações que normalmente ficam espalhadas entre certificados, planilhas e controles operacionais.

Nesta Portfolio Edition, o projeto demonstra como transformar esse fluxo em uma aplicação web com:

- indicadores executivos;
- regras técnicas automatizadas;
- filtros operacionais;
- análise de certificados;
- identificação de pendências;
- organização de medições;
- API REST;
- interface web responsiva;
- testes automatizados e CI.

## Demonstração funcional

A aplicação possui quatro áreas principais:

| Módulo | Objetivo |
| --- | --- |
| **Dashboard** | Consolidar indicadores, aprovações, reprovações, medições e pendências |
| **Certificados** | Consultar resultados técnicos com busca, filtros e paginação |
| **Pendências** | Identificar datas medidas que ainda não possuem documentação técnica válida |
| **Medições** | Visualizar a base operacional por contratada e ciclo |

A demonstração utiliza duas empresas fictícias, **Contratada A** e **Contratada B**, e rodovias/trechos totalmente sintéticos.

## Regras técnicas demonstradas

O domínio da aplicação mantém as regras separadas da interface.

Na configuração padrão da demo:

- **Volume de vazios (Vv):** aprovado entre **3,5% e 7,5%**;
- **Relação A/B:** aprovada a partir de **90%**;
- qualquer resultado fora dos limites classifica o certificado como **REPROVADO**;
- ausência de ensaio é exibida como **SEM RESULTADO**.

Os limites podem ser alterados por variáveis de ambiente.

```env
VV_MIN=3.5
VV_MAX=7.5
AB_MIN=90
```

## Tecnologias

### Backend
- Python 3.12+
- FastAPI
- Uvicorn
- API REST em JSON

### Frontend
- HTML5
- CSS3
- JavaScript sem framework
- layout responsivo

### Qualidade de código
- Pytest
- GitHub Actions
- validação de sintaxe JavaScript
- compilação automática dos módulos Python

## Arquitetura

```text
┌─────────────────────┐
│      Frontend       │
│ HTML / CSS / JS     │
└─────────┬───────────┘
          │ HTTP / JSON
          ▼
┌─────────────────────┐
│       FastAPI       │
│ Rotas e paginação   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   Camada de domínio │
│ Vv • A/B • ciclos   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   Dados sintéticos  │
│ Certificados / RDO  │
└─────────────────────┘
```

Mais detalhes em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Endpoints principais

| Método | Endpoint | Descrição |
| --- | --- | --- |
| GET | `/api/health` | Estado da aplicação |
| GET | `/api/dashboard` | Indicadores consolidados |
| GET | `/api/certificates` | Certificados com filtros e paginação |
| GET | `/api/measurements` | Medições operacionais |
| GET | `/api/pending` | Pendências documentais |

O FastAPI também disponibiliza documentação interativa automaticamente em:

```
http://127.0.0.1:8000/docs
```

## Executar localmente

### 1. Clonar

```bash
git clone https://github.com/LuanHCP/Qualimatch_portfolio.git
cd Qualimatch_portfolio
```

### 2. Criar ambiente virtual

```bash
python -m venv .venv
```

No Windows:

```bash
.venv\Scripts\activate
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Iniciar

```bash
python run.py
```

Acesse:

```
http://127.0.0.1:8000
```

## Estrutura do projeto

```text
Qualimatch_portfolio/
├── app.py
├── domain.py
├── demo_data.py
├── run.py
├── requirements.txt
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── docs/
│   └── ARCHITECTURE.md
└── tests/
    ├── conftest.py
    └── test_domain.py
```

## O que este projeto demonstra

Do ponto de vista de desenvolvimento de software, o projeto apresenta:

- modelagem de regras de negócio;
- separação entre API, domínio e interface;
- criação de endpoints REST;
- paginação server-side;
- filtros combináveis;
- tratamento de estados técnicos;
- organização de dados para dashboards;
- design de interface administrativa;
- testes automatizados;
- integração contínua.

## Privacidade e dados

Esta edição foi construída especificamente para exposição pública.

Ela não contém:

- certificados reais;
- planilhas operacionais;
- banco de produção;
- credenciais;
- caminhos locais;
- nomes de clientes ou fornecedores;
- documentos internos;
- histórico do sistema utilizado em ambiente real.

Os exemplos presentes no repositório foram criados exclusivamente para demonstração.

---

### Autor

Desenvolvido por **Luan HCP** como projeto de software, automação e análise aplicada à gestão da qualidade.
