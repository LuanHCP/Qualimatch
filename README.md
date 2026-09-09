# QualiMatch — Portfolio Edition

Versão pública e sanitizada do QualiMatch, preservando a identidade visual e o fluxo da aplicação de gestão de qualidade, mas utilizando **exclusivamente dados sintéticos**.

> Nenhum certificado, planilha, caminho local, empresa, valor financeiro ou registro operacional real é distribuído nesta edição.

## O que esta versão preserva

- Dashboard com visão financeira e técnica;
- filtros por contratada, status, medição Mxx e certificados;
- seleção múltipla de certificados no Dashboard;
- tabela de certificados com VV, espessura, A/B, contra-prova e status de leitura;
- 30 certificados por página;
- Pendências por data de execução;
- Medições com 40 linhas por página;
- modal de detalhes e corpos de prova;
- tema escuro/roxo, cartões, tabelas e hierarquia visual do sistema;
- cena de rodovia animada ao fundo para manter a identidade visual da aplicação.

## Banco local fictício

Ao iniciar a aplicação pela primeira vez, o QualiMatch cria automaticamente:

```text
data/qualimatch_demo.db
```

O arquivo é um banco **SQLite local**, preenchido com uma base determinística de demonstração:

- 68 certificados BI330 fictícios;
- mais de 150 linhas de medição;
- Contratada A e Contratada B;
- ciclos Mxx;
- aprovações, reprovações e resultados parciais;
- contra-provas;
- pendências;
- valores financeiros, extensão, CBUQ e CAP sintéticos.

Os nomes, rodovias, trechos, traços, datas e valores são inventados para portfólio.

### Recriar a base

Se quiser voltar a demo para o estado inicial:

```bash
python reset_demo.py
```

## Executar no Windows

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Depois acesse:

```text
http://127.0.0.1:8000
```

A documentação da API fica em:

```text
http://127.0.0.1:8000/docs
```

## Estrutura

```text
Qualimatch_portfolio/
├── app.py                 # API FastAPI
├── database.py            # SQLite + geração dos dados fictícios
├── domain.py              # regras técnicas e ciclos Mxx
├── reset_demo.py          # recria o banco local
├── run.py
├── requirements.txt
├── data/
│   └── qualimatch_demo.db # criado localmente e ignorado pelo Git
└── frontend/
    ├── index.html
    ├── styles.css
    └── app.js
```

## Regras técnicas demonstradas

Na base padrão de demonstração:

- Vv aprovado entre **3,5% e 7,5%**;
- relação A/B aprovada a partir de **90%**;
- espessura de demonstração aprovada a partir de **4,5 cm**;
- ausência de resultado permanece visível como **SEM RESULTADO**.

Os dados foram construídos apenas para demonstrar o funcionamento do software e não representam critérios contratuais de uma operação real.

## Privacidade

Esta edição foi preparada para GitHub e apresentação profissional. Ela não depende de SharePoint, PostgreSQL corporativo, PDFs internos ou planilhas de produção.

O banco SQLite é gerado localmente e está no `.gitignore`, evitando publicação acidental da base criada durante a execução.

---

Desenvolvido por **Luan HCP** como projeto de software, automação e análise aplicada à gestão da qualidade.
