import json
import sqlite3
from pathlib import Path

import pytest

from extensions.career_mcp.database import migrations
from extensions.career_mcp.database.migrations import (
    connect,
    migrate,
    schema_version,
)


def test_schema_v5_backfills_resume_document_metadata(tmp_path):
    database_path = tmp_path / "career.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );
        INSERT INTO schema_migrations VALUES (4, '2026-08-08T00:00:00Z');
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
        INSERT INTO resume_imports VALUES (
            'resume-1', 'hash', 'token', 'pdf', 'resume.pdf',
            'resumes/hash.pdf', 'private text', 'confirmed',
            '2026-08-09T00:00:00Z', '2026-08-08T00:00:00Z',
            '2026-08-08T00:00:00Z'
        );
        PRAGMA user_version = 4;
        """
    )

    migrate(connection)

    assert schema_version(connection) == migrations.SCHEMA_VERSION
    row = connection.execute(
        """
        SELECT display_name, target_roles_json, deleted_at
        FROM resume_imports
        """
    ).fetchone()
    assert row["display_name"] == "resume.pdf"
    assert row["target_roles_json"] == "[]"
    assert row["deleted_at"] is None
    connection.close()


def test_schema_v6_adds_job_resume_match_snapshots(tmp_path: Path):
    connection = connect(tmp_path / "career.sqlite3")
    migrate(connection)
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }

    assert schema_version(connection) == migrations.SCHEMA_VERSION
    assert "job_resume_matches" in tables
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(job_resume_matches)"
        )
    }
    assert columns == {
        "id",
        "job_id",
        "resume_import_id",
        "job_content_hash",
        "resume_revision_at",
        "result_json",
        "created_at",
    }
    connection.close()


def test_schema_v7_adds_job_tracking_and_events(tmp_path: Path):
    connection = connect(tmp_path / "career.sqlite3")
    migrate(connection)
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }

    assert schema_version(connection) == migrations.SCHEMA_VERSION
    assert {"job_tracking", "job_application_events"} <= tables
    assert {
        row["name"]
        for row in connection.execute("PRAGMA table_info(job_tracking)")
    } == {
        "job_id",
        "is_favorite",
        "favorited_at",
        "application_status",
        "applied_at",
        "note",
        "version",
        "created_at",
        "updated_at",
    }
    connection.close()


def test_schema_v7_failure_is_atomic_and_retryable(
    tmp_path: Path,
    monkeypatch,
):
    connection = connect(tmp_path / "career.sqlite3")
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 6)
    migrate(connection)
    connection.execute(
        """
        CREATE TABLE job_application_events (
            id TEXT PRIMARY KEY
        )
        """
    )
    connection.commit()
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 7)

    with pytest.raises(sqlite3.OperationalError):
        migrate(connection)

    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert schema_version(connection) == 6
    assert "job_tracking" not in tables

    connection.execute("DROP TABLE job_application_events")
    connection.commit()
    migrate(connection)

    assert schema_version(connection) == 7
    assert connection.execute(
        """
        SELECT COUNT(*) FROM sqlite_master
        WHERE type = 'table' AND name IN (
            'job_tracking',
            'job_application_events'
        )
        """
    ).fetchone()[0] == 2
    connection.close()


def test_schema_v8_adds_tailored_resume_tables(tmp_path: Path):
    connection = connect(tmp_path / "career.sqlite3")
    migrate(connection)

    assert schema_version(connection) == migrations.SCHEMA_VERSION
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {
        "tailored_resume_drafts",
        "tailored_resume_exports",
    } <= tables
    assert {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(tailored_resume_drafts)"
        )
    } == {
        "id",
        "job_id",
        "resume_import_id",
        "snapshot_id",
        "job_content_hash",
        "resume_revision_at",
        "template_id",
        "status",
        "items_json",
        "version",
        "created_at",
        "updated_at",
        "confirmed_at",
        "exported_at",
    }
    connection.close()


def test_current_schema_decouples_interviews_from_match_snapshots(
    tmp_path: Path,
):
    connection = connect(tmp_path / "career.sqlite3")
    migrate(connection)

    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(interview_sessions)"
        )
    }
    foreign_tables = {
        row["table"]
        for row in connection.execute(
            "PRAGMA foreign_key_list(interview_sessions)"
        )
    }

    assert "snapshot_id" not in columns
    assert "legacy_snapshot_id" in columns
    assert "job_resume_matches" not in foreign_tables
    connection.close()


def test_schema_v8_failure_is_atomic_and_retryable(
    tmp_path: Path,
    monkeypatch,
):
    connection = connect(tmp_path / "career.sqlite3")
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 7)
    migrate(connection)
    connection.execute(
        "CREATE TABLE tailored_resume_exports(id TEXT PRIMARY KEY)"
    )
    connection.commit()
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 8)

    with pytest.raises(sqlite3.OperationalError):
        migrate(connection)

    assert schema_version(connection) == 7
    assert connection.execute(
        """
        SELECT COUNT(*) FROM sqlite_master
        WHERE type = 'table' AND name = 'tailored_resume_drafts'
        """
    ).fetchone()[0] == 0

    connection.execute("DROP TABLE tailored_resume_exports")
    connection.commit()
    migrate(connection)

    assert schema_version(connection) == 8
    assert connection.execute(
        """
        SELECT COUNT(*) FROM sqlite_master
        WHERE type = 'table' AND name IN (
            'tailored_resume_drafts',
            'tailored_resume_exports'
        )
        """
    ).fetchone()[0] == 2
    connection.close()


def _insert_v8_resume(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO resume_imports(
            id, content_hash, upload_token, source_kind,
            original_filename, private_path, extracted_text, status,
            expires_at, created_at, updated_at, display_name,
            target_roles_json, deleted_at
        ) VALUES (
            'legacy-resume', 'legacy-hash', 'legacy-token', 'pdf',
            'legacy.pdf', 'resumes/legacy.pdf', 'legacy private text',
            'confirmed', '2026-08-11T00:00:00Z',
            '2026-08-10T00:00:00Z', '2026-08-10T00:00:00Z',
            'Legacy Resume', '[]', NULL
        )
        """
    )
    connection.commit()


