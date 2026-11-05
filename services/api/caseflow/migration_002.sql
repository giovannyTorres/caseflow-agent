-- Additive migration; existing case history and checkpoints are preserved.
CREATE TABLE IF NOT EXISTS login_attempts (
 key text PRIMARY KEY,
 window_start timestamptz NOT NULL,
 attempts integer NOT NULL CHECK(attempts>0)
);
INSERT INTO schema_migrations(version) VALUES(2) ON CONFLICT DO NOTHING;
