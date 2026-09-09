# Arquitetura — QualiMatch Portfolio Edition

## Objetivo

A Portfolio Edition demonstra a arquitetura e os principais fluxos do QualiMatch sem depender de infraestrutura, credenciais, documentos ou dados operacionais externos.

Toda informação apresentada pela aplicação é criada localmente a partir de um conjunto determinístico de dados sintéticos.

## Visão de arquitetura

```text
Navegador
   │
   │ HTTP / JSON
   ▼
FastAPI
   │
   ├── BV
   │   ├── Dashboard
   │   ├── Certificados
   │   ├── Pendências
   │   └── Medições
   │
   ├── Contratada
   │   ├── Visão geral
   │   ├── Kits
   │   ├── Documentos
   │   └── Pendências
   │
   ├── Qualidade Geral
   │   ├── Traços
   │   └── Não Conformidades
   │
   └── Administração
       ├── Usuários
       ├── Indicadores
       └── Auditoria
   │
   ▼
Camada de domínio
   ├── classificação de Vv
   ├── classificação de A/B
   ├── estado técnico dos certificados
   └── ciclos de medição Mxx
   │
   ▼
SQLite local
   └── dados 100% sintéticos
```

## Componentes

### `app.py`

Responsável pela API FastAPI e pelas rotas utilizadas pelo frontend. Também aplica filtros, paginação e agregações necessárias para os diferentes ambientes.

### `database.py`

Cria o banco SQLite local, define o esquema das tabelas e gera os dados sintéticos utilizados na demonstração.

Entre as entidades demonstradas estão:

- certificados;
- medições;
- kits;
- documentos;
- traços;
- Não Conformidades;
- usuários;
- eventos de auditoria.

### `domain.py`

Mantém regras que não dependem da interface, como classificação técnica e cálculo dos ciclos Mxx.

### `frontend/`

Interface construída em HTML, CSS e JavaScript sem framework. A navegação é dividida em portais para representar diferentes perfis e contextos de uso.

## Decisões da edição pública

### SQLite no lugar de infraestrutura externa

A versão pública usa SQLite para que o projeto possa ser executado localmente sem configuração de servidor de banco de dados.

### Dados determinísticos

O gerador usa uma semente fixa. Isso faz com que o banco possa ser apagado e recriado mantendo um cenário estável para demonstrações, testes e screenshots.

### Integrações substituídas

Fluxos que, em um ambiente operacional, dependeriam de documentos, autenticação, sincronização ou serviços corporativos foram removidos ou representados por dados simulados.

A intenção é demonstrar arquitetura, interface e regras de negócio sem expor informações sensíveis ou criar dependência de infraestrutura privada.

## Princípios

- separação entre interface, API e domínio;
- API REST previsível;
- regras técnicas isoladas e testáveis;
- dados de demonstração reproduzíveis;
- execução local simples;
- nenhuma credencial necessária;
- nenhuma dependência de infraestrutura corporativa;
- segurança por sanitização da edição pública.
