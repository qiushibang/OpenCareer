"""Opt-in, anonymous real shared-feed acceptance; no model calls or server writes."""
import json
import os

import pytest


@pytest.mark.skipif(os.environ.get("OPENCAR_TEST_PUBLIC_CATALOG_LIVE") != "1",
                    reason="opt-in public catalog live download")
def test_new_local_database_matches_the_real_public_snapshot(tmp_path):
    from extensions.career_mcp.config import CareerConfig
    from extensions.career_mcp.services.jobs import JobService
    from extensions.career_mcp.services.job_tracking import JobTrackingService
    from extensions.career_mcp.services.public_catalog import PublicCatalogSync, download
    requests = []
    manifests = []
    def fetch(url, max_bytes):
        body = download(url, max_bytes)
        requests.append(url)
        if url.endswith("manifest.json"):
            manifests.append(json.loads(body))
        return body
    config = CareerConfig(tmp_path / "career")
    sync = PublicCatalogSync(config, fetch=fetch)
    result = sync.run()
    assert result["failed"] == 0 and result["completed"] == len(manifests[0]["sources"])
    jobs = JobService(config)
    assert jobs.search_jobs()["total"] == manifests[0]["job_count"]
    assert jobs.search_jobs(statuses=["active"])["total"] == manifests[0]["active_count"]
    job_id = jobs.search_jobs(statuses=["active"])["jobs"][0]["id"]
    tracker = JobTrackingService(config)
    tracker.update(job_id, {"expected_version": 0, "is_favorite": True, "note": "隔离验收备注，不应上传"})
    before = {entry["descriptor"]["source_slug"]: entry["sha256"] for entry in manifests[0]["sources"]}
    requests.clear()
    repeated = sync.run()
    changed = [entry for entry in manifests[-1]["sources"] if before.get(entry["descriptor"]["source_slug"]) != entry["sha256"]]
    assert repeated["failed"] == 0
    assert repeated["unchanged"] == len(manifests[-1]["sources"]) - len(changed)
    assert len(requests) == 1 + len(changed) and requests[0].endswith("manifest.json")
    assert tracker.get(job_id)["note"] == "隔离验收备注，不应上传"