def test_schema_v9_backfills_resume_extraction_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = connect(tmp_path / "career.sqlite3")
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 8)
    migrate(connection)
    _insert_v8_resume(connection)
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 9)

    migrate(connection)

    columns = {
        row["name"]: row
        for row in connection.execute("PRAGMA table_info(resume_imports)")
    }
    row = connection.execute(
        """
        SELECT extraction_method, extraction_metadata_json
        FROM resume_imports
        WHERE id = 'legacy-resume'
        """
    ).fetchone()
    metadata = json.loads(row["extraction_metadata_json"])
    assert schema_version(connection) == 9
    assert columns["extraction_method"]["notnull"] == 1
    assert columns["extraction_metadata_json"]["notnull"] == 1
    assert row["extraction_method"] == "native"
    assert metadata == {
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
    connection.close()


class _FailingV9Connection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.fail = True

    def execute(self, sql: str, parameters=()):
        if (
            self.fail
            and "ADD COLUMN extraction_metadata_json" in sql
        ):
            raise sqlite3.OperationalError("injected v9 migration failure")
        return self.connection.execute(sql, parameters)

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()


def test_schema_v9_failure_is_atomic_and_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = connect(tmp_path / "career.sqlite3")
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 8)
    migrate(connection)
    _insert_v8_resume(connection)
    proxy = _FailingV9Connection(connection)
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 9)

    with pytest.raises(sqlite3.OperationalError):
        migrate(proxy)  # type: ignore[arg-type]

    columns_after_failure = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(resume_imports)")
    }
    assert schema_version(connection) == 8
    assert "extraction_method" not in columns_after_failure
    assert "extraction_metadata_json" not in columns_after_failure

    proxy.fail = False
    migrate(proxy)  # type: ignore[arg-type]

    columns_after_retry = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(resume_imports)")
    }
    assert schema_version(connection) == 9
    assert {
        "extraction_method",
        "extraction_metadata_json",
    } <= columns_after_retry
    connection.close()


