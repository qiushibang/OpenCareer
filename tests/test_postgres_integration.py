from __future__ import annotations

import os
import json
import sys
from pathlib import Path

import pytest
import psycopg
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coworker.runtime.local_coordinator import LocalRuntimeCoordinator
from coworker.server.app import create_app
from coworker.server.identity import Principal
from coworker.server.manager import SessionManager
from coworker.sessions import SessionRecord
from coworker.storage.postgres.database import CloudDatabase
from coworker.storage.postgres.conversations import (
    PostgresConversationRepository,
)
from coworker.storage.postgres.inbox_repository import (
    PostgresInboxRepository,
)
from coworker.storage.postgres.interviews import (
    PostgresInterviewRepository,
)
from deploy.test_database import (
    cleanup_catalog_test_rows,
    validated_test_database_url,
)


@pytest.fixture()
def database() -> CloudDatabase:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration")
    url = validated_test_database_url(url)
    database = CloudDatabase.from_url(url, min_size=1, max_size=1)
    database.migrate()
    try:
        yield database
    finally:
        cleanup_catalog_test_rows(database)
        database.close()


def test_migration_is_repeatable_on_postgres_16(
    database: CloudDatabase,
) -> None:
    assert database.migrate() == ()
    with database.pool.connection() as connection:
        schemas = {
            row[0]
            for row in connection.execute(
                """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name IN (
                    'identity', 'catalog', 'career', 'agent', 'blob'
                )
                """
            ).fetchall()
        }
    assert schemas == {"identity", "catalog", "career", "agent", "blob"}


def test_rls_isolates_same_conversation_id_across_pool_reuse(
    database: CloudDatabase,
) -> None:
    alice = Principal("alice", "integration")
    bob = Principal("bob", "integration")
    for principal in (alice, bob):
        with database.transaction(principal) as connection:
            connection.execute(
                """
                INSERT INTO identity.users(id)
                VALUES (%s)
                ON CONFLICT (id) DO NOTHING
                """,
                (principal.user_id,),
            )
            connection.execute(
                """
                INSERT INTO agent.conversations(id, user_id, metadata)
                VALUES ('shared-id', %s, %s::jsonb)
                ON CONFLICT (user_id, id)
                DO UPDATE SET metadata = EXCLUDED.metadata
                """,
                (
                    principal.user_id,
                    f'{{"owner":"{principal.user_id}"}}',
                ),
            )

    with database.transaction(alice) as connection:
        rows = connection.execute(
            """
            SELECT user_id, metadata->>'owner'
            FROM agent.conversations
            WHERE id = 'shared-id'
            """
        ).fetchall()
        assert rows == [("alice", "alice")]
        assert connection.execute(
            """
            UPDATE agent.conversations
            SET metadata = '{"owner":"tampered"}'::jsonb
            WHERE user_id = 'bob' AND id = 'shared-id'
            RETURNING id
            """
        ).fetchone() is None

    with database.transaction(bob) as connection:
        rows = connection.execute(
            """
            SELECT user_id, metadata->>'owner'
            FROM agent.conversations
            WHERE id = 'shared-id'
            """
        ).fetchall()
    assert rows == [("bob", "bob")]


def test_delete_conversation_cascades_resolved_inbox_records(
    database: CloudDatabase,
) -> None:
    principal = Principal("conversation-delete", "integration")
    conversations = PostgresConversationRepository(database, principal)
    inbox = PostgresInboxRepository(database, principal)
    conversations.save(
        SessionRecord(
            session_id="conversation-delete",
            workspace="/workspace",
            model="deepseek:model",
            mode="interactive",
            messages=[{"role": "user", "content": "delete me"}],
            agent="career",
        )
    )
    item = inbox.add_approval(
        "conversation-delete",
        "Approve?",
        tool_call_id="delete-call",
    )
    assert inbox.resolve(item.id, "deny")

    assert conversations.delete("conversation-delete")
    assert conversations.load("conversation-delete") is None
    assert inbox.get(item.id) is None
    with database.transaction(principal) as connection:
        assert connection.execute(
            """
            SELECT count(*)
            FROM agent.inbox_resolutions
            WHERE user_id = %s AND inbox_item_id = %s
            """,
            (principal.user_id, item.id),
        ).fetchone() == (0,)


