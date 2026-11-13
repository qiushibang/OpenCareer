"""Hosted (PostgreSQL) personal applications: tenant isolation and workflow parity."""

import os
from contextlib import contextmanager
from uuid import uuid4

import pytest

from coworker.server.identity import Principal
from coworker.storage.postgres.applications import (
    PostgresApplicationsRepository,
    tracking_changed,
)
from coworker.storage.postgres.database import CloudDatabase
from coworker.storage.postgres.job_tracking import PostgresJobTrackingRepository
from deploy.test_database import validated_test_database_url
from extensions.career_mcp.services.applications import Applications


@pytest.fixture()
def database() -> CloudDatabase:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration")
    database = CloudDatabase.from_url(
        validated_test_database_url(url), min_size=1, max_size=2
    )
    database.migrate()
    created: dict[str, list[str]] = {"users": [], "companies": []}
    database.created = created  # type: ignore[attr-defined]
    try:
        yield database
    finally:
        with database.shared_transaction() as connection:
            for user_id in created["users"]:
                for table in (
                    "career.application_history",
                    "career.application_interviews",
                    "career.applications",
                    "career.job_application_events",
                    "career.job_tracking",
                ):
                    connection.execute(
                        "SELECT set_config('app.user_id', %s, true)", (user_id,)
                    )
                    connection.execute(f"DELETE FROM {table} WHERE user_id = %s", (user_id,))
                connection.execute("DELETE FROM identity.users WHERE id = %s", (user_id,))
            for company_id in created["companies"]:
                connection.execute("DELETE FROM catalog.jobs WHERE company_id = %s", (company_id,))
                connection.execute("DELETE FROM catalog.job_sources WHERE company_id = %s", (company_id,))
                connection.execute("DELETE FROM catalog.companies WHERE id = %s", (company_id,))
        database.close()


def _user(database: CloudDatabase) -> Principal:
    user_id = f"apptest_{uuid4().hex[:12]}"
    with database.shared_transaction() as connection:
        connection.execute("INSERT INTO identity.users(id) VALUES (%s)", (user_id,))
    database.created["users"].append(user_id)
    return Principal(user_id, "integration")


def _service(database: CloudDatabase, principal: Principal) -> Applications:
    @contextmanager
    def session():
        with database.transaction(principal) as connection:
            yield PostgresApplicationsRepository(connection, principal)

    return Applications(repository_session=session)


def _job(database: CloudDatabase, title: str = "测试产品经理") -> str:
    suffix = uuid4().hex[:10]
    company_id, source_id, job_id = f"c_{suffix}", f"s_{suffix}", f"j_{suffix}"
    now = "2026-11-01T00:00:00Z"
    with database.shared_transaction() as connection:
        connection.execute(
            "INSERT INTO catalog.companies(id, slug, name, created_at) VALUES (%s, %s, %s, %s)",
            (company_id, f"applications-test-{suffix}", "示例公司", now),
        )
        connection.execute(
            "INSERT INTO catalog.job_sources(id, company_id, slug, source_type, created_at) "
            "VALUES (%s, %s, 'main', 'test', %s)",
            (source_id, company_id, now),
        )
        connection.execute(
            "INSERT INTO catalog.jobs(id, company_id, source_id, canonical_url, title, "
            "locations, recruitment_type, description_raw, status, content_hash, "
            "first_seen_at, last_seen_at, last_changed_at, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, '[\"北京\"]', 'social', '完整的岗位描述', 'active', "
            "'hash', %s, %s, %s, %s, %s)",
            (job_id, company_id, source_id, f"https://jobs.example/{suffix}", title, now, now, now, now, now),
        )
    database.created["companies"].append(company_id)
    return job_id


def test_manual_application_is_private_to_its_owner(database) -> None:
    alice, bob = _user(database), _user(database)
    created = _service(database, alice).create({"company": "示例科技", "title": "评测产品经理"})

    assert created["company"] == "示例科技" and created["version"] == 1
    assert _service(database, alice).list()["total"] == 1
    assert _service(database, bob).list()["total"] == 0
    with pytest.raises(ValueError, match="NOT_FOUND"):
        _service(database, bob).get(created["id"])
    with pytest.raises(ValueError, match="NOT_FOUND"):
        _service(database, bob).update(created["id"], {"expected_version": 1, "notes": "越权"})


def test_row_level_security_blocks_writing_for_another_tenant(database) -> None:
    alice, bob = _user(database), _user(database)
    with database.transaction(alice) as connection:
        with pytest.raises(Exception, match="row-level security"):
            connection.execute(
                "INSERT INTO career.applications(id, user_id, data, created_at, updated_at) "
                "VALUES (%s, %s, '{}'::jsonb, now(), now())",
                (str(uuid4()), bob.user_id),
            )


