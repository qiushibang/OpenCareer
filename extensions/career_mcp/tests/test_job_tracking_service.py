from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import sqlite3
from threading import Barrier

import pytest

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.database.job_tracking_repository import (
    JobTrackingRepository,
)
from extensions.career_mcp.database.migrations import SCHEMA_VERSION, connect
from extensions.career_mcp.services.job_tracking import (
    JobTrackingService,
    JobTrackingServiceError,
)
from extensions.career_mcp.services.jobs import JobService

NOW = datetime(2026, 8, 9, 1, 0, tzinfo=timezone.utc)
JD = """职位：AI 工程师
公司：DeepSeek
任职要求：
1. 熟悉 Python
"""


@pytest.fixture
def seeded_tracking(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    jobs = JobService(config)
    values = {
        "raw_text": JD,
        "source_url": "https://careers.deepseek.com/jobs/tracking",
        "company_name": "DeepSeek",
        "title": "AI 工程师",
    }
    preview = jobs.import_manual_jd(**values, confirmed=False)
    job_id = jobs.import_manual_jd(
        **values,
        preview_hash=preview["preview_hash"],
        confirmed=True,
    )["job_id"]
    service = JobTrackingService(config, clock=lambda: NOW)
    return config, service, job_id


def test_tracking_defaults_without_persisting(seeded_tracking):
    config, service, job_id = seeded_tracking

    result = service.get(job_id)

    assert result["application_status"] == "not_started"
    assert result["is_favorite"] is False
    assert result["version"] == 0
    with connect(config.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM job_tracking"
        ).fetchone()[0] == 0


def test_tracking_updates_with_cas_and_appends_status_events(
    seeded_tracking,
):
    _, service, job_id = seeded_tracking

    first = service.update(
        job_id,
        {
            "expected_version": 0,
            "is_favorite": True,
            "application_status": "preparing",
        },
    )
    second = service.update(
        job_id,
        {
            "expected_version": first["version"],
            "application_status": "applied",
            "note": "已完成官网投递",
        },
    )

    assert first["version"] == 1
    assert second["version"] == 2
    assert second["applied_at"] == "2026-08-09T01:00:00Z"
    assert [event["to_status"] for event in second["events"]] == [
        "applied",
        "preparing",
    ]


def test_tracking_rejects_stale_version(seeded_tracking):
    _, service, job_id = seeded_tracking
    service.update(job_id, {"expected_version": 0, "is_favorite": True})

    with pytest.raises(JobTrackingServiceError) as error:
        service.update(
            job_id,
            {"expected_version": 0, "application_status": "applied"},
        )

    assert error.value.code == "VERSION_CONFLICT"


def test_tracking_cas_allows_only_one_concurrent_version(
    seeded_tracking,
):
    config, _, job_id = seeded_tracking
    barrier = Barrier(2)

    def update(status):
        service = JobTrackingService(config, clock=lambda: NOW)
        barrier.wait()
        try:
            result = service.update(
                job_id,
                {
                    "expected_version": 0,
                    "application_status": status,
                },
            )
            return "ok", result["application_status"]
        except JobTrackingServiceError as exc:
            return exc.code, None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(update, ("preparing", "applied"))
        )

    assert sorted(code for code, _ in results) == [
        "VERSION_CONFLICT",
        "ok",
    ]
    with connect(config.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM job_application_events WHERE job_id = ?",
            (job_id,),
        ).fetchone()[0] == 1


def test_tracking_orders_same_second_events_by_commit_order(
    seeded_tracking,
    monkeypatch,
):
    _, service, job_id = seeded_tracking
    event_ids = iter(["z-first-event", "a-second-event"])
    monkeypatch.setattr(
        "extensions.career_mcp.services.job_tracking.uuid4",
        lambda: next(event_ids),
    )

    first = service.update(
        job_id,
        {"expected_version": 0, "application_status": "preparing"},
    )
    second = service.update(
        job_id,
        {
            "expected_version": first["version"],
            "application_status": "applied",
        },
    )

    assert [event["to_status"] for event in second["events"]] == [
        "applied",
        "preparing",
    ]


def test_tracking_rolls_back_when_result_read_fails(
    seeded_tracking,
    monkeypatch,
):
    config, service, job_id = seeded_tracking
    original = JobTrackingRepository.get
    calls = 0

    def fail_second_read(repository, selected_job_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise sqlite3.OperationalError("simulated result read failure")
        return original(repository, selected_job_id)

    monkeypatch.setattr(
        JobTrackingRepository,
        "get",
        fail_second_read,
    )

    with pytest.raises(sqlite3.OperationalError):
        service.update(
            job_id,
            {"expected_version": 0, "application_status": "preparing"},
        )

    with connect(config.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM job_tracking WHERE job_id = ?",
            (job_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            """
            SELECT COUNT(*) FROM job_application_events
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()[0] == 0


def test_tracking_migrates_fresh_database_before_locking(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    service = JobTrackingService(config, clock=lambda: NOW)

    with pytest.raises(JobTrackingServiceError) as error:
        service.get("missing")

    assert error.value.code == "JOB_NOT_FOUND"
    with connect(config.database_path) as connection:
        assert (
            connection.execute("PRAGMA user_version").fetchone()[0]
            == SCHEMA_VERSION
        )
