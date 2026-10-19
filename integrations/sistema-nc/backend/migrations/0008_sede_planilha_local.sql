ALTER TABLE sedes
  ADD COLUMN IF NOT EXISTS planilha_local_path text;

UPDATE sedes
SET planilha_local_path = ''
WHERE lower(sigla) = lower('PRVias')
  AND COALESCE(planilha_local_path, '') = '';
