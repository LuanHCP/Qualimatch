CREATE INDEX IF NOT EXISTS ncs_sede_status_data_idx ON ncs (sede_id, status_atual, data_emissao DESC);
CREATE INDEX IF NOT EXISTS ncs_sede_contrato_idx ON ncs (sede_id, contrato_id);
CREATE INDEX IF NOT EXISTS ncs_sede_contratada_idx ON ncs (sede_id, contratada_id);
CREATE INDEX IF NOT EXISTS ncs_sede_categoria_idx ON ncs (sede_id, categoria);
CREATE INDEX IF NOT EXISTS ncs_sede_prazo_idx ON ncs (sede_id, prazo_resposta) WHERE data_encerramento IS NULL;
CREATE INDEX IF NOT EXISTS ncs_updated_at_idx ON ncs (updated_at DESC);
CREATE INDEX IF NOT EXISTS audit_log_created_at_idx ON audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS nc_historico_nc_data_idx ON nc_historico (nc_id, data_hora DESC);
CREATE INDEX IF NOT EXISTS nc_anexos_nc_created_idx ON nc_anexos (nc_id, created_at DESC);