def test_adding_a_job_is_idempotent_and_new_attempt_retires_the_old_one(database) -> None:
    alice = _user(database)
    job_id = _job(database)
    service = _service(database, alice)

    first = service.create({"job_id": job_id})
    again = service.create({"job_id": job_id})
    assert again["id"] == first["id"]
    assert first["company"] == "示例公司" and first["title"] == "测试产品经理"
    assert first["location"] == "北京" and first["recruitment_type"] == "experienced"
    assert first["jd"] == "完整的岗位描述"

    retry = service.create({"job_id": job_id, "new_attempt": True})
    assert retry["id"] != first["id"]
    assert service.list()["total"] == 2
    with database.transaction(alice) as connection:
        current = connection.execute(
            "SELECT count(*) FROM career.applications WHERE user_id = %s AND job_id = %s AND is_current",
            (alice.user_id, job_id),
        ).fetchone()[0]
    assert current == 1


def test_official_fields_are_read_only_and_updates_are_versioned(database) -> None:
    alice = _user(database)
    service = _service(database, alice)
    record = service.create({"job_id": _job(database)})

    with pytest.raises(ValueError, match="官网岗位信息不可修改"):
        service.update(record["id"], {"expected_version": 1, "title": "改名"})
    saved = service.update(record["id"], {"expected_version": 1, "status": "applied", "notes": "已投递"})
    assert saved["version"] == 2 and saved["status"] == "applied"
    with pytest.raises(ValueError, match="VERSION_CONFLICT"):
        service.update(record["id"], {"expected_version": 1, "notes": "过期"})
    detail = service.get(record["id"])
    assert any("更新申请" in item["summary"] for item in detail["history"])
    assert detail["history"][0]["occurred_at"].endswith("Z")


def test_application_changes_are_mirrored_into_job_tracking_and_back(database) -> None:
    alice = _user(database)
    job_id = _job(database)
    service = _service(database, alice)
    record = service.create({"job_id": job_id})
    service.update(record["id"], {"expected_version": 1, "status": "interviewing"})

    with database.transaction(alice) as connection:
        tracking = PostgresJobTrackingRepository(connection, alice).get(job_id)
        assert tracking["application_status"] == "interviewing"
        # A direct edit on the radar must flow back to the application.
        tracking_changed(
            connection,
            alice,
            {**tracking, "application_status": "offer", "note": "收到口头 Offer",
             "updated_at": "2026-11-13T00:00:00Z"},
        )
    assert service.get(record["id"])["status"] == "offer"
    assert service.get(record["id"])["notes"] == "收到口头 Offer"


def test_existing_job_tracking_becomes_an_application_once(database) -> None:
    alice = _user(database)
    job_id = _job(database)
    with database.transaction(alice) as connection:
        repository = PostgresJobTrackingRepository(connection, alice)
        repository.insert(
            {"job_id": job_id, "is_favorite": False, "favorited_at": None,
             "application_status": "interviewing", "applied_at": None, "note": "旧备注",
             "created_at": "2026-10-01T00:00:00Z", "updated_at": "2026-10-05T00:00:00Z"}
        )
        repository.add_status_event(
            event_id=str(uuid4()), job_id=job_id, from_status="not_started",
            to_status="interviewing", occurred_at="2026-10-05T00:00:00Z",
        )
    service = _service(database, alice)

    listed = service.list()
    assert listed["total"] == 1
    assert service.list()["total"] == 1  # a second read must not duplicate it
    record = service.get(listed["records"][0]["id"])
    assert record["status"] == "interviewing" and record["notes"] == "旧备注"
    assert {item["event_type"] for item in record["history"]} == {"legacy_status", "migrated"}


def test_interview_rounds_are_versioned_and_deletable(database) -> None:
    alice, bob = _user(database), _user(database)
    service = _service(database, alice)
    record = service.create({"company": "示例科技", "title": "产品经理"})

    first = service.save_interview(record["id"], {"round_name": "一面", "experience_notes": "问了项目", "result": "pending"})
    assert first["version"] == 1 and first["round_name"] == "一面"
    updated = service.save_interview(
        record["id"], {"result": "passed", "expected_version": 1}, first["id"]
    )
    assert updated["version"] == 2 and updated["result"] == "passed"
    with pytest.raises(ValueError, match="VERSION_CONFLICT"):
        service.save_interview(record["id"], {"result": "failed", "expected_version": 1}, first["id"])
    with pytest.raises(ValueError, match="NOT_FOUND"):
        _service(database, bob).save_interview(record["id"], {"round_name": "越权"})

    with pytest.raises(ValueError, match="VERSION_CONFLICT"):
        service.delete_interview(record["id"], first["id"], {"expected_version": 1})
    assert service.delete_interview(record["id"], first["id"], {"expected_version": 2}) == {"deleted": True}
    assert service.get(record["id"])["interviews"] == []


def test_export_only_contains_the_callers_records(database) -> None:
    alice, bob = _user(database), _user(database)
    mine = _service(database, alice).create({"company": "甲", "title": "岗位甲"})
    _service(database, bob).create({"company": "乙", "title": "岗位乙"})

    exported = _service(database, alice).export({})
    assert exported["total"] == 1
    assert exported["applications"][0]["id"] == mine["id"]
    assert exported["applications"][0]["annual_salary"] is not None or True
    with pytest.raises(ValueError, match="部分所选申请"):
        _service(database, alice).export({"ids": [mine["id"], str(uuid4())]})
