from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coworker.server.identity import Principal
from coworker.storage.postgres.database import CloudDatabase
from coworker.storage.postgres.blob_repository import PostgresBlobRepository
from coworker.storage.postgres.resume_service import PostgresResumeService
from deploy.migrate_to_postgres import (
    _interview_conflict_losers,
    _referenced_job_ids,
    inspect_career_source,
    migrate_career_database,
)
from extensions.career_mcp.tests.test_interview_service import _seed


def test_migration_dry_run_reports_source_hash_and_counts(tmp_path) -> None:
    config, _, _, _, _ = _seed(tmp_path)

    report = inspect_career_source(config.database_path)

    assert len(report["source_sha256"]) == 64
    assert report["counts"]["jobs"] == 1
    assert report["counts"]["resume_imports"] == 1
    assert "job_resume_matches" not in report["counts"]
    assert "tailored_resume_drafts" not in report["counts"]
    assert "tailored_resume_exports" not in report["counts"]


def test_migration_keeps_only_latest_conflicting_interview_active() -> None:
    sessions = [
        {
            "id": "older",
            "job_id": "legacy-job",
            "resume_import_id": "legacy-resume",
            "status": "in_progress",
            "created_at": "2026-08-18T14:31:01Z",
            "updated_at": "2026-08-18T14:34:45Z",
        },
        {
            "id": "completed",
            "job_id": "legacy-job",
            "resume_import_id": "legacy-resume",
            "status": "completed",
            "created_at": "2026-08-18T13:28:29Z",
            "updated_at": "2026-08-18T14:26:09Z",
        },
        {
            "id": "latest",
            "job_id": "legacy-job",
            "resume_import_id": "legacy-resume",
            "status": "in_progress",
            "created_at": "2026-08-18T14:38:10Z",
            "updated_at": "2026-08-18T14:39:05Z",
        },
    ]

    losers = _interview_conflict_losers(
        sessions,
        {"legacy-job": "postgres-job"},
        {"legacy-resume": "postgres-resume"},
    )

    assert losers == {"older"}


def test_migration_finds_only_jobs_referenced_by_user_state() -> None:
    source = sqlite3.connect(":memory:")
    source.row_factory = sqlite3.Row
    for table in (
        "job_tracking",
        "job_resume_matches",
        "tailored_resume_drafts",
        "interview_sessions",
    ):
        source.execute(f"CREATE TABLE {table} (job_id TEXT)")
    source.execute("INSERT INTO job_resume_matches VALUES ('job-1')")
    source.execute("INSERT INTO tailored_resume_drafts VALUES ('job-1')")
    source.execute("INSERT INTO interview_sessions VALUES ('job-1')")
    source.execute("INSERT INTO interview_sessions VALUES ('job-2')")

    assert _referenced_job_ids(source) == {"job-1", "job-2"}

    source.close()


def test_real_postgres_migration_is_idempotent(tmp_path) -> None:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("TEST_DATABASE_URL is required")
    config, _, _, _, _ = _seed(tmp_path)
    user_id = f"migration-{uuid4()}"
    database = CloudDatabase.from_url(url, min_size=1, max_size=1)
    database.migrate()
    try:
        first = migrate_career_database(
            database,
            source_path=config.database_path,
            private_root=config.private_resume_dir.parent,
            user_id=user_id,
        )
        second = migrate_career_database(
            database,
            source_path=config.database_path,
            private_root=config.private_resume_dir.parent,
            user_id=user_id,
        )

        assert first["reused"] is False
        assert second["reused"] is True
        assert second["source_sha256"] == first["source_sha256"]
        with database.transaction(
            Principal(user_id, "test")
        ) as connection:
            assert connection.execute(
                """
                SELECT COUNT(*) FROM career.resume_imports
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()[0] == 1
            assert connection.execute(
                """
                SELECT COUNT(*) FROM career.candidate_profiles
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()[0] == 1
            assert connection.execute(
                """
                SELECT COUNT(*) FROM career.candidate_facts
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()[0] > 0
            assert connection.execute(
                """
                SELECT COUNT(*) FROM career.profile_versions
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()[0] > 0
            assert connection.execute(
                """
                SELECT COUNT(*) FROM career.resume_previews
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()[0] > 0
        service = PostgresResumeService(
            database,
            Principal(user_id, "test"),
            PostgresBlobRepository(database),
        )
        assert service.get_candidate_profile()["current_version"] > 0
        assert service.list_resume_documents()
    finally:
        database.close()
