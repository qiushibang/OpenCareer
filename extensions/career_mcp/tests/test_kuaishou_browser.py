import json
import asyncio
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.crawler import kuaishou
from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler.adapters import default_adapters
from extensions.career_mcp.crawler.kuaishou import (
    KuaishouBrowserAdapter,
    KuaishouDataError,
    fetch_kuaishou_dataset,
    parse_kuaishou_dictionary,
    parse_kuaishou_page,
)
from extensions.career_mcp.services.crawler import CrawlerService

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "kuaishou-social"
OBSERVED_AT = "2026-08-06T00:00:00Z"


def _json(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_parse_dictionary_maps_domestic_codes():
    dictionary = parse_kuaishou_dictionary(_json("dictionary.json"))

    assert dictionary.locations["Beijing"] == "北京"
    assert dictionary.categories["J0012"] == "工程类"
    assert dictionary.experiences["5"] == "3-5年"


def test_parse_page_maps_complete_jobs():
    dictionary = parse_kuaishou_dictionary(_json("dictionary.json"))
    page = parse_kuaishou_page(
        _json("listing_page_1.json"),
        dictionary=dictionary,
        observed_at=OBSERVED_AT,
    )

    assert page.total == 2
    assert [job.external_job_id for job in page.jobs] == ["31947", "29268"]
    assert page.jobs[0].location_raw == "北京"
    assert page.jobs[1].location_raw == "北京、上海、深圳、杭州"
    assert page.jobs[0].recruitment_type == "experienced"
    assert "岗位职责：" in page.jobs[0].description_raw
    assert "岗位要求：" in page.jobs[0].description_raw
    assert "职类：工程类" in page.jobs[0].description_raw
    assert "工作经验：1-3年" in page.jobs[0].description_raw


def test_parse_page_rejects_unknown_location_code():
    payload = _json("listing_page_1.json")
    payload["result"]["list"][0]["workLocationsCode"] = ["Unknown"]

    with pytest.raises(KuaishouDataError, match="location"):
        parse_kuaishou_page(
            payload,
            dictionary=parse_kuaishou_dictionary(_json("dictionary.json")),
            observed_at=OBSERVED_AT,
        )


def test_parse_page_rejects_missing_requirement():
    payload = _json("listing_page_1.json")
    payload["result"]["list"][0]["positionDemand"] = ""

    with pytest.raises(KuaishouDataError, match="positionDemand"):
        parse_kuaishou_page(
            payload,
            dictionary=parse_kuaishou_dictionary(_json("dictionary.json")),
            observed_at=OBSERVED_AT,
        )


def test_parse_page_accepts_official_social_outsourcing_subproject():
    payload = _json("listing_page_1.json")
    payload["result"]["list"][0]["recruitProjectCode"] = "epiboly"

    page = parse_kuaishou_page(
        payload,
        dictionary=parse_kuaishou_dictionary(_json("dictionary.json")),
        observed_at=OBSERVED_AT,
    )

    assert page.jobs[0].external_job_id == "31947"


def test_dataset_adapter_maps_complete_fixture():
    adapter = KuaishouBrowserAdapter(
        fetch_dataset=lambda: (
            _json("dictionary.json"),
            [_json("listing_page_1.json")],
        ),
        clock=lambda: OBSERVED_AT,
    )

    jobs = adapter.fetch_jobs()

    assert [job.external_job_id for job in jobs] == ["31947", "29268"]
    assert adapter.descriptor.company_slug == "kuaishou"
    assert adapter.descriptor.scope_key == "social-domestic"


def test_public_fetch_runs_playwright_off_asyncio_thread(monkeypatch):
    caller_thread = threading.get_ident()
    worker_threads: list[int] = []

    def fake_sync_fetch():
        worker_threads.append(threading.get_ident())
        return _json("dictionary.json"), [_json("listing_page_1.json")]

    monkeypatch.setattr(kuaishou, "_fetch_kuaishou_dataset_sync", fake_sync_fetch)

    async def call():
        return fetch_kuaishou_dataset()

    dictionary, pages = asyncio.run(call())

    assert dictionary["code"] == 0
    assert pages[0]["code"] == 0
    assert worker_threads and worker_threads[0] != caller_thread


def test_dataset_adapter_accepts_bounded_pass_union_when_pagination_drifts():
    first = _json("listing_page_1.json")
    second = _json("listing_page_1.json")
    first["result"]["total"] = 3
    second["result"]["total"] = 3
    first["result"]["list"] = first["result"]["list"][:2]
    second["result"]["list"][0] = dict(second["result"]["list"][1])
    second["result"]["list"][1] = dict(second["result"]["list"][1])
    second["result"]["list"][1]["id"] = 30000
    second["result"]["list"][1]["name"] = "Recovered job"

    adapter = KuaishouBrowserAdapter(
        fetch_dataset=lambda: (
            _json("dictionary.json"),
            [first, second, second, second],
        ),
        clock=lambda: OBSERVED_AT,
    )

    jobs = adapter.fetch_jobs()

    assert {job.external_job_id for job in jobs} == {
        "31947",
        "29268",
        "30000",
    }


def test_browser_crawl_deadline_allows_slow_server_pagination():
    kuaishou._require_crawl_time_remaining(100.0, current=379.9)

    with pytest.raises(RuntimeError, match="exceeded 280 seconds"):
        kuaishou._require_crawl_time_remaining(100.0, current=380.1)


def test_fixture_adapter_creates_jobs_through_existing_pipeline(tmp_path):
    adapter = KuaishouBrowserAdapter(
        fetch_dataset=lambda: (
            _json("dictionary.json"),
            [_json("listing_page_1.json")],
        ),
        clock=lambda: OBSERVED_AT,
    )
    config = CareerConfig(data_dir=tmp_path / "career")
    service = CrawlerService(config, adapters=[adapter])

    created = service.crawl_registered_source(adapter.source_slug)
    unchanged = service.crawl_registered_source(adapter.source_slug)

    assert created.transitions == {"created": 2}
    assert unchanged.transitions == {"unchanged": 2}


def test_default_registry_includes_live_accepted_kuaishou():
    assert "kuaishou-social-cn" in {
        adapter.source_slug for adapter in default_adapters()
    }
