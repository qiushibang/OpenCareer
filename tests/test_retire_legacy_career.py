from __future__ import annotations

import hashlib
import sqlite3
from contextlib import nullcontext
from pathlib import Path

import pytest

from deploy.archive_legacy_career import archive_postgres, archive_sqlite
from deploy.retire_legacy_career import retire_postgres, retire_sqlite
from extensions.career_mcp.database.migrations import connect
from extensions.career_mcp.services.interviews import InterviewService
from extensions.career_mcp.tests.test_interview_service import _seed
from tests.test_archive_legacy_career import (
    _Cursor,
    _PostgresArchiveConnection,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _legacy_database(
    tmp_path: Path,
) -> tuple[Path, Path, str, str, str]:
    config, resumes, _, job_id, resume_id = _seed(tmp_path)
    workspace = tmp_path / "workspace"
    session = InterviewService(
        config,
        workspace=workspace,
    ).create(
        job_id,
        resume_id,
        conversation_id="retirement-conversation",
        difficulty="standard",
        duration_minutes=15,
    )
    export_dir = workspace / "artifacts" / "tailored-resumes" / "draft-1"
    export_dir.mkdir(parents=True)
    docx = export_dir / "resume.docx"
    pdf = export_dir / "resume.pdf"
    docx.write_bytes(b"docx-content")
    pdf.write_bytes(b"pdf-content")
    packet_dir = workspace / "artifacts" / "application-packets"
    packet_dir.mkdir(parents=True)
    (packet_dir / "packet.md").write_text(
        "# legacy packet\n",
        encoding="utf-8",
    )
    connection = connect(config.database_path)
    connection.execute(
        """
        INSERT INTO job_resume_matches(
            id, job_id, resume_import_id, job_content_hash,
            resume_revision_at, result_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "match-1",
            job_id,
            resume_id,
            "a" * 64,
            "2026-08-24T00:00:00Z",
            '{"score":80}',
            "2026-08-24T00:00:00Z",
        ),
    )
    connection.execute(
        """
        INSERT INTO tailored_resume_drafts(
            id, job_id, resume_import_id, snapshot_id,
            job_content_hash, resume_revision_at, template_id,
            status, items_json, version, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "draft-1",
            job_id,
            resume_id,
            "match-1",
            "a" * 64,
            "2026-08-24T00:00:00Z",
            "ats",
            "exported",
            "[]",
            1,
            "2026-08-24T00:00:00Z",
            "2026-08-24T00:00:00Z",
        ),
    )
    connection.execute(
        """
        INSERT INTO tailored_resume_exports(
            id, draft_id, draft_version, directory_path,
            docx_path, pdf_path, docx_sha256, pdf_sha256, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "export-1",
            "draft-1",
            1,
            "artifacts/tailored-resumes/draft-1",
            "artifacts/tailored-resumes/draft-1/resume.docx",
            "artifacts/tailored-resumes/draft-1/resume.pdf",
            _sha256(docx),
            _sha256(pdf),
            "2026-08-24T00:00:00Z",
        ),
    )
    connection.commit()
    connection.close()
    assert resumes.list_resume_documents()
    return (
        config.database_path,
        workspace,
        session["id"],
        job_id,
        resume_id,
    )


def _table_names(database_path: Path) -> set[str]:
    connection = sqlite3.connect(database_path)
    try:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        connection.close()


def test_retire_sqlite_requires_matching_external_manifest_hash(
    tmp_path: Path,
) -> None:
    database_path, workspace, _, _, _ = _legacy_database(tmp_path)
    archive = tmp_path / "archive"
    archive_sqlite(database_path, workspace, archive)
    before = _table_names(database_path)

    with pytest.raises(ValueError, match="manifest hash"):
        retire_sqlite(
            database_path,
            workspace,
            archive,
            expected_manifest_sha256="0" * 64,
        )

    assert _table_names(database_path) == before
    assert (workspace / "artifacts/application-packets/packet.md").exists()


def test_retire_sqlite_rejects_source_changes_after_archive(
    tmp_path: Path,
) -> None:
    database_path, workspace, _, _, _ = _legacy_database(tmp_path)
    archive = tmp_path / "archive"
    manifest = archive_sqlite(database_path, workspace, archive)
    connection = sqlite3.connect(database_path)
    connection.execute(
        "UPDATE job_resume_matches SET result_json = '{\"score\":10}'"
    )
    connection.commit()
    connection.close()

    with pytest.raises(ValueError, match="source data"):
        retire_sqlite(
            database_path,
            workspace,
            archive,
            expected_manifest_sha256=manifest["manifest_sha256"],
        )

    assert "job_resume_matches" in _table_names(database_path)


def test_retire_sqlite_removes_only_archived_legacy_data(
    tmp_path: Path,
) -> None:
    database_path, workspace, session_id, _, resume_id = _legacy_database(
        tmp_path
    )
    archive = tmp_path / "archive"
    manifest = archive_sqlite(database_path, workspace, archive)

    result = retire_sqlite(
        database_path,
        workspace,
        archive,
        expected_manifest_sha256=manifest["manifest_sha256"],
    )

    assert result["status"] == "completed"
    tables = _table_names(database_path)
    assert {
        "job_resume_matches",
        "application_packets",
        "tailored_resume_drafts",
        "tailored_resume_exports",
    }.isdisjoint(tables)
    connection = sqlite3.connect(database_path)
    try:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(interview_sessions)"
            )
        }
        assert "snapshot_id" not in columns
        assert "legacy_snapshot_id" not in columns
        assert connection.execute(
            "SELECT id FROM interview_sessions WHERE id = ?",
            (session_id,),
        ).fetchone() == (session_id,)
        assert connection.execute(
            "SELECT id FROM resume_imports WHERE id = ?",
            (resume_id,),
        ).fetchone() == (resume_id,)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute("PRAGMA integrity_check").fetchone() == (
            "ok",
        )
    finally:
        connection.close()
    assert not (
        workspace / "artifacts/application-packets/packet.md"
    ).exists()
    assert not (
        workspace
        / "artifacts/tailored-resumes/draft-1/resume.docx"
    ).exists()
    assert not (
        workspace
        / "artifacts/tailored-resumes/draft-1/resume.pdf"
    ).exists()


def test_retire_sqlite_is_idempotent_for_the_same_archive(
    tmp_path: Path,
) -> None:
    database_path, workspace, _, _, _ = _legacy_database(tmp_path)
    archive = tmp_path / "archive"
    manifest = archive_sqlite(database_path, workspace, archive)

    retire_sqlite(
        database_path,
        workspace,
        archive,
        expected_manifest_sha256=manifest["manifest_sha256"],
    )
    repeated = retire_sqlite(
        database_path,
        workspace,
        archive,
        expected_manifest_sha256=manifest["manifest_sha256"],
    )

    assert repeated["status"] == "already_completed"


class _UnprivilegedPostgresConnection:
    def transaction(self):
        return nullcontext()

    def execute(self, query: str, params=None):
        normalized = " ".join(query.split())
        if normalized.startswith("SET TRANSACTION"):
            return None
        if "FROM pg_roles" in normalized:
            return type(
                "Cursor",
                (),
                {"fetchone": lambda self: (False, False)},
            )()
        raise AssertionError(normalized)


class _RetirementPostgresConnection(_PostgresArchiveConnection):
    def __init__(self) -> None:
        super().__init__()
        self.retirement_sql_executed = False
        self.marker_inserted = False

    def transaction(self):
        return nullcontext()

    def execute(self, query: str, params=None):
        normalized = " ".join(query.split())
        if normalized.startswith("SET TRANSACTION"):
            return _Cursor([], [])
        if "FROM opencareer_meta.data_migrations" in normalized:
            return _Cursor(["source_sha256", "report"], [])
        if normalized.startswith("CREATE TEMP TABLE"):
            self.retirement_sql_executed = True
            return _Cursor([], [])
        if normalized.startswith(
            "INSERT INTO opencareer_meta.data_migrations"
        ):
            self.marker_inserted = True
            return _Cursor([], [])
        return super().execute(query, params)


def test_retire_postgres_requires_recovery_point_and_rls_bypass(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="recovery point"):
        retire_postgres(
            _UnprivilegedPostgresConnection(),
            tmp_path,
            expected_manifest_sha256="0" * 64,
            recovery_point_id="",
        )
    with pytest.raises(ValueError, match="BYPASSRLS"):
        retire_postgres(
            _UnprivilegedPostgresConnection(),
            tmp_path,
            expected_manifest_sha256="0" * 64,
            recovery_point_id="backup-1",
        )


def test_postgres_retirement_sql_is_explicit_and_not_automatic() -> None:
    root = Path(__file__).resolve().parents[1]
    sql_path = root / "deploy" / "sql" / "retire_legacy_career.sql"
    sql = sql_path.read_text(encoding="utf-8")
    compact = " ".join(sql.split())

    for table in (
        "career.tailored_resume_exports",
        "career.tailored_resume_drafts",
        "career.application_packets",
        "career.job_resume_matches",
    ):
        assert f"DROP TABLE {table}" in compact
    for kind in (
        "application_packet",
        "tailored_resume_docx",
        "tailored_resume_pdf",
    ):
        assert kind in sql
    assert "CREATE TEMP TABLE legacy_blob_candidates" in compact
    assert "career.resume_imports" in compact
    assert "catalog.raw_snapshots" in compact
    assert "CASCADE" not in sql.upper()
    assert "retire_legacy_career.sql" not in (
        root / "coworker" / "storage" / "postgres" / "migrations.py"
    ).read_text(encoding="utf-8")


def test_retire_postgres_verifies_archive_and_records_completion(
    tmp_path: Path,
) -> None:
    connection = _RetirementPostgresConnection()
    archive = tmp_path / "archive"
    manifest = archive_postgres(connection, archive)

    result = retire_postgres(
        connection,
        archive,
        expected_manifest_sha256=manifest["manifest_sha256"],
        recovery_point_id="backup-20260824",
    )

    assert result["status"] == "completed"
    assert result["recovery_point_id"] == "backup-20260824"
    assert connection.retirement_sql_executed is True
    assert connection.marker_inserted is True
