-- ============================================================================
-- Sistema de Gestão de NC / RNC / AC-AP — schema inicial (PostgreSQL)
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS citext;     -- e-mail case-insensitive

CREATE TYPE perfil_usuario AS ENUM (
  'admin_geral', 'admin_sede', 'qualidade', 'fiscalizacao',
  'gestor_contrato', 'contratada', 'consulta'
);

-- ---------------------------------------------------------------- sedes ----
CREATE TABLE sedes (
  id                                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sigla                                text NOT NULL UNIQUE,
  nome                                 text NOT NULL,
  razao_social                        text,
  logo_letra                          text,
  cor_primaria                        text DEFAULT '#2e6c8e',
  cor_secundaria                      text DEFAULT '#c8791f',
  nomenclatura_nc                     text NOT NULL DEFAULT 'RNC',
  nomenclatura_ac                     text NOT NULL DEFAULT 'RACP',
  mascara_numeracao                   text NOT NULL DEFAULT '{SIGLA}_{TIPO}_{SEQ}_{ANO}',
  prazo_padrao_dias                   integer NOT NULL DEFAULT 3,
  dias_uteis                          boolean NOT NULL DEFAULT true,
  encerramento_automatico_desconto    boolean NOT NULL DEFAULT false,
  areas                                text[] NOT NULL DEFAULT '{}',
  disciplinas                          text[] NOT NULL DEFAULT '{}',
  classificacoes                       jsonb NOT NULL DEFAULT '[{"key":"leve","label":"Leve"},{"key":"media","label":"Média"},{"key":"grave","label":"Grave"}]',
  ativo                                boolean NOT NULL DEFAULT true,
  created_at                           timestamptz NOT NULL DEFAULT now(),
  updated_at                           timestamptz NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------- contratadas --
CREATE TABLE contratadas (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  razao_social  text NOT NULL,
  cnpj          text,
  ativo         boolean NOT NULL DEFAULT true,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT contratadas_cnpj_unique UNIQUE (cnpj)
);
-- CNPJ é opcional; permite múltiplas linhas com CNPJ nulo
CREATE UNIQUE INDEX contratadas_razao_social_unique_idx ON contratadas (lower(razao_social)) WHERE cnpj IS NULL;

-- -------------------------------------------------------------- contratos --
CREATE TABLE contratos (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sede_id           uuid NOT NULL REFERENCES sedes(id) ON DELETE RESTRICT,
  numero            text NOT NULL,
  descricao_obra    text,
  tipo_obra         text,
  ano               integer,
  lote              text,
  gerente           text,
  gestor_obra       text,
  vigencia_inicio   date,
  vigencia_fim      date,
  situacao          text,
  created_at        timestamptz NOT NULL DEFAULT now(),
  updated_at        timestamptz NOT NULL DEFAULT now(),
  UNIQUE (sede_id, numero)
);
CREATE INDEX contratos_sede_idx ON contratos (sede_id);

CREATE TABLE contrato_contratadas (
  contrato_id    uuid NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
  contratada_id  uuid NOT NULL REFERENCES contratadas(id) ON DELETE CASCADE,
  PRIMARY KEY (contrato_id, contratada_id)
);

-- ----------------------------------------------------------------- users --
CREATE TABLE users (
  id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nome                    text NOT NULL,
  email                   citext NOT NULL UNIQUE,
  senha_hash              text NOT NULL,
  perfil                  perfil_usuario NOT NULL,
  ativo                   boolean NOT NULL DEFAULT true,
  bloqueado               boolean NOT NULL DEFAULT false,
  must_change_password    boolean NOT NULL DEFAULT true,
  failed_login_attempts   integer NOT NULL DEFAULT 0,
  locked_until            timestamptz,
  last_login_at           timestamptz,
  password_changed_at     timestamptz,
  created_by              uuid REFERENCES users(id),
  created_at              timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE user_sedes (
  user_id  uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  sede_id  uuid NOT NULL REFERENCES sedes(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, sede_id)
);
CREATE TABLE user_contratos (
  user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  contrato_id uuid NOT NULL REFERENCES contratos(id) ON DELETE CASCADE,
  PRIMARY KEY (user_id, contrato_id)
);

-- ------------------------------------------------------------- sessions ---
-- Sessões de servidor (token opaco no cookie; só o hash SHA-256 é gravado).
CREATE TABLE sessions (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash     text NOT NULL UNIQUE,
  csrf_token     text NOT NULL,
  ip             text,
  user_agent     text,
  created_at     timestamptz NOT NULL DEFAULT now(),
  last_seen_at   timestamptz NOT NULL DEFAULT now(),
  expires_at     timestamptz NOT NULL
);
CREATE INDEX sessions_user_idx ON sessions (user_id);
CREATE INDEX sessions_expires_idx ON sessions (expires_at);

-- Histórico de tentativas de login (throttling / bloqueio).
CREATE TABLE login_attempts (
  id           bigserial PRIMARY KEY,
  identifier   text NOT NULL,     -- e-mail informado (normalizado)
  ip           text,
  success      boolean NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX login_attempts_identifier_idx ON login_attempts (identifier, created_at);
CREATE INDEX login_attempts_ip_idx ON login_attempts (ip, created_at);

-- ------------------------------------------------------------ auditoria ---
CREATE TABLE audit_log (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      uuid REFERENCES users(id) ON DELETE SET NULL,
  user_nome    text,
  action       text NOT NULL,
  entity       text NOT NULL,
  entity_id    text,
  detail       jsonb,
  ip           text,
  created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_log_created_idx ON audit_log (created_at DESC);
CREATE INDEX audit_log_entity_idx ON audit_log (entity, entity_id);

-- ------------------------------------------------------- textos padrão ---
CREATE TABLE textos_padrao (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sede_id      uuid REFERENCES sedes(id) ON DELETE CASCADE,  -- NULL = GLOBAL
  categoria    text NOT NULL,
  item         text NOT NULL,
  subitem      text NOT NULL DEFAULT '',
  texto        text NOT NULL,
  created_at   timestamptz NOT NULL DEFAULT now(),
  updated_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX textos_padrao_sede_idx ON textos_padrao (sede_id);
CREATE INDEX textos_padrao_cat_idx ON textos_padrao (categoria, item, subitem);

-- ------------------------------------------------------------------ ncs ---
CREATE TABLE ncs (
  id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sede_id                     uuid NOT NULL REFERENCES sedes(id) ON DELETE RESTRICT,
  tipo_core                   text NOT NULL DEFAULT 'NC' CHECK (tipo_core IN ('NC','AC')),
  contrato_id                 uuid REFERENCES contratos(id) ON DELETE SET NULL,
  contratada_id                uuid REFERENCES contratadas(id) ON DELETE SET NULL,
  numero_sequencial            integer,
  ano                          integer,
  codigo_formatado             text NOT NULL,
  data_emissao                 date,
  data_ocorrencia              date,
  responsavel_emissao_nome     text,
  area                         text,
  disciplina                   text,
  categoria                    text,
  item                         text,
  subitem                      text,
  classificacao                text,
  unidade_quantidade           text,
  rodovia                      text,
  trecho                       text,
  km_inicial                   numeric,
  km_final                     numeric,
  pista_sentido                text,
  faixa                        text,
  estaca_inicial                text,
  estaca_final                  text,
  comprimento                   numeric,
  largura                       numeric,
  espessura                     numeric,
  quantidade                    numeric,
  descricao                     text,
  observacao_campo              text,
  norma_referencia               text,
  valor_estimado                  numeric(14,2),
  valor_retencao_proposto         numeric(14,2),
  valor_retencao_efetivo          numeric(14,2),
  prazo_resposta                   timestamptz,
  solicita_ac_ap                    boolean NOT NULL DEFAULT false,
  status_atual                      text NOT NULL DEFAULT 'aguardando_resposta',
  data_encerramento                  timestamptz,
  resposta_contratada                 jsonb,
  avaliacao_concessionaria             jsonb,
  origem                                text NOT NULL DEFAULT 'manual' CHECK (origem IN ('manual','importacao')),
  import_id                             uuid,
  numero_emissao_planilha               text,   -- "nº Emissão" bruto da planilha (rastreabilidade/dedup)
  unidade_planilha                      text,   -- "Unidade" bruta da planilha (dedup quando contrato não localizado)
  situacao_planilha_raw                 text,   -- status bruto original da planilha
  created_by                            uuid REFERENCES users(id),
  updated_by                            uuid REFERENCES users(id),
  created_at                            timestamptz NOT NULL DEFAULT now(),
  updated_at                            timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ncs_sede_idx ON ncs (sede_id);
CREATE INDEX ncs_contrato_idx ON ncs (contrato_id);
CREATE INDEX ncs_status_idx ON ncs (status_atual);
CREATE INDEX ncs_dedup_idx ON ncs (unidade_planilha, numero_emissao_planilha, contrato_id);
-- Numeração automática só precisa ser única quando gerada pelo próprio sistema
CREATE UNIQUE INDEX ncs_numeracao_unique_idx ON ncs (sede_id, tipo_core, ano, numero_sequencial)
  WHERE origem = 'manual';

CREATE TABLE nc_historico (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nc_id             uuid NOT NULL REFERENCES ncs(id) ON DELETE CASCADE,
  data_hora         timestamptz NOT NULL DEFAULT now(),
  usuario_id        uuid REFERENCES users(id) ON DELETE SET NULL,
  usuario_nome      text,
  status_anterior   text,
  status_novo       text,
  comentario        text,
  created_at        timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX nc_historico_nc_idx ON nc_historico (nc_id, data_hora);

CREATE TABLE nc_anexos (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nc_id          uuid NOT NULL REFERENCES ncs(id) ON DELETE CASCADE,
  tipo           text NOT NULL DEFAULT 'foto',
  nome_arquivo   text,
  storage_path   text,
  legenda        text,
  data_foto      date,
  km             text,
  pista          text,
  faixa          text,
  tamanho_bytes  bigint,
  content_type   text,
  uploaded_by    uuid REFERENCES users(id),
  created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX nc_anexos_nc_idx ON nc_anexos (nc_id);

-- ------------------------------------------------------ importação ------
CREATE TABLE header_aliases (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  campo_sistema  text NOT NULL,       -- ex.: 'numeroEmissao', 'unidade', 'contrato'...
  alias          text NOT NULL,       -- cabeçalho alternativo aceito na planilha
  sede_id        uuid REFERENCES sedes(id) ON DELETE CASCADE, -- NULL = global
  created_at     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (campo_sistema, alias, sede_id)
);

CREATE TABLE import_logs (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  sede_id           uuid NOT NULL REFERENCES sedes(id) ON DELETE CASCADE,
  user_id           uuid REFERENCES users(id) ON DELETE SET NULL,
  user_nome         text,
  filename          text NOT NULL,
  sheet_name        text,
  status            text NOT NULL DEFAULT 'preview' CHECK (status IN ('preview','committed','failed')),
  total_rows        integer NOT NULL DEFAULT 0,
  valid_count       integer NOT NULL DEFAULT 0,
  duplicate_count   integer NOT NULL DEFAULT 0,
  update_count      integer NOT NULL DEFAULT 0,
  rejected_count    integer NOT NULL DEFAULT 0,
  error_count       integer NOT NULL DEFAULT 0,
  header_mapping    jsonb,
  error_report      jsonb,
  preview_token     text,
  preview_payload   jsonb,
  started_at        timestamptz NOT NULL DEFAULT now(),
  finished_at       timestamptz
);
CREATE INDEX import_logs_sede_idx ON import_logs (sede_id, started_at DESC);

ALTER TABLE ncs ADD CONSTRAINT ncs_import_fk FOREIGN KEY (import_id) REFERENCES import_logs(id) ON DELETE SET NULL;
-- (tabela schema_migrations é criada e gerenciada por migrate.py)
