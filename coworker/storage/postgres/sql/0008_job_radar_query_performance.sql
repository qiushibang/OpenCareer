ALTER TABLE catalog.jobs
ADD COLUMN IF NOT EXISTS visibility_user_id TEXT
REFERENCES identity.users(id);

UPDATE catalog.jobs jobs
SET visibility_user_id = owner.user_id
FROM career.manual_job_owners owner
WHERE owner.job_id = jobs.id
  AND jobs.visibility_user_id IS DISTINCT FROM owner.user_id;

CREATE OR REPLACE FUNCTION career.sync_manual_job_visibility()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, career, catalog
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        UPDATE catalog.jobs
        SET visibility_user_id = NULL
        WHERE id = OLD.job_id;
        RETURN OLD;
    END IF;

    IF TG_OP = 'UPDATE' AND OLD.job_id IS DISTINCT FROM NEW.job_id THEN
        UPDATE catalog.jobs
        SET visibility_user_id = NULL
        WHERE id = OLD.job_id;
    END IF;

    UPDATE catalog.jobs
    SET visibility_user_id = NEW.user_id
    WHERE id = NEW.job_id;
    RETURN NEW;
END
$$;

DROP TRIGGER IF EXISTS sync_manual_job_visibility
ON career.manual_job_owners;

CREATE TRIGGER sync_manual_job_visibility
AFTER INSERT OR UPDATE OF user_id, job_id OR DELETE
ON career.manual_job_owners
FOR EACH ROW EXECUTE FUNCTION career.sync_manual_job_visibility();

CREATE OR REPLACE FUNCTION career.job_visible_to_user(
    target_job_id TEXT,
    target_user_id TEXT
) RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, career, catalog
AS $$
    SELECT COALESCE(
        (
            SELECT
                jobs.visibility_user_id IS NULL
                OR jobs.visibility_user_id = target_user_id
            FROM catalog.jobs jobs
            WHERE jobs.id = target_job_id
        ),
        TRUE
    )
$$;

CREATE OR REPLACE VIEW career.visible_jobs
WITH (security_barrier = true)
AS
SELECT jobs.*
FROM catalog.jobs jobs
WHERE jobs.visibility_user_id IS NULL
   OR jobs.visibility_user_id = current_setting('app.user_id', true);

CREATE INDEX IF NOT EXISTS jobs_active_feed
ON catalog.jobs(first_seen_at DESC, id ASC)
WHERE status = 'active';
