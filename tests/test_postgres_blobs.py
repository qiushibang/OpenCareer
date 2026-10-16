from contextlib import contextmanager

import pytest

from coworker.server.identity import Principal
from coworker.storage.postgres.blob_repository import PostgresBlobRepository


class _Result:
    def __init__(self, row=None) -> None:
        self._row = row

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.row = None

    def execute(self, sql: str, params: object = None) -> _Result:
        self.calls.append((sql, params))
        return _Result(self.row)


class _Database:
    def __init__(self) -> None:
        self.connection = _Connection()

    @contextmanager
    def transaction(self, principal):
        yield self.connection


def test_put_user_blob_calculates_integrity_metadata() -> None:
    database = _Database()
    repository = PostgresBlobRepository(database)

    metadata = repository.put(
        Principal("alice", "test"),
        content=b"resume",
        kind="resume_original",
        media_type="application/pdf",
        original_name="resume.pdf",
    )

    assert metadata.user_id == "alice"
    assert metadata.size_bytes == 6
    assert (
        metadata.sha256
        == "a83a31320d921b888a48fa5edd0b4b5a29984de6e96bf7b8ac7d29ba06caf616"
    )
    assert database.connection.calls[0][1][-1] == b"resume"


def test_put_rejects_a_resume_larger_than_ten_megabytes() -> None:
    repository = PostgresBlobRepository(_Database())

    with pytest.raises(ValueError, match="10 MB"):
        repository.put(
            Principal("alice", "test"),
            content=b"x" * (10 * 1024 * 1024 + 1),
            kind="resume_original",
            media_type="application/pdf",
        )


def test_iter_content_returns_fixed_size_chunks() -> None:
    database = _Database()
    database.connection.row = (b"abcdefgh",)
    repository = PostgresBlobRepository(database)

    chunks = list(
        repository.iter_content(
            Principal("alice", "test"),
            "11111111-1111-1111-1111-111111111111",
            chunk_size=3,
        )
    )

    assert chunks == [b"abc", b"def", b"gh"]
