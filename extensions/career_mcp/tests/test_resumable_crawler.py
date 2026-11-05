from __future__ import annotations

from contextlib import contextmanager

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler.bytedance import (
    ResumableListingPage,
)
from extensions.career_mcp.database.migrations import connect
from extensions.career_mcp.database.repository import JobRepository
from extensions.career_mcp.domain.crawler import (
    JobSnapshot,
    SourceDescriptor,
)
from extensions.career_mcp.services.resumable_crawler import (
    ResumableCrawlerService,
)

OBSERVED_AT = "2026-08-20T00:00:00Z"


def _job(job_id: str) -> JobSnapshot:
    return JobSnapshot(
        external_job_id=job_id,
        title=f"AI Engineer {job_id}",
        description_raw="负责大模型训练与评测",
        source_url=f"https://jobs.bytedance.com/job/{job_id}",
        observed_at=OBSERVED_AT,
        location_raw="北京",
        recruitment_type="experienced",
    )


class _Adapter:
    source_slug = "bytedance-mainland-social"
    descriptor = SourceDescriptor(
        source_slug=source_slug,
        source_name="字节跳动中国大陆社招",
        company_slug="bytedance",
        company_name="字节跳动",
        scope_key="mainland-social",
        adapter_type="playwright-json-resumable",
        base_url="https://jobs.bytedance.com/experienced/position",
    )

    def __init__(self, pages):
        self.pages = pages
        self.requested = []

    def initial_shards(self):
        return [
            {
                "shard_key": "location:beijing",
                "filters": {"location_code": "CT_11"},
            }
        ]

    def fetch_page(self, filters, offset):
        self.requested.append((filters, offset))
        return self.pages[offset]


def test_continuation_does_not_start_a_completed_or_absent_cycle(tmp_path):
    adapter = _Adapter({})
    adapter.initial_shards = lambda: (_ for _ in ()).throw(AssertionError("must not fetch metadata"))
    service = ResumableCrawlerService(CareerConfig(tmp_path))
    result = service.run_batch(adapter, continuation_only=True)
    assert result["status"] == "idle" and result["has_more"] is False
    assert adapter.requested == []


def test_default_batch_commits_small_checkpoints_before_fetching_more(tmp_path):
    adapter = _Adapter({i: ResumableListingPage(
        jobs=[_job(str(i))], total=20, next_offset=i + 1,
        complete=False, fingerprint=f"page-{i}") for i in range(20)})
    config = CareerConfig(tmp_path)
    service = ResumableCrawlerService(config)
    result = service.run_batch(adapter)
    assert result["has_more"] is True and result["processed_pages"] == 5
    with connect(config.database_path) as db:
        assert db.execute("SELECT next_offset FROM crawl_cycle_shards").fetchone()[0] == 5
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_completed_shard_checkpoint_survives_next_shard_timeout(tmp_path):
    import pytest
    class Adapter(_Adapter):
        def initial_shards(self):
            return [{"shard_key": key, "filters": {"location_code": key}} for key in ("a", "b")]
        def fetch_page(self, filters, offset):
            if filters["location_code"] == "b":
                raise TimeoutError("next category is unavailable")
            return ResumableListingPage(jobs=[_job("1")], total=1,
                next_offset=1, complete=True, fingerprint="first-category")
    config = CareerConfig(tmp_path)
    service = ResumableCrawlerService(config)
    adapter = Adapter({})
    result = service.run_batch(adapter)
    assert result["has_more"] and result["processed_pages"] == 1
    with pytest.raises(TimeoutError):
        service.run_batch(adapter, continuation_only=True)
    with connect(config.database_path) as db:
        assert [tuple(row) for row in db.execute("SELECT shard_key,status FROM crawl_cycle_shards ORDER BY shard_key")] == [
            ("a", "complete"), ("b", "pending")]
        assert db.execute("SELECT count(*) FROM crawl_cycle_jobs").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_resumable_crawler_checkpoints_without_partial_catalog_write(
    tmp_path,
):
    adapter = _Adapter(
        {
            0: ResumableListingPage(
                jobs=[_job("1")],
                total=2,
                next_offset=1,
                complete=False,
                fingerprint="page-0",
            ),
            1: ResumableListingPage(
                jobs=[_job("2")],
                total=2,
                next_offset=2,
                complete=True,
                fingerprint="page-1",
            ),
        }
    )
    config = CareerConfig(data_dir=tmp_path / "career")
    service = ResumableCrawlerService(
        config,
        max_pages_per_batch=1,
    )

    first = service.run_batch(adapter)

    assert first["status"] == "running"
    assert first["has_more"] is True
    assert adapter.requested == [
        ({"location_code": "CT_11"}, 0)
    ]
    with connect(config.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM jobs"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT next_offset FROM crawl_cycle_shards"
        ).fetchone()[0] == 1

    adapter.initial_shards = lambda: (_ for _ in ()).throw(AssertionError("checkpoint must not depend on refetching metadata"))
    second = service.run_batch(adapter, continuation_only=True)

    assert second["status"] == "running"
    assert adapter.requested[-1] == (
        {"location_code": "CT_11"},
        1,
    )
    with connect(config.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM jobs"
        ).fetchone()[0] == 0

    third = service.run_batch(adapter, continuation_only=True)
    fourth = service.run_batch(adapter, continuation_only=True)

    assert third["status"] == "running"
    assert fourth["status"] == "committed"


