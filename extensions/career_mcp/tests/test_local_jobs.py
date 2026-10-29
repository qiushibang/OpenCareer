"""Local distribution sync reuses the real catalog services, without network."""
from pathlib import Path
import pytest

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler.adapters import FakeAdapter
from extensions.career_mcp.domain.crawler import JobSnapshot
from extensions.career_mcp.services.jobs import JobService
from extensions.career_mcp.services.job_tracking import JobTrackingService
from extensions.career_mcp.local_jobs import LocalJobSync, read_status, request_refresh


def snapshot(job_id: str = "one") -> JobSnapshot:
    return JobSnapshot(
        external_job_id=job_id, title="本地算法工程师",
        source_url=f"https://careers.example.com/jobs/{job_id}",
        location_raw="北京",
        description_raw="训练模型，熟悉 Python", observed_at="2026-10-28T00:00:00Z",
    )


class Broken(FakeAdapter):
    def fetch_jobs(self):
        raise RuntimeError("untrusted response with secret query")


def test_first_sync_partial_failure_and_fresh_restart(tmp_path):
    config = CareerConfig(tmp_path)
    good = FakeAdapter("good", [snapshot()])
    broken = Broken("broken", [])
    sync = LocalJobSync(config, adapters=[good, broken], resumable_adapters=[], pause=0)
    result = sync.run_cycle()
    assert result["state"] == "partial"
    assert result["completed"] == 1 and result["failed"] == 1
    assert "secret query" not in str(read_status(config))
    jobs = JobService(config).search_jobs()
    assert jobs["total"] == 1
    job_id = jobs["jobs"][0]["id"]
    # Fresh successful sources must not contact the website again on restart.
    restarted = LocalJobSync(config, adapters=[Broken("good", [])], resumable_adapters=[], pause=0)
    assert restarted.run_cycle()["sources"][0]["status"] == "succeeded"
    assert JobService(config).search_jobs()["jobs"][0]["id"] == job_id


def test_refresh_is_coalesced_and_forces_a_new_successful_fetch(tmp_path):
    config = CareerConfig(tmp_path)
    sync = LocalJobSync(config, adapters=[FakeAdapter("good", [snapshot()])], resumable_adapters=[], pause=0)
    sync.run_cycle()
    job_id = JobService(config).search_jobs()["jobs"][0]["id"]
    tracking = JobTrackingService(config)
    tracking.update(job_id, {"expected_version": 0, "is_favorite": True, "application_status": "applied", "note": "保留我的申请记录"})
    assert request_refresh(config) is True
    assert request_refresh(config) is False
    updated = LocalJobSync(config, adapters=[FakeAdapter("good", [snapshot(), snapshot("two")])], resumable_adapters=[], pause=0)
    updated.run_cycle(force=True)
    assert JobService(config).search_jobs()["total"] == 2
    saved = tracking.get(job_id)
    assert saved["is_favorite"] is True and saved["application_status"] == "applied"
    assert saved["note"] == "保留我的申请记录"


def test_resumable_source_repeats_batches_until_commit(tmp_path):
    adapter = FakeAdapter("resumable", [])
    calls = []
    sync = LocalJobSync(CareerConfig(tmp_path), adapters=[], resumable_adapters=[adapter], pause=0)
    def batch(_adapter):
        calls.append(True)
        return {"status": "running" if len(calls) == 1 else "committed", "has_more": len(calls) == 1}
    sync.resumable.run_batch = batch
    sync._publish_resumable = lambda _adapter, _result: True
    result = sync.run_cycle()
    assert len(calls) == 2
    assert result["state"] == "completed" and result["completed"] == 1


def test_interruption_preserves_source_checkpoint_and_retries_next_time(tmp_path):
    sync = LocalJobSync(CareerConfig(tmp_path), adapters=[FakeAdapter("good", [snapshot()])], resumable_adapters=[], pause=0)
    def interrupted(_adapter):
        raise KeyboardInterrupt
    sync.crawler.crawl = interrupted
    import pytest
    with pytest.raises(KeyboardInterrupt):
        sync.run_cycle()
    assert read_status(sync.config)["sources"][0]["status"] == "running"
    restarted = LocalJobSync(sync.config, adapters=[FakeAdapter("good", [snapshot()])], resumable_adapters=[], pause=0)
    assert restarted.run_cycle()["completed"] == 1


def test_real_sqlite_resumable_catalog_is_committed_and_searchable(tmp_path):
    from extensions.career_mcp.crawler.bytedance import ResumableListingPage
    class Pages(FakeAdapter):
        def initial_shards(self):
            return [{"shard_key": "beijing", "filters": {}}]
        def fetch_page(self, filters, offset):
            return ResumableListingPage(jobs=[snapshot()], total=1, next_offset=1, complete=True, fingerprint="page")
    config = CareerConfig(tmp_path)
    sync = LocalJobSync(config, adapters=[], resumable_adapters=[Pages("resumable", [])], pause=0)
    result = sync.run_cycle()
    assert result["completed"] == 1
    assert JobService(config).search_jobs()["total"] == 1


