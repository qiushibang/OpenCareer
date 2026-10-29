"""Public catalog distribution must not transfer user-owned state."""
from dataclasses import asdict
import gzip
import hashlib
import json

import pytest

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler.adapters import FakeAdapter
from extensions.career_mcp.domain.crawler import SourceDescriptor
from extensions.career_mcp.public_catalog_format import publish_stream
from extensions.career_mcp.services.public_catalog import PublicCatalogSync
from extensions.career_mcp.services.jobs import JobService
from extensions.career_mcp.services.job_tracking import JobTrackingService

DESCRIPTOR = SourceDescriptor("test-official", "测试官方招聘", "test", "测试公司", "all", "public-json", "https://careers.example.com")
NOW = "2026-10-29T00:00:00+00:00"


def job(job_id="one", **changes):
    return {"external_job_id": job_id, "title": "算法工程师", "description_raw": "负责模型训练与评测",
            "source_url": f"https://careers.example.com/job/{job_id}", "location_raw": "北京",
            "locations": ["北京"], "recruitment_type": "experienced", "status": "active",
            "first_seen_at": NOW, "observed_at": NOW, "last_changed_at": NOW,
            "responsibilities": [], "requirements": [], **changes}


def publish(root, jobs):
    records = [{"kind": "source", "descriptor": asdict(DESCRIPTOR), "last_success_at": NOW,
                "latest_status": "succeeded", "expected_count": len(jobs)}]
    records += [{"kind": "job", "job": value} for value in jobs]
    records += [{"kind": "end_source"}, {"kind": "end_feed"}]
    return publish_stream(iter(records), root)


def syncer(config, root):
    def fetch(url, max_bytes):
        relative = url.removeprefix("https://feed.example.com/")
        content = (root / relative).read_bytes()
        if len(content) > max_bytes:
            raise ValueError("too large")
        return content
    return PublicCatalogSync(config, base_url="https://feed.example.com/", fetch=fetch,
                             descriptors=[DESCRIPTOR])


def test_first_download_is_complete_idempotent_and_preserves_tracking(tmp_path):
    root, config = tmp_path / "feed", CareerConfig(tmp_path / "local")
    publish(root, [job(), job("two")])
    sync = syncer(config, root)
    assert sync.run()["completed"] == 1
    rows = JobService(config).search_jobs()["jobs"]
    assert len(rows) == 2
    job_id = rows[0]["id"]
    JobTrackingService(config).update(job_id, {"expected_version": 0, "is_favorite": True, "note": "私有申请备注"})
    assert sync.run()["unchanged"] == 1
    assert JobTrackingService(config).get(job_id)["note"] == "私有申请备注"
    assert JobService(config).search_jobs()["total"] == 2
    assert "私有申请备注" not in (root / "manifest.json").read_text()


def test_updated_and_offline_jobs_follow_server_without_deleting_local_notes(tmp_path):
    root, config = tmp_path / "feed", CareerConfig(tmp_path / "local")
    publish(root, [job()])
    sync = syncer(config, root)
    sync.run()
    job_id = JobService(config).search_jobs()["jobs"][0]["id"]
    JobTrackingService(config).update(job_id, {"expected_version": 0, "is_favorite": True})
    later = "2026-10-30T00:00:00+00:00"
    publish(root, [job(title="高级算法工程师", status="inactive", observed_at=later, last_changed_at=later)])
    sync.run()
    assert JobService(config).search_jobs(statuses=["active"])["total"] == 0
    result = JobService(config).search_jobs(statuses=["inactive"])["jobs"][0]
    assert result["id"] == job_id and result["title"] == "高级算法工程师"
    assert JobTrackingService(config).get(job_id)["is_favorite"] is True


