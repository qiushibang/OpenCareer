from contextlib import contextmanager
import os
from pathlib import Path
import subprocess

from coworker.runtime.local_coordinator import LocalRuntimeCoordinator
from extensions.career_mcp import crawl_cli
from extensions.career_mcp.crawl_cli import (
    _FetchOutcome,
    _PersistOutcome,
    _persist_one_postgres,
)
from extensions.career_mcp.domain.crawler import JobSnapshot, SourceDescriptor


DESCRIPTOR = SourceDescriptor(
    source_slug="example-careers",
    source_name="Example careers",
    company_slug="example",
    company_name="Example",
    scope_key="all",
    adapter_type="fixture",
    base_url="https://jobs.example.com",
)
SNAPSHOT = JobSnapshot(
    external_job_id="job-1",
    title="AI Engineer",
    description_raw="Build reliable AI systems",
    source_url="https://jobs.example.com/job-1",
    observed_at="2026-08-19T00:00:00Z",
)


class _Repository:
    def __init__(self) -> None:
        self.raw_snapshot = None

    def ensure_crawl_source(self, descriptor):
        return {
            "crawl_source_id": "source-1",
            "company_id": "company-1",
            "source_slug": descriptor.source_slug,
            "missing_threshold": 2,
        }

    def acquire_source_lock(self, source_slug):
        return True

    def start_crawl_run(self, source_id):
        return "run-1"

    def store_raw_snapshot(self, source_id, run_id, **values):
        self.raw_snapshot = (source_id, run_id, values)

    def find_crawled_job(self, source_id, external_job_id):
        return None

    def create_crawled_job(self, source, job):
        return "job-1"

    def active_crawled_jobs(self, source_id):
        return []

    def complete_crawl_run(self, run_id, **values):
        return None


class _Database:
    def __init__(self, repository) -> None:
        self.repository = repository
        self.transactions = 0

    @contextmanager
    def shared_transaction(self):
        self.transactions += 1
        yield self.repository


class _Coordinator(LocalRuntimeCoordinator):
    def __init__(self) -> None:
        super().__init__()
        self.events = []

    def publish(self, channel: str, event: dict) -> None:
        self.events.append((channel, event))


def test_postgres_crawl_uses_redis_gate_and_publishes_after_commit() -> None:
    repository = _Repository()
    database = _Database(repository)
    coordinator = _Coordinator()

    result = _persist_one_postgres(
        database,
        coordinator,
        DESCRIPTOR,
        [SNAPSHOT],
        lock_ttl_seconds=60,
        repository_factory=lambda connection: connection,
    )

    assert result.status == "succeeded"
    assert result.transitions == {"created": 1}
    assert database.transactions == 2
    assert repository.raw_snapshot is not None
    assert coordinator.events == [
        (
            "catalog",
            {
                "type": "source_updated",
                "source_slug": "example-careers",
                "run_id": "run-1",
            },
        )
    ]
    assert coordinator.acquire_crawler_lock(
        DESCRIPTOR.source_slug,
        "second-owner",
        60,
    )


def test_postgres_crawl_stops_before_database_when_redis_lock_is_held() -> None:
    repository = _Repository()
    database = _Database(repository)
    coordinator = _Coordinator()
    assert coordinator.acquire_crawler_lock(
        DESCRIPTOR.source_slug,
        "existing-owner",
        60,
    )

    result = _persist_one_postgres(
        database,
        coordinator,
        DESCRIPTOR,
        [SNAPSHOT],
        lock_ttl_seconds=60,
        repository_factory=lambda connection: connection,
    )

    assert result.status == "failed"
    assert result.error == "crawl source is already running"
    assert database.transactions == 0
    assert coordinator.events == []


def test_cli_uses_one_postgres_target_when_cloud_is_configured(
    monkeypatch,
) -> None:
    class Runtime:
        mode = "postgres"
        database = object()
        coordinator = object()
        closed = False

        def close(self):
            self.closed = True

    runtime = Runtime()
    persisted = []
    monkeypatch.setenv("DATABASE_URL", "postgresql://db/opencareer")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setattr(
        crawl_cli,
        "_select_adapters",
        lambda only, skip: [object()],
    )
    monkeypatch.setattr(
        crawl_cli,
        "_fetch_all",
        lambda adapters, timeout, pause: [
            _FetchOutcome(
                DESCRIPTOR.source_slug,
                True,
                snapshot_count=1,
                descriptor=DESCRIPTOR,
                snapshots=[SNAPSHOT],
            )
        ],
    )
    monkeypatch.setattr(
        crawl_cli,
        "build_storage_runtime",
        lambda: runtime,
        raising=False,
    )

    def persist(database, coordinator, descriptor, snapshots, **kwargs):
        persisted.append((database, coordinator, descriptor, snapshots))
        return _PersistOutcome(
            "postgresql",
            descriptor.source_slug,
            "succeeded",
            {"created": 1},
        )

    monkeypatch.setattr(crawl_cli, "_persist_one_postgres", persist)

    assert crawl_cli.main(["--pause", "0"]) == 0
    assert len(persisted) == 1
    assert runtime.closed is True


def test_cli_runs_bounded_resumable_batches(monkeypatch) -> None:
    class Runtime:
        mode = "postgres"
        database = _Database(object())
        coordinator = object()
        closed = False

        def close(self):
            self.closed = True

    class Adapter:
        source_slug = "bytedance-mainland-social"

    calls = []

    class Service:
        def __init__(self, **kwargs):
            calls.append(("init", kwargs))

        def run_batch(self, adapter):
            calls.append(("run", adapter.source_slug))
            return {
                "source_slug": adapter.source_slug,
                "status": (
                    "running"
                    if len(
                        [
                            item
                            for item in calls
                            if item[0] == "run"
                        ]
                    )
                    == 1
                    else "committed"
                ),
                "has_more": True,
                "transitions": {},
            }

    runtime = Runtime()
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://db/opencareer_gate",
    )
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setattr(
        crawl_cli,
        "build_storage_runtime",
        lambda: runtime,
    )
    monkeypatch.setattr(
        crawl_cli,
        "default_resumable_adapters",
        lambda: [Adapter()],
        raising=False,
    )
    monkeypatch.setattr(
        crawl_cli,
        "ResumableCrawlerService",
        Service,
        raising=False,
    )

    code = crawl_cli.main(
        [
            "--resumable-only",
            "--resumable-batches",
            "2",
        ]
    )

    assert code == 0
    assert [item for item in calls if item[0] == "run"] == [
        ("run", "bytedance-mainland-social"),
        ("run", "bytedance-mainland-social"),
    ]
    assert runtime.closed is True


def test_crawler_entrypoint_runs_resumable_batches_after_regular_crawl(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls_path = tmp_path / "python-calls.txt"
    python_path = bin_dir / "python"
    python_path.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$CALLS_PATH\"\n",
        encoding="utf-8",
    )
    python_path.chmod(0o755)
    environment = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "CALLS_PATH": str(calls_path),
        "DATABASE_URL": "postgresql://db/opencareer",
        "CRAWL_RESUMABLE_BATCHES": "7",
    }

    result = subprocess.run(
        ["sh", "deploy/crawler/entrypoint.sh", "once"],
        cwd=Path(__file__).parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert calls_path.read_text(encoding="utf-8").splitlines() == [
        "-m extensions.career_mcp.crawl_cli --json",
        (
            "-m extensions.career_mcp.crawl_cli --resumable-only "
            "--resumable-batches 7"
        ),
    ]