def test_slow_resumable_fetch_does_not_lock_user_favorites(tmp_path):
    from extensions.career_mcp.crawler.bytedance import ResumableListingPage
    config = CareerConfig(tmp_path)
    LocalJobSync(config, adapters=[FakeAdapter("existing", [snapshot("existing")])], resumable_adapters=[], pause=0).run_cycle()
    job_id = JobService(config).search_jobs()["jobs"][0]["id"]
    saved = []
    class Pages(FakeAdapter):
        def initial_shards(self):
            return [{"shard_key": "beijing", "filters": {}}]
        def fetch_page(self, filters, offset):
            if not saved:
                saved.append(JobTrackingService(config).update(job_id, {"expected_version": 0, "is_favorite": True}))
            return ResumableListingPage(jobs=[snapshot()], total=1, next_offset=1, complete=True, fingerprint="page")
    sync = LocalJobSync(config, adapters=[], resumable_adapters=[Pages("full", [])], pause=0)
    assert sync.run_cycle()["completed"] == 1
    assert saved[0]["is_favorite"] is True
    assert JobService(config).search_jobs()["total"] == 2


def test_worker_lock_prevents_duplicate_crawls_and_releases_after_exit(tmp_path):
    from extensions.career_mcp.local_jobs import worker_lock
    import pytest
    path = tmp_path / "worker.lock"
    with worker_lock(path):
        with pytest.raises(OSError):
            with worker_lock(path):
                pass
    with worker_lock(path):
        pass


def test_default_local_registry_keeps_all_official_and_full_mainland_sources(tmp_path):
    from extensions.career_mcp.crawler.adapters import default_adapters, default_resumable_adapters
    sync = LocalJobSync(CareerConfig(tmp_path))
    expected = {a.source_slug for a in [*default_adapters(), *default_resumable_adapters()]}
    actual = {a.source_slug for a in [*sync.adapters, *sync.resumable_adapters]}
    assert actual == expected
    assert {"bytedance-mainland-social", "bytedance-mainland-campus", "deepseek-careers", "xiaomi-careers"} <= actual


@pytest.mark.parametrize("mode,delay", [("shared", 86400), ("local", 43200)])
def test_worker_automatically_repeats_at_the_configured_interval(tmp_path, monkeypatch, mode, delay):
    import sys
    from extensions.career_mcp import local_jobs
    from extensions.career_mcp.services import public_catalog
    monkeypatch.setenv("OPENCAR_LOCAL_MODE", "1")
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENCAR_LOCAL_JOB_SOURCE", mode)
    monkeypatch.setattr(sys, "argv", ["local_jobs"])
    clock = [0]
    calls = []
    class Worker:
        def __init__(self, *args, **kwargs): pass
        def run(self):
            calls.append(clock[0])
            if len(calls) == 2:
                raise KeyboardInterrupt
            return {"failed": 0}
        def run_cycle(self, **kwargs): return self.run()
    monkeypatch.setattr(local_jobs, "LocalJobSync", Worker)
    monkeypatch.setattr(public_catalog, "PublicCatalogSync", Worker)
    monkeypatch.setattr(local_jobs.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(local_jobs.time, "sleep", lambda _seconds: clock.__setitem__(0, clock[0] + delay))
    assert local_jobs.main() == 0
    assert calls == [0, delay]


def test_shared_feed_failure_preserves_data_and_retries_after_fifteen_minutes(tmp_path, monkeypatch):
    import sys
    from extensions.career_mcp import local_jobs
    from extensions.career_mcp.services import public_catalog
    marker = tmp_path / "career.sqlite3"
    marker.write_bytes(b"existing test data")
    monkeypatch.setenv("OPENCAR_LOCAL_MODE", "1")
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENCAR_LOCAL_JOB_SOURCE", "shared")
    monkeypatch.setattr(sys, "argv", ["local_jobs"])
    clock, calls = [0], []
    class Offline:
        def __init__(self, *args, **kwargs): pass
        def run(self):
            calls.append(clock[0])
            if len(calls) == 2: raise KeyboardInterrupt
            raise OSError("untrusted network error")
    monkeypatch.setattr(public_catalog, "PublicCatalogSync", Offline)
    monkeypatch.setattr(local_jobs.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(local_jobs.time, "sleep", lambda _seconds: clock.__setitem__(0, clock[0] + 900))
    assert local_jobs.main() == 0
    assert calls == [0, 900]
    assert marker.read_bytes() == b"existing test data"
    assert read_status(CareerConfig(tmp_path))["error_code"] == "FEED_UNAVAILABLE"
