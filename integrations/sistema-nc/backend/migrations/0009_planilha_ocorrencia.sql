-- Permite manter linhas distintas da planilha que compartilham
-- Unidade + nº Emissão + Contrato. A ordem da ocorrência dentro do arquivo
-- diferencia cada registro de maneira estável entre sincronizações.
ALTER TABLE ncs
  ADD COLUMN IF NOT EXISTS planilha_ocorrencia integer NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS ncs_planilha_ocorrencia_idx
  ON ncs (sede_id, unidade_planilha, numero_emissao_planilha,
          contrato_planilha_raw, planilha_ocorrencia);
