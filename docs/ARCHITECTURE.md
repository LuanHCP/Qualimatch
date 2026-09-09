# Arquitetura — Portfolio Edition

## Objetivo

A edição pública preserva os conceitos técnicos do QualiMatch sem carregar dados ou integrações do ambiente real.

## Fluxo

```
Frontend
  │
  │ HTTP / JSON
  ▼
FastAPI
  ├── Dashboard
  ├── Certificados
  ├── Pendências
  └── Medições
  │
  ▼
Camada de domínio
  ├── classificação Vv
  ├── classificação A/B
  └── ciclos mensais
  │
  ▼
Dados sintéticos
```

## Versão privada

A versão de desenvolvimento possui recursos adicionais como autenticação, PostgreSQL, importação de planilhas, processamento de PDFs, sincronização de arquivos, auditoria e automações. Esses componentes não fazem parte deste repositório público porque dependem de contexto e dados operacionais.

## Princípios

- domínio separado da interface;
- API REST previsível;
- regras técnicas testáveis;
- configuração por ambiente;
- dados de demonstração reproduzíveis;
- nenhuma dependência de infraestrutura corporativa.
