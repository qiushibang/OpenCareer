CREATE TABLE IF NOT EXISTS opencareer_meta.data_migrations (
    source_kind TEXT NOT NULL,
    user_id TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    report JSONB NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_kind, user_id, source_sha256)
);
