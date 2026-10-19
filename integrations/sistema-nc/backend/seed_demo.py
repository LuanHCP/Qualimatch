#!/usr/bin/env python3
"""Carrega os dados de demonstração (SEDEs, contratadas, contratos e
biblioteca de textos padronizados) que antes vinham embutidos no
localStorage do protótipo (assets/js/db.js -> SEED_DATA). É o equivalente
a "migrar os dados atuais" do protótipo: nenhum usuário de demonstração é
criado aqui (usuários exigem senha real — use bootstrap_admin.py e a tela
de Administração). Idempotente: não duplica se já existir uma SEDE com a
mesma sigla.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db  # noqa: E402

SEDES = [
    dict(sigla="MinasSP", nome="Minas SP", razao_social="Concessionária Minas SP (exemplo)", logo_letra="MSP",
         cor_primaria="#5b3fa0", cor_secundaria="#2e6c8e", nomenclatura_nc="RNC", nomenclatura_ac="RACP",
         mascara_numeracao="{TIPO}-{SEQ}/{ANO}", prazo_padrao_dias=3, dias_uteis=True, encerramento=True,
         areas=["Implantação", "Manutenção", "Operação"],
         disciplinas=["Pavimentação", "Drenagem: Bueiros/Galerias", "Segurança do Trabalho: Equipamentos", "Sinalização",
                       "Meio Ambiente", "Laboratório e Controle Tecnológico"]),
    dict(sigla="SPVias", nome="SPVias", razao_social="Concessionária SPVias (exemplo)", logo_letra="SPV",
         cor_primaria="#1d6f42", cor_secundaria="#c8791f", nomenclatura_nc="NC", nomenclatura_ac="AC",
         mascara_numeracao="SPV_{TIPO}_{SEQ}_{ANO}", prazo_padrao_dias=5, dias_uteis=True, encerramento=False,
         areas=["Implantação", "Manutenção", "Duplicação"],
         disciplinas=["Pavimentação", "Drenagem: Bueiros/Galerias", "Terraplenagem", "Sinalização", "Segurança do Trabalho: Equipamentos"]),
    dict(sigla="PRVias", nome="PRVias", razao_social="Concessionária PRVias (exemplo)", logo_letra="PRV",
         cor_primaria="#2e6c8e", cor_secundaria="#af4634", nomenclatura_nc="RNC", nomenclatura_ac="AC",
         mascara_numeracao="{SIGLA}_{TIPO}_{SEQ}_{ANO}", prazo_padrao_dias=2, dias_uteis=False, encerramento=False,
         areas=["Implantação", "Manutenção", "Qualidade"],
         disciplinas=["Pavimentação", "Laboratório e Controle Tecnológico", "Equipamentos", "Sinalização"]),
]

CONTRATADAS = ["FBS Construção Civil e Pavimentação S/A", "Dromos Infraestrutura", "Construtora Exemplo PR"]

CONTRATOS = [
    ("MinasSP", "CW260410", "FBS Construção Civil e Pavimentação S/A",
     "Intervenções e obras de recuperação do pavimento na BR-381, trecho km 90,0 (Guarulhos/SP) a km 845,0 (Pouso Alegre/MG)",
     "2025-01-01", "2027-12-31"),
    ("SPVias", "SPV-2026-045", "Dromos Infraestrutura",
     "Duplicação da Rodovia SP-250, km 45,000 ao km 68,700 — Lote 1", "2025-06-01", "2028-06-01"),
    ("PRVias", "PRV-2026-012", "Construtora Exemplo PR",
     "Serviços de manutenção e restauração de pavimento na BR-376, trecho km 120 ao km 180", "2025-03-01", "2027-03-01"),
]

TEXTOS = [
    ("Pavimentação", "Espessura", "", "O segmento avaliado não atendeu ao critério mínimo de espessura de camada estabelecido em projeto. Durante as verificações realizadas, o valor obtido ficou abaixo do percentual mínimo especificado, caracterizando não conformidade em relação ao requisito técnico aplicável."),
    ("Pavimentação", "Volume de Vazios", "", "Os ensaios de controle tecnológico indicaram volume de vazios da mistura asfáltica fora da faixa especificada em projeto, o que pode comprometer a durabilidade e o desempenho estrutural do revestimento executado."),
    ("Pavimentação", "Teor de Betume", "", "Foi constatada variação no teor de ligante asfáltico em relação à dosagem de projeto estabelecida para a mistura, com resultado fora da faixa de aceitação especificada, exigindo verificação da usina e do material já aplicado."),
    ("Pavimentação", "Granulometria", "", "A curva granulométrica do agregado/mistura apresentou desvio em relação à faixa de projeto especificada, podendo comprometer o desempenho mecânico do revestimento."),
    ("Pavimentação", "Segregação", "", "Foram identificados pontos com segregação da mistura asfáltica na camada de rolamento, com indícios de desagregação precoce do material, evidenciando deficiência na uniformidade da mistura aplicada."),
    ("Pavimentação", "Pintura de Ligação", "", "Não foi respeitado o tempo necessário para a ruptura completa da pintura de ligação antes da aplicação da mistura asfáltica, em desacordo com as boas práticas executivas e os requisitos técnicos aplicáveis ao serviço."),
    ("Pavimentação", "Deflexão", "", "Foram constatados valores de bacia defletométrica superiores aos limites de projeto, indicando possível fadiga estrutural ou baixa capacidade de suporte do pavimento, exigindo avaliação estrutural complementar."),
    ("Pavimentação", "Trincamento", "", "Foi constatada ocorrência de rupturas superficiais no revestimento asfáltico executado — transversais, longitudinais ou tipo 'jacaré' — indicando fadiga ou reflexão de camadas inferiores, comprometendo a impermeabilidade e a integridade estrutural do pavimento."),
    ("Pavimentação", "Falha de Compactação", "", "Foi constatada execução do serviço sem a comprovação normativa mínima necessária de grau de compactação, comprometendo a rastreabilidade, a aceitação técnica e a confiabilidade da execução."),
    ("Drenagem", "Falhas em Drenagem", "", "Foram constatadas falhas na execução dos dispositivos de drenagem, incluindo acabamento inadequado, drenos sem saída para escoamento de água e caimentos incorretos, prejudicando o direcionamento adequado do fluxo."),
    ("Segurança do Trabalho", "Equipamento Quebrado", "", "Foi constatada a paralisação de equipamento(s) durante a execução dos serviços, resultando em interrupção do fluxo operacional e potencial impacto na qualidade e na segurança da atividade em execução."),
    ("Laboratório e Controle Tecnológico", "Falta de Ensaios ou Certificados", "", "Verificou-se que os equipamentos/materiais relacionados não possuem certificados ou ensaios de controle tecnológico vigentes, comprometendo a rastreabilidade metrológica das medições e a confiabilidade dos resultados dos serviços executados."),
    ("Laboratório e Controle Tecnológico", "Temperatura", "", "Foi constatado desvio de temperatura da mistura/material fora da faixa especificada em norma no momento da aplicação, podendo comprometer a homogeneidade e o desempenho da camada executada."),
    ("Laboratório e Controle Tecnológico", "Umidade", "", "Os ensaios indicaram teor de umidade do material fora da faixa admissível de projeto, exigindo verificação e eventual reprocessamento antes da aplicação/compactação."),
    ("Sinalização", "Sinalização Deficiente", "", "Foi constatada deficiência na sinalização horizontal/vertical do trecho executado, em desacordo com o projeto e com os requisitos de segurança viária aplicáveis."),
    ("Meio Ambiente", "Disposição Inadequada de Resíduos", "", "Foi constatada disposição inadequada de resíduos/materiais da obra, em desacordo com o plano de gerenciamento ambiental do contrato e com a legislação aplicável."),
    ("Acabamento", "Acabamento Inadequado", "", "Foi constatado acabamento inadequado do serviço executado, sem atendimento aos padrões estéticos e funcionais previstos em projeto, exigindo correção/refinamento pontual."),
    ("Equipamentos", "Calibração Vencida", "", "Constatou-se que equipamentos utilizados nas atividades laboratoriais/de campo apresentam selos de calibração com prazo de validade expirado, comprometendo a rastreabilidade metrológica das medições e a confiabilidade dos ensaios executados até a regularização."),
]


def main():
    for s in SEDES:
        existing = db.fetchone(f"SELECT id FROM sedes WHERE sigla = {db.lit(s['sigla'])};")
        if existing:
            print(f"SEDE {s['sigla']} já existe — pulando.")
            continue
        db.execute(f"""
            INSERT INTO sedes (sigla, nome, razao_social, logo_letra, cor_primaria, cor_secundaria,
                                nomenclatura_nc, nomenclatura_ac, mascara_numeracao, prazo_padrao_dias,
                                dias_uteis, encerramento_automatico_desconto, areas, disciplinas)
            VALUES ({db.lit(s['sigla'])}, {db.lit(s['nome'])}, {db.lit(s['razao_social'])}, {db.lit(s['logo_letra'])},
                    {db.lit(s['cor_primaria'])}, {db.lit(s['cor_secundaria'])}, {db.lit(s['nomenclatura_nc'])},
                    {db.lit(s['nomenclatura_ac'])}, {db.lit(s['mascara_numeracao'])}, {db.lit(s['prazo_padrao_dias'])},
                    {db.lit(s['dias_uteis'])}, {db.lit(s['encerramento'])}, {db.lit(s['areas'])}, {db.lit(s['disciplinas'])});
        """)
        print(f"SEDE {s['sigla']} criada.")

    contratada_ids = {}
    for nome in CONTRATADAS:
        existing = db.fetchone(f"SELECT id FROM contratadas WHERE lower(razao_social) = {db.lit(nome.lower())};")
        if existing:
            contratada_ids[nome] = existing["id"]
            continue
        row = db.fetchone(f"INSERT INTO contratadas (razao_social) VALUES ({db.lit(nome)}) RETURNING id;")
        contratada_ids[nome] = row["id"]
        print(f"Contratada '{nome}' criada.")

    for sigla, numero, contratada_nome, desc, ini, fim in CONTRATOS:
        sede = db.fetchone(f"SELECT id FROM sedes WHERE sigla = {db.lit(sigla)};")
        if not sede:
            continue
        existing = db.fetchone(f"SELECT id FROM contratos WHERE sede_id = {db.lit(sede['id'])} AND numero = {db.lit(numero)};")
        if existing:
            continue
        row = db.fetchone(f"""
            INSERT INTO contratos (sede_id, numero, descricao_obra, vigencia_inicio, vigencia_fim)
            VALUES ({db.lit(sede['id'])}, {db.lit(numero)}, {db.lit(desc)}, {db.lit(ini)}::date, {db.lit(fim)}::date)
            RETURNING id;
        """)
        cid = contratada_ids.get(contratada_nome)
        if cid:
            db.execute(f"INSERT INTO contrato_contratadas (contrato_id, contratada_id) VALUES ({db.lit(row['id'])}, {db.lit(cid)});")
        print(f"Contrato {numero} ({sigla}) criado.")

    for categoria, item, subitem, texto in TEXTOS:
        existing = db.fetchone(f"""
            SELECT id FROM textos_padrao WHERE sede_id IS NULL AND categoria = {db.lit(categoria)} AND item = {db.lit(item)};
        """)
        if existing:
            continue
        db.execute(f"""
            INSERT INTO textos_padrao (sede_id, categoria, item, subitem, texto)
            VALUES (NULL, {db.lit(categoria)}, {db.lit(item)}, {db.lit(subitem)}, {db.lit(texto)});
        """)
    # 200 registros operacionais fictícios. A condição externa torna o seed
    # idempotente sem depender de dados ou planilhas reais.
    db.execute("""
        INSERT INTO ncs (
            sede_id,tipo_core,contrato_id,contratada_id,numero_sequencial,ano,codigo_formatado,
            data_emissao,data_ocorrencia,responsavel_emissao_nome,area,disciplina,categoria,item,
            classificacao,rodovia,trecho,km_inicial,km_final,pista_sentido,faixa,descricao,
            valor_estimado,valor_retencao_proposto,valor_retencao_efetivo,prazo_resposta,
            status_atual,data_encerramento,origem,numero_emissao_planilha,unidade_planilha,
            situacao_planilha_raw
        )
        SELECT
            s.id,'NC',c.id,cc.contratada_id,n,extract(year from current_date)::int,
            'RNC-DEMO-' || lpad(n::text,4,'0'),current_date-(n*2),current_date-(n*2),
            'Fiscal Demonstração',(ARRAY['Implantação','Manutenção','Qualidade'])[1+(n%3)],
            (ARRAY['Pavimentação','Drenagem','Sinalização','Meio Ambiente','Laboratório'])[1+(n%5)],
            'Ocorrência demonstrativa','Item fictício ' || (1+n%12),
            (ARRAY['baixa','media','alta'])[1+(n%3)],
            (ARRAY['BR-101','BR-116','BR-277','PR-445'])[1+(n%4)],
            'Trecho fictício ' || (1+n%20),80+(n%100),81+(n%100),
            CASE WHEN n%2=0 THEN 'Norte' ELSE 'Sul' END,'Faixa 1',
            'Registro criado exclusivamente para demonstração do Sistema de Não Conformidades.',
            5000+(n*731.37)%95000,2500+(n*391.21)%42000,
            CASE WHEN n%5 IN (3,4) THEN 2500+(n*391.21)%42000 ELSE 0 END,
            now()+((10-(n%25)) || ' days')::interval,
            (ARRAY['aguardando_resposta','respondida','em_analise','em_execucao','encerrada'])[1+(n%5)],
            CASE WHEN n%5=4 THEN now()-(n || ' days')::interval ELSE NULL END,
            'importacao','RNC-DEMO-' || lpad(n::text,4,'0'),s.sigla,
            CASE WHEN n%5=4 THEN 'Encerrada' ELSE 'Em aberto' END
        FROM generate_series(1,200) n
        CROSS JOIN LATERAL (SELECT id,sigla FROM sedes ORDER BY sigla LIMIT 1) s
        LEFT JOIN LATERAL (SELECT id FROM contratos WHERE sede_id=s.id ORDER BY numero LIMIT 1) c ON TRUE
        LEFT JOIN LATERAL (SELECT contratada_id FROM contrato_contratadas WHERE contrato_id=c.id LIMIT 1) cc ON TRUE
        WHERE NOT EXISTS (SELECT 1 FROM ncs WHERE codigo_formatado LIKE 'RNC-DEMO-%');
    """)
    print(f"Biblioteca de textos padronizados: {len(TEXTOS)} verificados/criados.")
    print("Não conformidades fictícias: 200 verificadas/criadas.")
    print("Seed de demonstração concluído.")


if __name__ == "__main__":
    main()
