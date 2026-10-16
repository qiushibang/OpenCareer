import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp import server
from extensions.career_mcp.crawler.adapters import (
    default_adapters,
    default_resumable_adapters,
)
from extensions.career_mcp.domain.crawler import CrawlResult


def test_production_adapters_expose_canonical_company_metadata():
    descriptors = {
        adapter.source_slug: adapter.descriptor for adapter in default_adapters()
    }

    assert descriptors["xiaomi-careers"].company_slug == "xiaomi"
    assert descriptors["xiaomi-careers"].company_name == "小米"
    assert descriptors["deepseek-careers"].company_slug == "deepseek"
    assert descriptors["deepseek-careers"].company_name == "DeepSeek"
    assert descriptors["bytedance-seed-campus"].company_slug == "bytedance"
    assert descriptors["bytedance-seed-campus"].company_name == "字节跳动"
    assert descriptors["bytedance-seed-campus"].scope_key == (
        "project:7621018151002507573"
    )


def test_list_sources_exposes_all_enabled_production_adapters(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))

    result = server.list_sources()

    assert result["ok"] is True
    sources = {
        source["slug"]: source for source in result["data"]["sources"]
    }
    assert set(sources) == {
        adapter.source_slug
        for adapter in [
            *default_adapters(),
            *default_resumable_adapters(),
        ]
    }
    assert sources["bytedance-seed-campus"]["name"] == (
        "字节跳动 2027 Seed 大模型人才校招"
    )
    assert sources["deepseek-careers"]["name"] == "DeepSeek 官方招聘"
    assert sources["tencent-cdg-experienced"]["name"] == "腾讯 CDG 社会招聘"
    assert sources["tencent-ieg-game-product-experienced"]["name"] == (
        "腾讯 IEG 游戏产品社会招聘"
    )
    assert sources["xiaomi-careers"]["name"] == "小米官方招聘"
    assert sources["bytedance-mainland-social"]["name"] == (
        "字节跳动中国大陆社招"
    )
    assert sources["bytedance-mainland-campus"]["name"] == (
        "字节跳动中国大陆校招"
    )
    assert all(source["configured"] is True for source in sources.values())


def test_list_recent_job_events_validates_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))

    result = server.list_recent_job_events(limit=0)

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_get_job_radar_digest_returns_read_only_summary(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))

    result = server.get_job_radar_digest()

    assert result["ok"] is True
    assert result["data"]["window"]["hours"] == 24
    assert result["data"]["events"]["total"] == 0
    assert result["data"]["sources"]["configured"] == len(
        default_adapters()
    )
    assert result["data"]["sources"]["pending"] == len(default_adapters())


def test_get_job_radar_digest_validates_window(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))

    result = server.get_job_radar_digest(hours=0)

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_INPUT"


def test_crawl_source_is_registered_and_rejects_unknown_sources(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))

    result = server.crawl_source(source_slug="unknown-source", dry_run=True)

    assert result["ok"] is False
    assert result["error"]["code"] == "SOURCE_NOT_FOUND"


def test_crawl_source_returns_explicit_error_for_failed_run(monkeypatch):
    class FailingService:
        def crawl_registered_source(self, source_slug, *, dry_run):
            return CrawlResult(
                source_slug,
                "dry-run",
                "failed",
                {},
                error_summary="upstream contract changed",
            )

    monkeypatch.setattr(server, "_crawler_service", lambda: FailingService())

    result = server.crawl_source("broken-source", dry_run=True)

    assert result["ok"] is False
    assert result["error"] == {
        "code": "CRAWL_FAILED",
        "message": "upstream contract changed",
        "retryable": True,
    }


def test_crawl_source_routes_resumable_bytedance_scope(monkeypatch):
    adapter = object()
    calls = []

    class Service:
        def run_batch(self, selected):
            calls.append(selected)
            return {
                "source_slug": "bytedance-mainland-social",
                "cycle_id": "cycle-1",
                "status": "running",
                "processed_pages": 20,
                "observed_unique": 180,
                "has_more": True,
            }

    monkeypatch.setattr(
        server,
        "_resumable_adapters",
        lambda: {"bytedance-mainland-social": adapter},
    )
    monkeypatch.setattr(
        server,
        "_resumable_crawler_service",
        lambda: Service(),
    )

    result = server.crawl_source(
        "bytedance-mainland-social",
        dry_run=False,
    )

    assert result["ok"] is True
    assert result["data"]["cycle_id"] == "cycle-1"
    assert calls == [adapter]


def test_crawl_all_sources_returns_one_cursor_bounded_result(
    tmp_path,
    monkeypatch,
):
    from extensions.career_mcp.config import CareerConfig
    from extensions.career_mcp.crawler.adapters import FakeAdapter
    from extensions.career_mcp.domain.crawler import JobSnapshot
    from extensions.career_mcp.services.crawler import CrawlerService

    snapshot = JobSnapshot(
        external_job_id="1",
        title="Engineer",
        description_raw="Build systems",
        source_url="https://jobs.example/1",
        observed_at="2026-08-06T00:00:00Z",
    )
    service = CrawlerService(
        CareerConfig(data_dir=tmp_path / "career"),
        adapters=[
            FakeAdapter("b-source", [snapshot]),
            FakeAdapter("a-source", [snapshot]),
        ],
    )
    monkeypatch.setattr(server, "_crawler_service", lambda: service)
    monkeypatch.setattr(server, "_resumable_adapters", lambda: {})

    first = server.crawl_all_sources(dry_run=True)
    second = server.crawl_all_sources(
        dry_run=True,
        cursor=first["data"]["next_cursor"],
    )

    assert first["ok"] is True
    assert first["data"]["results"][0]["source_slug"] == "a-source"
    assert first["data"]["has_more"] is True
    assert first["data"]["next_cursor"] == "a-source"
    assert second["data"]["results"][0]["source_slug"] == "b-source"
    assert second["data"]["has_more"] is False
    assert second["data"]["next_cursor"] is None


def test_crawl_all_sources_keeps_cursor_on_running_resumable_source(
    monkeypatch,
):
    adapter = object()
    calls = []

    class RegularService:
        class Adapters:
            @staticmethod
            def source_slugs():
                return ["z-regular"]

        adapters = Adapters()

    class ResumableService:
        def run_batch(self, selected):
            calls.append(selected)
            return {
                "source_slug": "a-resumable",
                "cycle_id": "cycle-1",
                "status": "running",
                "processed_pages": 20,
                "observed_unique": 200,
                "has_more": True,
                "transitions": {},
            }

    monkeypatch.setattr(
        server,
        "_crawler_service",
        lambda: RegularService(),
    )
    monkeypatch.setattr(
        server,
        "_resumable_adapters",
        lambda: {"a-resumable": adapter},
    )
    monkeypatch.setattr(
        server,
        "_resumable_crawler_service",
        lambda: ResumableService(),
    )

    first = server.crawl_all_sources(dry_run=False)
    second = server.crawl_all_sources(
        dry_run=False,
        cursor=first["data"]["next_cursor"],
    )

    assert first["data"]["results"][0]["source_slug"] == "a-resumable"
    assert first["data"]["has_more"] is True
    assert first["data"]["next_cursor"] is None
    assert second["data"]["results"][0]["source_slug"] == "a-resumable"
    assert calls == [adapter, adapter]
