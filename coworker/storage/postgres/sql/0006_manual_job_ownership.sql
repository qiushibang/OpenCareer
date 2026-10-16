CREATE TABLE career.manual_job_owners (
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    job_id TEXT NOT NULL REFERENCES catalog.jobs(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, job_id),
    UNIQUE (job_id)
);

ALTER TABLE career.manual_job_owners ENABLE ROW LEVEL SECURITY;
ALTER TABLE career.manual_job_owners FORCE ROW LEVEL SECURITY;

CREATE POLICY manual_job_owner_isolation
ON career.manual_job_owners
USING (user_id = current_setting('app.user_id', true))
WITH CHECK (user_id = current_setting('app.user_id', true));

CREATE FUNCTION career.job_visible_to_user(
    target_job_id TEXT,
    target_user_id TEXT
) RETURNS BOOLEAN
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, career
AS $$
    SELECT
        NOT EXISTS (
            SELECT 1
            FROM career.manual_job_owners owner
            WHERE owner.job_id = target_job_id
        )
        OR EXISTS (
            SELECT 1
            FROM career.manual_job_owners owner
            WHERE owner.job_id = target_job_id
              AND owner.user_id = target_user_id
        )
$$;

CREATE VIEW career.visible_jobs
WITH (security_barrier = true)
AS
SELECT jobs.*
FROM catalog.jobs jobs
WHERE career.job_visible_to_user(
    jobs.id,
    current_setting('app.user_id', true)
);

CREATE FUNCTION career.enforce_job_visibility()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, career
AS $$
BEGIN
    IF NOT career.job_visible_to_user(NEW.job_id, NEW.user_id) THEN
        RAISE EXCEPTION 'job is not visible to the current tenant'
            USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER job_tracking_visible_job
BEFORE INSERT OR UPDATE OF user_id, job_id
ON career.job_tracking
FOR EACH ROW EXECUTE FUNCTION career.enforce_job_visibility();

CREATE TRIGGER job_application_events_visible_job
BEFORE INSERT OR UPDATE OF user_id, job_id
ON career.job_application_events
FOR EACH ROW EXECUTE FUNCTION career.enforce_job_visibility();

CREATE TRIGGER job_resume_matches_visible_job
BEFORE INSERT OR UPDATE OF user_id, job_id
ON career.job_resume_matches
FOR EACH ROW EXECUTE FUNCTION career.enforce_job_visibility();

CREATE TRIGGER application_packets_visible_job
BEFORE INSERT OR UPDATE OF user_id, job_id
ON career.application_packets
FOR EACH ROW EXECUTE FUNCTION career.enforce_job_visibility();

CREATE TRIGGER tailored_resume_drafts_visible_job
BEFORE INSERT OR UPDATE OF user_id, job_id
ON career.tailored_resume_drafts
FOR EACH ROW EXECUTE FUNCTION career.enforce_job_visibility();

CREATE TRIGGER interview_sessions_visible_job
BEFORE INSERT OR UPDATE OF user_id, job_id
ON career.interview_sessions
FOR EACH ROW EXECUTE FUNCTION career.enforce_job_visibility();