def test_career_foreign_keys_reject_cross_tenant_parent(
    database: CloudDatabase,
) -> None:
    alice = Principal("alice-fk", "integration")
    bob = Principal("bob-fk", "integration")
    for principal in (alice, bob):
        with database.transaction(principal) as connection:
            connection.execute(
                """
                INSERT INTO identity.users(id)
                VALUES (%s)
                ON CONFLICT (id) DO NOTHING
                """,
                (principal.user_id,),
            )
    with database.transaction(alice) as connection:
        connection.execute(
            """
            INSERT INTO career.candidate_profiles(
                id, user_id, data, created_at, updated_at
            ) VALUES ('shared-profile-id', %s, '{}'::jsonb, now(), now())
            ON CONFLICT (id) DO NOTHING
            """,
            (alice.user_id,),
        )

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with database.transaction(bob) as connection:
            connection.execute(
                """
                INSERT INTO career.candidate_facts(
                    id, user_id, profile_id, section, fact_key,
                    fact_value, confirmed_at
                ) VALUES (
                    'cross-tenant-fact', %s, 'shared-profile-id',
                    'project', 'name', '"forbidden"'::jsonb, now()
                )
                """,
                (bob.user_id,),
            )


def test_career_jobs_api_uses_shared_catalog_and_tenant_tracking(
    database: CloudDatabase,
    tmp_path,
    monkeypatch,
) -> None:
    alice = Principal("alice-api", "integration")
    bob = Principal("bob-api", "integration")
    with database.shared_transaction() as connection:
        for user_id in (alice.user_id, bob.user_id):
            connection.execute(
                """
                INSERT INTO identity.users(id)
                VALUES (%s)
                ON CONFLICT (id) DO NOTHING
                """,
                (user_id,),
            )
        connection.execute(
            """
            INSERT INTO catalog.companies(id, slug, name, created_at)
            VALUES ('api-company', 'api-company', 'API Company', now())
            ON CONFLICT (id) DO NOTHING
            """
        )
        connection.execute(
            """
            INSERT INTO catalog.job_sources(
                id, company_id, slug, source_type, base_url, created_at
            ) VALUES (
                'api-source', 'api-company', 'api-source',
                'integration', 'https://jobs.example.com', now()
            )
            ON CONFLICT (id) DO NOTHING
            """
        )
        connection.execute(
            """
            INSERT INTO catalog.jobs(
                id, company_id, source_id, canonical_url, title,
                locations, recruitment_type, description_raw,
                responsibilities, requirements, status, content_hash,
                first_seen_at, last_seen_at, last_changed_at,
                created_at, updated_at
            ) VALUES (
                'api-job', 'api-company', 'api-source',
                'https://jobs.example.com/api-job', 'API AI Engineer',
                '["北京"]'::jsonb, 'experienced', 'Build AI',
                '["Build"]'::jsonb, '["Python"]'::jsonb, 'active',
                %s, now(), now(), now(), now(), now()
            )
            ON CONFLICT (id) DO NOTHING
            """,
            ("a" * 64,),
        )

    class Runtime:
        mode = "postgres"
        origin_repository = None
        coordinator = LocalRuntimeCoordinator()

        def __init__(self, current: CloudDatabase) -> None:
            self.database = current

        def health(self) -> dict[str, str]:
            return {
                "mode": "postgres",
                "postgres": "ready",
                "redis": "ready",
            }

        def close(self) -> None:
            pass

    monkeypatch.setenv(
        "OPENCAR_USER_TOKENS",
        "alice-api:alice-token,bob-api:bob-token",
    )
    client = TestClient(
        create_app(
            SessionManager(data_dir=tmp_path / "state"),
            storage_runtime=Runtime(database),
        )
    )
    alice_headers = {"X-OpenWorker-Token": "alice-token"}
    bob_headers = {"X-OpenWorker-Token": "bob-token"}
    with database.transaction(alice) as connection:
        connection.execute(
            """
            DELETE FROM career.job_tracking
            WHERE user_id = %s AND job_id = 'api-job'
            """,
            (alice.user_id,),
        )

    assert client.get(
        "/v1/career/jobs",
        headers=alice_headers,
    ).status_code == 200
    updated = client.patch(
        "/v1/career/jobs/api-job/tracking",
        headers=alice_headers,
        json={"expected_version": 0, "is_favorite": True},
    )
    alice_favorites = client.get(
        "/v1/career/jobs",
        headers=alice_headers,
        params={"favorite_only": "true", "status": ""},
    )
    bob_favorites = client.get(
        "/v1/career/jobs",
        headers=bob_headers,
        params={"favorite_only": "true", "status": ""},
    )

    assert updated.status_code == 200
    assert updated.json()["tracking"]["version"] == 1
    assert alice_favorites.json()["total"] == 1
    assert bob_favorites.json()["total"] == 0


