"""Repeatable migration of one legacy Career SQLite database to PostgreSQL."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from coworker.server.identity import Principal
from coworker.storage.postgres.database import CloudDatabase

_USER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _table_exists(source: sqlite3.Connection, table: str) -> bool:
    return (
        source.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def _rows(source: sqlite3.Connection, table: str) -> list[dict]:
    if not _table_exists(source, table):
        return []
    return [dict(row) for row in source.execute(f"SELECT * FROM {table}")]


def _json(value: object, default):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(str(value))
    except (TypeError, ValueError):
        return default


def _postgres_timestamp(value: object) -> object:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, timezone.utc)
    return value


def inspect_career_source(path: Path) -> dict:
    source = sqlite3.connect(path)
    source.row_factory = sqlite3.Row
    try:
        tables = (
            "companies",
            "job_sources",
            "jobs",
            "job_versions",
            "job_events",
            "resume_imports",
            "candidate_profile",
            "candidate_facts",
            "profile_versions",
            "resume_previews",
            "job_tracking",
            "job_application_events",
            "interview_sessions",
            "interview_turns",
        )
        return {
            "source_sha256": file_sha256(path),
            "counts": {
                table: len(_rows(source, table))
                for table in tables
            },
        }
    finally:
        source.close()


def context_state_sha256(state_root: Path) -> str:
    digest = hashlib.sha256()
    names = (
        "coworker.db",
        "automation.db",
        "inbox.json",
        "inbox_routing.json",
        "mentions.json",
        "subscriptions.json",
        "wakes.json",
    )
    paths = [
        path for name in names if (path := state_root / name).is_file()
    ]
    conversations = state_root / "conversations"
    if conversations.is_dir():
        paths.extend(conversations.glob("*.jsonl"))
    for path in sorted(paths):
        relative = path.relative_to(state_root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha256(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def migrate_context_state(
    database: CloudDatabase,
    *,
    state_root: Path,
    user_id: str,
) -> dict:
    if _USER_ID.fullmatch(user_id) is None:
        raise ValueError("invalid user id")
    state_root = state_root.expanduser().resolve()
    source_sha = context_state_sha256(state_root)
    principal = Principal(user_id, "migration")
    with database.transaction(principal) as target:
        target.execute(
            """
            INSERT INTO identity.users(id)
            VALUES (%s)
            ON CONFLICT (id) DO NOTHING
            """,
            (user_id,),
        )
        applied = target.execute(
            """
            SELECT report
            FROM opencareer_meta.data_migrations
            WHERE source_kind = 'agent_context_state'
              AND user_id = %s
              AND source_sha256 = %s
            """,
            (user_id, source_sha),
        ).fetchone()
        if applied is not None:
            return {**dict(applied[0]), "reused": True}

        counts: dict[str, int] = {}
        _migrate_context_database(
            state_root / "coworker.db",
            state_root,
            target,
            user_id,
            counts,
        )
        _migrate_inbox(
            state_root / "inbox.json",
            target,
            user_id,
            counts,
        )
        _migrate_automations(
            state_root / "automation.db",
            target,
            user_id,
            counts,
        )
        _migrate_legacy_context_snapshots(
            state_root,
            target,
            user_id,
            counts,
        )
        report = {
            "source_kind": "agent_context_state",
            "source_sha256": source_sha,
            "user_id": user_id,
            "counts": counts,
            "reused": False,
        }
        target.execute(
            """
            INSERT INTO opencareer_meta.data_migrations(
                source_kind, user_id, source_sha256, report
            ) VALUES ('agent_context_state', %s, %s, %s::jsonb)
            """,
            (
                user_id,
                source_sha,
                json.dumps(report, ensure_ascii=False, sort_keys=True),
            ),
        )
        return report


def _migrate_context_database(
    path: Path,
    state_root: Path,
    target,
    user_id: str,
    counts: dict[str, int],
) -> None:
    if not path.is_file():
        counts.update(
            {"conversations": 0, "messages": 0, "compactions": 0, "memories": 0}
        )
        return
    source = sqlite3.connect(path)
    source.row_factory = sqlite3.Row
    try:
        sessions = _rows(source, "sessions")
        message_count = 0
        compaction_count = 0
        for row in sessions:
            session_id = str(row["session_id"])
            messages = _conversation_messages(state_root, row)
            metadata = {
                "workspace": row.get("workspace") or "",
                "model": row.get("model") or "",
                "mode": row.get("mode") or "interactive",
                "title": row.get("title"),
                "auto_title": row.get("auto_title"),
                "renamed": bool(row.get("renamed")),
                "agent": row.get("agent") or "code",
                "message_count": len(messages),
                "extra_roots": _json(row.get("extra_roots"), []),
                "grants": _json(row.get("grants"), {}),
                "pinned": bool(row.get("pinned")),
                "archived": bool(row.get("archived")),
                "origin": row.get("origin"),
                "origin_label": row.get("origin_label"),
                "updated_at": row.get("updated_at"),
            }
            target.execute(
                """
                INSERT INTO agent.conversations(
                    id, user_id, metadata, updated_at
                ) VALUES (%s, %s, %s::jsonb, COALESCE(%s::timestamptz, now()))
                ON CONFLICT (user_id, id)
                DO UPDATE SET metadata = EXCLUDED.metadata,
                              updated_at = EXCLUDED.updated_at
                """,
                (
                    session_id,
                    user_id,
                    json.dumps(metadata, ensure_ascii=False),
                    _postgres_timestamp(row.get("updated_at")),
                ),
            )
            for sequence, content in enumerate(messages, start=1):
                target.execute(
                    """
                    INSERT INTO agent.messages(
                        id, user_id, conversation_id, sequence, content
                    ) VALUES (%s, %s, %s, %s, %s::jsonb)
                    ON CONFLICT (user_id, conversation_id, sequence)
                    DO NOTHING
                    """,
                    (
                        str(
                            uuid5(
                                NAMESPACE_URL,
                                f"context:{user_id}:{session_id}:{sequence}",
                            )
                        ),
                        user_id,
                        session_id,
                        sequence,
                        json.dumps(content, ensure_ascii=False),
                    ),
                )
            message_count += len(messages)
            compaction = _json(row.get("compaction"), {})
            boundary = int(compaction.get("boundary_index") or 0)
            if compaction and 0 < boundary <= len(messages):
                source_json = json.dumps(
                    messages[:boundary],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
                target.execute(
                    """
                    INSERT INTO agent.compactions(
                        id, user_id, conversation_id, version,
                        boundary_sequence, summary, omitted_message_count,
                        source_hash, state, created_at
                    ) VALUES (
                        %s, %s, %s, 1, %s, %s, %s, %s, %s::jsonb,
                        COALESCE(%s::timestamptz, now())
                    )
                    ON CONFLICT (user_id, conversation_id, version)
                    DO NOTHING
                    """,
                    (
                        str(
                            uuid5(
                                NAMESPACE_URL,
                                f"context:{user_id}:{session_id}:compaction:1",
                            )
                        ),
                        user_id,
                        session_id,
                        boundary,
                        str(compaction.get("summary_text") or ""),
                        boundary,
                        hashlib.sha256(
                            source_json.encode("utf-8")
                        ).hexdigest(),
                        json.dumps(
                            compaction,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        _postgres_timestamp(compaction.get("created_at")),
                    ),
                )
                compaction_count += 1
            workspace = str(row.get("workspace") or "").strip()
            if workspace:
                target.execute(
                    """
                    INSERT INTO agent.workspaces(user_id, path, last_used)
                    VALUES (
                        %s, %s, COALESCE(%s::timestamptz, now())
                    )
                    ON CONFLICT (user_id, path)
                    DO UPDATE SET last_used = EXCLUDED.last_used
                    """,
                    (
                        user_id,
                        workspace,
                        _postgres_timestamp(row.get("updated_at")),
                    ),
                )

        memories = _rows(source, "memories")
        for row in memories:
            conversation_id = row.get("session_id")
            if conversation_id:
                target.execute(
                    """
                    INSERT INTO agent.conversations(id, user_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id, id) DO NOTHING
                    """,
                    (conversation_id, user_id),
                )
            target.execute(
                """
                INSERT INTO agent.memories(
                    user_id, scope, key, content, workspace,
                    conversation_id, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s,
                    COALESCE(%s::timestamptz, now()),
                    COALESCE(%s::timestamptz, now())
                )
                """,
                (
                    user_id,
                    row["scope"],
                    row.get("key"),
                    row["content"],
                    row.get("workspace"),
                    conversation_id,
                    _postgres_timestamp(row.get("created_at")),
                    _postgres_timestamp(row.get("created_at")),
                ),
            )
        counts.update(
            {
                "conversations": len(sessions),
                "messages": message_count,
                "compactions": compaction_count,
                "memories": len(memories),
            }
        )
    finally:
        source.close()


def _conversation_messages(state_root: Path, row: dict) -> list[dict]:
    path = state_root / "conversations" / f"{row['session_id']}.jsonl"
    if path.is_file():
        messages = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                if isinstance(item, dict):
                    messages.append(item)
        return messages
    inline = _json(row.get("messages"), [])
    return [item for item in inline if isinstance(item, dict)]


def _migrate_inbox(
    path: Path,
    target,
    user_id: str,
    counts: dict[str, int],
) -> None:
    payload = _json(path.read_text(encoding="utf-8"), {}) if path.is_file() else {}
    items = payload.get("items") if isinstance(payload, dict) else []
    items = items if isinstance(items, list) else []
    resolution_count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        session_id = str(item.get("session_id") or "")
        if not session_id:
            continue
        target.execute(
            """
            INSERT INTO agent.conversations(id, user_id)
            VALUES (%s, %s)
            ON CONFLICT (user_id, id) DO NOTHING
            """,
            (session_id, user_id),
        )
        target.execute(
            """
            INSERT INTO agent.inbox_items(
                id, user_id, conversation_id, tool_call_id,
                state, data, created_at, resolved_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s::jsonb,
                COALESCE(%s::timestamptz, now()), %s
            )
            ON CONFLICT (user_id, id) DO NOTHING
            """,
            (
                item["id"],
                user_id,
                session_id,
                item.get("tool_call_id"),
                item.get("state") or "pending",
                json.dumps(item, ensure_ascii=False),
                _postgres_timestamp(item.get("created_at")),
                _postgres_timestamp(item.get("resolved_at")),
            ),
        )
        if item.get("state") == "resolved":
            target.execute(
                """
                INSERT INTO agent.inbox_resolutions(
                    id, user_id, inbox_item_id, resolution, created_at
                ) VALUES (
                    %s, %s, %s, %s::jsonb,
                    COALESCE(%s::timestamptz, now())
                )
                ON CONFLICT (user_id, inbox_item_id) DO NOTHING
                """,
                (
                    str(
                        uuid5(
                            NAMESPACE_URL,
                            f"context:{user_id}:inbox:{item['id']}:resolution",
                        )
                    ),
                    user_id,
                    item["id"],
                    json.dumps(
                        {"value": item.get("resolution") or ""},
                        ensure_ascii=False,
                    ),
                    _postgres_timestamp(item.get("resolved_at")),
                ),
            )
            resolution_count += 1
    counts["inbox_items"] = len(items)
    counts["inbox_resolutions"] = resolution_count


def _migrate_automations(
    path: Path,
    target,
    user_id: str,
    counts: dict[str, int],
) -> None:
    if not path.is_file():
        counts.update({"automations": 0, "automation_runs": 0})
        return
    source = sqlite3.connect(path)
    source.row_factory = sqlite3.Row
    try:
        tasks = _rows(source, "scheduled_tasks")
        for row in tasks:
            target.execute(
                """
                INSERT INTO agent.automations(
                    id, user_id, enabled, next_run, data
                ) VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (user_id, id)
                DO UPDATE SET enabled = EXCLUDED.enabled,
                              next_run = EXCLUDED.next_run,
                              data = EXCLUDED.data
                """,
                (
                    row["id"],
                    user_id,
                    bool(row["enabled"]),
                    row.get("next_run"),
                    json.dumps(_json(row["data"], {}), ensure_ascii=False),
                ),
            )
        runs = _rows(source, "task_runs")
        for row in runs:
            target.execute(
                """
                INSERT INTO agent.automation_runs(
                    id, user_id, automation_id, data, created_at
                ) VALUES (
                    %s, %s, %s, %s::jsonb,
                    to_timestamp(COALESCE(%s, 0))
                )
                ON CONFLICT (user_id, id)
                DO UPDATE SET data = EXCLUDED.data
                """,
                (
                    row["run_id"],
                    user_id,
                    row["task_id"],
                    json.dumps(_json(row["data"], {}), ensure_ascii=False),
                    row.get("started_at"),
                ),
            )
        counts["automations"] = len(tasks)
        counts["automation_runs"] = len(runs)
    finally:
        source.close()


def _migrate_legacy_context_snapshots(
    state_root: Path,
    target,
    user_id: str,
    counts: dict[str, int],
) -> None:
    names = (
        "inbox_routing.json",
        "mentions.json",
        "subscriptions.json",
        "wakes.json",
    )
    migrated = 0
    for name in names:
        path = state_root / name
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        target.execute(
            """
            INSERT INTO agent.audit_events(
                id, user_id, event_type, data
            ) VALUES (%s, %s, 'legacy_context_snapshot', %s::jsonb)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                str(
                    uuid5(
                        NAMESPACE_URL,
                        f"context:{user_id}:legacy-snapshot:{name}",
                    )
                ),
                user_id,
                json.dumps(
                    {
                        "name": name,
                        "sha256": hashlib.sha256(
                            path.read_bytes()
                        ).hexdigest(),
                        "content": content,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        migrated += 1
    counts["legacy_context_snapshots"] = migrated


def migrate_career_database(
    database: CloudDatabase,
    *,
    source_path: Path,
    private_root: Path,
    user_id: str,
) -> dict:
    if _USER_ID.fullmatch(user_id) is None:
        raise ValueError("invalid user id")
    source_sha = file_sha256(source_path)
    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    principal = Principal(user_id, "migration")
    try:
        with database.transaction(principal) as target:
            target.execute(
                """
                INSERT INTO identity.users(id)
                VALUES (%s)
                ON CONFLICT (id) DO NOTHING
                """,
                (user_id,),
            )
            applied = target.execute(
                """
                SELECT report
                FROM opencareer_meta.data_migrations
                WHERE source_kind = 'career_sqlite'
                  AND user_id = %s
                  AND source_sha256 = %s
                """,
                (user_id, source_sha),
            ).fetchone()
            if applied is not None:
                return {**dict(applied[0]), "reused": True}

            counts: dict[str, int] = {}
            job_ids = _migrate_catalog(source, target, counts)
            resume_ids = _migrate_resumes(
                source,
                target,
                private_root,
                user_id,
                counts,
            )
            _migrate_tracking(
                source, target, user_id, counts, job_ids
            )
            _migrate_interviews(
                source,
                target,
                user_id,
                counts,
                job_ids,
                resume_ids,
            )
            report = {
                "source_kind": "career_sqlite",
                "source_sha256": source_sha,
                "user_id": user_id,
                "counts": counts,
                "reused": False,
            }
            target.execute(
                """
                INSERT INTO opencareer_meta.data_migrations(
                    source_kind, user_id, source_sha256, report
                ) VALUES ('career_sqlite', %s, %s, %s::jsonb)
                """,
                (
                    user_id,
                    source_sha,
                    json.dumps(report, ensure_ascii=False, sort_keys=True),
                ),
            )
            return report
    finally:
        source.close()


def _migrate_catalog(
    source,
    target,
    counts: dict[str, int],
) -> dict[str, str]:
    authoritative_catalog = bool(
        target.execute(
            """
            SELECT EXISTS(
                SELECT 1
                FROM catalog.jobs
                WHERE crawl_source_id IS NOT NULL
            )
            """
        ).fetchone()[0]
    )
    companies = _rows(source, "companies")
    company_ids: dict[str, str] = {}
    for row in companies:
        existing = target.execute(
            "SELECT id FROM catalog.companies WHERE slug = %s",
            (row["slug"],),
        ).fetchone()
        if existing is None:
            if authoritative_catalog:
                continue
            target.execute(
                """
                INSERT INTO catalog.companies(
                    id, slug, name, created_at
                ) VALUES (%s, %s, %s, %s)
                """,
                (
                    row["id"],
                    row["slug"],
                    row["name"],
                    row["created_at"],
                ),
            )
            company_ids[row["id"]] = row["id"]
        else:
            company_ids[row["id"]] = str(existing[0])
    counts["companies"] = len(companies)

    sources = _rows(source, "job_sources")
    source_ids: dict[str, str] = {}
    for row in sources:
        company_id = company_ids.get(row["company_id"])
        if company_id is None:
            if authoritative_catalog:
                continue
            raise ValueError("legacy job source has no company mapping")
        existing = target.execute(
            """
            SELECT id
            FROM catalog.job_sources
            WHERE company_id = %s AND slug = %s
            """,
            (company_id, row["slug"]),
        ).fetchone()
        if existing is None:
            if authoritative_catalog:
                continue
            target.execute(
                """
                INSERT INTO catalog.job_sources(
                    id, company_id, slug, source_type,
                    base_url, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    row["id"],
                    company_id,
                    row["slug"],
                    row["source_type"],
                    row.get("base_url"),
                    row["created_at"],
                ),
            )
            source_ids[row["id"]] = row["id"]
        else:
            source_ids[row["id"]] = str(existing[0])
    counts["job_sources"] = len(sources)

    jobs = _rows(source, "jobs")
    job_ids: dict[str, str] = {}
    for row in jobs:
        source_id = source_ids.get(row["source_id"])
        if authoritative_catalog:
            existing = target.execute(
                """
                SELECT id
                FROM catalog.jobs
                WHERE canonical_url = %s
                  AND crawl_source_id IS NOT NULL
                ORDER BY updated_at DESC, id
                LIMIT 1
                """,
                (row["canonical_url"],),
            ).fetchone()
            company_id = company_ids.get(row["company_id"])
            if (
                existing is None
                and company_id is not None
                and row.get("external_job_id")
            ):
                existing = target.execute(
                    """
                    SELECT id
                    FROM catalog.jobs
                    WHERE company_id = %s
                      AND external_job_id = %s
                      AND crawl_source_id IS NOT NULL
                    ORDER BY updated_at DESC, id
                    LIMIT 1
                    """,
                    (
                        company_id,
                        row["external_job_id"],
                    ),
                ).fetchone()
        elif row.get("external_job_id"):
            if source_id is None:
                raise ValueError("legacy job has no source mapping")
            existing = target.execute(
                """
                SELECT id
                FROM catalog.jobs
                WHERE source_id = %s AND external_job_id = %s
                LIMIT 1
                """,
                (source_id, row["external_job_id"]),
            ).fetchone()
        else:
            if source_id is None:
                raise ValueError("legacy job has no source mapping")
            existing = target.execute(
                """
                SELECT id
                FROM catalog.jobs
                WHERE source_id = %s AND canonical_url = %s
                LIMIT 1
                """,
                (source_id, row["canonical_url"]),
            ).fetchone()
        if existing is not None:
            job_ids[row["id"]] = str(existing[0])
            continue
        if authoritative_catalog:
            continue
        target.execute(
            """
            INSERT INTO catalog.jobs(
                id, company_id, source_id, external_job_id,
                canonical_url, title, location_raw, locations,
                recruitment_type, description_raw, responsibilities,
                requirements, status, content_hash, missing_count,
                first_seen_at, last_seen_at, last_changed_at,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s,
                %s::jsonb, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT DO NOTHING
            """,
            (
                row["id"],
                company_ids[row["company_id"]],
                source_id,
                row.get("external_job_id"),
                row["canonical_url"],
                row.get("title"),
                row.get("location_raw"),
                json.dumps(_json(row.get("locations_json"), [])),
                row.get("recruitment_type"),
                row["description_raw"],
                json.dumps(_json(row.get("responsibilities_json"), [])),
                json.dumps(_json(row.get("requirements_json"), [])),
                row["status"],
                row["content_hash"],
                row.get("missing_count", 0),
                row["first_seen_at"],
                row["last_seen_at"],
                row["last_changed_at"],
                row["created_at"],
                row["updated_at"],
            ),
        )
        job_ids[row["id"]] = row["id"]
    counts["jobs"] = len(jobs)
    counts["jobs_mapped_to_authoritative_catalog"] = (
        len(job_ids) if authoritative_catalog else 0
    )
    counts["jobs_skipped_authoritative_catalog"] = (
        len(jobs) - len(job_ids) if authoritative_catalog else 0
    )

    missing_references = _referenced_job_ids(source) - job_ids.keys()
    if missing_references:
        raise ValueError(
            "legacy user data references jobs absent from the "
            "authoritative catalog: "
            + ", ".join(sorted(missing_references))
        )

    versions = _rows(source, "job_versions")
    migrated_versions = 0
    for row in versions:
        if authoritative_catalog or row["job_id"] not in job_ids:
            continue
        target.execute(
            """
            INSERT INTO catalog.job_versions(
                id, job_id, version_number, content_hash,
                snapshot, captured_at
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                row["id"],
                job_ids[row["job_id"]],
                row["version_number"],
                row["content_hash"],
                row.get("snapshot_json", "{}"),
                row["captured_at"],
            ),
        )
        migrated_versions += 1
    counts["job_versions"] = len(versions)
    counts["job_versions_migrated"] = migrated_versions

    events = _rows(source, "job_events")
    migrated_events = 0
    for row in events:
        if authoritative_catalog or row["job_id"] not in job_ids:
            continue
        target.execute(
            """
            INSERT INTO catalog.job_events(
                id, job_id, event_type, summary,
                changed_fields, occurred_at
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT DO NOTHING
            """,
            (
                row["id"],
                job_ids[row["job_id"]],
                row["event_type"],
                row["summary"],
                row.get("changed_fields_json", "[]"),
                row["occurred_at"],
            ),
        )
        migrated_events += 1
    counts["job_events"] = len(events)
    counts["job_events_migrated"] = migrated_events
    return job_ids


def _referenced_job_ids(source: sqlite3.Connection) -> set[str]:
    result: set[str] = set()
    for table in (
        "job_tracking",
        "interview_sessions",
    ):
        for row in _rows(source, table):
            job_id = row.get("job_id")
            if job_id:
                result.add(str(job_id))
    return result


def _migrate_resumes(
    source,
    target,
    private_root: Path,
    user_id: str,
    counts: dict[str, int],
) -> dict[str, str]:
    previews = _rows(source, "resume_previews")
    latest_preview: dict[str, dict] = {}
    for row in previews:
        current = latest_preview.get(row["resume_import_id"])
        if current is None or (row["updated_at"], row["id"]) > (
            current["updated_at"],
            current["id"],
        ):
            latest_preview[row["resume_import_id"]] = row

    imports = _rows(source, "resume_imports")
    imports_by_id = {row["id"]: row for row in imports}
    resume_ids: dict[str, str] = {}
    migrated = 0
    for row in imports:
        preview = latest_preview.get(row["id"])
        proposal = _json(
            preview.get("proposal_json") if preview else None,
            {},
        )
        confirmed = _json(
            preview.get("confirmed_sections_json") if preview else None,
            [],
        )
        sections = {
            section: proposal[section]
            for section in confirmed
            if section in proposal
        }
        existing = target.execute(
            """
            SELECT id
            FROM career.resume_imports
            WHERE user_id = %s AND content_hash = %s
            """,
            (user_id, row["content_hash"]),
        ).fetchone()
        if existing is not None:
            resume_ids[row["id"]] = str(existing[0])
            continue
        blob_id = None
        original = private_root / str(row["private_path"])
        if original.is_file():
            content = original.read_bytes()
            blob_id = str(uuid4())
            target.execute(
                """
                INSERT INTO blob.objects(
                    id, scope, user_id, kind, media_type, original_name,
                    size_bytes, sha256, content
                ) VALUES (
                    %s, 'user', %s, 'resume_original',
                    'application/octet-stream', %s, %s, %s, %s
                )
                """,
                (
                    blob_id,
                    user_id,
                    row["original_filename"],
                    len(content),
                    hashlib.sha256(content).hexdigest(),
                    content,
                ),
            )
        data = {
            "status": row["status"],
            "filename": row["original_filename"],
            "display_name": row.get("display_name")
            or row["original_filename"],
            "target_roles": _json(row.get("target_roles_json"), []),
            "source_kind": row["source_kind"],
            "sections": sections,
            "confirmed_sections": confirmed,
            "revision_at": row["updated_at"],
            "deleted_at": row.get("deleted_at"),
        }
        target.execute(
            """
            INSERT INTO career.resume_imports(
                id, user_id, blob_id, content_hash, data,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                row["id"],
                user_id,
                blob_id,
                row["content_hash"],
                json.dumps(data, ensure_ascii=False, sort_keys=True),
                row["created_at"],
                row["updated_at"],
            ),
        )
        resume_ids[row["id"]] = row["id"]
        migrated += 1
    counts["resume_imports"] = migrated

    facts = _rows(source, "candidate_facts")
    facts_by_profile: dict[str, dict[str, object]] = {}
    for row in facts:
        facts_by_profile.setdefault(row["profile_id"], {})[
            row["section"]
        ] = _json(row.get("fact_value_json"), None)

    profiles = _rows(source, "candidate_profile")
    for row in profiles:
        sections = facts_by_profile.get(row["id"], {})
        data = {
            "display_name": row.get("display_name"),
            "current_version": int(row["current_version"]),
            "sections": sections,
        }
        target.execute(
            """
            INSERT INTO career.candidate_profiles(
                id, user_id, data, created_at, updated_at
            ) VALUES (%s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                row["id"],
                user_id,
                json.dumps(data, ensure_ascii=False),
                row["created_at"],
                row["updated_at"],
            ),
        )
    counts["candidate_profiles"] = len(profiles)

    for row in facts:
        target.execute(
            """
            INSERT INTO career.candidate_facts(
                id, user_id, profile_id, section, fact_key,
                fact_value, confirmed_at
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                row["id"],
                user_id,
                row["profile_id"],
                row["section"],
                row["fact_key"],
                row["fact_value_json"],
                row["confirmed_at"],
            ),
        )
    counts["candidate_facts"] = len(facts)

    versions = _rows(source, "profile_versions")
    for row in versions:
        source_import = imports_by_id.get(row["source_import_id"], {})
        snapshot = {
            "source_import_id": resume_ids[row["source_import_id"]],
            "filename": source_import.get("original_filename")
            or "resume",
            "source_kind": source_import.get("source_kind") or "text",
            "confirmed_sections": _json(
                row.get("confirmed_sections_json"),
                [],
            ),
            "sections": _json(row.get("snapshot_json"), {}),
        }
        target.execute(
            """
            INSERT INTO career.profile_versions(
                id, user_id, profile_id, version_number,
                snapshot, created_at
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                row["id"],
                user_id,
                row["profile_id"],
                row["version_number"],
                json.dumps(snapshot, ensure_ascii=False),
                row["created_at"],
            ),
        )
    counts["profile_versions"] = len(versions)

    for row in previews:
        data = {
            "preview_token": row["preview_token"],
            "proposal": _json(row.get("proposal_json"), {}),
            "conflicts": _json(row.get("conflicts_json"), []),
            "confirmed_sections": _json(
                row.get("confirmed_sections_json"),
                [],
            ),
        }
        target.execute(
            """
            INSERT INTO career.resume_previews(
                id, user_id, resume_import_id, data,
                expires_at, created_at
            ) VALUES (%s, %s, %s, %s::jsonb, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                row["id"],
                user_id,
                resume_ids[row["resume_import_id"]],
                json.dumps(data, ensure_ascii=False),
                row["expires_at"],
                row["created_at"],
            ),
        )
    counts["resume_previews"] = len(previews)
    return resume_ids


def _migrate_tracking(
    source,
    target,
    user_id,
    counts,
    job_ids: dict[str, str],
) -> None:
    rows = _rows(source, "job_tracking")
    for row in rows:
        data = {
            "is_favorite": bool(row["is_favorite"]),
            "favorited_at": row.get("favorited_at"),
            "application_status": row["application_status"],
            "applied_at": row.get("applied_at"),
            "note": row.get("note"),
            "updated_at": row["updated_at"],
        }
        target.execute(
            """
            INSERT INTO career.job_tracking(
                user_id, job_id, data, version, created_at, updated_at
            ) VALUES (%s, %s, %s::jsonb, %s, %s, %s)
            ON CONFLICT (user_id, job_id) DO NOTHING
            """,
            (
                user_id,
                job_ids[row["job_id"]],
                json.dumps(data, ensure_ascii=False),
                row["version"],
                row["created_at"],
                row["updated_at"],
            ),
        )
    counts["job_tracking"] = len(rows)


def _migrate_interviews(
    source,
    target,
    user_id,
    counts,
    job_ids: dict[str, str],
    resume_ids: dict[str, str],
) -> None:
    sessions = _rows(source, "interview_sessions")
    conflict_losers = _interview_conflict_losers(
        sessions,
        job_ids,
        resume_ids,
    )
    for row in sessions:
        conversation_id = row.get("conversation_id")
        if conversation_id:
            target.execute(
                """
                INSERT INTO agent.conversations(id, user_id)
                VALUES (%s, %s)
                ON CONFLICT (user_id, id) DO NOTHING
                """,
                (conversation_id, user_id),
            )
        data = {
            **row,
            "resume_id": row["resume_import_id"],
            "blueprint": _json(row["blueprint_json"], {}),
        }
        if row["id"] in conflict_losers:
            data.update(
                {
                    "migration_original_status": data["status"],
                    "migration_conflict_resolution": (
                        "cancelled_older_active_session"
                    ),
                    "status": "cancelled",
                    "phase": "idle",
                    "ended_at": data.get("ended_at") or row["updated_at"],
                }
            )
        for key in (
            "id",
            "job_id",
            "resume_import_id",
            "conversation_id",
            "version",
            "created_at",
            "updated_at",
            "blueprint_json",
        ):
            data.pop(key, None)
        target.execute(
            """
            INSERT INTO career.interview_sessions(
                id, user_id, job_id, resume_import_id,
                conversation_id, data, version, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                row["id"],
                user_id,
                job_ids[row["job_id"]],
                resume_ids[row["resume_import_id"]],
                conversation_id,
                json.dumps(data, ensure_ascii=False, sort_keys=True),
                row["version"],
                row["created_at"],
                row["updated_at"],
            ),
        )
    counts["interview_sessions"] = len(sessions)
    counts["interview_sessions_cancelled_conflicts"] = len(
        conflict_losers
    )

    turns = _rows(source, "interview_turns")
    for row in turns:
        data = {
            **row,
            "question_refs": _json(row["question_refs_json"], []),
            "evaluation": _json(row.get("evaluation_json"), None),
        }
        for key in (
            "id",
            "session_id",
            "turn_index",
            "started_at",
            "question_refs_json",
            "evaluation_json",
        ):
            data.pop(key, None)
        target.execute(
            """
            INSERT INTO career.interview_turns(
                id, user_id, session_id, turn_index, data, created_at
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                row["id"],
                user_id,
                row["session_id"],
                row["turn_index"],
                json.dumps(data, ensure_ascii=False, sort_keys=True),
                row["started_at"],
            ),
        )
    counts["interview_turns"] = len(turns)


def _interview_conflict_losers(
    sessions: list[dict],
    job_ids: dict[str, str],
    resume_ids: dict[str, str],
) -> set[str]:
    active = {"ready", "in_progress"}
    winners: dict[tuple[str, str], dict] = {}
    for row in sessions:
        if row.get("status") not in active:
            continue
        key = (
            job_ids[row["job_id"]],
            resume_ids[row["resume_import_id"]],
        )
        winner = winners.get(key)
        rank = (
            str(row.get("updated_at") or ""),
            str(row.get("created_at") or ""),
            str(row["id"]),
        )
        if winner is None or rank > winner["rank"]:
            winners[key] = {"id": row["id"], "rank": rank}
    return {
        str(row["id"])
        for row in sessions
        if row.get("status") in active
        and winners[
            (
                job_ids[row["job_id"]],
                resume_ids[row["resume_import_id"]],
            )
        ]["id"]
        != row["id"]
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--career-db", type=Path)
    source.add_argument("--state-root", type=Path)
    parser.add_argument("--private-root", type=Path)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    source_path = (args.career_db or args.state_root).expanduser().resolve()
    if _USER_ID.fullmatch(args.user_id) is None:
        return 2
    if args.career_db is not None:
        if not source_path.is_file() or args.private_root is None:
            return 2
    elif not source_path.is_dir():
        return 2
    if args.dry_run:
        report = (
            inspect_career_source(source_path)
            if args.career_db is not None
            else {
                "source_kind": "agent_context_state",
                "source_sha256": context_state_sha256(source_path),
                "counts": {},
            }
        )
    else:
        if not args.database_url:
            return 2
        database = CloudDatabase.from_url(args.database_url)
        try:
            database.migrate()
            report = (
                migrate_career_database(
                    database,
                    source_path=source_path,
                    private_root=args.private_root.expanduser().resolve(),
                    user_id=args.user_id,
                )
                if args.career_db is not None
                else migrate_context_state(
                    database,
                    state_root=source_path,
                    user_id=args.user_id,
                )
            )
        finally:
            database.close()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    else:
        print(
            "migration "
            f"source_sha256={report['source_sha256']} "
            f"counts={json.dumps(report.get('counts', {}), sort_keys=True)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
