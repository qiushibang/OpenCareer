"""Versioned SQLite schema setup for the Career database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from ..domain.manual_jd import utc_now_iso

SCHEMA_VERSION = 13

_KNOWN_CRAWL_SOURCES = {
    "xiaomi-careers": {
        "source_name": "小米官方招聘",
        "company_slug": "xiaomi",
        "company_name": "小米",
        "scope_key": "all-public-jobs",
        "adapter_type": "public-json-api",
        "base_url": "https://hr.xiaomi.com/website/opportunities.html",
    },
    "deepseek-careers": {
        "source_name": "DeepSeek 官方招聘",
        "company_slug": "deepseek",
        "company_name": "DeepSeek",
        "scope_key": "all-public-jobs",
        "adapter_type": "static-javascript-bundle",
        "base_url": "https://talent.deepseek.com/",
    },
    "bytedance-seed-campus": {
        "source_name": "字节跳动 2027 Seed 大模型人才校招",
        "company_slug": "bytedance",
        "company_name": "字节跳动",
        "scope_key": "project:7621018151002507573",
        "adapter_type": "playwright-json",
        "base_url": "https://jobs.bytedance.com/campus/position",
    },
}


def connect(database_path: Path) -> sqlite3.Connection:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def migrate(connection: sqlite3.Connection) -> None:
    version = schema_version(connection)
    if version >= SCHEMA_VERSION:
        return
    connection.execute("BEGIN IMMEDIATE")
    try:
        if version < 1:
            connection.executescript(
                """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL
            );
            CREATE TABLE companies (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE job_sources (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL REFERENCES companies(id),
                slug TEXT NOT NULL,
                source_type TEXT NOT NULL,
                base_url TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(company_id, slug)
            );
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY,
                company_id TEXT NOT NULL REFERENCES companies(id),
                source_id TEXT NOT NULL REFERENCES job_sources(id),
                external_job_id TEXT,
                canonical_url TEXT NOT NULL,
                title TEXT,
                location_raw TEXT,
                locations_json TEXT NOT NULL,
                recruitment_type TEXT,
                description_raw TEXT NOT NULL,
                responsibilities_json TEXT NOT NULL,
                requirements_json TEXT NOT NULL,
                status TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_changed_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(source_id, content_hash)
            );
            CREATE TABLE job_versions (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES jobs(id),
                version_number INTEGER NOT NULL,
                content_hash TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                UNIQUE(job_id, version_number)
            );
            CREATE TABLE job_events (
                id TEXT PRIMARY KEY,
                job_id TEXT NOT NULL REFERENCES jobs(id),
                event_type TEXT NOT NULL,
                summary TEXT NOT NULL,
                changed_fields_json TEXT NOT NULL,
                occurred_at TEXT NOT NULL
            );
            CREATE INDEX jobs_source_first_seen ON jobs(source_id, first_seen_at DESC);
            CREATE INDEX jobs_status_first_seen ON jobs(status, first_seen_at DESC);
            CREATE INDEX jobs_company_id ON jobs(company_id);
            """
            )
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (1, utc_now_iso()),
            )
            connection.execute("PRAGMA user_version = 1")
        if version < 2:
            connection.executescript(
                """
                CREATE TABLE crawl_sources (
                    id TEXT PRIMARY KEY,
                    slug TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    missing_threshold INTEGER NOT NULL,
                    enabled INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE crawl_runs (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES crawl_sources(id),
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    observed_count INTEGER NOT NULL,
                    invalid_count INTEGER NOT NULL,
                    error_summary TEXT
                );
                ALTER TABLE jobs ADD COLUMN crawl_source_id TEXT REFERENCES crawl_sources(id);
                ALTER TABLE jobs ADD COLUMN missing_count INTEGER NOT NULL DEFAULT 0;
                CREATE UNIQUE INDEX jobs_crawl_identity
                    ON jobs(crawl_source_id, external_job_id)
                    WHERE crawl_source_id IS NOT NULL;
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (2, utc_now_iso()),
            )
        if version < 3 <= SCHEMA_VERSION:
            connection.executescript(
                """
                ALTER TABLE crawl_sources
                    ADD COLUMN company_id TEXT REFERENCES companies(id);
                ALTER TABLE crawl_sources ADD COLUMN scope_key TEXT;
                ALTER TABLE crawl_sources ADD COLUMN adapter_type TEXT;
                ALTER TABLE crawl_sources ADD COLUMN base_url TEXT;
                """
            )
            _backfill_crawl_source_companies(connection)
            connection.execute(
                """
                CREATE UNIQUE INDEX crawl_sources_company_scope
                ON crawl_sources(company_id, scope_key)
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (3, utc_now_iso()),
            )
        if version < 4 <= SCHEMA_VERSION:
            connection.executescript(
                """
                CREATE TABLE resume_imports (
                    id TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL UNIQUE,
                    upload_token TEXT NOT NULL UNIQUE,
                    source_kind TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    private_path TEXT NOT NULL,
                    extracted_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE candidate_profile (
                    id TEXT PRIMARY KEY,
                    display_name TEXT,
                    current_version INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE candidate_facts (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL
                        REFERENCES candidate_profile(id) ON DELETE CASCADE,
                    section TEXT NOT NULL,
                    fact_key TEXT NOT NULL,
                    fact_value_json TEXT NOT NULL,
                    sensitivity TEXT NOT NULL,
                    source_import_id TEXT NOT NULL
                        REFERENCES resume_imports(id),
                    confirmed_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(profile_id, section, fact_key)
                );
                CREATE TABLE profile_versions (
                    id TEXT PRIMARY KEY,
                    profile_id TEXT NOT NULL
                        REFERENCES candidate_profile(id) ON DELETE CASCADE,
                    version_number INTEGER NOT NULL,
                    confirmed_sections_json TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    source_import_id TEXT NOT NULL
                        REFERENCES resume_imports(id),
                    created_at TEXT NOT NULL,
                    UNIQUE(profile_id, version_number)
                );
                CREATE TABLE resume_previews (
                    id TEXT PRIMARY KEY,
                    resume_import_id TEXT NOT NULL
                        REFERENCES resume_imports(id) ON DELETE CASCADE,
                    preview_token TEXT NOT NULL UNIQUE,
                    proposal_json TEXT NOT NULL,
                    conflicts_json TEXT NOT NULL,
                    confirmed_sections_json TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX candidate_facts_profile_section
                    ON candidate_facts(profile_id, section);
                CREATE INDEX resume_previews_import
                    ON resume_previews(resume_import_id);
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (4, utc_now_iso()),
            )
        if version < 5 <= SCHEMA_VERSION:
            connection.executescript(
                """
                ALTER TABLE resume_imports ADD COLUMN display_name TEXT;
                ALTER TABLE resume_imports
                    ADD COLUMN target_roles_json TEXT NOT NULL DEFAULT '[]';
                ALTER TABLE resume_imports ADD COLUMN deleted_at TEXT;
                UPDATE resume_imports
                SET display_name = original_filename
                WHERE display_name IS NULL;
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (5, utc_now_iso()),
            )
        if version < 6 <= SCHEMA_VERSION:
            connection.executescript(
                """
                CREATE TABLE job_resume_matches (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    resume_import_id TEXT NOT NULL REFERENCES resume_imports(id),
                    job_content_hash TEXT NOT NULL,
                    resume_revision_at TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(
                        job_id,
                        resume_import_id,
                        job_content_hash,
                        resume_revision_at
                    )
                );
                CREATE INDEX job_resume_matches_job
                    ON job_resume_matches(job_id, created_at DESC);
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (6, utc_now_iso()),
            )
        if version < 7 <= SCHEMA_VERSION:
            for statement in (
                """
                CREATE TABLE job_tracking (
                    job_id TEXT PRIMARY KEY REFERENCES jobs(id),
                    is_favorite INTEGER NOT NULL DEFAULT 0
                        CHECK(is_favorite IN (0, 1)),
                    favorited_at TEXT,
                    application_status TEXT NOT NULL DEFAULT 'not_started'
                        CHECK(application_status IN (
                            'not_started', 'preparing', 'applied',
                            'assessment', 'interviewing', 'offer',
                            'accepted', 'rejected', 'withdrawn'
                        )),
                    applied_at TEXT,
                    note TEXT,
                    version INTEGER NOT NULL DEFAULT 1
                        CHECK(version >= 1),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
                """
                CREATE INDEX job_tracking_favorite
                    ON job_tracking(is_favorite, updated_at DESC)
                """,
                """
                CREATE INDEX job_tracking_application_status
                    ON job_tracking(
                        application_status,
                        updated_at DESC
                    )
                """,
                """
                CREATE TABLE job_application_events (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES job_tracking(job_id),
                    from_status TEXT NOT NULL,
                    to_status TEXT NOT NULL,
                    occurred_at TEXT NOT NULL
                )
                """,
                """
                CREATE INDEX job_application_events_job
                    ON job_application_events(
                        job_id,
                        occurred_at DESC,
                        id DESC
                    )
                """,
            ):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (7, utc_now_iso()),
            )
        if version < 8 <= SCHEMA_VERSION:
            for statement in (
                """
                CREATE TABLE tailored_resume_drafts (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    resume_import_id TEXT NOT NULL REFERENCES resume_imports(id),
                    snapshot_id TEXT NOT NULL REFERENCES job_resume_matches(id),
                    job_content_hash TEXT NOT NULL,
                    resume_revision_at TEXT NOT NULL,
                    template_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN (
                        'draft', 'review', 'confirmed',
                        'exported', 'stale'
                    )),
                    items_json TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK(version >= 1),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    confirmed_at TEXT,
                    exported_at TEXT
                )
                """,
                """
                CREATE INDEX tailored_resume_drafts_lookup
                    ON tailored_resume_drafts(
                        job_id,
                        resume_import_id,
                        updated_at DESC,
                        id DESC
                    )
                """,
                """
                CREATE TABLE tailored_resume_exports (
                    id TEXT PRIMARY KEY,
                    draft_id TEXT NOT NULL
                        REFERENCES tailored_resume_drafts(id),
                    draft_version INTEGER NOT NULL,
                    directory_path TEXT NOT NULL,
                    docx_path TEXT NOT NULL,
                    pdf_path TEXT NOT NULL,
                    docx_sha256 TEXT NOT NULL,
                    pdf_sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(draft_id, draft_version)
                )
                """,
            ):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (8, utc_now_iso()),
            )
        if version < 9 <= SCHEMA_VERSION:
            connection.execute(
                """
                ALTER TABLE resume_imports
                ADD COLUMN extraction_method TEXT NOT NULL DEFAULT 'native'
                CHECK(extraction_method IN ('native', 'ocr', 'hybrid'))
                """
            )
            connection.execute(
                """
                ALTER TABLE resume_imports
                ADD COLUMN extraction_metadata_json TEXT NOT NULL DEFAULT '{}'
                """
            )
            legacy_metadata = {
                "version": 1,
                "method": "native",
                "total_pages": 1,
                "native_pages": [1],
                "ocr_pages": [],
                "ocr_attempted_pages": [],
                "mean_confidence": None,
                "quality": "native",
                "review_required": False,
                "warning_codes": ["LEGACY_PROVENANCE"],
                "engine": None,
            }
            connection.execute(
                """
                UPDATE resume_imports
                SET extraction_method = 'native',
                    extraction_metadata_json = ?
                """,
                (
                    json.dumps(
                        legacy_metadata,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            )
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (9, utc_now_iso()),
            )
        if version < 10 <= SCHEMA_VERSION:
            for statement in (
                """
                CREATE TABLE interview_sessions (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    resume_import_id TEXT NOT NULL
                        REFERENCES resume_imports(id),
                    snapshot_id TEXT NOT NULL
                        REFERENCES job_resume_matches(id),
                    conversation_id TEXT,
                    company TEXT,
                    position TEXT NOT NULL,
                    difficulty TEXT NOT NULL CHECK(
                        difficulty IN ('simple', 'standard', 'deep')
                    ),
                    duration_minutes INTEGER NOT NULL CHECK(
                        duration_minutes IN (10, 15, 20)
                    ),
                    question_budget INTEGER NOT NULL CHECK(
                        question_budget IN (5, 8, 10)
                    ),
                    blueprint_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN (
                        'created', 'ready', 'in_progress',
                        'completed', 'cancelled', 'failed'
                    )),
                    phase TEXT NOT NULL CHECK(phase IN (
                        'preparing', 'asking', 'waiting_for_answer',
                        'transcribing', 'evaluating',
                        'generating_report', 'idle'
                    )),
                    version INTEGER NOT NULL CHECK(version >= 1),
                    started_at TEXT,
                    ended_at TEXT,
                    report_path TEXT,
                    transcript_path TEXT,
                    session_path TEXT,
                    report_sha256 TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """,
                """
                CREATE INDEX interview_sessions_lookup
                    ON interview_sessions(
                        job_id,
                        resume_import_id,
                        created_at DESC,
                        id DESC
                    )
                """,
                """
                CREATE TABLE interview_turns (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL
                        REFERENCES interview_sessions(id)
                        ON DELETE CASCADE,
                    turn_index INTEGER NOT NULL CHECK(turn_index >= 1),
                    question_text TEXT NOT NULL,
                    question_refs_json TEXT NOT NULL,
                    answer_text TEXT,
                    evaluation_json TEXT,
                    next_action TEXT CHECK(
                        next_action IS NULL OR next_action IN (
                            'FOLLOW_UP', 'VERIFY_CLAIM', 'DEEP_DIVE',
                            'SWITCH_TOPIC', 'WRAP_UP'
                        )
                    ),
                    next_reason TEXT,
                    started_at TEXT NOT NULL,
                    answered_at TEXT,
                    evaluated_at TEXT,
                    UNIQUE(session_id, turn_index)
                )
                """,
                """
                CREATE INDEX interview_turns_session
                    ON interview_turns(
                        session_id,
                        turn_index
                    )
                """,
            ):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (10, utc_now_iso()),
            )
        if version < 11 <= SCHEMA_VERSION:
            for statement in (
                (
                    "ALTER TABLE interview_turns "
                    "ADD COLUMN question_topic TEXT"
                ),
                (
                    "ALTER TABLE interview_turns "
                    "ADD COLUMN probe_target TEXT"
                ),
                (
                    "ALTER TABLE interview_turns "
                    "ADD COLUMN probe_dimension TEXT"
                ),
                (
                    "ALTER TABLE interview_turns "
                    "ADD COLUMN depth_level INTEGER "
                    "CHECK(depth_level IS NULL OR depth_level >= 1)"
                ),
            ):
                connection.execute(statement)
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (11, utc_now_iso()),
            )
        if version < 12 <= SCHEMA_VERSION:
            connection.executescript(
                """
                CREATE TABLE crawl_cycles (
                    id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES crawl_sources(id),
                    status TEXT NOT NULL CHECK(status IN (
                        'running', 'degraded', 'failed', 'committed'
                    )),
                    pass_number INTEGER NOT NULL DEFAULT 1
                        CHECK(pass_number BETWEEN 1 AND 3),
                    expected_total INTEGER,
                    started_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    error_summary TEXT
                );
                CREATE UNIQUE INDEX crawl_cycles_one_running_source
                    ON crawl_cycles(source_id)
                    WHERE status = 'running';
                CREATE TABLE crawl_cycle_shards (
                    cycle_id TEXT NOT NULL
                        REFERENCES crawl_cycles(id) ON DELETE CASCADE,
                    shard_key TEXT NOT NULL,
                    filters_json TEXT NOT NULL,
                    expected_count INTEGER,
                    next_offset INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL CHECK(status IN (
                        'pending', 'running', 'complete', 'degraded'
                    )),
                    last_page_fingerprint TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (cycle_id, shard_key)
                );
                CREATE TABLE crawl_cycle_jobs (
                    cycle_id TEXT NOT NULL
                        REFERENCES crawl_cycles(id) ON DELETE CASCADE,
                    external_job_id TEXT NOT NULL,
                    snapshot_json TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    first_pass INTEGER NOT NULL,
                    last_pass INTEGER NOT NULL,
                    observed_at TEXT NOT NULL,
                    PRIMARY KEY (cycle_id, external_job_id)
                );
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (12, utc_now_iso()),
            )
        if version < 13 <= SCHEMA_VERSION:
            connection.executescript(
                """
                PRAGMA foreign_keys = OFF;
                DROP INDEX interview_turns_session;
                DROP INDEX interview_sessions_lookup;
                ALTER TABLE interview_turns
                    RENAME TO interview_turns_legacy;
                ALTER TABLE interview_sessions
                    RENAME TO interview_sessions_legacy;
                CREATE TABLE interview_sessions (
                    id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(id),
                    resume_import_id TEXT NOT NULL
                        REFERENCES resume_imports(id),
                    legacy_snapshot_id TEXT,
                    conversation_id TEXT,
                    company TEXT,
                    position TEXT NOT NULL,
                    difficulty TEXT NOT NULL CHECK(
                        difficulty IN ('simple', 'standard', 'deep')
                    ),
                    duration_minutes INTEGER NOT NULL CHECK(
                        duration_minutes IN (10, 15, 20)
                    ),
                    question_budget INTEGER NOT NULL CHECK(
                        question_budget IN (5, 8, 10)
                    ),
                    blueprint_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN (
                        'created', 'ready', 'in_progress',
                        'completed', 'cancelled', 'failed'
                    )),
                    phase TEXT NOT NULL CHECK(phase IN (
                        'preparing', 'asking', 'waiting_for_answer',
                        'transcribing', 'evaluating',
                        'generating_report', 'idle'
                    )),
                    version INTEGER NOT NULL CHECK(version >= 1),
                    started_at TEXT,
                    ended_at TEXT,
                    report_path TEXT,
                    transcript_path TEXT,
                    session_path TEXT,
                    report_sha256 TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO interview_sessions(
                    id, job_id, resume_import_id, legacy_snapshot_id,
                    conversation_id, company, position, difficulty,
                    duration_minutes, question_budget, blueprint_json,
                    status, phase, version, started_at, ended_at,
                    report_path, transcript_path, session_path,
                    report_sha256, created_at, updated_at
                )
                SELECT
                    id, job_id, resume_import_id, snapshot_id,
                    conversation_id, company, position, difficulty,
                    duration_minutes, question_budget, blueprint_json,
                    status, phase, version, started_at, ended_at,
                    report_path, transcript_path, session_path,
                    report_sha256, created_at, updated_at
                FROM interview_sessions_legacy;
                CREATE INDEX interview_sessions_lookup
                    ON interview_sessions(
                        job_id,
                        resume_import_id,
                        created_at DESC,
                        id DESC
                    );
                CREATE TABLE interview_turns (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL
                        REFERENCES interview_sessions(id)
                        ON DELETE CASCADE,
                    turn_index INTEGER NOT NULL CHECK(turn_index >= 1),
                    question_text TEXT NOT NULL,
                    question_refs_json TEXT NOT NULL,
                    answer_text TEXT,
                    evaluation_json TEXT,
                    next_action TEXT CHECK(
                        next_action IS NULL OR next_action IN (
                            'FOLLOW_UP', 'VERIFY_CLAIM', 'DEEP_DIVE',
                            'SWITCH_TOPIC', 'WRAP_UP'
                        )
                    ),
                    next_reason TEXT,
                    question_topic TEXT,
                    probe_target TEXT,
                    probe_dimension TEXT,
                    depth_level INTEGER
                        CHECK(depth_level IS NULL OR depth_level >= 1),
                    started_at TEXT NOT NULL,
                    answered_at TEXT,
                    evaluated_at TEXT,
                    UNIQUE(session_id, turn_index)
                );
                INSERT INTO interview_turns(
                    id, session_id, turn_index, question_text,
                    question_refs_json, answer_text, evaluation_json,
                    next_action, next_reason, question_topic,
                    probe_target, probe_dimension, depth_level,
                    started_at, answered_at, evaluated_at
                )
                SELECT
                    id, session_id, turn_index, question_text,
                    question_refs_json, answer_text, evaluation_json,
                    next_action, next_reason, question_topic,
                    probe_target, probe_dimension, depth_level,
                    started_at, answered_at, evaluated_at
                FROM interview_turns_legacy;
                CREATE INDEX interview_turns_session
                    ON interview_turns(session_id, turn_index);
                DROP TABLE interview_turns_legacy;
                DROP TABLE interview_sessions_legacy;
                PRAGMA foreign_keys = ON;
                """
            )
            connection.execute(
                "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (13, utc_now_iso()),
            )
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def _backfill_crawl_source_companies(connection: sqlite3.Connection) -> None:
    sources = connection.execute("SELECT id, slug, name FROM crawl_sources").fetchall()
    for source in sources:
        slug = str(source["slug"])
        metadata = _KNOWN_CRAWL_SOURCES.get(slug)
        if metadata is None:
            metadata = {
                "source_name": str(source["name"]),
                "company_slug": slug,
                "company_name": str(source["name"]),
                "scope_key": f"source:{slug}",
                "adapter_type": "legacy",
                "base_url": None,
            }

        legacy_company = connection.execute(
            "SELECT id FROM companies WHERE slug = ?", (slug,)
        ).fetchone()
        canonical_company = connection.execute(
            "SELECT id FROM companies WHERE slug = ?",
            (metadata["company_slug"],),
        ).fetchone()

        if canonical_company is None and legacy_company is not None:
            company_id = str(legacy_company["id"])
            connection.execute(
                "UPDATE companies SET slug = ?, name = ? WHERE id = ?",
                (
                    metadata["company_slug"],
                    metadata["company_name"],
                    company_id,
                ),
            )
        elif canonical_company is not None:
            company_id = str(canonical_company["id"])
            connection.execute(
                "UPDATE companies SET name = ? WHERE id = ?",
                (metadata["company_name"], company_id),
            )
            if legacy_company is not None and legacy_company["id"] != company_id:
                legacy_id = str(legacy_company["id"])
                connection.execute(
                    "UPDATE jobs SET company_id = ? WHERE company_id = ?",
                    (company_id, legacy_id),
                )
                connection.execute(
                    "UPDATE job_sources SET company_id = ? WHERE company_id = ?",
                    (company_id, legacy_id),
                )
                connection.execute(
                    """
                    DELETE FROM companies
                    WHERE id = ?
                      AND NOT EXISTS (
                          SELECT 1 FROM jobs WHERE company_id = companies.id
                      )
                      AND NOT EXISTS (
                          SELECT 1 FROM job_sources WHERE company_id = companies.id
                      )
                    """,
                    (legacy_id,),
                )
        else:
            company_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO companies(id, slug, name, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    company_id,
                    metadata["company_slug"],
                    metadata["company_name"],
                    utc_now_iso(),
                ),
            )

        connection.execute(
            """
            UPDATE crawl_sources
            SET name = ?, company_id = ?, scope_key = ?, adapter_type = ?,
                base_url = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                metadata["source_name"],
                company_id,
                metadata["scope_key"],
                metadata["adapter_type"],
                metadata["base_url"],
                utc_now_iso(),
                source["id"],
            ),
        )