def test_corrupt_snapshot_never_changes_local_catalog(tmp_path):
    root, config = tmp_path / "feed", CareerConfig(tmp_path / "local")
    manifest = publish(root, [job()])
    path = root / manifest["sources"][0]["path"]
    path.write_bytes(b"corrupt")
    result = syncer(config, root).run()
    assert result["failed"] == 1
    assert JobService(config).search_jobs()["total"] == 0


def test_half_publish_preserves_previous_manifest(tmp_path):
    root = tmp_path / "feed"
    publish(root, [job()])
    previous = (root / "manifest.json").read_bytes()
    records = [{"kind": "source", "descriptor": asdict(DESCRIPTOR), "last_success_at": NOW,
                "latest_status": "succeeded", "expected_count": 2}, {"kind": "job", "job": job()}]
    with pytest.raises(ValueError):
        publish_stream(iter(records), root)
    assert (root / "manifest.json").read_bytes() == previous


def test_private_or_unknown_fields_are_not_published(tmp_path):
    with pytest.raises(ValueError):
        publish(tmp_path / "feed", [job(note="private", visibility_user_id="someone")])


def test_manifest_cannot_redirect_download_outside_fixed_origin(tmp_path):
    root, config = tmp_path / "feed", CareerConfig(tmp_path / "local")
    manifest = publish(root, [job()])
    manifest["sources"][0]["path"] = "https://evil.example/collect"
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        syncer(config, root).run()


def test_duplicate_job_ids_are_rejected_before_import(tmp_path):
    with pytest.raises(ValueError):
        publish(tmp_path / "feed", [job(), job()])


def test_hash_valid_but_invalid_rows_never_partially_replace_a_source(tmp_path):
    root, config = tmp_path / "feed", CareerConfig(tmp_path / "local")
    publish(root, [job()])
    sync = syncer(config, root)
    sync.run()
    manifest = publish(root, [job(title="修改后的标题"), job("two")])
    entry = manifest["sources"][0]
    payload = {"schema_version": 1, "source_slug": DESCRIPTOR.source_slug,
               "jobs": [job(title="不应写入"), job("two", title="")]}
    data = gzip.compress(json.dumps(payload).encode())
    checksum = hashlib.sha256(data).hexdigest()
    entry.update({"sha256": checksum, "size": len(data), "path": f"sources/{DESCRIPTOR.source_slug}/{checksum}.json.gz"})
    (root / entry["path"]).write_bytes(data)
    (root / "manifest.json").write_text(json.dumps(manifest))
    assert sync.run()["failed"] == 1
    result = JobService(config).search_jobs()
    assert result["total"] == 1 and result["jobs"][0]["title"] == "算法工程师"


def test_an_empty_recreated_database_does_not_trust_an_old_cache(tmp_path):
    root, config = tmp_path / "feed", CareerConfig(tmp_path / "local")
    publish(root, [job()])
    sync = syncer(config, root)
    sync.run()
    config.database_path.unlink()
    assert JobService(config).search_jobs()["total"] == 0
    sync.run()
    assert JobService(config).search_jobs()["total"] == 1


def test_export_enforces_public_and_crawler_filters_and_never_boots_storage():
    from extensions.career_mcp.public_catalog_export import PUBLIC_ONLY, stream_public_catalog
    queries = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql, args): queries.append(sql)
        def fetchmany(self, size):
            if getattr(self, "done", False): return []
            self.done = True
            return [tuple(job()[k] for k in ("external_job_id", "title", "description_raw", "source_url", "location_raw", "locations", "recruitment_type", "status", "first_seen_at", "observed_at", "last_changed_at", "responsibilities", "requirements"))]
    class Connection:
        def execute(self, sql, args): queries.append(sql); return self
        def fetchall(self): return [("source-id", *asdict(DESCRIPTOR).values(), 1, NOW, "succeeded")]
        def cursor(self, **kwargs): return Cursor()
    records = list(stream_public_catalog(Connection(), [DESCRIPTOR.source_slug]))
    assert records[-1] == {"kind": "end_feed"}
    assert all(PUBLIC_ONLY in query for query in queries)
    assert "visibility_user_id IS NULL" in PUBLIC_ONLY and "source_type = 'crawler'" in PUBLIC_ONLY
    assert all("SELECT *" not in query for query in queries)
    assert not {"user_id", "visibility_user_id", "note", "resume", "api_key"} & records[1]["job"].keys()


