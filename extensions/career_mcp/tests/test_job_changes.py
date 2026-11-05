from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler.adapters import FakeAdapter
from extensions.career_mcp.database.migrations import connect
from extensions.career_mcp.domain.crawler import JobSnapshot
from extensions.career_mcp.services.crawler import CrawlerService


def test_complete_baselines_changes_gaps_and_reopening(tmp_path):
    config = CareerConfig(tmp_path / "career")
    crawler = CrawlerService(config)
    def crawl(day, items):
        rows = [JobSnapshot(key, title, "职责：产品设计", f"https://example.com/{key}",
                            f"2026-10-{day:02d}T01:00:00Z", "北京", "experienced") for key, title in items]
        return crawler.crawl(FakeAdapter("fixture", rows))
    crawl(20, [("1", "产品经理")])
    crawl(21, [("1", "AI产品经理"), ("2", "策略产品经理")])
    crawl(21, [("1", "AI产品经理"), ("2", "策略产品经理")])
    crawl(28, [("1", "AI产品经理"), ("2", "策略产品经理"), ("3", "增长产品经理")])
    with connect(config.database_path) as db:
        changes = [tuple(r) for r in db.execute("SELECT j.external_job_id,c.kind FROM job_catalog_changes c JOIN jobs j ON j.id=c.job_id ORDER BY c.rowid")]
        assert changes == [("1", "backfill"), ("1", "updated"), ("2", "new"), ("3", "backfill")]
        db.execute("UPDATE jobs SET status='inactive' WHERE external_job_id='2'")
    crawl(29, [("1", "AI产品经理"), ("2", "策略产品经理"), ("3", "增长产品经理")])
    with connect(config.database_path) as db:
        assert db.execute("SELECT kind FROM job_catalog_changes ORDER BY rowid DESC LIMIT 1").fetchone()[0] == "reopened"


def test_first_download_is_not_today_new(tmp_path):
    from datetime import datetime, timezone
    from extensions.career_mcp.services.job_catalog import JobCatalog
    config = CareerConfig(tmp_path / "career")
    CrawlerService(config).crawl(FakeAdapter("fixture", [JobSnapshot("1", "产品经理", "职责：产品设计", "https://example.com/1", "2026-10-29T01:00:00Z", "北京", "experienced")]))
    catalog = JobCatalog(config)
    catalog.clock = lambda: datetime(2026, 10, 29, 2, tzinfo=timezone.utc)
    assert catalog.search(today=True)["total"] == 0
    assert catalog.search()["jobs"][0]["change_kind"] == "backfill"
    summary = CrawlerService(config, clock=lambda: datetime(2026,10,29,2,tzinfo=timezone.utc)).get_job_radar_digest()
    assert summary["events"]["by_type"] == {"backfill": 1}
    assert summary["events"]["samples"][0]["event_type"] == "backfill"
    import json
    (config.data_dir / "local-job-sync.json").write_text(json.dumps({"mode":"local", "sources":[{"slug":"fixture", "name":"测试来源", "status":"running"}]}))
    assert CrawlerService(config).get_job_radar_digest()["sources"]["configured"] == 1
