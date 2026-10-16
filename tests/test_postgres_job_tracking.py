from contextlib import contextmanager
from datetime import datetime, timezone

from coworker.server.identity import Principal
from coworker.storage.postgres.job_tracking import (
    PostgresJobTrackingRepository,
)
from extensions.career_mcp.services.job_tracking import JobTrackingService


class _Rows:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self):
        self.calls = []
        self.responses = []

    def execute(self, sql, params=()):
        self.calls.append((" ".join(sql.split()), params))
        return self.responses.pop(0) if self.responses else _Rows()


def test_postgres_job_tracking_repository_scopes_writes_to_principal() -> None:
    connection = _Connection()
    connection.responses = [_Rows([(1,)])]
    repository = PostgresJobTrackingRepository(
        connection,
        Principal("alice", "test"),
    )
    tracking = {
        "job_id": "job-1",
        "is_favorite": True,
        "favorited_at": "2026-08-19T00:00:00Z",
        "application_status": "interviewing",
        "applied_at": None,
        "note": "prepare",
        "created_at": "2026-08-19T00:00:00Z",
        "updated_at": "2026-08-19T00:00:00Z",
    }

    assert repository.job_exists("job-1")
    repository.insert(tracking)

    insert_sql, insert_params = connection.calls[-1]
    assert "INSERT INTO career.job_tracking" in insert_sql
    assert insert_params[0] == "alice"
    assert insert_params[1] == "job-1"


class _Repository:
    def __init__(self):
        self.current = None
        self.events = []

    def job_exists(self, job_id):
        return True

    def get(self, job_id):
        return self.current

    def list_events(self, job_id):
        return list(self.events)

    def insert(self, tracking):
        self.current = {**tracking, "version": 1}

    def update_if_version(self, tracking, expected_version):
        if self.current["version"] != expected_version:
            return False
        self.current = {
            **tracking,
            "version": expected_version + 1,
        }
        return True

    def add_status_event(self, **event):
        self.events.append(event)


def test_job_tracking_service_uses_injected_tenant_repository() -> None:
    repository = _Repository()

    @contextmanager
    def repository_session(write=False):
        yield repository

    service = JobTrackingService(
        repository_session=repository_session,
        clock=lambda: datetime(2026, 8, 19, tzinfo=timezone.utc),
    )

    saved = service.update(
        "job-1",
        {
            "expected_version": 0,
            "is_favorite": True,
            "application_status": "interviewing",
        },
    )

    assert saved["version"] == 1
    assert saved["is_favorite"] is True
    assert saved["application_status"] == "interviewing"
    assert len(saved["events"]) == 1
