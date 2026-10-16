CREATE SCHEMA IF NOT EXISTS support;
CREATE TABLE support.diagnostics (
    user_id TEXT NOT NULL REFERENCES identity.users(id) ON DELETE CASCADE,
    id TEXT NOT NULL CHECK (id ~ '^[0-9a-f]{32}$'),
    created_at BIGINT NOT NULL,
    data TEXT NOT NULL CHECK (octet_length(data) <= 2048),
    PRIMARY KEY (user_id, id)
);
CREATE INDEX support_diagnostic_time ON support.diagnostics(user_id, created_at);
ALTER TABLE support.diagnostics ENABLE ROW LEVEL SECURITY;
ALTER TABLE support.diagnostics FORCE ROW LEVEL SECURITY;
CREATE POLICY diagnostic_owner ON support.diagnostics
    USING (user_id = current_setting('app.user_id', true))
    WITH CHECK (user_id = current_setting('app.user_id', true));