def test_schema_v10_adds_interview_sessions_and_turns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = connect(tmp_path / "career.sqlite3")
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 10)

    migrate(connection)

    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert schema_version(connection) == 10
    assert {"interview_sessions", "interview_turns"} <= tables
    assert {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(interview_sessions)"
        )
    } == {
        "id",
        "job_id",
        "resume_import_id",
        "snapshot_id",
        "conversation_id",
        "company",
        "position",
        "difficulty",
        "duration_minutes",
        "question_budget",
        "blueprint_json",
        "status",
        "phase",
        "version",
        "started_at",
        "ended_at",
        "report_path",
        "transcript_path",
        "session_path",
        "report_sha256",
        "created_at",
        "updated_at",
    }
    assert {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(interview_turns)"
        )
    } == {
        "id",
        "session_id",
        "turn_index",
        "question_text",
        "question_refs_json",
        "answer_text",
        "evaluation_json",
        "next_action",
        "next_reason",
        "started_at",
        "answered_at",
        "evaluated_at",
    }
    assert connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchall() == []
    connection.close()


class _FailingV10Connection:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.fail = True

    def execute(self, sql: str, parameters=()):
        if self.fail and "CREATE TABLE interview_turns" in sql:
            raise sqlite3.OperationalError(
                "injected v10 migration failure"
            )
        return self.connection.execute(sql, parameters)

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()


def test_schema_v10_failure_is_atomic_and_retryable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = connect(tmp_path / "career.sqlite3")
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 9)
    migrate(connection)
    proxy = _FailingV10Connection(connection)
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 10)

    with pytest.raises(sqlite3.OperationalError):
        migrate(proxy)  # type: ignore[arg-type]

    tables_after_failure = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert schema_version(connection) == 9
    assert "interview_sessions" not in tables_after_failure
    assert "interview_turns" not in tables_after_failure

    proxy.fail = False
    migrate(proxy)  # type: ignore[arg-type]

    tables_after_retry = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert schema_version(connection) == 10
    assert {"interview_sessions", "interview_turns"} <= tables_after_retry
    assert connection.execute(
        "PRAGMA foreign_key_check"
    ).fetchall() == []
    connection.close()


def test_schema_v11_adds_interview_probe_metadata(
    tmp_path: Path,
) -> None:
    connection = connect(tmp_path / "career.sqlite3")

    migrate(connection)

    assert schema_version(connection) == migrations.SCHEMA_VERSION
    columns = {
        row["name"]
        for row in connection.execute(
            "PRAGMA table_info(interview_turns)"
        )
    }
    assert {
        "question_topic",
        "probe_target",
        "probe_dimension",
        "depth_level",
    } <= columns
    connection.close()


def test_schema_v11_preserves_v10_turn_with_null_probe_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = connect(tmp_path / "career.sqlite3")
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 10)
    migrate(connection)
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute(
        """
        INSERT INTO interview_sessions(
            id, job_id, resume_import_id, snapshot_id,
            position, difficulty, duration_minutes, question_budget,
            blueprint_json, status, phase, version, created_at, updated_at
        ) VALUES (
            'session-v10', 'job-v10', 'resume-v10', 'snapshot-v10',
            '研发工程师', 'standard', 15, 8,
            '{"version":1,"focus_areas":[]}',
            'in_progress', 'waiting_for_answer', 1,
            '2026-08-11T00:00:00Z', '2026-08-11T00:00:00Z'
        )
        """
    )
    connection.execute(
        """
        INSERT INTO interview_turns(
            id, session_id, turn_index, question_text,
            question_refs_json, started_at
        ) VALUES (
            'turn-v10', 'session-v10', 1, '请介绍相关经历？',
            '["INTRO"]', '2026-08-11T00:00:00Z'
        )
        """
    )
    connection.commit()
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 11)

    migrate(connection)

    row = connection.execute(
        "SELECT * FROM interview_turns WHERE id = 'turn-v10'"
    ).fetchone()
    assert schema_version(connection) == migrations.SCHEMA_VERSION
    assert row["question_topic"] is None
    assert row["probe_target"] is None
    assert row["probe_dimension"] is None
    assert row["depth_level"] is None
    connection.close()
