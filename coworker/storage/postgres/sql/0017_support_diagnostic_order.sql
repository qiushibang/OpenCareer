ALTER TABLE support.diagnostics ADD COLUMN created_order BIGINT NOT NULL DEFAULT 0;
CREATE INDEX support_diagnostic_order ON support.diagnostics(user_id,created_at,created_order);
