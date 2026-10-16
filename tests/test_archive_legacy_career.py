from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from deploy.archive_legacy_career import (
    archive_postgres,
    archive_sqlite,
    verify_archive,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _legacy_source(tmp_path: Path) -> tuple[Path, Path]:
    database_path = tmp_path / "career.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE job_resume_matches (
            id TEXT PRIMARY KEY,
            result_json TEXT NOT NULL
        );
        CREATE TABLE tailored_resume_drafts (
            id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL
        );
        CREATE TABLE tailored_resume_exports (
            id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            directory_path TEXT NOT NULL,
            docx_path TEXT NOT NULL,
            pdf_path TEXT NOT NULL,
            docx_sha256 TEXT NOT NULL,
            pdf_sha256 TEXT NOT NULL
        );
        INSERT INTO job_resume_matches
        VALUES ('match-1', '{"score":80}');
        INSERT INTO tailored_resume_drafts
        VALUES ('draft-1', 'match-1');
        """
    )
    workspace = tmp_path / "workspace"
    export_dir = workspace / "artifacts" / "tailored-resumes" / "draft-1"
    export_dir.mkdir(parents=True)
    docx = export_dir / "resume.docx"
    pdf = export_dir / "resume.pdf"
    docx.write_bytes(b"docx-content")
    pdf.write_bytes(b"pdf-content")
    connection.execute(
        """
        INSERT INTO tailored_resume_exports
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "export-1",
            "draft-1",
            "artifacts/tailored-resumes/draft-1",
            "artifacts/tailored-resumes/draft-1/resume.docx",
            "artifacts/tailored-resumes/draft-1/resume.pdf",
            _sha256(docx),
            _sha256(pdf),
        ),
    )
    connection.commit()
    connection.close()
    packet_dir = workspace / "artifacts" / "application-packets"
    packet_dir.mkdir(parents=True)
    (packet_dir / "packet.md").write_text(
        "# archived packet\n",
        encoding="utf-8",
    )
    return database_path, workspace


def test_archive_sqlite_exports_rows_files_and_verifies_source_is_unchanged(
    tmp_path: Path,
) -> None:
    database_path, workspace = _legacy_source(tmp_path)
    before = database_path.read_bytes()

    manifest = archive_sqlite(
        database_path,
        workspace,
        tmp_path / "archive",
    )

    assert database_path.read_bytes() == before
    assert manifest["tables"]["job_resume_matches"]["count"] == 1
    assert manifest["tables"]["application_packets"] == {
        "present": False,
        "count": 0,
    }
    assert {
        item["kind"] for item in manifest["blobs"]
    } == {
        "application_packet",
        "tailored_resume_docx",
        "tailored_resume_pdf",
    }
    for item in manifest["blobs"]:
        archived = tmp_path / "archive" / item["archive_path"]
        assert archived.is_file()
        assert _sha256(archived) == item["sha256"]
    verified = verify_archive(
        tmp_path / "archive",
        expected_manifest_sha256=manifest["manifest_sha256"],
    )
    assert verified["manifest_sha256"] == manifest["manifest_sha256"]


def test_archive_sqlite_is_deterministic_except_for_output_location(
    tmp_path: Path,
) -> None:
    database_path, workspace = _legacy_source(tmp_path)

    first = archive_sqlite(database_path, workspace, tmp_path / "first")
    second = archive_sqlite(database_path, workspace, tmp_path / "second")

    assert first == second
    assert (
        tmp_path / "first" / "database" / "job_resume_matches.jsonl"
    ).read_bytes() == (
        tmp_path / "second" / "database" / "job_resume_matches.jsonl"
    ).read_bytes()


def test_archive_sqlite_rejects_nonempty_destination(tmp_path: Path) -> None:
    database_path, workspace = _legacy_source(tmp_path)
    destination = tmp_path / "archive"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        archive_sqlite(database_path, workspace, destination)

    assert (destination / "keep.txt").read_text(encoding="utf-8") == "keep"


@pytest.mark.parametrize("failure", ["missing", "symlink"])
def test_archive_sqlite_rejects_unreadable_export_without_writing_output(
    tmp_path: Path,
    failure: str,
) -> None:
    database_path, workspace = _legacy_source(tmp_path)
    pdf = (
        workspace
        / "artifacts"
        / "tailored-resumes"
        / "draft-1"
        / "resume.pdf"
    )
    if failure == "missing":
        pdf.unlink()
    else:
        content = pdf.read_bytes()
        pdf.unlink()
        outside = tmp_path / "outside.pdf"
        outside.write_bytes(content)
        pdf.symlink_to(outside)

    destination = tmp_path / "archive"
    with pytest.raises(ValueError):
        archive_sqlite(database_path, workspace, destination)

    assert not destination.exists()


