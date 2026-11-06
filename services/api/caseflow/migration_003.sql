-- Bind each proposal and its exact approval to immutable policy/case context.
ALTER TABLE cases ADD COLUMN IF NOT EXISTS proposal_context jsonb;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS proposal_context_sha256 text;
ALTER TABLE cases ADD COLUMN IF NOT EXISTS approved_context_sha256 text;
INSERT INTO schema_migrations(version) VALUES(3) ON CONFLICT DO NOTHING;
