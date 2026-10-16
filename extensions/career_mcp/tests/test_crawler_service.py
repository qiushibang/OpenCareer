import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler.adapters import FakeAdapter
from extensions.career_mcp.domain.crawler import JobSnapshot, SourceDescriptor
from extensions.career_mcp.services.crawler import CrawlerService


def _snapshot(description: str = "Build tools") -> JobSnapshot:
    return JobSnapshot(
        external_job_id="42",
        title="Agent Engineer",
        description_raw=description,
        source_url="https://jobs.example/42",
        observed_at="2026-08-05T00:00:00Z",
        location_raw="北京",
        recruitment_type="internship",
    )


def test_successive_runs_cover_the_crawler_state_machine(tmp_path):
    service = CrawlerService(CareerConfig(data_dir=tmp_path / "career"))

    created = service.crawl(FakeAdapter("fake-source", [_snapshot()]))
    unchanged = service.crawl(FakeAdapter("fake-source", [_snapshot()]))
    changed = service.crawl(FakeAdapter("fake-source", [_snapshot("Build reliable tools")]))
    missing = service.crawl(FakeAdapter("fake-source", []))
    offline = service.crawl(FakeAdapter("fake-source", []))
    reopened = service.crawl(
        FakeAdapter("fake-source", [_snapshot("Build reliable tools")])
    )

    assert created.transitions == {"created": 1}
    assert unchanged.transitions == {"unchanged": 1}
    assert changed.transitions == {"changed": 1}
    assert missing.transitions == {"missing": 1}
    assert offline.transitions == {"offline": 1}
    assert reopened.transitions == {"reopened": 1}


class FailingAdapter:
    source_slug = "failing-source"
    descriptor = SourceDescriptor(
        source_slug=source_slug,
        source_name="Failing source",
        company_slug="failing-company",
        company_name="Failing company",
        scope_key="fixture:failure",
        adapter_type="fixture",
        base_url=None,
    )

    def fetch_jobs(self) -> list[JobSnapshot]:
        raise RuntimeError("fixture failure")


def test_adapter_failure_does_not_apply_absence_state(tmp_path):
    service = CrawlerService(CareerConfig(data_dir=tmp_path / "career"))
    service.crawl(FakeAdapter("fake-source", [_snapshot()]))

    failed = service.crawl(FailingAdapter())
    after_failure = service.crawl(FakeAdapter("fake-source", [_snapshot()]))

    assert failed.status == "failed"
    assert failed.transitions == {}
    assert failed.error_summary == "fixture failure"
    assert after_failure.transitions == {"unchanged": 1}


def test_distinct_external_jobs_can_have_identical_content(tmp_path):
    service = CrawlerService(CareerConfig(data_dir=tmp_path / "career"))
    first = _snapshot()
    second = JobSnapshot(
        external_job_id="43",
        title=first.title,
        description_raw=first.description_raw,
        source_url="https://jobs.example/43",
        observed_at=first.observed_at,
        location_raw=first.location_raw,
        recruitment_type=first.recruitment_type,
    )

    result = service.crawl(FakeAdapter("fake-source", [first, second]))

    assert result.transitions == {"created": 2}


