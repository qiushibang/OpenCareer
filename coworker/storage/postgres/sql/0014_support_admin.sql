-- The trusted support service checks the deployment's admin allowlist before
-- setting this transaction-local flag. No global RLS bypass is granted.
CREATE POLICY feedback_support_admin ON support.feedback
USING (current_setting('app.support_admin', true) = current_setting('app.user_id', true)
       AND COALESCE(current_setting('app.user_id', true), '') <> '')
WITH CHECK (current_setting('app.support_admin', true) = current_setting('app.user_id', true)
            AND COALESCE(current_setting('app.user_id', true), '') <> '');
CREATE POLICY diagnostics_support_admin ON support.diagnostics FOR SELECT
USING (current_setting('app.support_admin', true) = current_setting('app.user_id', true)
       AND COALESCE(current_setting('app.user_id', true), '') <> '');
CREATE TABLE support.admin_audit (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id) ON DELETE CASCADE,
    created_at BIGINT NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('list','detail','update','merge','alerts','maintenance')),
    target_id TEXT CHECK (target_id IS NULL OR target_id ~ '^[0-9a-f]{32}$')
);
ALTER TABLE support.admin_audit ENABLE ROW LEVEL SECURITY;
ALTER TABLE support.admin_audit FORCE ROW LEVEL SECURITY;
CREATE POLICY audit_support_admin ON support.admin_audit
USING (current_setting('app.support_admin', true) = current_setting('app.user_id', true)
       AND COALESCE(current_setting('app.user_id', true), '') <> '')
WITH CHECK (current_setting('app.support_admin', true) = current_setting('app.user_id', true)
            AND COALESCE(current_setting('app.user_id', true), '') <> '');
