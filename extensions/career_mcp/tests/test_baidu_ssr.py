import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.crawler.baidu import (
    AccessRestricted,
    BaiduSsrHtmlAdapter,
    BaiduSsrParseError,
    extract_initial_data,
    parse_baidu_social_html,
)
from extensions.career_mcp.crawler.adapters import default_adapters
from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.services.crawler import CrawlerService

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "baidu-careers"


def test_extract_initial_data_handles_braces_inside_json_strings():
    html = (
        '<script>window.__INITIAL_DATA__ = '
        '{"listData":{"listDetailData":[{"jobId":"job-1","name":"Role {A}"}]}};</script>'
    )

    state = extract_initial_data(html)

    assert state["listData"]["listDetailData"][0]["jobId"] == "job-1"


def test_extract_initial_data_rejects_missing_assignment():
    with pytest.raises(BaiduSsrParseError, match="INITIAL_DATA"):
        extract_initial_data("<html><body>no state</body></html>")


def test_parse_baidu_fixture_uses_metadata_job_ids():
    metadata = json.loads((FIXTURE_DIR / "metadata.json").read_text(encoding="utf-8"))
    html = (FIXTURE_DIR / "social_page.html").read_text(encoding="utf-8")

    jobs = parse_baidu_social_html(html, metadata["source_url"])

    assert [job.external_job_id for job in jobs][:2] == metadata["expected_job_ids"]
    assert all(job.title and job.description_raw and job.source_url for job in jobs)
    assert all(job.location_raw for job in jobs)


def test_parse_baidu_social_html_rejects_duplicate_job_ids():
    html = (
        '<script>window.__INITIAL_DATA__ = {"listData":{"listDetailData":['
        '{"jobId":"same","name":"A","workPlace":"北京"},'
        '{"jobId":"same","name":"B","workPlace":"上海"}]}};</script>'
    )

    with pytest.raises(BaiduSsrParseError, match="duplicate jobId"):
        parse_baidu_social_html(html, "https://talent.baidu.com/jobs/social")


def test_adapter_uses_injected_public_html_fetcher():
    html = (
        '<script>window.__INITIAL_DATA__ = {"listData":{"listDetailData":['
        '{"jobId":"job-1","name":"测试职位","workPlace":"北京","projectType":"社会招聘"}'
        "]}};</script>"
    )
    adapter = BaiduSsrHtmlAdapter(fetch_html=lambda _: html)

    jobs = adapter.fetch_jobs()

    assert adapter.source_slug == "baidu-careers"
    assert jobs[0].external_job_id == "job-1"
    assert jobs[0].recruitment_type == "experienced"


def test_adapter_propagates_access_restriction():
    def restricted(_: str) -> str:
        raise AccessRestricted("HTTP 403")

    with pytest.raises(AccessRestricted, match="HTTP 403"):
        BaiduSsrHtmlAdapter(fetch_html=restricted).fetch_jobs()


def test_default_registry_keeps_baidu_disabled_after_unconfirmed_live_smoke():
    slugs = {adapter.source_slug for adapter in default_adapters()}

    assert "baidu-careers" not in slugs
    assert {"bytedance-seed-campus", "deepseek-careers", "xiaomi-careers"} <= slugs


def test_fixture_adapter_drives_created_job_through_pipeline(tmp_path):
    html = (
        '<script>window.__INITIAL_DATA__ = {"listData":{"listDetailData":['
        '{"jobId":"job-1","name":"测试职位","workPlace":"北京","projectType":"社会招聘"}'
        "]}};</script>"
    )
    adapter = BaiduSsrHtmlAdapter(fetch_html=lambda _: html)
    service = CrawlerService(
        CareerConfig(data_dir=tmp_path / "career"),
        adapters=[adapter],
    )

    result = service.crawl_registered_source("baidu-careers")

    assert result.transitions == {"created": 1}
