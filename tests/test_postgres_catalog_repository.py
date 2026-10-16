from datetime import datetime, timezone

from extensions.career_mcp.database.postgres_catalog_repository import (
    PostgresCatalogRepository,
)
from extensions.career_mcp.domain.crawler import NormalizedJob, SourceDescriptor
from extensions.career_mcp.domain.models import ManualJDPreview


class _Rows:
    def __init__(self, rows: list[tuple] = ()) -> None:
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.responses: list[_Rows] = []

    def execute(self, sql: str, params: tuple = ()) -> _Rows:
        self.calls.append((" ".join(sql.split()), params))
        return self.responses.pop(0) if self.responses else _Rows()


DESCRIPTOR = SourceDescriptor(
    source_slug="tencent-careers",
    source_name="Tencent careers",
    company_slug="tencent",
    company_name="腾讯",
    scope_key="experienced",
    adapter_type="api",
    base_url="https://careers.tencent.com",
)

JOB = NormalizedJob(
    identity="tencent-careers:job-1",
    external_job_id="job-1",
    title="AI 产品经理",
    description_raw="负责大模型产品",
    source_url="https://careers.tencent.com/job-1",
    observed_at="2026-08-18T00:00:00Z",
    locations=["北京"],
    recruitment_type="experienced",
    content_hash="a" * 64,
)


def test_postgres_catalog_registers_source_and_crawl_run() -> None:
    connection = _Connection()
    connection.responses = [
        _Rows(),
        _Rows([("company-1",)]),
        _Rows([("source-1", 3)]),
        _Rows([("run-1",)]),
        _Rows(),
    ]
    repository = PostgresCatalogRepository(
        connection,
        clock=lambda: datetime(2026, 8, 18, tzinfo=timezone.utc),
    )

    source = repository.ensure_crawl_source(DESCRIPTOR)
    run_id = repository.start_crawl_run(source["crawl_source_id"])
    repository.complete_crawl_run(
        run_id,
        status="succeeded",
        observed_count=10,
    )

    assert source == {
        "crawl_source_id": "source-1",
        "company_id": "company-1",
        "source_slug": "tencent-careers",
        "missing_threshold": 3,
    }
    assert run_id == "run-1"
    sql = "\n".join(call[0] for call in connection.calls)
    assert "INSERT INTO catalog.companies" in sql
    assert "INSERT INTO catalog.crawl_sources" in sql
    assert "INSERT INTO catalog.crawl_runs" in sql
    assert "UPDATE catalog.crawl_runs" in sql


def test_postgres_catalog_reuses_existing_company_without_upsert() -> None:
    connection = _Connection()
    connection.responses = [
        _Rows([("company-1",)]),
        _Rows([("source-1", 3)]),
    ]
    repository = PostgresCatalogRepository(connection)

    source = repository.ensure_crawl_source(DESCRIPTOR)

    assert source["company_id"] == "company-1"
    sql = "\n".join(call[0] for call in connection.calls)
    assert "SELECT id FROM catalog.companies WHERE slug = %s" in sql
    assert "INSERT INTO catalog.companies" not in sql
    assert "INSERT INTO catalog.crawl_sources" in sql


def test_postgres_catalog_creates_job_version_and_event() -> None:
    connection = _Connection()
    connection.responses = [
        _Rows([("job-source-1",)]),
        _Rows([("job-1",)]),
        _Rows(),
        _Rows(),
    ]
    repository = PostgresCatalogRepository(connection)

    job_id = repository.create_crawled_job(
        {
            "crawl_source_id": "crawl-source-1",
            "company_id": "company-1",
            "source_slug": "tencent-careers",
            "missing_threshold": 3,
        },
        JOB,
    )

    assert job_id == "job-1"
    sql = "\n".join(call[0] for call in connection.calls)
    assert "INSERT INTO catalog.job_sources" in sql
    assert "INSERT INTO catalog.jobs" in sql
    assert "INSERT INTO catalog.job_versions" in sql
    assert "INSERT INTO catalog.job_events" in sql


