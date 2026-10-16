"""Read-only archive tooling for retired Career generation data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import UUID


ARCHIVE_VERSION = 1
LEGACY_TABLES = (
    "job_resume_matches",
    "application_packets",
    "tailored_resume_drafts",
    "tailored_resume_exports",
)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            _json_value(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _json_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bytes):
        raise TypeError("binary content must be archived separately")
    return value


def _prepare_destination(destination: Path) -> tuple[Path, bool]:
    destination = destination.expanduser().absolute()
    if destination.is_symlink():
        raise ValueError("archive destination must not be a symlink")
    existed = destination.exists()
    if existed:
        if not destination.is_dir():
            raise ValueError("archive destination must be a directory")
        if any(destination.iterdir()):
            raise ValueError("archive destination must be empty")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{destination.name}.tmp-",
            dir=destination.parent,
        )
    )
    os.chmod(temporary, 0o700)
    return temporary, existed


def _publish_destination(
    temporary: Path,
    destination: Path,
    destination_existed: bool,
) -> None:
    if destination_existed:
        destination.rmdir()
    os.replace(temporary, destination)


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def _sqlite_rows(
    connection: sqlite3.Connection,
    table: str,
) -> list[dict[str, Any]]:
    columns = connection.execute(
        f'PRAGMA table_info("{table}")'
    ).fetchall()
    primary_keys = [
        str(row["name"])
        for row in sorted(columns, key=lambda row: int(row["pk"]))
        if int(row["pk"]) > 0
    ]
    order = primary_keys or [str(row["name"]) for row in columns]
    order_sql = ", ".join(f'"{name}"' for name in order)
    query = f'SELECT * FROM "{table}"'
    if order_sql:
        query += f" ORDER BY {order_sql}"
    return [dict(row) for row in connection.execute(query)]


def _write_table(
    root: Path,
    table: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    relative = Path("database") / f"{table}.jsonl"
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    content = b"".join(_json_bytes(row) for row in rows)
    target.write_bytes(content)
    os.chmod(target, 0o600)
    digest = _sha256_bytes(content)
    return {
        "present": True,
        "count": len(rows),
        "path": relative.as_posix(),
        "sha256": digest,
        "rows_sha256": digest,
    }


def _safe_workspace_file(workspace: Path, relative: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("legacy file path escapes workspace")
    candidate = workspace / relative_path
    current = workspace
    for part in relative_path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("legacy file path contains a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(workspace)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise ValueError("legacy file is unavailable") from exc
    if not resolved.is_file():
        raise ValueError("legacy file is unavailable")
    return resolved


def _archive_file(
    root: Path,
    workspace: Path,
    *,
    source_path: str,
    kind: str,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    source = _safe_workspace_file(workspace, source_path)
    content = source.read_bytes()
    digest = _sha256_bytes(content)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError("legacy file hash does not match its database row")
    relative = Path("blobs") / digest
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != content:
        raise ValueError("archive content hash collision")
    if not target.exists():
        target.write_bytes(content)
        os.chmod(target, 0o600)
    return {
        "source_path": source_path,
        "kind": kind,
        "size_bytes": len(content),
        "sha256": digest,
        "archive_path": relative.as_posix(),
    }


def _legacy_files(
    root: Path,
    workspace: Path,
    exports: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blobs: list[dict[str, Any]] = []
    packet_dir = workspace / "artifacts" / "application-packets"
    if packet_dir.is_symlink():
        raise ValueError("application packet directory must not be a symlink")
    if packet_dir.exists():
        if not packet_dir.is_dir():
            raise ValueError("application packet path must be a directory")
        for path in sorted(packet_dir.glob("*.md")):
            relative = path.relative_to(workspace).as_posix()
            blobs.append(
                _archive_file(
                    root,
                    workspace,
                    source_path=relative,
                    kind="application_packet",
                )
            )
    for row in exports:
        for file_kind in ("docx", "pdf"):
            path_key = f"{file_kind}_path"
            hash_key = f"{file_kind}_sha256"
            blobs.append(
                _archive_file(
                    root,
                    workspace,
                    source_path=str(row[path_key]),
                    kind=f"tailored_resume_{file_kind}",
                    expected_sha256=str(row[hash_key]),
                )
            )
    return sorted(
        blobs,
        key=lambda item: (
            item["source_path"],
            item["kind"],
            item["sha256"],
        ),
    )


def _write_manifest(root: Path, manifest: dict[str, Any]) -> str:
    manifest_path = root / "manifest.json"
    manifest_path.write_bytes(_json_bytes(manifest))
    os.chmod(manifest_path, 0o600)
    return _sha256_file(manifest_path)


def _write_checksums(root: Path, manifest: dict[str, Any]) -> None:
    paths = [
        details["path"]
        for details in manifest["tables"].values()
        if details.get("present")
    ]
    paths.extend(item["archive_path"] for item in manifest["blobs"])
    unique_paths = sorted(set(paths))
    content = "".join(
        f"{_sha256_file(root / relative)}  {relative}\n"
        for relative in unique_paths
    )
    target = root / "SHA256SUMS"
    target.write_text(content, encoding="utf-8")
    os.chmod(target, 0o600)


def archive_sqlite(
    source_db: Path,
    workspace_root: Path,
    output_dir: Path,
) -> dict[str, Any]:
    source_db = source_db.expanduser().resolve(strict=True)
    workspace = workspace_root.expanduser().resolve(strict=True)
    destination = output_dir.expanduser().absolute()
    temporary, existed = _prepare_destination(destination)
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(
            f"{source_db.as_uri()}?mode=ro",
            uri=True,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("BEGIN")
        tables: dict[str, dict[str, Any]] = {}
        rows_by_table: dict[str, list[dict[str, Any]]] = {}
        for table in LEGACY_TABLES:
            if not _table_exists(connection, table):
                tables[table] = {"present": False, "count": 0}
                rows_by_table[table] = []
                continue
            rows = _sqlite_rows(connection, table)
            rows_by_table[table] = rows
            tables[table] = _write_table(temporary, table, rows)
        blobs = _legacy_files(
            temporary,
            workspace,
            rows_by_table["tailored_resume_exports"],
        )
        manifest = {
            "archive_version": ARCHIVE_VERSION,
            "source_kind": "sqlite",
            "tables": tables,
            "blobs": blobs,
        }
        _write_checksums(temporary, manifest)
        manifest_sha256 = _write_manifest(temporary, manifest)
        connection.rollback()
        connection.close()
        connection = None
        _publish_destination(temporary, destination, existed)
        return {**manifest, "manifest_sha256": manifest_sha256}
    except Exception:
        if connection is not None:
            connection.rollback()
            connection.close()
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _postgres_rows(connection, table: str) -> list[dict[str, Any]]:
    cursor = connection.execute(
        f"SELECT * FROM career.{table} ORDER BY user_id, id"
    )
    columns = [str(column.name) for column in cursor.description]
    return [
        {
            column: _json_value(value)
            for column, value in zip(columns, row, strict=True)
        }
        for row in cursor.fetchall()
    ]


def _store_postgres_blob(
    root: Path,
    row: dict[str, Any],
) -> dict[str, Any]:
    content = bytes(row.pop("content"))
    digest = _sha256_bytes(content)
    if int(row["size_bytes"]) != len(content):
        raise ValueError("legacy Blob size mismatch")
    if str(row["sha256"]) != digest:
        raise ValueError("legacy Blob hash mismatch")
    relative = Path("blobs") / digest
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_bytes() != content:
        raise ValueError("archive content hash collision")
    if not target.exists():
        target.write_bytes(content)
        os.chmod(target, 0o600)
    return {
        **{key: _json_value(value) for key, value in row.items()},
        "archive_path": relative.as_posix(),
    }


def archive_postgres(
    connection,
    output_dir: Path,
) -> dict[str, Any]:
    with connection.transaction():
        connection.execute(
            "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
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
                "PostgreSQL archive requires superuser or BYPASSRLS"
            )
        destination = output_dir.expanduser().absolute()
        temporary, existed = _prepare_destination(destination)
        try:
            tables: dict[str, dict[str, Any]] = {}
            rows_by_table: dict[str, list[dict[str, Any]]] = {}
            for table in LEGACY_TABLES:
                rows = _postgres_rows(connection, table)
                rows_by_table[table] = rows
                tables[table] = _write_table(temporary, table, rows)

            references: dict[str, tuple[str, str]] = {}
            for row in rows_by_table["application_packets"]:
                blob_id = row.get("blob_id")
                if blob_id:
                    references[str(blob_id)] = (
                        str(row["user_id"]),
                        "application_packet",
                    )
            for row in rows_by_table["tailored_resume_exports"]:
                references[str(row["docx_blob_id"])] = (
                    str(row["user_id"]),
                    "tailored_resume_docx",
                )
                references[str(row["pdf_blob_id"])] = (
                    str(row["user_id"]),
                    "tailored_resume_pdf",
                )

            blobs: list[dict[str, Any]] = []
            if references:
                cursor = connection.execute(
                    """
                    SELECT id, user_id, kind, media_type, original_name,
                           size_bytes, sha256, content
                    FROM blob.objects
                    WHERE id = ANY(%s)
                    ORDER BY user_id, id
                    """,
                    (list(references),),
                )
                columns = [
                    str(column.name) for column in cursor.description
                ]
                rows = [
                    dict(zip(columns, row, strict=True))
                    for row in cursor.fetchall()
                ]
                found = {str(row["id"]) for row in rows}
                if found != set(references):
                    raise ValueError("referenced legacy Blob is missing")
                for row in rows:
                    expected_user, expected_kind = references[
                        str(row["id"])
                    ]
                    if (
                        str(row["user_id"]) != expected_user
                        or str(row["kind"]) != expected_kind
                    ):
                        raise ValueError(
                            "legacy Blob ownership or kind mismatch"
                        )
                    blobs.append(_store_postgres_blob(temporary, row))

            manifest = {
                "archive_version": ARCHIVE_VERSION,
                "source_kind": "postgres",
                "tables": tables,
                "blobs": sorted(
                    blobs,
                    key=lambda item: (
                        str(item["user_id"]),
                        str(item["id"]),
                    ),
                ),
            }
            _write_checksums(temporary, manifest)
            manifest_sha256 = _write_manifest(temporary, manifest)
            _publish_destination(temporary, destination, existed)
            return {
                **manifest,
                "manifest_sha256": manifest_sha256,
            }
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise


def _verified_path(root: Path, relative: str) -> Path:
    candidate = root / relative
    if candidate.is_symlink():
        raise ValueError("archive path contains a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        raise ValueError("archive file is unavailable") from exc
    if not resolved.is_file():
        raise ValueError("archive file is unavailable")
    return resolved


def verify_archive(
    archive_dir: Path,
    *,
    expected_manifest_sha256: str,
) -> dict[str, Any]:
    root = archive_dir.expanduser().resolve(strict=True)
    if root.is_symlink() or not root.is_dir():
        raise ValueError("archive directory is unsafe")
    manifest_path = _verified_path(root, "manifest.json")
    actual_manifest_sha256 = _sha256_file(manifest_path)
    if actual_manifest_sha256 != expected_manifest_sha256:
        raise ValueError("manifest hash mismatch")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("manifest is invalid") from exc
    if manifest.get("archive_version") != ARCHIVE_VERSION:
        raise ValueError("unsupported archive version")
    expected_files: dict[str, str] = {}
    for details in manifest.get("tables", {}).values():
        if details.get("present"):
            expected_files[str(details["path"])] = str(details["sha256"])
    for item in manifest.get("blobs", []):
        expected_files[str(item["archive_path"])] = str(item["sha256"])
    for relative, digest in expected_files.items():
        if _sha256_file(_verified_path(root, relative)) != digest:
            raise ValueError("archive content hash mismatch")
    checksum_path = _verified_path(root, "SHA256SUMS")
    expected_lines = "".join(
        f"{digest}  {relative}\n"
        for relative, digest in sorted(expected_files.items())
    )
    if checksum_path.read_text(encoding="utf-8") != expected_lines:
        raise ValueError("archive checksum index mismatch")
    return {**manifest, "manifest_sha256": actual_manifest_sha256}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sqlite-db", type=Path)
    source.add_argument("--postgres", action="store_true")
    parser.add_argument("--workspace-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.sqlite_db is not None:
        if args.workspace_root is None:
            parser.error("--workspace-root is required with --sqlite-db")
        manifest = archive_sqlite(
            args.sqlite_db,
            args.workspace_root,
            args.output,
        )
    else:
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if not database_url:
            parser.error("DATABASE_URL is required with --postgres")
        import psycopg

        with psycopg.connect(database_url) as connection:
            with connection.transaction():
                connection.execute(
                    "SET TRANSACTION ISOLATION LEVEL "
                    "REPEATABLE READ READ ONLY"
                )
                manifest = archive_postgres(connection, args.output)
    print(
        json.dumps(
            {
                "archive": str(args.output),
                "manifest_sha256": manifest["manifest_sha256"],
                "table_counts": {
                    name: details["count"]
                    for name, details in manifest["tables"].items()
                },
                "blob_count": len(manifest["blobs"]),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
