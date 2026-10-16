import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.crawler.didi import (
    DidiSocialAdapter,
    parse_didi_detail,
    parse_didi_listing,
)
from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler.adapters import default_adapters
from extensions.career_mcp.services.crawler import CrawlerService

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "didi-social"
OBSERVED_AT = "2026-08-06T00:00:00Z"


def _json(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_parse_listing_maps_stable_ids():
    page = parse_didi_listing(_json("listing_page_1.json"))

    assert page.total == 2
    assert page.page == 1
    assert page.size == 16
    assert [post.jd_id for post in page.posts] == ["65596", "65580"]


def test_parse_detail_maps_complete_jd():
    job = parse_didi_detail(
        _json("detail_1.json"),
        expected_jd_id="65596",
        expected_jd_no="JR20260804017",
        observed_at=OBSERVED_AT,
    )

    assert job.external_job_id == "65596"
    assert job.source_url == "https://talent.didiglobal.com/social/p/65596"
    assert job.location_raw == "北京市"
    assert "岗位职责：" in job.description_raw
    assert "岗位要求：" in job.description_raw


def test_adapter_fetches_pages_and_details_serially():
    details = {"65596": _json("detail_1.json"), "65580": _json("detail_2.json")}
    requested = []
    adapter = DidiSocialAdapter(
        fetch_listing=lambda page: requested.append(page)
        or _json("listing_page_1.json"),
        fetch_detail=lambda jd_id: requested.append(jd_id) or details[jd_id],
        clock=lambda: OBSERVED_AT,
    )

    jobs = adapter.fetch_jobs()

    assert requested == [1, "65596", "65580"]
    assert [job.external_job_id for job in jobs] == ["65596", "65580"]
    assert adapter.descriptor.company_slug == "didi"


def test_fixture_adapter_creates_jobs_through_pipeline(tmp_path):
    details = {"65596": _json("detail_1.json"), "65580": _json("detail_2.json")}
    adapter = DidiSocialAdapter(
        fetch_listing=lambda _: _json("listing_page_1.json"),
        fetch_detail=lambda jd_id: details[jd_id],
        clock=lambda: OBSERVED_AT,
    )
    service = CrawlerService(
        CareerConfig(data_dir=tmp_path / "career"),
        adapters=[adapter],
    )

    assert service.crawl_registered_source(adapter.source_slug).transitions == {
        "created": 2
    }


def test_default_registry_includes_live_accepted_didi():
    assert "didi-social-cn" in {
        adapter.source_slug for adapter in default_adapters()
    }