def test_postgres_catalog_marks_missing_then_offline() -> None:
    connection = _Connection()
    connection.responses = [
        _Rows([(2,)]),
        _Rows(),
        _Rows([(3,)]),
        _Rows(),
        _Rows(),
    ]
    repository = PostgresCatalogRepository(connection)

    row = {"id": "job-1", "missing_count": 1}
    assert repository.mark_absent(row, threshold=3) == "missing"
    assert repository.mark_absent(row, threshold=2) == "offline"

    sql = "\n".join(call[0] for call in connection.calls)
    parameters = [value for _, params in connection.calls for value in params]
    assert "status = 'inactive'" in sql
    assert "missing" in parameters
    assert "offline" in parameters


def test_postgres_catalog_uses_advisory_source_lock() -> None:
    connection = _Connection()
    connection.responses = [_Rows([(True,)])]
    repository = PostgresCatalogRepository(connection)

    assert repository.acquire_source_lock("tencent-careers")
    sql, params = connection.calls[0]
    assert "pg_try_advisory_xact_lock" in sql
    assert params == ("tencent-careers",)


def test_postgres_catalog_reconciles_only_requested_stale_jobs() -> None:
    connection = _Connection()
    connection.responses = [
        _Rows([("active-1",), ("off-1",)]),
        _Rows(),
        _Rows(),
    ]
    repository = PostgresCatalogRepository(connection)

    result = repository.reconcile_cycle_tail(
        "cycle-1",
        active_ids={"active-1"},
        offline_ids={"off-1"},
        pass_number=3,
        observed_at="2026-08-21T00:00:00Z",
    )

    assert result == {"active": 1, "offline": 1}
    sql = "\n".join(call[0] for call in connection.calls)
    assert "last_pass < %s" in sql
    assert "UPDATE catalog.crawl_cycle_jobs" in sql
    assert "DELETE FROM catalog.crawl_cycle_jobs" in sql


def test_postgres_catalog_stores_raw_snapshot_as_shared_blob() -> None:
    connection = _Connection()
    repository = PostgresCatalogRepository(connection)

    result = repository.store_raw_snapshot(
        "source-1",
        "run-1",
        url="https://careers.tencent.com",
        payload=b'{"jobs":[]}',
        fetched_at="2026-08-18T00:00:00Z",
    )

    assert result["sha256"]
    sql = "\n".join(call[0] for call in connection.calls)
    assert "INSERT INTO blob.objects" in sql
    assert "'shared'" in sql
    assert "INSERT INTO catalog.raw_snapshots" in sql


def test_postgres_catalog_creates_tenant_owned_manual_job() -> None:
    connection = _Connection()
    connection.responses = [
        _Rows([("company-1",)]),
        _Rows([("source-1",)]),
        _Rows(),
        _Rows([("manual-job-1",)]),
        _Rows(),
        _Rows(),
        _Rows(),
    ]
    repository = PostgresCatalogRepository(
        connection,
        principal_user_id="alice",
    )
    company_id, source_id = repository.ensure_manual_source("示例 AI 公司")
    assert repository.find_by_source_and_hash(source_id, "a" * 64) is None

    job_id = repository.create_manual_job(
        company_id=company_id,
        source_id=source_id,
        content_hash="a" * 64,
        canonical_url="manual://job",
        preview=ManualJDPreview(
            raw_text="职位：AI 工程师",
            cleaned_text="职位：AI 工程师",
            company_name="示例 AI 公司",
            title="AI 工程师",
            location_raw="北京",
            locations=["北京"],
            recruitment_type="experienced",
            responsibilities=[],
            requirements=[],
            missing_fields=[],
        ),
    )

    assert job_id == "manual-job-1"
    sql = "\n".join(call[0] for call in connection.calls)
    assert "INSERT INTO career.manual_job_owners" in sql
    assert any("alice" in params for _, params in connection.calls)
