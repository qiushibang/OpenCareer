CREATE TABLE support.alerts (
    category TEXT PRIMARY KEY,
    data TEXT NOT NULL CHECK (octet_length(data) <= 2048)
);
ALTER TABLE support.alerts ENABLE ROW LEVEL SECURITY;
ALTER TABLE support.alerts FORCE ROW LEVEL SECURITY;
CREATE POLICY alerts_support_admin ON support.alerts
USING (current_setting('app.support_admin', true) = current_setting('app.user_id', true)
       AND COALESCE(current_setting('app.user_id', true), '') <> '')
WITH CHECK (current_setting('app.support_admin', true) = current_setting('app.user_id', true)
            AND COALESCE(current_setting('app.user_id', true), '') <> '');
CREATE POLICY diagnostics_support_retention ON support.diagnostics FOR DELETE
USING (current_setting('app.support_admin', true) = current_setting('app.user_id', true)
       AND COALESCE(current_setting('app.user_id', true), '') <> '');