def test_dry_run_computes_transitions_without_creating_a_database(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    service = CrawlerService(config)

    result = service.crawl(FakeAdapter("fake-source", [_snapshot()]), dry_run=True)

    assert result.status == "dry_run"
    assert result.transitions == {"created": 1}
    assert not config.database_path.exists()


def test_dry_run_failure_preserves_error_summary(tmp_path):
    service = CrawlerService(CareerConfig(data_dir=tmp_path / "career"))

    result = service.crawl(FailingAdapter(), dry_run=True)

    assert result.status == "failed"
    assert result.error_summary == "fixture failure"


def test_dry_run_previews_changed_job_without_persisting_it(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    service = CrawlerService(config)
    service.crawl(FakeAdapter("fake-source", [_snapshot()]))

    preview = service.crawl(
        FakeAdapter("fake-source", [_snapshot("Build reliable tools")]),
        dry_run=True,
    )

    assert preview.status == "dry_run"
    assert preview.transitions == {"changed": 1}

    connection = __import__("sqlite3").connect(config.database_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM job_versions").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM job_events").fetchone()[0] == 1
    finally:
        connection.close()


def test_registered_source_requires_an_explicit_adapter(tmp_path):
    service = CrawlerService(
        CareerConfig(data_dir=tmp_path / "career"),
        adapters=[FakeAdapter("fake-source", [_snapshot()])],
    )

    result = service.crawl_registered_source("fake-source", dry_run=True)

    assert result.status == "dry_run"
    with pytest.raises(LookupError, match="source not found"):
        service.crawl_registered_source("unknown-source")


def test_multiple_sources_share_one_canonical_company(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    seed = SourceDescriptor(
        source_slug="bytedance-campus-seed-2027",
        source_name="字节跳动 Seed 校招",
        company_slug="bytedance",
        company_name="字节跳动",
        scope_key="project:seed",
        adapter_type="fixture",
        base_url="https://jobs.bytedance.com/campus/position",
    )
    frontier = SourceDescriptor(
        source_slug="bytedance-campus-frontier-2027",
        source_name="字节跳动前沿技术校招",
        company_slug="bytedance",
        company_name="字节跳动",
        scope_key="project:frontier",
        adapter_type="fixture",
        base_url="https://jobs.bytedance.com/campus/position",
    )
    service = CrawlerService(config)

    service.crawl(
        FakeAdapter(seed.source_slug, [_snapshot()], descriptor=seed)
    )
    second = JobSnapshot(
        external_job_id="43",
        title="Research Engineer",
        description_raw="Build frontier models",
        source_url="https://jobs.example/43",
        observed_at="2026-08-05T00:00:00Z",
        location_raw="北京",
        recruitment_type="campus",
    )
    service.crawl(
        FakeAdapter(frontier.source_slug, [second], descriptor=frontier)
    )

    connection = __import__("sqlite3").connect(config.database_path)
    connection.row_factory = __import__("sqlite3").Row
    try:
        companies = connection.execute(
            "SELECT id, slug, name FROM companies WHERE slug = 'bytedance'"
        ).fetchall()
        sources = connection.execute(
            """
            SELECT slug, company_id, scope_key
            FROM crawl_sources
            ORDER BY slug
            """
        ).fetchall()
        job_company_ids = {
            row["company_id"]
            for row in connection.execute("SELECT company_id FROM jobs")
        }
    finally:
        connection.close()

    assert len(companies) == 1
    assert companies[0]["name"] == "字节跳动"
    assert [row["scope_key"] for row in sources] == [
        "project:frontier",
        "project:seed",
    ]
    assert {row["company_id"] for row in sources} == {companies[0]["id"]}
    assert job_company_ids == {companies[0]["id"]}


def test_source_overlap_validation_rejects_duplicate_company_job_ids(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    seed = SourceDescriptor(
        source_slug="bytedance-campus-seed-2027",
        source_name="字节跳动 Seed 校招",
        company_slug="bytedance",
        company_name="字节跳动",
        scope_key="project:seed",
        adapter_type="fixture",
        base_url="https://jobs.bytedance.com/campus/position",
    )
    frontier = SourceDescriptor(
        source_slug="bytedance-campus-frontier-2027",
        source_name="字节跳动前沿技术校招",
        company_slug="bytedance",
        company_name="字节跳动",
        scope_key="project:frontier",
        adapter_type="fixture",
        base_url="https://jobs.bytedance.com/campus/position",
    )
    service = CrawlerService(config)
    service.crawl(FakeAdapter(seed.source_slug, [_snapshot()], descriptor=seed))

    with pytest.raises(ValueError, match="overlaps.*42"):
        service.validate_source_overlap(
            FakeAdapter(frontier.source_slug, [_snapshot()], descriptor=frontier)
        )


def test_source_overlap_validation_accepts_disjoint_scope(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    first = SourceDescriptor(
        source_slug="company-campus",
        source_name="Company campus",
        company_slug="company",
        company_name="Company",
        scope_key="campus",
        adapter_type="fixture",
        base_url=None,
    )
    second = SourceDescriptor(
        source_slug="company-experienced",
        source_name="Company experienced",
        company_slug="company",
        company_name="Company",
        scope_key="experienced",
        adapter_type="fixture",
        base_url=None,
    )
    service = CrawlerService(config)
    service.crawl(FakeAdapter(first.source_slug, [_snapshot()], descriptor=first))
    distinct = JobSnapshot(
        external_job_id="43",
        title="Experienced Engineer",
        description_raw="Build systems",
        source_url="https://jobs.example/43",
        observed_at="2026-08-05T00:00:00Z",
    )

    service.validate_source_overlap(
        FakeAdapter(second.source_slug, [distinct], descriptor=second)
    )


def test_crawl_all_sources_is_sorted_and_isolates_failures(tmp_path):
    class BatchFailingAdapter:
        source_slug = "b-failing"
        descriptor = SourceDescriptor(
            source_slug=source_slug,
            source_name="B failing",
            company_slug="b",
            company_name="B",
            scope_key="all",
            adapter_type="fixture",
            base_url=None,
        )

        def fetch_jobs(self):
            raise RuntimeError("batch fixture failure")

    service = CrawlerService(
        CareerConfig(data_dir=tmp_path / "career"),
        adapters=[
            FakeAdapter("c-success", [_snapshot("C")]),
            BatchFailingAdapter(),
            FakeAdapter("a-success", [_snapshot("A")]),
        ],
    )

    batch = service.crawl_all_sources(dry_run=True, batch_size=3)

    assert [result.source_slug for result in batch.results] == [
        "a-success",
        "b-failing",
        "c-success",
    ]
    assert [result.status for result in batch.results] == [
        "dry_run",
        "failed",
        "dry_run",
    ]
    assert batch.transitions == {"created": 2}
    assert batch.failed == 1
    assert batch.has_more is False
    assert batch.next_cursor is None


def test_crawl_all_sources_uses_cursor_for_bounded_batches(tmp_path):
    service = CrawlerService(
        CareerConfig(data_dir=tmp_path / "career"),
        adapters=[
            FakeAdapter("b-source", [_snapshot("B")]),
            FakeAdapter("a-source", [_snapshot("A")]),
        ],
    )

    first = service.crawl_all_sources(dry_run=True, batch_size=1)
    second = service.crawl_all_sources(
        dry_run=True,
        cursor=first.next_cursor,
        batch_size=1,
    )

    assert [result.source_slug for result in first.results] == ["a-source"]
    assert first.has_more is True
    assert first.next_cursor == "a-source"
    assert [result.source_slug for result in second.results] == ["b-source"]
    assert second.has_more is False
    assert second.next_cursor is None


def test_crawler_service_uses_injected_catalog_repository_session(
    tmp_path,
):
    class Repository:
        def __init__(self) -> None:
            self.created: list[str] = []
            self.completed: list[tuple[str, str, int]] = []
            self.raw_snapshots: list[tuple[str, str, bytes]] = []

        def ensure_crawl_source(self, descriptor):
            return {
                "crawl_source_id": "source-1",
                "company_id": "company-1",
                "source_slug": descriptor.source_slug,
                "missing_threshold": 2,
            }

        def start_crawl_run(self, source_id):
            return "run-1"

        def store_raw_snapshot(
            self,
            source_id,
            run_id,
            *,
            url,
            payload,
            fetched_at,
        ):
            self.raw_snapshots.append((source_id, run_id, payload))

        def find_crawled_job(self, source_id, external_job_id):
            return None

        def create_crawled_job(self, source, job):
            self.created.append(job.external_job_id)
            return "job-1"

        def active_crawled_jobs(self, source_id):
            return []

        def complete_crawl_run(
            self,
            run_id,
            *,
            status,
            observed_count,
            error_summary=None,
        ):
            self.completed.append((run_id, status, observed_count))

    repository = Repository()

    @contextmanager
    def repository_session():
        yield repository

    service = CrawlerService(
        CareerConfig(data_dir=tmp_path / "unused"),
        adapters=[FakeAdapter("source-a", [_snapshot("A")])],
        repository_session=repository_session,
    )

    result = service.crawl_registered_source("source-a")

    assert result.status == "succeeded"
    assert repository.created == ["42"]
    assert repository.completed == [("run-1", "succeeded", 1)]
    assert repository.raw_snapshots
    assert b'"external_job_id":"42"' in repository.raw_snapshots[0][2]


def test_crawler_service_does_not_write_without_catalog_source_lock(
    tmp_path,
):
    class Repository:
        def __init__(self) -> None:
            self.started = False

        def ensure_crawl_source(self, descriptor):
            return {
                "crawl_source_id": "source-1",
                "company_id": "company-1",
                "source_slug": descriptor.source_slug,
                "missing_threshold": 2,
            }

        def acquire_source_lock(self, source_slug):
            return False

        def start_crawl_run(self, source_id):
            self.started = True
            raise AssertionError("locked source must not create a crawl run")

    repository = Repository()

    @contextmanager
    def repository_session():
        yield repository

    service = CrawlerService(
        CareerConfig(data_dir=tmp_path / "unused"),
        adapters=[FakeAdapter("source-a", [_snapshot("A")])],
        repository_session=repository_session,
    )

    result = service.crawl_registered_source("source-a")

    assert result.status == "failed"
    assert result.error_summary == "crawl source is already running"
    assert repository.started is False


def test_job_radar_digest_uses_rolling_window_and_marks_unpersisted_source_pending(
    tmp_path,
):
    service = CrawlerService(
        CareerConfig(data_dir=tmp_path / "career"),
        adapters=[FakeAdapter("pending-source", [_snapshot()])],
        clock=lambda: datetime(
            2026,
            8,
            6,
            1,
            0,
            tzinfo=timezone.utc,
        ),
    )

    result = service.get_job_radar_digest(hours=24, sample_limit=20)

    assert result["window"] == {
        "started_at": "2026-08-05T01:00:00Z",
        "ended_at": "2026-08-06T01:00:00Z",
        "hours": 24,
    }
    assert result["events"]["total"] == 0
    assert result["sources"] == {
        "configured": 1,
        "healthy": 0,
        "failed": 0,
        "pending": 1,
        "items": [
            {
                "source_slug": "pending-source",
                "source_name": "pending-source",
                "last_run_status": None,
                "last_run_at": None,
                "last_observed_count": None,
                "last_error": None,
            }
        ],
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"hours": 0}, "hours must be between 1 and 168"),
        ({"hours": 169}, "hours must be between 1 and 168"),
        (
            {"sample_limit": 0},
            "sample_limit must be between 1 and 100",
        ),
        (
            {"sample_limit": 101},
            "sample_limit must be between 1 and 100",
        ),
    ],
)
def test_job_radar_digest_validates_ranges(tmp_path, kwargs, message):
    service = CrawlerService(CareerConfig(data_dir=tmp_path / "career"))

    with pytest.raises(ValueError, match=message):
        service.get_job_radar_digest(**kwargs)
