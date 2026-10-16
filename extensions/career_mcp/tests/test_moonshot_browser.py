import asyncio
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler import moonshot
from extensions.career_mcp.crawler.adapters import default_adapters
from extensions.career_mcp.crawler.moonshot import (
    MoonshotDataError,
    MoonshotSocialAdapter,
    fetch_moonshot_dataset,
    parse_moonshot_card,
)
from extensions.career_mcp.services.crawler import CrawlerService

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "moonshot-social"
OBSERVED_AT = "2026-08-06T00:00:00Z"


def _json(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _raw_job(index: int) -> dict:
    return {
        "href": f"#/job/00000000-0000-4000-8000-{index:012d}",
        "title": f"Job {index}",
        "published_at": "发布于 2026-08-06",
        "metadata": ["全职", "技术类", "北京市"],
        "description": f"岗位职责\nBuild system {index}.\n\n岗位要求\nTest system {index}.",
    }


def _page(page: int, page_count: int, jobs: list[dict]) -> dict:
    return {
        "page": page,
        "page_count": page_count,
        "page_size": 30,
        "jobs": jobs,
    }


def test_parse_card_maps_complete_job():
    raw = _json("page_1.json")["jobs"][0]

    job = parse_moonshot_card(raw, observed_at=OBSERVED_AT)

    assert job.external_job_id == "33f1df2b-19b3-4f60-ac30-6c64c75f42ed"
    assert job.title == "KIMI产品设计师"
    assert job.source_url.endswith(
        "#/job/33f1df2b-19b3-4f60-ac30-6c64c75f42ed"
    )
    assert job.location_raw == "上海市 北京市"
    assert job.recruitment_type == "experienced"
    assert "职类：设计类" in job.description_raw
    assert "【我们希望你】" in job.description_raw


def test_parse_card_preserves_missing_location():
    raw = _json("page_1.json")["jobs"][1]

    job = parse_moonshot_card(raw, observed_at=OBSERVED_AT)

    assert job.location_raw is None
    assert "职类：市场类" in job.description_raw


def test_parse_card_rejects_invalid_uuid():
    raw = _raw_job(1)
    raw["href"] = "#/job/not-a-uuid"

    with pytest.raises(MoonshotDataError, match="UUID"):
        parse_moonshot_card(raw, observed_at=OBSERVED_AT)


def test_adapter_validates_complete_pagination():
    pages = [
        _page(1, 3, [_raw_job(index) for index in range(1, 31)]),
        _page(2, 3, [_raw_job(index) for index in range(31, 61)]),
        _page(3, 3, [_raw_job(61)]),
    ]
    adapter = MoonshotSocialAdapter(
        fetch_dataset=lambda: pages,
        clock=lambda: OBSERVED_AT,
    )

    jobs = adapter.fetch_jobs()

    assert len(jobs) == 61
    assert len({job.external_job_id for job in jobs}) == 61


def test_adapter_rejects_short_non_final_page():
    pages = [
        _page(1, 2, [_raw_job(1)]),
        _page(2, 2, [_raw_job(2)]),
    ]
    adapter = MoonshotSocialAdapter(fetch_dataset=lambda: pages)

    with pytest.raises(MoonshotDataError, match="non-final"):
        adapter.fetch_jobs()


def test_adapter_rejects_duplicate_uuid():
    page = _json("page_1.json")
    page["jobs"][1]["href"] = page["jobs"][0]["href"]
    adapter = MoonshotSocialAdapter(fetch_dataset=lambda: [page])

    with pytest.raises(MoonshotDataError, match="duplicate"):
        adapter.fetch_jobs()


def test_public_fetch_runs_playwright_off_asyncio_thread(monkeypatch):
    caller_thread = threading.get_ident()
    worker_threads: list[int] = []

    def fake_sync_fetch():
        worker_threads.append(threading.get_ident())
        return [_json("page_1.json")]

    monkeypatch.setattr(moonshot, "_fetch_moonshot_dataset_sync", fake_sync_fetch)

    async def call():
        return fetch_moonshot_dataset()

    pages = asyncio.run(call())

    assert pages[0]["page"] == 1
    assert worker_threads and worker_threads[0] != caller_thread


def test_fixture_adapter_creates_jobs_through_pipeline(tmp_path):
    adapter = MoonshotSocialAdapter(
        fetch_dataset=lambda: [_json("page_1.json")],
        clock=lambda: OBSERVED_AT,
    )
    service = CrawlerService(
        CareerConfig(data_dir=tmp_path / "career"),
        adapters=[adapter],
    )

    created = service.crawl_registered_source(adapter.source_slug)
    unchanged = service.crawl_registered_source(adapter.source_slug)

    assert created.transitions == {"created": 2}
    assert unchanged.transitions == {"unchanged": 2}


def test_default_registry_includes_live_accepted_moonshot():
    assert "moonshot-social" in {
        adapter.source_slug for adapter in default_adapters()
    }
