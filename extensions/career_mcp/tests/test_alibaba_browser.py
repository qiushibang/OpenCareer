import asyncio
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler import alibaba
from extensions.career_mcp.crawler.adapters import default_adapters
from extensions.career_mcp.crawler.alibaba import (
    ALIBABA_TONGYI_SCOPE,
    AlibabaCareersAdapter,
    AlibabaDataError,
    fetch_alibaba_pages,
    parse_alibaba_page,
)
from extensions.career_mcp.services.crawler import CrawlerService

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "alibaba-tongyi"
OBSERVED_AT = "2026-08-06T00:00:00Z"


def _json(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_parse_page_maps_complete_jobs():
    page = parse_alibaba_page(
        _json("listing_page_1.json"),
        scope=ALIBABA_TONGYI_SCOPE,
        observed_at=OBSERVED_AT,
    )

    assert page.total == 2
    assert [job.external_job_id for job in page.jobs] == [
        "100030500001",
        "100030500002",
    ]
    assert page.jobs[0].location_raw == "北京、杭州"
    assert "岗位职责：" in page.jobs[0].description_raw
    assert "岗位要求：" in page.jobs[0].description_raw
    assert "职类：技术类-算法" in page.jobs[0].description_raw


def test_parse_page_rejects_missing_requirement():
    payload = _json("listing_page_1.json")
    payload["content"]["datas"][0]["requirement"] = ""

    with pytest.raises(AlibabaDataError, match="requirement"):
        parse_alibaba_page(
            payload,
            scope=ALIBABA_TONGYI_SCOPE,
            observed_at=OBSERVED_AT,
        )


def test_adapter_requires_complete_unique_count():
    payload = _json("listing_page_1.json")
    payload["content"]["totalCount"] = 3
    adapter = AlibabaCareersAdapter(
        ALIBABA_TONGYI_SCOPE,
        fetch_pages=lambda _: [payload],
    )

    with pytest.raises(AlibabaDataError, match="count"):
        adapter.fetch_jobs()


def test_public_fetch_runs_playwright_off_asyncio_thread(monkeypatch):
    caller_thread = threading.get_ident()
    worker_threads: list[int] = []

    def fake_sync_fetch(scope):
        worker_threads.append(threading.get_ident())
        assert scope is ALIBABA_TONGYI_SCOPE
        return [_json("listing_page_1.json")]

    monkeypatch.setattr(alibaba, "_fetch_alibaba_pages_sync", fake_sync_fetch)

    async def call():
        return fetch_alibaba_pages(ALIBABA_TONGYI_SCOPE)

    pages = asyncio.run(call())

    assert pages[0]["success"] is True
    assert worker_threads and worker_threads[0] != caller_thread


def test_fixture_adapter_creates_jobs_through_pipeline(tmp_path):
    adapter = AlibabaCareersAdapter(
        ALIBABA_TONGYI_SCOPE,
        fetch_pages=lambda _: [_json("listing_page_1.json")],
        clock=lambda: OBSERVED_AT,
    )
    service = CrawlerService(
        CareerConfig(data_dir=tmp_path / "career"),
        adapters=[adapter],
    )

    assert service.crawl_registered_source(adapter.source_slug).transitions == {
        "created": 2
    }


def test_default_registry_includes_live_accepted_tongyi():
    assert ALIBABA_TONGYI_SCOPE.source_slug in {
        adapter.source_slug for adapter in default_adapters()
    }
