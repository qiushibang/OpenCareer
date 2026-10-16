-- This transaction flag is set only by the fixed, bounded anonymous intake route.
-- Anonymous records are never exposed through user history or the Agent surface.
CREATE POLICY feedback_anonymous_intake ON support.feedback
USING (user_id IS NULL AND current_setting('app.support_intake', true) = '1')
WITH CHECK (user_id IS NULL AND current_setting('app.support_intake', true) = '1');
