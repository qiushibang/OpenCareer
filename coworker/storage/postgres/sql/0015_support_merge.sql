CREATE TABLE support.merge_links (
    source_id TEXT PRIMARY KEY REFERENCES support.feedback(id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES support.feedback(id) ON DELETE CASCADE,
    CHECK (source_id <> target_id)
);
CREATE INDEX support_merge_target ON support.merge_links(target_id);
ALTER TABLE support.merge_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE support.merge_links FORCE ROW LEVEL SECURITY;
CREATE POLICY merge_support_admin ON support.merge_links
USING (current_setting('app.support_admin', true) = current_setting('app.user_id', true)
       AND COALESCE(current_setting('app.user_id', true), '') <> '')
WITH CHECK (current_setting('app.support_admin', true) = current_setting('app.user_id', true)
            AND COALESCE(current_setting('app.user_id', true), '') <> '');