def test_postgres_interview_repository_persists_tenant_state(
    database: CloudDatabase,
) -> None:
    alice = Principal("alice-interview", "integration")
    bob = Principal("bob-interview", "integration")
    with database.shared_transaction() as connection:
        for user_id in (alice.user_id, bob.user_id):
            connection.execute(
                """
                INSERT INTO identity.users(id)
                VALUES (%s)
                ON CONFLICT (id) DO NOTHING
                """,
                (user_id,),
            )
        connection.execute(
            """
            INSERT INTO catalog.companies(id, slug, name, created_at)
            VALUES (
                'interview-company', 'api-company',
                'API Company', now()
            )
            ON CONFLICT (slug) DO NOTHING
            """
        )
        company_id = connection.execute(
            """
            SELECT id
            FROM catalog.companies
            WHERE slug = 'api-company'
            """
        ).fetchone()[0]
        connection.execute(
            """
            INSERT INTO catalog.job_sources(
                id, company_id, slug, source_type, base_url, created_at
            ) VALUES (
                'interview-source', %s, 'interview-source',
                'integration', 'https://jobs.example.com', now()
            )
            ON CONFLICT (id) DO NOTHING
            """,
            (company_id,),
        )
        connection.execute(
            """
            INSERT INTO catalog.jobs(
                id, company_id, source_id, canonical_url, title,
                locations, recruitment_type, description_raw,
                responsibilities, requirements, status, content_hash,
                first_seen_at, last_seen_at, last_changed_at,
                created_at, updated_at
            ) VALUES (
                'api-job', %s, 'interview-source',
                'https://jobs.example.com/api-job', 'API AI Engineer',
                '["北京"]'::jsonb, 'experienced', 'Build AI',
                '["Build"]'::jsonb, '["Python"]'::jsonb, 'active',
                %s, now(), now(), now(), now(), now()
            )
            ON CONFLICT (id) DO NOTHING
            """,
            (company_id, "a" * 64),
        )
    with database.transaction(alice) as connection:
        connection.execute(
            """
            DELETE FROM career.interview_turns
            WHERE user_id = %s AND session_id = 'postgres-interview'
            """,
            (alice.user_id,),
        )
        connection.execute(
            """
            DELETE FROM career.interview_sessions
            WHERE user_id = %s AND id = 'postgres-interview'
            """,
            (alice.user_id,),
        )
        connection.execute(
            """
            INSERT INTO career.resume_imports(
                id, user_id, content_hash, data, created_at, updated_at
            ) VALUES (
                'interview-resume', %s, %s, '{}'::jsonb, now(), now()
            )
            ON CONFLICT (id) DO NOTHING
            """,
            (alice.user_id, "b" * 64),
        )
        connection.execute(
            """
            INSERT INTO agent.conversations(id, user_id)
            VALUES ('interview-conversation', %s)
            ON CONFLICT (user_id, id) DO NOTHING
            """,
            (alice.user_id,),
        )
        repository = PostgresInterviewRepository(connection, alice)
        created = repository.create_session(
            {
                "id": "postgres-interview",
                "job_id": "api-job",
                "resume_id": "interview-resume",
                "snapshot_id": "snapshot-1",
                "conversation_id": "interview-conversation",
                "company": "API Company",
                "position": "API AI Engineer",
                "difficulty": "standard",
                "duration_minutes": 15,
                "question_budget": 5,
                "blueprint": {"version": 2},
                "status": "ready",
                "phase": "idle",
                "started_at": None,
                "ended_at": None,
                "report_path": None,
                "transcript_path": None,
                "session_path": None,
                "report_sha256": None,
                "created_at": "2026-08-19T00:00:00Z",
                "updated_at": "2026-08-19T00:00:00Z",
            }
        )
        repository.insert_turn(
            {
                "id": "postgres-turn",
                "session_id": created["id"],
                "turn_index": 1,
                "question_text": "请说明个人贡献？",
                "question_refs": ["project[0]"],
                "answer_text": None,
                "evaluation": None,
                "next_action": None,
                "next_reason": None,
                "question_topic": "个人贡献",
                "probe_target": "project[0]",
                "probe_dimension": "personal_contribution",
                "depth_level": 1,
                "started_at": "2026-08-19T00:00:00Z",
                "answered_at": None,
                "evaluated_at": None,
            }
        )
        assert repository.answer_turn(
            "postgres-turn",
            answer_text="我负责核心链路。",
            answered_at="2026-08-19T00:01:00Z",
        )
        assert repository.get_active_session(
            "api-job",
            "interview-resume",
        )["id"] == created["id"]
        assert repository.list_turns(created["id"])[0]["answer_text"] == (
            "我负责核心链路。"
        )

    with database.transaction(bob) as connection:
        repository = PostgresInterviewRepository(connection, bob)
        assert repository.get_session("postgres-interview") is None