def test_resumable_crawler_commits_only_complete_cycle(tmp_path):
    adapter = _Adapter(
        {
            0: ResumableListingPage(
                jobs=[_job("1")],
                total=1,
                next_offset=1,
                complete=True,
                fingerprint="page-0",
            )
        }
    )
    config = CareerConfig(data_dir=tmp_path / "career")
    service = ResumableCrawlerService(config)

    validation = service.run_batch(adapter)
    result = service.run_batch(adapter)

    assert validation["status"] == "running"
    assert result["status"] == "committed"
    assert result["transitions"] == {"created": 1}
    with connect(config.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM jobs"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT status FROM crawl_cycles"
        ).fetchone()[0] == "committed"


def test_resumable_crawler_degrades_a_still_capped_shard(tmp_path):
    adapter = _Adapter(
        {
            0: ResumableListingPage(
                jobs=[_job("1")],
                total=10_000,
                next_offset=1,
                complete=False,
                fingerprint="page-0",
            )
        }
    )
    service = ResumableCrawlerService(
        CareerConfig(data_dir=tmp_path / "career")
    )

    result = service.run_batch(adapter)

    assert result["status"] == "degraded"
    assert result["transitions"] == {}


def test_resumable_crawler_commits_catalog_and_cycle_in_one_session(
    tmp_path,
):
    adapter = _Adapter(
        {
            0: ResumableListingPage(
                jobs=[_job("1")],
                total=1,
                next_offset=1,
                complete=True,
                fingerprint="page-0",
            )
        }
    )
    config = CareerConfig(data_dir=tmp_path / "career")
    sessions = 0

    @contextmanager
    def repository_session():
        nonlocal sessions
        sessions += 1
        connection = connect(config.database_path)
        try:
            yield JobRepository(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    service = ResumableCrawlerService(
        config,
        repository_session=repository_session,
    )
    validation = service.run_batch(adapter)
    sessions_before_commit = sessions
    result = service.run_batch(adapter)

    assert validation["status"] == "running"
    assert result["status"] == "committed"
    assert sessions - sessions_before_commit == 2


def test_resumable_crawler_degrades_conflicting_job_snapshots(tmp_path):
    changed = _job("1")
    changed = JobSnapshot(
        **{
            **changed.__dict__,
            "description_raw": "同一岗位返回了冲突的 JD",
        }
    )
    adapter = _Adapter(
        {
            0: ResumableListingPage(
                jobs=[_job("1")],
                total=2,
                next_offset=1,
                complete=False,
                fingerprint="page-0",
            ),
            1: ResumableListingPage(
                jobs=[changed],
                total=2,
                next_offset=2,
                complete=True,
                fingerprint="page-1",
            ),
        }
    )
    config = CareerConfig(data_dir=tmp_path / "career")

    result = ResumableCrawlerService(config).run_batch(adapter)

    assert result["status"] == "degraded"
    assert result["has_more"] is False
    assert result["transitions"] == {}
    assert "conflicting snapshot" in result["error_summary"]
    with connect(config.database_path) as connection:
        assert connection.execute(
            "SELECT status FROM crawl_cycles"
        ).fetchone()[0] == "degraded"


def test_resumable_crawler_requires_stable_validation_pass(tmp_path):
    adapter = _Adapter(
        {
            0: ResumableListingPage(
                jobs=[_job("1")],
                total=1,
                next_offset=1,
                complete=True,
                fingerprint="page-0",
            )
        }
    )
    config = CareerConfig(data_dir=tmp_path / "career")
    service = ResumableCrawlerService(config)

    first = service.run_batch(adapter)
    second = service.run_batch(adapter)

    assert first["status"] == "running"
    assert first["has_more"] is True
    assert first["pass_number"] == 2
    assert second["status"] == "committed"
    assert adapter.requested == [
        ({"location_code": "CT_11"}, 0),
        ({"location_code": "CT_11"}, 0),
    ]


def test_resumable_crawler_degrades_after_three_drifting_passes(
    tmp_path,
):
    class DriftingAdapter(_Adapter):
        def __init__(self):
            super().__init__({})
            self.pass_jobs = [["1"], ["2"], ["2"]]

        def fetch_page(self, filters, offset):
            self.requested.append((filters, offset))
            job_ids = self.pass_jobs.pop(0)
            return ResumableListingPage(
                jobs=[_job(job_id) for job_id in job_ids],
                total=1,
                next_offset=1,
                complete=True,
                fingerprint=f"page-{job_ids[0]}",
            )

    adapter = DriftingAdapter()
    service = ResumableCrawlerService(
        CareerConfig(data_dir=tmp_path / "career")
    )

    first = service.run_batch(adapter)
    second = service.run_batch(adapter)
    third = service.run_batch(adapter)

    assert first["pass_number"] == 2
    assert second["pass_number"] == 3
    assert third["status"] == "degraded"
    assert "three passes" in third["error_summary"]
    assert third["transitions"] == {}


def test_resumable_crawler_reconciles_six_stale_jobs_from_details(
    tmp_path,
):
    stale_ids = [
        "active-1",
        "active-2",
        "off-1",
        "off-2",
        "off-3",
        "off-4",
    ]

    class TailAdapter(_Adapter):
        def __init__(self):
            super().__init__({})
            self.responses = [
                ResumableListingPage(
                    jobs=[_job(job_id) for job_id in [*stale_ids, "current"]],
                    total=7,
                    next_offset=7,
                    complete=True,
                    fingerprint="pass-1",
                ),
                ResumableListingPage(
                    jobs=[_job("current")],
                    total=1,
                    next_offset=1,
                    complete=True,
                    fingerprint="pass-2",
                ),
                ResumableListingPage(
                    jobs=[_job("current")],
                    total=1,
                    next_offset=1,
                    complete=True,
                    fingerprint="pass-3",
                ),
            ]
            self.verified = []

        def fetch_page(self, filters, offset):
            self.requested.append((filters, offset))
            return self.responses.pop(0)

        def verify_stale_jobs(self, snapshots):
            self.verified.append(
                [snapshot.external_job_id for snapshot in snapshots]
            )
            statuses = {
                "active-1": "active",
                "active-2": "active",
                "off-1": "offline",
                "off-2": "offline",
                "off-3": "offline",
                "off-4": "offline",
            }
            return {snapshot.external_job_id: statuses[snapshot.external_job_id] for snapshot in snapshots}

    adapter = TailAdapter()
    config = CareerConfig(data_dir=tmp_path / "career")
    service = ResumableCrawlerService(config)

    assert service.run_batch(adapter)["pass_number"] == 2
    assert service.run_batch(adapter)["pass_number"] == 3
    result = service.run_batch(adapter)

    assert result["status"] == "running" and result["tail_remaining"] == 1
    first = result["tail_verification"]
    result = service.run_batch(adapter)
    assert result["status"] == "committed"
    assert {key: first[key] + result["tail_verification"][key] for key in first} == {
        "active": 2,
        "offline": 4,
    }
    assert sorted(job_id for batch in adapter.verified for job_id in batch) == sorted(stale_ids)
    assert all(len(batch) <= 5 for batch in adapter.verified)
    with connect(config.database_path) as connection:
        rows = connection.execute(
            "SELECT external_job_id FROM jobs ORDER BY external_job_id"
        ).fetchall()
    assert [row[0] for row in rows] == [
        "active-1",
        "active-2",
        "current",
    ]


def test_resumable_crawler_degrades_unknown_stale_detail(tmp_path):
    class UnknownTailAdapter(_Adapter):
        def __init__(self):
            super().__init__({})
            self.responses = [
                ResumableListingPage(
                    jobs=[_job("stale"), _job("current")],
                    total=2,
                    next_offset=2,
                    complete=True,
                    fingerprint="pass-1",
                ),
                ResumableListingPage(
                    jobs=[_job("current")],
                    total=1,
                    next_offset=1,
                    complete=True,
                    fingerprint="pass-2",
                ),
                ResumableListingPage(
                    jobs=[_job("current")],
                    total=1,
                    next_offset=1,
                    complete=True,
                    fingerprint="pass-3",
                ),
            ]

        def fetch_page(self, filters, offset):
            return self.responses.pop(0)

        def verify_stale_jobs(self, snapshots):
            return {"stale": "unknown"}

    adapter = UnknownTailAdapter()
    config = CareerConfig(data_dir=tmp_path / "career")
    service = ResumableCrawlerService(config)

    service.run_batch(adapter)
    service.run_batch(adapter)
    result = service.run_batch(adapter)

    assert result["status"] == "degraded"
    assert result["transitions"] == {}
    with connect(config.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM jobs"
        ).fetchone()[0] == 0


def test_resumable_crawler_does_not_verify_large_stale_tail(tmp_path):
    stale_ids = [str(index) for index in range(41)]

    class LargeTailAdapter(_Adapter):
        def __init__(self):
            super().__init__({})
            self.responses = [
                ResumableListingPage(
                    jobs=[
                        _job(job_id)
                        for job_id in [*stale_ids, "current"]
                    ],
                    total=42,
                    next_offset=42,
                    complete=True,
                    fingerprint="pass-1",
                ),
                ResumableListingPage(
                    jobs=[_job("current")],
                    total=1,
                    next_offset=1,
                    complete=True,
                    fingerprint="pass-2",
                ),
                ResumableListingPage(
                    jobs=[_job("current")],
                    total=1,
                    next_offset=1,
                    complete=True,
                    fingerprint="pass-3",
                ),
            ]
            self.verify_calls = 0

        def fetch_page(self, filters, offset):
            return self.responses.pop(0)

        def verify_stale_jobs(self, snapshots):
            self.verify_calls += 1
            return {}

    adapter = LargeTailAdapter()
    service = ResumableCrawlerService(
        CareerConfig(data_dir=tmp_path / "career")
    )

    service.run_batch(adapter)
    service.run_batch(adapter)
    result = service.run_batch(adapter)

    assert result["status"] == "degraded"
    assert adapter.verify_calls == 0


def test_resumable_crawler_rebases_count_for_third_pass(tmp_path):
    class CountDriftingAdapter(_Adapter):
        def __init__(self):
            super().__init__({})
            self.totals = [1, 2, 2]

        def fetch_page(self, filters, offset):
            self.requested.append((filters, offset))
            total = self.totals.pop(0)
            return ResumableListingPage(
                jobs=[_job(str(index)) for index in range(1, total + 1)],
                total=total,
                next_offset=total,
                complete=True,
                fingerprint=f"page-{total}",
            )

    adapter = CountDriftingAdapter()
    service = ResumableCrawlerService(
        CareerConfig(data_dir=tmp_path / "career")
    )

    first = service.run_batch(adapter)
    second = service.run_batch(adapter)
    third = service.run_batch(adapter)

    assert first["pass_number"] == 2
    assert second["pass_number"] == 3
    assert third["status"] == "committed"


def test_resumable_crawler_allows_count_drift_during_complete_third_pass(
    tmp_path,
):
    class ThirdPassCountDriftAdapter(_Adapter):
        def __init__(self):
            super().__init__({})
            self.responses = [
                ResumableListingPage(
                    jobs=[_job("1")],
                    total=1,
                    next_offset=1,
                    complete=True,
                    fingerprint="pass-1",
                ),
                ResumableListingPage(
                    jobs=[_job("1"), _job("2")],
                    total=2,
                    next_offset=2,
                    complete=True,
                    fingerprint="pass-2",
                ),
                ResumableListingPage(
                    jobs=[_job("1")],
                    total=2,
                    next_offset=1,
                    complete=False,
                    fingerprint="pass-3-page-1",
                ),
                ResumableListingPage(
                    jobs=[_job("2"), _job("3")],
                    total=3,
                    next_offset=3,
                    complete=True,
                    fingerprint="pass-3-page-2",
                ),
            ]

        def fetch_page(self, filters, offset):
            self.requested.append((filters, offset))
            return self.responses.pop(0)

    adapter = ThirdPassCountDriftAdapter()
    service = ResumableCrawlerService(
        CareerConfig(data_dir=tmp_path / "career")
    )

    first = service.run_batch(adapter)
    second = service.run_batch(adapter)
    third = service.run_batch(adapter)

    assert first["pass_number"] == 2
    assert second["pass_number"] == 3
    assert third["status"] == "committed"
    assert third["observed_unique"] == 3


def test_resumable_crawler_allows_count_drift_in_first_pass(
    tmp_path,
):
    adapter = _Adapter(
        {
            0: ResumableListingPage(
                jobs=[_job("1")],
                total=2,
                next_offset=1,
                complete=False,
                fingerprint="page-0",
            ),
            1: ResumableListingPage(
                jobs=[_job("2"), _job("3")],
                total=3,
                next_offset=3,
                complete=True,
                fingerprint="page-1",
            ),
        }
    )

    result = ResumableCrawlerService(
        CareerConfig(data_dir=tmp_path / "career")
    ).run_batch(adapter)

    assert result["status"] == "running"
    assert result["pass_number"] == 2
    assert result["observed_unique"] == 3


def _recent_legacy_tail(tmp_path, monkeypatch):
    from extensions.career_mcp.services import resumable_crawler as module
    monkeypatch.setattr(module, 'utc_now_iso', lambda: '2026-08-20T01:00:00Z')
    class Adapter(_Adapter):
        def __init__(self):
            super().__init__({})
            self.responses = [ResumableListingPage(
                jobs=[_job(str(i)) for i in range(25)], total=25,
                next_offset=25, complete=True, fingerprint='first')]
            self.responses += [ResumableListingPage(jobs=[_job('24')], total=1,
                next_offset=1, complete=True, fingerprint=f'pass-{i}') for i in (2, 3)]
            self.details = []
        def fetch_page(self, filters, offset):
            return self.responses.pop(0)
        def verify_stale_jobs(self, snapshots):
            self.details.append(len(snapshots))
            return {snapshot.external_job_id: 'active' for snapshot in snapshots}
    adapter = Adapter()
    config = CareerConfig(tmp_path)
    legacy = ResumableCrawlerService(config)
    legacy.tail_limit = 20
    legacy.run_batch(adapter)
    legacy.run_batch(adapter)
    result = legacy.run_batch(adapter)
    assert result['status'] == 'degraded'
    return adapter, config, result['cycle_id']


def test_recent_legacy_tail_resumes_in_bounded_batches_without_publishing_partial(tmp_path, monkeypatch):
    adapter, config, cycle_id = _recent_legacy_tail(tmp_path, monkeypatch)
    service = ResumableCrawlerService(config)
    results = []
    for _ in range(5):
        result = service.run_batch(adapter, continuation_only=True)
        results.append(result)
        assert result['cycle_id'] == cycle_id
        if result['has_more']:
            with connect(config.database_path) as db:
                assert db.execute('SELECT count(*) FROM jobs').fetchone()[0] == 0
    assert results[-1]['status'] == 'committed'
    assert adapter.details == [5, 5, 5, 5, 4]
    assert [r['tail_remaining'] for r in results] == [19, 14, 9, 4, 0]


def test_archived_tail_and_other_validation_failures_are_not_reopened(tmp_path, monkeypatch):
    from extensions.career_mcp.services import resumable_crawler as module
    adapter, config, cycle_id = _recent_legacy_tail(tmp_path, monkeypatch)
    service = ResumableCrawlerService(config)
    monkeypatch.setattr(module, 'utc_now_iso', lambda: '2026-08-22T01:00:00Z')
    assert service.run_batch(adapter, continuation_only=True)['status'] == 'idle'
    monkeypatch.setattr(module, 'utc_now_iso', lambda: '2026-08-20T01:00:00Z')
    with connect(config.database_path) as db:
        db.execute('UPDATE crawl_cycles SET error_summary=? WHERE id=?',
                   ('ByteDance stale detail verification returned unknown results', cycle_id))
        db.commit()
    assert service.run_batch(adapter, continuation_only=True)['status'] == 'idle'
    assert adapter.details == []


def test_tail_transport_failure_preserves_running_cycle_for_retry(tmp_path):
    import pytest
    class Adapter(_Adapter):
        def __init__(self):
            super().__init__({})
            self.responses = [ResumableListingPage(jobs=[_job('old'), _job('current')],
                total=2, next_offset=2, complete=True, fingerprint='first')]
            self.responses += [ResumableListingPage(jobs=[_job('current')], total=1,
                next_offset=1, complete=True, fingerprint='next') for _ in range(3)]
            self.calls = 0
        def fetch_page(self, filters, offset): return self.responses.pop(0)
        def verify_stale_jobs(self, snapshots):
            self.calls += 1
            if self.calls == 1: raise TimeoutError('transport unavailable')
            return {snapshot.external_job_id: 'active' for snapshot in snapshots}
    adapter = Adapter()
    config = CareerConfig(tmp_path)
    service = ResumableCrawlerService(config)
    service.run_batch(adapter)
    second = service.run_batch(adapter)
    with pytest.raises(TimeoutError): service.run_batch(adapter)
    with connect(config.database_path) as db:
        assert db.execute('SELECT status FROM crawl_cycles').fetchone()[0] == 'running'
        assert db.execute('SELECT count(*) FROM jobs').fetchone()[0] == 0
    result = service.run_batch(adapter)
    assert result['status'] == 'committed' and result['cycle_id'] == second['cycle_id']
