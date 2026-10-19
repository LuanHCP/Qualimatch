CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS app_users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'Analista',
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Controle de acesso por Sede (PRVias, SPVias, MinasSP...): administrador
-- (is_admin) enxerga e gerencia todas as Sedes; os demais usuários ficam
-- restritos às Sedes listadas em "sites". ADD COLUMN IF NOT EXISTS deixa
-- seguro rodar este script de novo num banco "tracos_teste" já existente
-- (é só rodar criar_banco.bat novamente).
ALTER TABLE app_users ADD COLUMN IF NOT EXISTS is_admin BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE app_users ADD COLUMN IF NOT EXISTS sites TEXT[] NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS traces (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  code TEXT NOT NULL UNIQUE,
  unit TEXT NOT NULL,
  company TEXT NOT NULL,
  contract TEXT NOT NULL,
  category TEXT NOT NULL,
  material TEXT NOT NULL,
  place TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('Aprovado','Não conforme','Restrito','Cancelado','Em análise','Solicitado')),
  owner TEXT NOT NULL,
  note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trace_history (
  id BIGSERIAL PRIMARY KEY,
  trace_id UUID NOT NULL REFERENCES traces(id) ON DELETE CASCADE,
  status TEXT NOT NULL,
  changed_by TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_traces_status ON traces(status);
CREATE INDEX IF NOT EXISTS idx_traces_unit ON traces(unit);
CREATE INDEX IF NOT EXISTS idx_history_trace ON trace_history(trace_id, created_at);

INSERT INTO app_users(name,email,password_hash,role,is_admin,sites)
VALUES ('Administrador Demo','admin@qualimatch.local',crypt('Demo@2026',gen_salt('bf')),'Administrador',TRUE,'{}')
ON CONFLICT (email) DO UPDATE SET is_admin=TRUE,active=TRUE;

INSERT INTO app_users(name,email,password_hash,role,is_admin,sites)
SELECT
  'Usuário Demonstração ' || lpad(n::text,3,'0'),
  'usuario' || lpad(n::text,3,'0') || '@qualimatch.local',
  crypt('Demo@2026',gen_salt('bf')),
  CASE WHEN n % 3 = 0 THEN 'Consulta' ELSE 'Analista de Qualidade' END,
  FALSE,
  CASE WHEN n % 2 = 0 THEN ARRAY['PRVias'] ELSE ARRAY['SPVias','MinasSP'] END
FROM generate_series(2,200) n
ON CONFLICT (email) DO NOTHING;

INSERT INTO traces(code,unit,company,contract,category,material,place,status,owner,note,created_at,updated_at)
SELECT
  'TR-DEMO-' || lpad(n::text,4,'0'),
  (ARRAY['PRVias','SPVias','MinasSP'])[1 + (n % 3)],
  (ARRAY['Construtora Alfa','Construtora Beta','Engenharia Gama'])[1 + (n % 3)],
  'CT-DEMO-' || lpad((1 + n % 8)::text,2,'0'),
  (ARRAY['CBUQ','Concreto','MRAF','BGS'])[1 + (n % 4)],
  'Material fictício ' || (1 + n % 12),
  'Usina Demo ' || (1 + n % 5),
  (ARRAY['Aprovado','Aprovado','Em análise','Restrito','Não conforme','Solicitado'])[1 + (n % 6)],
  'Equipe Demonstração',
  'Registro gerado automaticamente; não representa obra real.',
  now() - (n || ' days')::interval,
  now() - ((n % 30) || ' days')::interval
FROM generate_series(1,200) n
ON CONFLICT (code) DO NOTHING;

INSERT INTO trace_history(trace_id,status,changed_by,created_at)
SELECT id,status,'Gerador da base demo',created_at FROM traces
WHERE code LIKE 'TR-DEMO-%'
  AND NOT EXISTS (SELECT 1 FROM trace_history h WHERE h.trace_id=traces.id);