def test_initial_sync_does_not_call_historical_jobs_new_or_sources_uncrawled(tmp_path):
    from datetime import datetime, timezone
    from extensions.career_mcp.services.crawler import CrawlerService
    root, config = tmp_path / "feed", CareerConfig(tmp_path / "local")
    publish(root, [job(first_seen_at="2026-10-01T00:00:00+00:00")])
    syncer(config, root).run()
    crawler = CrawlerService(config, adapters=[FakeAdapter(DESCRIPTOR.source_slug, [], descriptor=DESCRIPTOR)],
                             clock=lambda: datetime(2026, 10, 29, 1, tzinfo=timezone.utc))
    digest = crawler.get_job_radar_digest()
    assert digest["events"]["by_type"].get("created", 0) == 0
    assert digest["sources"]["healthy"] == 1 and digest["sources"]["pending"] == 0
    source = crawler.list_sources()["sources"][0]
    assert source["data_origin"] == "shared" and source["upstream_last_success_at"] == NOW


@pytest.mark.parametrize("change", [{"latest_status": ["succeeded"]}, {"active_count": 99}, {"last_success_at": "invalid"}])
def test_invalid_remote_source_health_metadata_is_rejected(tmp_path, change):
    root, config = tmp_path / "feed", CareerConfig(tmp_path / "local")
    manifest = publish(root, [job()])
    manifest["sources"][0].update(change)
    (root / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        syncer(config, root).run()


def test_new_official_feed_sources_do_not_require_downloading_adapter_code(tmp_path):
    root, config = tmp_path / "feed", CareerConfig(tmp_path / "local")
    descriptor = asdict(DESCRIPTOR)
    descriptor.update(source_slug="new-official-source", company_slug="new-company", company_name="新公司")
    publish_stream(iter([{"kind": "source", "descriptor": descriptor, "expected_count": 1,
                         "last_success_at": NOW, "latest_status": "succeeded"},
                        {"kind": "job", "job": job()}, {"kind": "end_source"}, {"kind": "end_feed"}]), root)
    sync = syncer(config, root)
    assert sync.run()["completed"] == 1
    assert JobService(config).search_jobs()["jobs"][0]["company"]["slug"] == "new-company"
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["sources"][0]["descriptor"]["scope_key"] = "different-scope"
    (root / "manifest.json").write_text(json.dumps(manifest))
    # Identity must remain protected after an application restart, even when the
    # older client has no built-in adapter for this new source.
    with pytest.raises(ValueError):
        syncer(config, root).run()


@pytest.mark.parametrize("first_seen,expected_new", [("2026-10-28T12:00:00+08:00", 0), ("2026-10-28T20:00:00+08:00", 1)])
def test_server_timezone_does_not_shift_the_daily_new_job_window(tmp_path, first_seen, expected_new):
    from datetime import datetime, timezone
    from extensions.career_mcp.services.crawler import CrawlerService
    root, config = tmp_path / "feed", CareerConfig(tmp_path / "local")
    publish(root, [job(first_seen_at=first_seen)])
    syncer(config, root).run()
    crawler = CrawlerService(config, adapters=[FakeAdapter(DESCRIPTOR.source_slug, [], descriptor=DESCRIPTOR)],
                             clock=lambda: datetime(2026, 10, 29, 10, tzinfo=timezone.utc))
    assert crawler.get_job_radar_digest()["events"]["by_type"].get("created", 0) == expected_new
    assert JobService(config).search_jobs()["jobs"][0]["first_seen_at"].endswith("Z")
