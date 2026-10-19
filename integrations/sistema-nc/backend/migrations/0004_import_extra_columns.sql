-- Colunas adicionais para preservar o valor bruto de origem de linhas
-- importadas da planilha de controle (rastreabilidade e auditoria da
-- importação, além da chave de deduplicação nº emissão + unidade + contrato).
ALTER TABLE ncs ADD COLUMN contrato_planilha_raw text;
ALTER TABLE ncs ADD COLUMN tipo_planilha_raw text;
