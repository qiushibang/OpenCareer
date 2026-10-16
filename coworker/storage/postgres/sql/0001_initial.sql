CREATE SCHEMA IF NOT EXISTS identity;
CREATE SCHEMA IF NOT EXISTS catalog;
CREATE SCHEMA IF NOT EXISTS career;
CREATE SCHEMA IF NOT EXISTS agent;
CREATE SCHEMA IF NOT EXISTS blob;

CREATE TABLE IF NOT EXISTS identity.users (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS identity.auth_credentials (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    credential_type TEXT NOT NULL,
    secret_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    revoked_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS identity.deployment_origins (
    id UUID PRIMARY KEY,
    origin TEXT NOT NULL UNIQUE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS catalog.companies (
    id TEXT PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog.job_sources (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES catalog.companies(id),
    slug TEXT NOT NULL,
    source_type TEXT NOT NULL,
    base_url TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (company_id, slug)
);

CREATE TABLE IF NOT EXISTS catalog.crawl_sources (
    id TEXT PRIMARY KEY,
    company_id TEXT REFERENCES catalog.companies(id),
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    scope_key TEXT,
    adapter_type TEXT,
    base_url TEXT,
    missing_threshold INTEGER NOT NULL,
    enabled BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (company_id, scope_key)
);

CREATE TABLE IF NOT EXISTS catalog.crawl_runs (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES catalog.crawl_sources(id),
    status TEXT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    observed_count INTEGER NOT NULL DEFAULT 0,
    invalid_count INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT
);

CREATE TABLE IF NOT EXISTS catalog.jobs (
    id TEXT PRIMARY KEY,
    company_id TEXT NOT NULL REFERENCES catalog.companies(id),
    source_id TEXT NOT NULL REFERENCES catalog.job_sources(id),
    crawl_source_id TEXT REFERENCES catalog.crawl_sources(id),
    external_job_id TEXT,
    canonical_url TEXT NOT NULL,
    title TEXT,
    department TEXT,
    location_raw TEXT,
    locations JSONB NOT NULL DEFAULT '[]',
    recruitment_type TEXT,
    employment_type TEXT,
    category TEXT,
    description_raw TEXT NOT NULL,
    responsibilities JSONB NOT NULL DEFAULT '[]',
    requirements JSONB NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    missing_count INTEGER NOT NULL DEFAULT 0,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at TIMESTAMPTZ NOT NULL,
    last_changed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    search_document TSVECTOR GENERATED ALWAYS AS (
        to_tsvector(
            'simple',
            coalesce(title, '') || ' ' ||
            coalesce(department, '') || ' ' ||
            coalesce(description_raw, '') || ' ' ||
            responsibilities::text || ' ' ||
            requirements::text
        )
    ) STORED,
    UNIQUE (crawl_source_id, external_job_id)
);

CREATE INDEX IF NOT EXISTS jobs_search_document_gin
    ON catalog.jobs USING GIN (search_document);
CREATE INDEX IF NOT EXISTS jobs_exact_filters
    ON catalog.jobs(company_id, recruitment_type, status, first_seen_at DESC);
CREATE INDEX IF NOT EXISTS jobs_locations_gin
    ON catalog.jobs USING GIN (locations);

CREATE TABLE IF NOT EXISTS catalog.job_versions (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES catalog.jobs(id),
    version_number INTEGER NOT NULL,
    content_hash TEXT NOT NULL,
    snapshot JSONB NOT NULL,
    field_diff JSONB NOT NULL DEFAULT '{}',
    crawl_run_id TEXT REFERENCES catalog.crawl_runs(id),
    captured_at TIMESTAMPTZ NOT NULL,
    UNIQUE (job_id, version_number)
);

CREATE TABLE IF NOT EXISTS catalog.job_events (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES catalog.jobs(id),
    event_type TEXT NOT NULL,
    summary TEXT NOT NULL,
    changed_fields JSONB NOT NULL DEFAULT '[]',
    crawl_run_id TEXT REFERENCES catalog.crawl_runs(id),
    occurred_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS blob.objects (
    id UUID PRIMARY KEY,
    scope TEXT NOT NULL CHECK (scope IN ('shared', 'user')),
    user_id TEXT REFERENCES identity.users(id),
    kind TEXT NOT NULL,
    media_type TEXT NOT NULL,
    original_name TEXT,
    size_bytes BIGINT NOT NULL,
    sha256 TEXT NOT NULL,
    content BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CHECK (
        (scope = 'shared' AND user_id IS NULL)
        OR (scope = 'user' AND user_id IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS catalog.raw_snapshots (
    id UUID PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES catalog.crawl_sources(id),
    crawl_run_id TEXT REFERENCES catalog.crawl_runs(id),
    blob_id UUID NOT NULL REFERENCES blob.objects(id),
    url TEXT NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS career.resume_imports (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    blob_id UUID REFERENCES blob.objects(id),
    content_hash TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE (user_id, content_hash)
);

CREATE TABLE IF NOT EXISTS career.candidate_profiles (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS career.candidate_facts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    profile_id TEXT NOT NULL REFERENCES career.candidate_profiles(id),
    section TEXT NOT NULL,
    fact_key TEXT NOT NULL,
    fact_value JSONB NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    UNIQUE (user_id, profile_id, section, fact_key)
);

CREATE TABLE IF NOT EXISTS career.profile_versions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    profile_id TEXT NOT NULL REFERENCES career.candidate_profiles(id),
    version_number INTEGER NOT NULL,
    snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (user_id, profile_id, version_number)
);

CREATE TABLE IF NOT EXISTS career.resume_previews (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    resume_import_id TEXT NOT NULL REFERENCES career.resume_imports(id),
    data JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS career.job_tracking (
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    job_id TEXT NOT NULL REFERENCES catalog.jobs(id),
    data JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, job_id)
);

CREATE TABLE IF NOT EXISTS career.job_application_events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    job_id TEXT NOT NULL REFERENCES catalog.jobs(id),
    data JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS career.job_resume_matches (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    job_id TEXT NOT NULL REFERENCES catalog.jobs(id),
    resume_import_id TEXT NOT NULL REFERENCES career.resume_imports(id),
    job_content_hash TEXT NOT NULL,
    resume_revision_at TIMESTAMPTZ NOT NULL,
    result JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS career.application_packets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    job_id TEXT NOT NULL REFERENCES catalog.jobs(id),
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS career.tailored_resume_drafts (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    job_id TEXT NOT NULL REFERENCES catalog.jobs(id),
    resume_import_id TEXT NOT NULL REFERENCES career.resume_imports(id),
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS agent.conversations (
    id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, id)
);

CREATE TABLE IF NOT EXISTS agent.workspaces (
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    path TEXT NOT NULL,
    last_used TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, path)
);

CREATE TABLE IF NOT EXISTS agent.messages (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    conversation_id TEXT NOT NULL,
    sequence BIGINT NOT NULL,
    content JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, conversation_id, sequence),
    FOREIGN KEY (user_id, conversation_id)
        REFERENCES agent.conversations(user_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent.compactions (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    conversation_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    boundary_sequence BIGINT NOT NULL,
    summary TEXT NOT NULL,
    omitted_message_count INTEGER NOT NULL,
    source_hash TEXT NOT NULL,
    state JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, conversation_id, version),
    FOREIGN KEY (user_id, conversation_id)
        REFERENCES agent.conversations(user_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent.context_manifests (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    conversation_id TEXT NOT NULL,
    turn_id TEXT NOT NULL,
    manifest JSONB NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (user_id, conversation_id)
        REFERENCES agent.conversations(user_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent.session_skills (
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    conversation_id TEXT NOT NULL,
    skill_name TEXT NOT NULL,
    skill_version TEXT,
    content_sha256 TEXT NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, conversation_id, skill_name),
    FOREIGN KEY (user_id, conversation_id)
        REFERENCES agent.conversations(user_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent.memories (
    id BIGSERIAL PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    scope TEXT NOT NULL,
    key TEXT,
    content TEXT NOT NULL,
    workspace TEXT,
    conversation_id TEXT,
    version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (user_id, conversation_id)
        REFERENCES agent.conversations(user_id, id)
        ON DELETE SET NULL (conversation_id)
);

CREATE TABLE IF NOT EXISTS agent.todos (
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    conversation_id TEXT NOT NULL,
    data JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, conversation_id),
    FOREIGN KEY (user_id, conversation_id)
        REFERENCES agent.conversations(user_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent.inbox_items (
    id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    conversation_id TEXT NOT NULL,
    tool_call_id TEXT,
    state TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    PRIMARY KEY (user_id, id),
    UNIQUE (user_id, conversation_id, tool_call_id),
    FOREIGN KEY (user_id, conversation_id)
        REFERENCES agent.conversations(user_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS agent.inbox_resolutions (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    inbox_item_id TEXT NOT NULL,
    resolution JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, inbox_item_id),
    FOREIGN KEY (user_id, inbox_item_id)
        REFERENCES agent.inbox_items(user_id, id)
);

CREATE TABLE IF NOT EXISTS agent.automations (
    id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    enabled BOOLEAN NOT NULL,
    next_run DOUBLE PRECISION,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, id)
);

CREATE INDEX IF NOT EXISTS automations_due
    ON agent.automations(user_id, enabled, next_run);

CREATE TABLE IF NOT EXISTS agent.automation_runs (
    id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    automation_id TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, id),
    FOREIGN KEY (user_id, automation_id)
        REFERENCES agent.automations(user_id, id)
);

CREATE TABLE IF NOT EXISTS agent.audit_events (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    event_type TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS career.interview_sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    job_id TEXT NOT NULL REFERENCES catalog.jobs(id),
    resume_import_id TEXT NOT NULL REFERENCES career.resume_imports(id),
    conversation_id TEXT,
    data JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (user_id, conversation_id)
        REFERENCES agent.conversations(user_id, id)
        ON DELETE SET NULL (conversation_id)
);

CREATE TABLE IF NOT EXISTS career.interview_turns (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id),
    session_id TEXT NOT NULL REFERENCES career.interview_sessions(id),
    turn_index INTEGER NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (session_id, turn_index)
);

ALTER TABLE blob.objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE blob.objects FORCE ROW LEVEL SECURITY;
CREATE POLICY blob_user_isolation ON blob.objects
    USING (
        scope = 'shared'
        OR user_id = current_setting('app.user_id', true)
    )
    WITH CHECK (
        scope = 'shared'
        OR user_id = current_setting('app.user_id', true)
    );

DO $$
DECLARE
    target TEXT;
BEGIN
    FOREACH target IN ARRAY ARRAY[
        'career.resume_imports',
        'career.candidate_profiles',
        'career.candidate_facts',
        'career.profile_versions',
        'career.resume_previews',
        'career.job_tracking',
        'career.job_application_events',
        'career.job_resume_matches',
        'career.application_packets',
        'career.tailored_resume_drafts',
        'career.interview_sessions',
        'career.interview_turns',
        'agent.conversations',
        'agent.workspaces',
        'agent.messages',
        'agent.compactions',
        'agent.context_manifests',
        'agent.session_skills',
        'agent.memories',
        'agent.todos',
        'agent.inbox_items',
        'agent.inbox_resolutions',
        'agent.automations',
        'agent.automation_runs',
        'agent.audit_events'
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
