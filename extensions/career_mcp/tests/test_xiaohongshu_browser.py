import asyncio
import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler import xiaohongshu
from extensions.career_mcp.crawler.adapters import default_adapters
from extensions.career_mcp.crawler.xiaohongshu import (
    XiaohongshuDataError,
    XiaohongshuSocialAdapter,
    fetch_xiaohongshu_pages,
    parse_xiaohongshu_page,
)
from extensions.career_mcp.services.crawler import CrawlerService

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "xiaohongshu-social"
OBSERVED_AT = "2026-08-06T00:00:00Z"


def _json(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_parse_page_maps_complete_jobs():
    page = parse_xiaohongshu_page(
        _json("listing_page_1.json"),
        observed_at=OBSERVED_AT,
    )

    assert page.total == 2
    assert [job.external_job_id for job in page.jobs] == ["21594", "20380"]
    assert page.jobs[0].location_raw == "上海市，北京市"
    assert "岗位职责：" in page.jobs[0].description_raw
    assert "岗位要求：" in page.jobs[0].description_raw
    assert "职类：内容运营" in page.jobs[0].description_raw


def test_parse_page_rejects_missing_qualification():
    payload = _json("listing_page_1.json")
    payload["data"]["list"][0]["qualification"] = ""

    with pytest.raises(XiaohongshuDataError, match="qualification"):
        parse_xiaohongshu_page(payload, observed_at=OBSERVED_AT)


def test_adapter_accepts_bounded_union_for_live_ordering_drift():
    first = _json("listing_page_1.json")
    second = _json("listing_page_1.json")
    first["data"]["total"] = 3
    second["data"]["total"] = 3
    second["data"]["list"][0] = dict(second["data"]["list"][1])
    second["data"]["list"][1] = dict(second["data"]["list"][1])
    second["data"]["list"][1]["positionId"] = 30000
    second["data"]["list"][1]["positionName"] = "Recovered job"

    adapter = XiaohongshuSocialAdapter(
        fetch_pages=lambda: [first, second],
        clock=lambda: OBSERVED_AT,
    )

    assert len(adapter.fetch_jobs()) == 3


def test_adapter_rejects_incomplete_union():
    payload = _json("listing_page_1.json")
    payload["data"]["total"] = 3
    adapter = XiaohongshuSocialAdapter(fetch_pages=lambda: [payload])

    with pytest.raises(XiaohongshuDataError, match="count"):
        adapter.fetch_jobs()


def test_adapter_allows_recovery_on_fourth_bounded_pass():
    first = _json("listing_page_1.json")
    first["data"]["total"] = 3
    recovered = _json("listing_page_1.json")
    recovered["data"]["total"] = 3
    recovered["data"]["list"][1]["positionId"] = 30000
    recovered["data"]["list"][1]["positionName"] = "Recovered job"
    adapter = XiaohongshuSocialAdapter(
        fetch_pages=lambda: [first, first, first, recovered],
        clock=lambda: OBSERVED_AT,
    )

    assert len(adapter.fetch_jobs()) == 3


def test_public_fetch_runs_playwright_off_asyncio_thread(monkeypatch):
    caller_thread = threading.get_ident()
    worker_threads: list[int] = []

    def fake_sync_fetch():
        worker_threads.append(threading.get_ident())
        return [_json("listing_page_1.json")]

    monkeypatch.setattr(
        xiaohongshu,
        "_fetch_xiaohongshu_pages_sync",
        fake_sync_fetch,
    )

    async def call():
        return fetch_xiaohongshu_pages()

    pages = asyncio.run(call())

    assert pages[0]["success"] is True
    assert worker_threads and worker_threads[0] != caller_thread


def test_fixture_adapter_creates_jobs_through_pipeline(tmp_path):
    adapter = XiaohongshuSocialAdapter(
        fetch_pages=lambda: [_json("listing_page_1.json")],
        clock=lambda: OBSERVED_AT,
    )
    service = CrawlerService(
        CareerConfig(data_dir=tmp_path / "career"),
        adapters=[adapter],
    )

    assert service.crawl_registered_source(adapter.source_slug).transitions == {
        "created": 2
    }


def test_default_registry_includes_live_accepted_xiaohongshu():
    assert "xiaohongshu-social-cn" in {
        adapter.source_slug for adapter in default_adapters()
    }


def test_browser_pagination_ignores_duplicate_previous_page_response(monkeypatch):
    """Official UI emitted requests 1, 1, 2; only request 2 is the next page."""
    from types import SimpleNamespace
    first, second = _json('listing_page_1.json'), _json('listing_page_1.json')
    first['data'].update(totalPage=2, list=first['data']['list'][:1])
    second['data'].update(totalPage=2, pageNum=2, list=second['data']['list'][1:])
    def response(payload):
        return SimpleNamespace(url='https://job.xiaohongshu.com'+xiaohongshu.TARGET_PATH,
            status=200, request=SimpleNamespace(method='POST', post_data_json={'pageNum':payload['data']['pageNum']}),
            json=lambda:payload)
    calls,closed=[],[]
    class ResponseContext:
        def __init__(self,value):self.value=value
        def __enter__(self):return self
        def __exit__(self,*args):pass
    class Page:
        def set_default_timeout(self,*args):pass
        def route(self,*args):pass
        def goto(self,*args,**kw):pass
        url=xiaohongshu.ENTRY_URL
        def locator(self,*args):return SimpleNamespace(click=lambda:None)
        def expect_response(self,matcher,**kw):
            candidates=[response(first)] if not calls else [response(first),response(second)]
            calls.append(True)
            return ResponseContext(next(r for r in candidates if matcher(r)))
    browser=SimpleNamespace(new_context=lambda:SimpleNamespace(new_page=lambda:Page()),close=lambda:closed.append(True))
    class Context:
        def __enter__(self):return SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kw:browser))
        def __exit__(self,*args):pass
    monkeypatch.setitem(sys.modules,'playwright.sync_api',SimpleNamespace(
        sync_playwright=Context,Error=RuntimeError,TimeoutError=TimeoutError))
    pages=xiaohongshu._fetch_xiaohongshu_pages_sync()
    assert [p['data']['pageNum'] for p in pages]==[1,2]
    assert len(XiaohongshuSocialAdapter(fetch_pages=lambda:pages).fetch_jobs())==2
    assert closed==[True]
