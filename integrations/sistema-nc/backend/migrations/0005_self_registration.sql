ALTER TABLE users
  ADD COLUMN IF NOT EXISTS approval_status text NOT NULL DEFAULT 'aprovado',
  ADD COLUMN IF NOT EXISTS requested_at timestamptz;

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_approval_status_check;
ALTER TABLE users ADD CONSTRAINT users_approval_status_check
  CHECK (approval_status IN ('pendente', 'aprovado', 'rejeitado'));

CREATE INDEX IF NOT EXISTS users_approval_status_idx ON users (approval_status);
