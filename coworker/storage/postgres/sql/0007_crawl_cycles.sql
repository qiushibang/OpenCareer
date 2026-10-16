CREATE TABLE catalog.crawl_cycles (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES catalog.crawl_sources(id),
    status TEXT NOT NULL CHECK (
        status IN ('running', 'degraded', 'failed', 'committed')
    ),
    pass_number INTEGER NOT NULL DEFAULT 1
        CHECK (pass_number BETWEEN 1 AND 3),
    expected_total INTEGER,
    started_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    error_summary TEXT
);

CREATE UNIQUE INDEX crawl_cycles_one_running_source
ON catalog.crawl_cycles(source_id)
WHERE status = 'running';

CREATE TABLE catalog.crawl_cycle_shards (
    cycle_id TEXT NOT NULL
        REFERENCES catalog.crawl_cycles(id) ON DELETE CASCADE,
    shard_key TEXT NOT NULL,
    filters_json JSONB NOT NULL,
    expected_count INTEGER,
    next_offset INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL CHECK (
        status IN ('pending', 'running', 'complete', 'degraded')
    ),
    last_page_fingerprint TEXT,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (cycle_id, shard_key)
);

CREATE TABLE catalog.crawl_cycle_jobs (
    cycle_id TEXT NOT NULL
        REFERENCES catalog.crawl_cycles(id) ON DELETE CASCADE,
    external_job_id TEXT NOT NULL,
    snapshot_json JSONB NOT NULL,
    content_hash TEXT NOT NULL,
    first_pass INTEGER NOT NULL,
    last_pass INTEGER NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (cycle_id, external_job_id)
);
