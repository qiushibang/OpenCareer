CREATE TABLE identity.external_identities (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id) ON DELETE CASCADE,
    issuer TEXT NOT NULL,
    subject TEXT NOT NULL,
    email TEXT,
    email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    display_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (issuer, subject)
);

CREATE TABLE identity.auth_sessions (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES identity.users(id) ON DELETE CASCADE,
    token_sha256 TEXT NOT NULL UNIQUE
        CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
);

CREATE INDEX auth_sessions_active_lookup
    ON identity.auth_sessions(token_sha256, expires_at)
    WHERE revoked_at IS NULL;
