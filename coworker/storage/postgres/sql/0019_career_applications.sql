-- Personal application workspace (求职进度) for hosted tenants.
--
-- Mirrors the local SQLite tables (career_applications, career_application_interviews,
-- career_application_history) but every row belongs to one user and is protected by
-- FORCE ROW LEVEL SECURITY, like the other tenant-owned career tables. Records are
-- private to the user and never become part of the shared job catalog.

CREATE TABLE career.applications (
    id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    job_id TEXT REFERENCES catalog.jobs(id) ON DELETE SET NULL,
    migrated_job_id TEXT,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    data JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, id),
    UNIQUE (user_id, migrated_job_id)
);

-- One live application per job and user; "new attempt" retires the previous one.
CREATE UNIQUE INDEX applications_current_job
    ON career.applications(user_id, job_id)
    WHERE job_id IS NOT NULL AND is_current;

CREATE INDEX applications_user_updated
    ON career.applications(user_id, updated_at DESC, id);

CREATE TABLE career.application_interviews (
    id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    application_id TEXT NOT NULL,
    data JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, id),
    FOREIGN KEY (user_id, application_id)
        REFERENCES career.applications(user_id, id) ON DELETE CASCADE
);

CREATE INDEX application_interviews_parent
    ON career.application_interviews(user_id, application_id, created_at, id);

CREATE TABLE career.application_history (
    id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    application_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, id),
    FOREIGN KEY (user_id, application_id)
        REFERENCES career.applications(user_id, id) ON DELETE CASCADE
);

CREATE INDEX application_history_parent
    ON career.application_history(user_id, application_id, occurred_at DESC, id);

DO $$
DECLARE
    target TEXT;
BEGIN
    FOREACH target IN ARRAY ARRAY[
        'career.applications',
        'career.application_interviews',
        'career.application_history'
    ]
    LOOP
        EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', target);
        EXECUTE format('ALTER TABLE %s FORCE ROW LEVEL SECURITY', target);
        EXECUTE format(
            'CREATE POLICY user_isolation ON %s '
            'USING (user_id = current_setting(''app.user_id'', true)) '
            'WITH CHECK (user_id = current_setting(''app.user_id'', true))',
            target
        );
    END LOOP;
END
$$;
