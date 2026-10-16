-- Intake needs idempotent reads and inserts only; never anonymous updates/deletes.
DROP POLICY feedback_anonymous_intake ON support.feedback;
CREATE POLICY feedback_anonymous_select ON support.feedback FOR SELECT
USING (user_id IS NULL AND current_setting('app.support_intake', true) = '1');
CREATE POLICY feedback_anonymous_insert ON support.feedback FOR INSERT
WITH CHECK (user_id IS NULL AND current_setting('app.support_intake', true) = '1');
