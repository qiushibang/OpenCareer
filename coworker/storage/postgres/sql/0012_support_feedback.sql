CREATE TABLE support.feedback (
    id TEXT PRIMARY KEY CHECK (id ~ '^[0-9a-f]{32}$'),
    user_id TEXT REFERENCES identity.users(id) ON DELETE CASCADE,
    nonce TEXT NOT NULL CHECK (nonce ~ '^[0-9a-f]{32}$'),
    created_at BIGINT NOT NULL,
    data TEXT NOT NULL CHECK (octet_length(data) <= 16384)
);
CREATE UNIQUE INDEX support_feedback_nonce ON support.feedback (COALESCE(user_id, ''), nonce);
CREATE INDEX support_feedback_time ON support.feedback(user_id, created_at);
ALTER TABLE support.feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE support.feedback FORCE ROW LEVEL SECURITY;
CREATE POLICY feedback_owner ON support.feedback
USING (user_id = current_setting('app.user_id', true))
WITH CHECK (user_id = current_setting('app.user_id', true));
