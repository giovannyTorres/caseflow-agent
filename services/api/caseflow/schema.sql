CREATE TABLE IF NOT EXISTS schema_migrations(version integer PRIMARY KEY, applied_at timestamptz DEFAULT now());
CREATE TABLE IF NOT EXISTS users (
 username text NOT NULL, mode text NOT NULL, role text NOT NULL CHECK(role IN ('analyst','supervisor')),
 salt text NOT NULL, password_hash text NOT NULL, PRIMARY KEY(username,mode)
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash text PRIMARY KEY, username text NOT NULL, mode text NOT NULL,
 expires_at timestamptz NOT NULL, FOREIGN KEY(username,mode) REFERENCES users(username,mode)
);
CREATE TABLE IF NOT EXISTS cases (
 id text PRIMARY KEY, mode text NOT NULL CHECK(mode IN ('DEMO','LIVE')), title text NOT NULL,
 scenario text NOT NULL, status text NOT NULL DEFAULT 'new' CHECK(status IN ('new','investigating','needs_evidence','awaiting_approval','approved','rejected','resolved','failed','interrupted')),
 priority text NOT NULL, assignee text NOT NULL DEFAULT 'analyst', amount integer NOT NULL CHECK(amount > 0),
 currency text NOT NULL DEFAULT 'MXN', movements jsonb NOT NULL DEFAULT '[]', evidence jsonb NOT NULL DEFAULT '[]',
 proposal_version integer NOT NULL DEFAULT 0, proposal_amount integer, proposal_reason text,
 approved_version integer, approved_by text, rejection_reason text,
 recovery_enabled boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS jobs (
 id uuid PRIMARY KEY, case_id text NOT NULL REFERENCES cases(id), actor text NOT NULL,
 status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','running','waiting','completed','failed','cancelled')),
 resume jsonb, lease_until timestamptz, attempts integer NOT NULL DEFAULT 0,
 error text, correlation_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON jobs(case_id) WHERE status IN ('queued','running');
CREATE TABLE IF NOT EXISTS events (
 id bigserial PRIMARY KEY, case_id text NOT NULL REFERENCES cases(id), actor text NOT NULL, event text NOT NULL,
 detail jsonb NOT NULL, correlation_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS messages (
 id bigserial PRIMARY KEY, case_id text NOT NULL REFERENCES cases(id), role text NOT NULL, content text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS resolutions (
 id uuid PRIMARY KEY, case_id text NOT NULL UNIQUE REFERENCES cases(id), proposal_version integer NOT NULL,
 amount integer NOT NULL, actor text NOT NULL, correlation_id text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS tool_receipts (
 case_id text NOT NULL REFERENCES cases(id), operation_key text NOT NULL, result jsonb NOT NULL,
 PRIMARY KEY(case_id,operation_key)
);
INSERT INTO schema_migrations(version) VALUES(1) ON CONFLICT DO NOTHING;