def test_verify_archive_rejects_tampered_content(tmp_path: Path) -> None:
    database_path, workspace = _legacy_source(tmp_path)
    destination = tmp_path / "archive"
    manifest = archive_sqlite(database_path, workspace, destination)
    table_path = destination / manifest["tables"][
        "job_resume_matches"
    ]["path"]
    table_path.write_text(
        json.dumps({"id": "tampered"}) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="hash"):
        verify_archive(
            destination,
            expected_manifest_sha256=manifest["manifest_sha256"],
        )


class _Cursor:
    def __init__(self, columns: list[str], rows: list[tuple]) -> None:
        self.description = [
            SimpleNamespace(name=column) for column in columns
        ]
        self._rows = rows

    def fetchall(self) -> list[tuple]:
        return self._rows

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None


class _PostgresArchiveConnection:
    def __init__(self, *, privileged: bool = True) -> None:
        self.privileged = privileged
        self.transaction_started = False
        self.read_only_snapshot = False

    def transaction(self):
        self.transaction_started = True
        return nullcontext()

    def execute(self, query: str, params=None) -> _Cursor:
        normalized = " ".join(query.split())
        if normalized.startswith("SET TRANSACTION"):
            self.read_only_snapshot = (
                normalized
                == "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
            )
            return _Cursor([], [])
        if "FROM pg_roles" in normalized:
            return _Cursor(
                ["rolsuper", "rolbypassrls"],
                [(self.privileged, False)],
            )
        if "FROM career.job_resume_matches" in normalized:
            return _Cursor(
                ["id", "user_id", "result"],
                [("match-1", "user-1", {"score": 80})],
            )
        if "FROM career.application_packets" in normalized:
            return _Cursor(
                ["id", "user_id", "blob_id"],
                [("packet-1", "user-1", UUID(int=1))],
            )
        if "FROM career.tailored_resume_drafts" in normalized:
            return _Cursor(
                ["id", "user_id", "data"],
                [("draft-1", "user-1", {"status": "confirmed"})],
            )
        if "FROM career.tailored_resume_exports" in normalized:
            return _Cursor(
                [
                    "id",
                    "user_id",
                    "docx_blob_id",
                    "pdf_blob_id",
                ],
                [
                    (
                        "export-1",
                        "user-1",
                        UUID(int=2),
                        UUID(int=3),
                    )
                ],
            )
        if "FROM blob.objects" in normalized:
            rows = [
                (
                    UUID(int=1),
                    "user-1",
                    "application_packet",
                    "text/markdown",
                    "packet.md",
                    len(b"packet"),
                    hashlib.sha256(b"packet").hexdigest(),
                    b"packet",
                ),
                (
                    UUID(int=2),
                    "user-1",
                    "tailored_resume_docx",
                    "application/vnd.openxmlformats-officedocument."
                    "wordprocessingml.document",
                    "resume.docx",
                    len(b"docx"),
                    hashlib.sha256(b"docx").hexdigest(),
                    b"docx",
                ),
                (
                    UUID(int=3),
                    "user-1",
                    "tailored_resume_pdf",
                    "application/pdf",
                    "resume.pdf",
                    len(b"pdf"),
                    hashlib.sha256(b"pdf").hexdigest(),
                    b"pdf",
                ),
            ]
            return _Cursor(
                [
                    "id",
                    "user_id",
                    "kind",
                    "media_type",
                    "original_name",
                    "size_bytes",
                    "sha256",
                    "content",
                ],
                rows,
            )
        raise AssertionError(normalized)


def test_archive_postgres_exports_all_tenants_and_referenced_blobs(
    tmp_path: Path,
) -> None:
    connection = _PostgresArchiveConnection()
    manifest = archive_postgres(
        connection,
        tmp_path / "archive",
    )

    assert connection.transaction_started is True
    assert connection.read_only_snapshot is True
    assert manifest["source_kind"] == "postgres"
    assert {
        name: details["count"]
        for name, details in manifest["tables"].items()
    } == {
        "job_resume_matches": 1,
        "application_packets": 1,
        "tailored_resume_drafts": 1,
        "tailored_resume_exports": 1,
    }
    assert {item["kind"] for item in manifest["blobs"]} == {
        "application_packet",
        "tailored_resume_docx",
        "tailored_resume_pdf",
    }


def test_archive_postgres_requires_rls_bypass_before_writing(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "archive"

    with pytest.raises(ValueError, match="BYPASSRLS"):
        archive_postgres(
            _PostgresArchiveConnection(privileged=False),
            destination,
        )

    assert not destination.exists()
