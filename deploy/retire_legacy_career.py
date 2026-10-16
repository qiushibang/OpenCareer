"""Explicit destructive retirement for archived Career generation data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from deploy.archive_legacy_career import (
    LEGACY_TABLES,
    _json_bytes,
    _postgres_rows,
    _safe_workspace_file,
    _sqlite_rows,
    _table_exists,
    verify_archive,
)


RETIREMENT_ID = "legacy-career-generation-v1"


def _rows_sha256(rows: list[dict[str, Any]]) -> str:
    return hashlib.sha256(
        b"".join(_json_bytes(row) for row in rows)
    ).hexdigest()


def _completion(
    connection: sqlite3.Connection,
) -> tuple[str, bool] | None:
    if not _table_exists(connection, "career_data_retirements"):
        return None
    row = connection.execute(
        """
        SELECT manifest_sha256, files_completed
        FROM career_data_retirements
        WHERE id = ?
        """,
        (RETIREMENT_ID,),
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), bool(row[1])


def _verify_sqlite_source(
    connection: sqlite3.Connection,
    manifest: dict[str, Any],
) -> None:
    tables = manifest.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("archive table manifest is invalid")
    for table in LEGACY_TABLES:
        expected = tables.get(table)
        if not isinstance(expected, dict):
            raise ValueError("archive table manifest is incomplete")
        present = _table_exists(connection, table)
        if present != bool(expected.get("present")):
            raise ValueError("source data no longer matches archive")
        if not present:
            continue
        rows = _sqlite_rows(connection, table)
        if (
            len(rows) != int(expected.get("count", -1))
            or _rows_sha256(rows) != expected.get("rows_sha256")
        ):
            raise ValueError("source data no longer matches archive")


def _manifest_source_paths(
    manifest: dict[str, Any],
) -> dict[str, str]:
    result: dict[str, str] = {}
    blobs = manifest.get("blobs")
    if not isinstance(blobs, list):
        raise ValueError("archive Blob manifest is invalid")
    for item in blobs:
        if not isinstance(item, dict):
            raise ValueError("archive Blob manifest is invalid")
        source_path = str(item.get("source_path") or "")
        digest = str(item.get("sha256") or "")
        if not source_path or len(digest) != 64:
            raise ValueError("archive Blob manifest is invalid")
        current = result.get(source_path)
        if current is not None and current != digest:
            raise ValueError("archive contains conflicting file references")
        result[source_path] = digest
    return result


def _verify_sqlite_files(
    workspace: Path,
    manifest: dict[str, Any],
) -> dict[str, str]:
    expected = _manifest_source_paths(manifest)
    packet_dir = workspace / "artifacts" / "application-packets"
    current_packets: set[str] = set()
    if packet_dir.is_symlink():
        raise ValueError("application packet directory must not be a symlink")
    if packet_dir.exists():
        current_packets = {
            path.relative_to(workspace).as_posix()
            for path in packet_dir.glob("*.md")
        }
    archived_packets = {
        path
        for path in expected
        if path.startswith("artifacts/application-packets/")
    }
    if current_packets != archived_packets:
        raise ValueError("source data no longer matches archive")
    for relative, digest in expected.items():
        source = _safe_workspace_file(workspace, relative)
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError("source data no longer matches archive")
    return expected


def _drop_legacy_sqlite(
    connection: sqlite3.Connection,
    manifest_sha256: str,
) -> None:
    columns = {
        str(row[1])
        for row in connection.execute(
            "PRAGMA table_info(interview_sessions)"
        )
    }
    if "snapshot_id" in columns:
        raise ValueError(
            "SQLite schema must be migrated to v13 before retirement"
        )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS career_data_retirements (
            id TEXT PRIMARY KEY,
            manifest_sha256 TEXT NOT NULL,
            database_committed INTEGER NOT NULL
                CHECK(database_committed IN (0, 1)),
            files_completed INTEGER NOT NULL
                CHECK(files_completed IN (0, 1)),
            completed_at TEXT
        )
        """
    )
    if "legacy_snapshot_id" in columns:
        connection.execute(
            "ALTER TABLE interview_sessions "
            "DROP COLUMN legacy_snapshot_id"
        )
    for table in (
        "tailored_resume_exports",
        "tailored_resume_drafts",
        "application_packets",
        "job_resume_matches",
    ):
        connection.execute(f'DROP TABLE IF EXISTS "{table}"')
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("SQLite foreign key check failed")
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("SQLite integrity check failed")
    connection.execute(
        """
        INSERT INTO career_data_retirements(
            id, manifest_sha256, database_committed, files_completed
        ) VALUES (?, ?, 1, 0)
        """,
        (RETIREMENT_ID, manifest_sha256),
    )