def test_postgres_api_creates_match_and_interview_without_sqlite(
    database: CloudDatabase,
    tmp_path,
    monkeypatch,
) -> None:
    alice = Principal("alice-flow", "integration")
    bob = Principal("bob-flow", "integration")
    with database.shared_transaction() as connection:
        for user_id in (alice.user_id, bob.user_id):
            connection.execute(
                """
                INSERT INTO identity.users(id)
                VALUES (%s)
                ON CONFLICT (id) DO NOTHING
                """,
                (user_id,),
            )
        connection.execute(
            """
            INSERT INTO catalog.companies(id, slug, name, created_at)
            VALUES ('flow-company', 'flow-company', 'Flow Company', now())
            ON CONFLICT (id) DO NOTHING
            """
        )
        connection.execute(
            """
            INSERT INTO catalog.job_sources(
                id, company_id, slug, source_type, base_url, created_at
            ) VALUES (
                'flow-source', 'flow-company', 'flow-source',
                'integration', 'https://jobs.example.com', now()
            )
            ON CONFLICT (id) DO NOTHING
            """
        )
        connection.execute(
            """
            INSERT INTO catalog.jobs(
                id, company_id, source_id, canonical_url, title,
                locations, recruitment_type, description_raw,
                responsibilities, requirements, status, content_hash,
                first_seen_at, last_seen_at, last_changed_at,
                created_at, updated_at
            ) VALUES (
                'flow-job', 'flow-company', 'flow-source',
                'https://jobs.example.com/flow-job', 'AI Engineer',
                '["北京"]'::jsonb, 'experienced',
                '任职要求：必须熟练 Python',
                '["Build AI systems"]'::jsonb,
                '["必须熟练 Python"]'::jsonb, 'active',
                %s, now(), now(), now(), now(), now()
            )
            ON CONFLICT (id) DO NOTHING
            """,
            ("c" * 64,),
        )
    resume_data = {
        "status": "confirmed",
        "display_name": "AI Resume",
        "target_roles": ["AI Engineer"],
        "revision_at": "2026-08-19T00:00:00Z",
        "sections": {
            "basic": {
                "name": "Candidate",
                "summary": "AI Engineer",
            },
            "education": [],
            "experience": [],
            "project": [],
            "skill": [{"name": "Python"}],
        },
    }
    with database.transaction(alice) as connection:
        connection.execute(
            """
            INSERT INTO career.resume_imports(
                id, user_id, content_hash, data, created_at, updated_at
            ) VALUES (
                'flow-resume', %s, %s, %s::jsonb, now(), now()
            )
            ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data
            """,
            (
                alice.user_id,
                "d" * 64,
                json.dumps(resume_data, ensure_ascii=False),
            ),
        )

    class Runtime:
        mode = "postgres"
        origin_repository = None
        coordinator = LocalRuntimeCoordinator()

        def __init__(self, current: CloudDatabase) -> None:
            self.database = current

        def health(self) -> dict[str, str]:
            return {
                "mode": "postgres",
                "postgres": "ready",
                "redis": "ready",
            }

        def close(self) -> None:
            pass

    monkeypatch.setenv(
        "OPENCAR_USER_TOKENS",
        "alice-flow:alice-flow-token,bob-flow:bob-flow-token",
    )
    client = TestClient(
        create_app(
            SessionManager(data_dir=tmp_path / "state"),
            storage_runtime=Runtime(database),
        )
    )
    alice_headers = {"X-OpenWorker-Token": "alice-flow-token"}
    bob_headers = {"X-OpenWorker-Token": "bob-flow-token"}
    removed_match = client.post(
        "/v1/career/jobs/flow-job/matches",
        headers=alice_headers,
        json={"resume_ids": ["flow-resume"]},
    )
    assert removed_match.status_code == 404
    created = client.post(
        "/v1/career/interviews",
        headers=alice_headers,
        json={
            "job_id": "flow-job",
            "resume_id": "flow-resume",
            "conversation_id": "flow-conversation",
            "difficulty": "standard",
            "duration_minutes": 15,
        },
    )

    assert created.status_code == 200
    interview = created.json()["interview"]
    restored = client.get(
        "/v1/career/interviews",
        headers=alice_headers,
        params={"conversation_id": "flow-conversation"},
    )
    denied = client.get(
        f"/v1/career/interviews/{interview['id']}",
        headers=bob_headers,
    )
    assert restored.json()["interview"]["id"] == interview["id"]
    assert denied.status_code == 404
    with database.transaction(alice) as connection:
        assert connection.execute(
            """
            SELECT COUNT(*)
            FROM career.interview_sessions
            WHERE user_id = %s AND id = %s
            """,
            (alice.user_id, interview["id"]),
        ).fetchone()[0] == 1
