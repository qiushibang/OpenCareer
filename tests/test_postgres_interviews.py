from coworker.server.identity import Principal
from coworker.storage.postgres.interviews import (
    PostgresInterviewRepository,
)


class _Result:
    def __init__(self, row=None) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple | None]] = []

    def execute(self, sql: str, params=None) -> _Result:
        self.calls.append((sql, params))
        if "SELECT id, job_id" in sql:
            return _Result(
                (
                    "interview-1",
                    "job-1",
                    "resume-1",
                    "conversation-1",
                    {},
                    1,
                    "2026-08-19T00:00:00Z",
                    "2026-08-19T00:00:00Z",
                )
            )
        return _Result()


def test_creating_linked_interview_marks_conversation_as_career() -> None:
    connection = _Connection()
    repository = PostgresInterviewRepository(
        connection,
        Principal("alice", "test"),
    )

    repository.create_session(
        {
            "id": "interview-1",
            "job_id": "job-1",
            "resume_id": "resume-1",
            "conversation_id": "conversation-1",
            "created_at": "2026-08-19T00:00:00Z",
            "updated_at": "2026-08-19T00:00:00Z",
        }
    )

    conversation_insert = next(
        (sql, params)
        for sql, params in connection.calls
        if "INSERT INTO agent.conversations" in sql
    )
    assert "'{\"agent\":\"career\"}'::jsonb" in conversation_insert[0]