def _delete_archived_files(
    workspace: Path,
    paths: dict[str, str],
    *,
    allow_missing: bool,
) -> None:
    for relative, digest in sorted(paths.items()):
        try:
            source = _safe_workspace_file(workspace, relative)
        except ValueError:
            if allow_missing and not (workspace / relative).exists():
                continue
            raise
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
            raise ValueError("source data no longer matches archive")
        source.unlink()
    for relative in (
        Path("artifacts/tailored-resumes"),
        Path("artifacts/application-packets"),
    ):
        root = workspace / relative
        if root.is_symlink() or not root.is_dir():
            continue
        for directory in sorted(
            (path for path in root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            if not any(directory.iterdir()):
                directory.rmdir()
        if not any(root.iterdir()):
            root.rmdir()


def retire_sqlite(
    source_db: Path,
    workspace_root: Path,
    archive_dir: Path,
    *,
    expected_manifest_sha256: str,
) -> dict[str, Any]:
    manifest = verify_archive(
        archive_dir,
        expected_manifest_sha256=expected_manifest_sha256,
    )
    if manifest.get("source_kind") != "sqlite":
        raise ValueError("archive source kind is not sqlite")
    database_path = source_db.expanduser().resolve(strict=True)
    workspace = workspace_root.expanduser().resolve(strict=True)
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        completion = _completion(connection)
        if completion is not None:
            recorded_hash, files_completed = completion
            if recorded_hash != expected_manifest_sha256:
                raise ValueError(
                    "database was retired with a different archive"
                )
            paths = _manifest_source_paths(manifest)
            if not files_completed:
                _delete_archived_files(
                    workspace,
                    paths,
                    allow_missing=True,
                )
                connection.execute(
                    """
                    UPDATE career_data_retirements
                    SET files_completed = 1,
                        completed_at = strftime(
                            '%Y-%m-%dT%H:%M:%fZ', 'now'
                        )
                    WHERE id = ?
                    """,
                    (RETIREMENT_ID,),
                )
                connection.commit()
            return {
                "status": "already_completed",
                "manifest_sha256": expected_manifest_sha256,
            }

        _verify_sqlite_source(connection, manifest)
        paths = _verify_sqlite_files(workspace, manifest)
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN IMMEDIATE")
        try:
            _drop_legacy_sqlite(connection, expected_manifest_sha256)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.execute("PRAGMA foreign_keys = ON")

        _delete_archived_files(workspace, paths, allow_missing=False)
        connection.execute(
            """
            UPDATE career_data_retirements
            SET files_completed = 1,
                completed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ?
            """,
            (RETIREMENT_ID,),
        )
        connection.commit()
        return {
            "status": "completed",
            "manifest_sha256": expected_manifest_sha256,
            "deleted_files": len(paths),
        }
    finally:
        connection.close()


def _verify_postgres_source(
    connection,
    manifest: dict[str, Any],
) -> None:
    tables = manifest.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("archive table manifest is invalid")
    for table in LEGACY_TABLES:
        expected = tables.get(table)
        if not isinstance(expected, dict) or not expected.get("present"):
            raise ValueError("PostgreSQL archive is incomplete")
        rows = _postgres_rows(connection, table)
        if (
            len(rows) != int(expected.get("count", -1))
            or _rows_sha256(rows) != expected.get("rows_sha256")
        ):
            raise ValueError("source data no longer matches archive")

    expected_blobs = {
        str(item["id"]): item
        for item in manifest.get("blobs", [])
        if isinstance(item, dict) and item.get("id")
    }
    if not expected_blobs:
        return
    cursor = connection.execute(
        """
        SELECT id, user_id, kind, media_type, original_name,
               size_bytes, sha256, content
        FROM blob.objects
        WHERE id = ANY(%s)
        ORDER BY user_id, id
        """,
        (list(expected_blobs),),
    )
    columns = [str(column.name) for column in cursor.description]
    rows = [
        dict(zip(columns, row, strict=True))
        for row in cursor.fetchall()
    ]
    if {str(row["id"]) for row in rows} != set(expected_blobs):
        raise ValueError("source data no longer matches archive")
    for row in rows:
        expected = expected_blobs[str(row["id"])]
        content = bytes(row["content"])
        actual_hash = hashlib.sha256(content).hexdigest()
        if (
            str(row["user_id"]) != str(expected["user_id"])
            or str(row["kind"]) != str(expected["kind"])
            or int(row["size_bytes"]) != int(expected["size_bytes"])
            or str(row["sha256"]) != str(expected["sha256"])
            or actual_hash != str(expected["sha256"])
        ):
            raise ValueError("source data no longer matches archive")


def retire_postgres(
    connection,
    archive_dir: Path,
    *,
    expected_manifest_sha256: str,
    recovery_point_id: str,
) -> dict[str, Any]:
    if not recovery_point_id.strip():
        raise ValueError("recovery point id is required")
    with connection.transaction():
        connection.execute(
            "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"
        )
        privilege = connection.execute(
            """
            SELECT rolsuper, rolbypassrls
            FROM pg_roles
            WHERE rolname = current_user
            """
        ).fetchone()
        if privilege is None or not (
            bool(privilege[0]) or bool(privilege[1])
        ):
            raise ValueError(
                "PostgreSQL retirement requires superuser or BYPASSRLS"
            )
        manifest = verify_archive(
            archive_dir,
            expected_manifest_sha256=expected_manifest_sha256,
        )
        if manifest.get("source_kind") != "postgres":
            raise ValueError("archive source kind is not postgres")
        marker = connection.execute(
            """
            SELECT source_sha256, report
            FROM opencareer_meta.data_migrations
            WHERE source_kind = 'legacy_career_retirement'
              AND user_id = '__all__'
            ORDER BY applied_at DESC
            LIMIT 1
            """
        ).fetchone()
        if marker is not None:
            if str(marker[0]) != expected_manifest_sha256:
                raise ValueError(
                    "database was retired with a different archive"
                )
            return {
                "status": "already_completed",
                "manifest_sha256": expected_manifest_sha256,
            }

        _verify_postgres_source(connection, manifest)
        sql_path = (
            Path(__file__).resolve().parent
            / "sql"
            / "retire_legacy_career.sql"
        )
        connection.execute(sql_path.read_text(encoding="utf-8"))
        report = {
            "status": "completed",
            "manifest_sha256": expected_manifest_sha256,
            "recovery_point_id": recovery_point_id,
        }
        connection.execute(
            """
            INSERT INTO opencareer_meta.data_migrations(
                source_kind, user_id, source_sha256, report
            ) VALUES (
                'legacy_career_retirement',
                '__all__',
                %s,
                %s::jsonb
            )
            """,
            (
                expected_manifest_sha256,
                json.dumps(report, ensure_ascii=False, sort_keys=True),
            ),
        )
        return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sqlite-db", type=Path)
    source.add_argument("--postgres", action="store_true")
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--recovery-point-id")
    args = parser.parse_args(argv)
    if args.sqlite_db is not None:
        if args.workspace_root is None:
            parser.error("--workspace-root is required with --sqlite-db")
        result = retire_sqlite(
            args.sqlite_db,
            args.workspace_root,
            args.archive,
            expected_manifest_sha256=args.manifest_sha256,
        )
    else:
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            parser.error("DATABASE_URL is required with --postgres")
        if not args.recovery_point_id:
            parser.error("--recovery-point-id is required with --postgres")
        import psycopg

        with psycopg.connect(database_url) as connection:
            result = retire_postgres(
                connection,
                args.archive,
                expected_manifest_sha256=args.manifest_sha256,
                recovery_point_id=args.recovery_point_id,
            )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
