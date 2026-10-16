from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coworker.server.identity import Principal
from coworker.storage.postgres.conversations import (
    PostgresConversationRepository,
)
from coworker.storage.postgres.automation_store import (
    PostgresAutomationStore,
)
from coworker.storage.postgres.database import CloudDatabase
from coworker.storage.postgres.inbox_repository import (
    PostgresInboxRepository,
)
from coworker.storage.postgres.memory_store import PostgresMemoryStore
from deploy.migrate_to_postgres import (
    _postgres_timestamp,
    context_state_sha256,
    main,
    migrate_context_state,
)


def _seed_state(root: Path) -> None:
    root.mkdir()
    conversations = root / "conversations"
    conversations.mkdir()
    messages = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "second"},
    ]
    (conversations / "session-1.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in messages),
        encoding="utf-8",
    )
    connection = sqlite3.connect(root / "coworker.db")
    connection.executescript(
        """
        CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY, workspace TEXT, model TEXT,
            mode TEXT, title TEXT, agent TEXT, n_msgs INTEGER,
            messages TEXT, extra_roots TEXT, pinned INTEGER,
            archived INTEGER, origin TEXT, origin_label TEXT,
            auto_title TEXT, renamed INTEGER, updated_at TEXT,
            grants TEXT, compaction TEXT
        );
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY, scope TEXT, key TEXT, content TEXT,
            workspace TEXT, session_id TEXT, created_at TEXT
        );
        """
    )
    compaction = {
        "boundary_index": 1,
        "summary_text": "first summary",
        "created_at": "2026-08-19T00:00:00Z",
    }
    connection.execute(
        """
        INSERT INTO sessions VALUES (
            'session-1', '/workspace', 'model:test', 'interactive',
            'Session One', 'career', 2, NULL, '[]', 1, 0, NULL, NULL,
            NULL, 1, '2026-08-19T00:00:00Z', '{}', ?
        )
        """,
        (json.dumps(compaction),),
    )
    connection.execute(
        """
        INSERT INTO memories VALUES (
            11, 'session', 'preference', 'Use evidence',
            '/workspace', 'session-1', '2026-08-19T00:00:00Z'
        )
        """
    )
    connection.commit()
    connection.close()

    (root / "inbox.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "id": "inbox-1",
                        "session_id": "session-1",
                        "kind": "question",
                        "title": "Need input",
                        "body": "",
                        "state": "resolved",
                        "resolution": "done",
                        "inbox": "default",
                        "created_at": "2026-08-19T00:00:00Z",
                        "resolved_at": "2026-08-19T00:01:00Z",
                        "visibility": "inbox",
                        "tool_call_id": "tool-1",
                        "options": [],
                        "allow_text": True,
                        "multi": False,
                        "data": {},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    automation = sqlite3.connect(root / "automation.db")
    automation.executescript(
        """
        CREATE TABLE scheduled_tasks (
            id TEXT PRIMARY KEY, enabled INTEGER, next_run REAL, data TEXT
        );
        CREATE TABLE task_runs (
            run_id TEXT PRIMARY KEY, task_id TEXT, started_at REAL, data TEXT
        );
        """
    )
    task = {
        "id": "task-1",
        "title": "Daily",
        "instructions": "Summarize",
        "schedule": {"kind": "cron", "cron": "0 4 * * *", "timezone": "UTC"},
        "workspace": "/workspace",
        "enabled": True,
        "created_at": 1.0,
        "updated_at": 2.0,
        "next_run": 3.0,
        "run_count": 0,
    }
    automation.execute(
        "INSERT INTO scheduled_tasks VALUES (?, 1, 3.0, ?)",
        ("task-1", json.dumps(task)),
    )
    automation.commit()
    automation.close()
    for name in (
        "inbox_routing.json",
        "mentions.json",
        "subscriptions.json",
        "wakes.json",
    ):
        (root / name).write_text(
            json.dumps({"source": name}),
            encoding="utf-8",
        )


def test_legacy_epoch_timestamp_is_normalized_to_utc() -> None:
    value = _postgres_timestamp(1787060200.9896398)

    assert value == datetime.fromtimestamp(
        1787060200.9896398,
        timezone.utc,
    )
    assert _postgres_timestamp("2026-08-19T00:00:00Z") == (
        "2026-08-19T00:00:00Z"
    )


def test_context_state_migration_is_complete_and_idempotent(tmp_path) -> None:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("TEST_DATABASE_URL is required")
    root = tmp_path / "state"
    _seed_state(root)
    user_id = f"context-{uuid4()}"
    principal = Principal(user_id, "test")
    database = CloudDatabase.from_url(url, min_size=1, max_size=1)
    database.migrate()
    try:
        first = migrate_context_state(
            database,
            state_root=root,
            user_id=user_id,
        )
        second = migrate_context_state(
            database,
            state_root=root,
            user_id=user_id,
        )

        assert first["reused"] is False
        assert second["reused"] is True
        record = PostgresConversationRepository(
            database,
            principal,
        ).load("session-1")
        assert [item["content"] for item in record.messages] == [
            "first",
            "second",
        ]
        assert record.compaction["summary_text"] == "first summary"
        memories = PostgresMemoryStore(database, principal).list()
        assert [item.content for item in memories] == ["Use evidence"]
        inbox = PostgresInboxRepository(database, principal).get("inbox-1")
        assert inbox is not None
        assert inbox.resolution == "done"
        automation = PostgresAutomationStore(database, principal).get(
            "task-1"
        )
        assert automation is not None
        assert automation.instructions == "Summarize"
        assert automation.workspace == "/workspace"
        with database.transaction(principal) as connection:
            assert connection.execute(
                "SELECT count(*) FROM agent.memories WHERE user_id = %s",
                (user_id,),
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT count(*) FROM agent.inbox_items WHERE user_id = %s",
                (user_id,),
            ).fetchone()[0] == 1
            assert connection.execute(
                "SELECT count(*) FROM agent.automations WHERE user_id = %s",
                (user_id,),
            ).fetchone()[0] == 1
            snapshots = connection.execute(
                """
                SELECT data
                FROM agent.audit_events
                WHERE user_id = %s
                  AND event_type = 'legacy_context_snapshot'
                """,
                (user_id,),
            ).fetchall()
        assert len(snapshots) == 4
        for (snapshot,) in snapshots:
            path = root / snapshot["name"]
            assert snapshot["sha256"] == hashlib.sha256(
                path.read_bytes()
            ).hexdigest()
    finally:
        database.close()


def test_context_state_migration_has_cli_entrypoint(tmp_path) -> None:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("TEST_DATABASE_URL is required")
    root = tmp_path / "state"
    _seed_state(root)
    user_id = f"context-cli-{uuid4()}"

    exit_code = main(
        [
            "--state-root",
            str(root),
            "--user-id",
            user_id,
            "--database-url",
            url,
            "--json",
        ]
    )

    assert exit_code == 0
    database = CloudDatabase.from_url(url, min_size=1, max_size=1)
    try:
        with database.transaction(
            Principal(user_id, "test")
        ) as connection:
            assert connection.execute(
                """
                SELECT count(*)
                FROM opencareer_meta.data_migrations
                WHERE source_kind = 'agent_context_state'
                  AND user_id = %s
                """,
                (user_id,),
            ).fetchone()[0] == 1
    finally:
        database.close()


def test_context_state_hash_ignores_unrelated_state_files(tmp_path) -> None:
    root = tmp_path / "state"
    _seed_state(root)
    original = context_state_sha256(root)

    (root / "runtime.log").write_text("changed", encoding="utf-8")
    assert context_state_sha256(root) == original

    conversation = root / "conversations" / "session-1.jsonl"
    conversation.write_text(
        conversation.read_text(encoding="utf-8")
        + '{"role":"user","content":"third"}\n',
        encoding="utf-8",
    )
    assert context_state_sha256(root) != original
