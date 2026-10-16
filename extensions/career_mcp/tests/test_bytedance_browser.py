import json
import asyncio
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.crawler import bytedance
from extensions.career_mcp.crawler.bytedance import (
    BYTEDANCE_FRONTIER_PROJECT,
    BYTEDANCE_MAINLAND_CAMPUS,
    BYTEDANCE_MAINLAND_SOCIAL,
    BYTEDANCE_SEED_PROJECT,
    ByteDanceApiError,
    ByteDanceCampusProjectAdapter,
    ByteDanceMainlandAdapter,
    ByteDanceSeedCampusAdapter,
    build_project_page_url,
    classify_bytedance_detail_text,
    parse_bytedance_filter_metadata,
    parse_bytedance_listing,
    parse_bytedance_scope_listing,
)
from extensions.career_mcp.crawler.adapters import (
    default_adapters,
    default_resumable_adapters,
)
from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.services.crawler import CrawlerService

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bytedance-seed-campus"
FRONTIER_FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "bytedance-frontier-campus"
    / "listing_page_1.json"
)
OBSERVED_AT = "2026-08-05T00:00:00Z"


def _payload() -> dict:
    return json.loads((FIXTURE_DIR / "listing_page_1.json").read_text())


def test_parse_fixture_maps_seed_jobs_with_complete_jd():
    metadata = json.loads((FIXTURE_DIR / "metadata.json").read_text())

    page = parse_bytedance_listing(_payload(), observed_at=OBSERVED_AT)

    assert [job.external_job_id for job in page.jobs] == metadata["expected_job_ids"]
    assert page.total == 2
    assert page.jobs[0].source_url.endswith(
        "/campus/position/7622492806745753909/detail"
    )
    assert page.jobs[0].location_raw == "北京"
    assert page.jobs[0].recruitment_type == "campus"
    assert "职位描述：" in page.jobs[0].description_raw
    assert "职位要求：" in page.jobs[0].description_raw
    assert "职位 ID：A90938A" in page.jobs[0].description_raw


def test_parse_rejects_wrong_project():
    payload = _payload()
    payload["data"]["job_post_list"][0]["job_subject"]["id"] = "wrong"

    with pytest.raises(ByteDanceApiError, match="project"):
        parse_bytedance_listing(payload, observed_at=OBSERVED_AT)


def test_parse_rejects_duplicate_ids():
    payload = _payload()
    jobs = payload["data"]["job_post_list"]
    jobs[1]["id"] = jobs[0]["id"]

    with pytest.raises(ByteDanceApiError, match="duplicate"):
        parse_bytedance_listing(payload, observed_at=OBSERVED_AT)


def _page(total: int, job_ids: list[str]) -> dict:
    payload = _payload()
    template = payload["data"]["job_post_list"][0]
    payload["data"]["job_post_list"] = [
        {**template, "id": job_id} for job_id in job_ids
    ]
    payload["data"]["count"] = total
    return payload


def test_adapter_fetches_pages_serially_with_one_timestamp():
    requested: list[int] = []
    expected_ids = [str(1000 + index) for index in range(1, 12)]
    pages = {
        1: _page(11, expected_ids[:10]),
        2: _page(11, expected_ids[10:]),
    }

    adapter = ByteDanceSeedCampusAdapter(
        fetch_page=lambda page_num: requested.append(page_num) or pages[page_num],
        clock=lambda: OBSERVED_AT,
    )

    jobs = adapter.fetch_jobs()

    assert requested == [1, 2]
    assert [job.external_job_id for job in jobs] == expected_ids
    assert {job.observed_at for job in jobs} == {OBSERVED_AT}


def test_adapter_rejects_total_change():
    pages = {
        1: _page(11, [str(1000 + index) for index in range(1, 11)]),
        2: _page(12, ["1011"]),
    }
    adapter = ByteDanceSeedCampusAdapter(
        fetch_page=lambda page_num: pages[page_num],
        clock=lambda: OBSERVED_AT,
    )

    with pytest.raises(ByteDanceApiError, match="total changed"):
        adapter.fetch_jobs()


def test_build_project_page_url_uses_exact_public_filter():
    assert build_project_page_url(3) == (
        "https://jobs.bytedance.com/campus/position"
        "?keywords=&category=&location=&project=7621018151002507573"
        "&type=&job_hot_flag=&current=3&limit=10&functionCategory=&tag="
    )


def test_project_response_matcher_waits_for_successful_post():
    url = (
        "https://jobs.bytedance.com/api/v1/search/job/posts"
        "?portal_type=3&subject_id_list=7621018151002507573"
        "&limit=10&offset=0&_signature=official"
    )

    assert not bytedance._project_response_matches(
        SimpleNamespace(
            url=url,
            status=405,
            request=SimpleNamespace(method="POST"),
        ),
        BYTEDANCE_SEED_PROJECT,
        0,
    )
    assert not bytedance._project_response_matches(
        SimpleNamespace(
            url=url,
            status=200,
            request=SimpleNamespace(method="GET"),
        ),
        BYTEDANCE_SEED_PROJECT,
        0,
    )
    assert bytedance._project_response_matches(
        SimpleNamespace(
            url=url,
            status=200,
            request=SimpleNamespace(method="POST"),
        ),
        BYTEDANCE_SEED_PROJECT,
        0,
    )


def test_default_adapter_uses_public_page_fetcher(monkeypatch):
    requested: list[int] = []
    monkeypatch.setattr(
        bytedance,
        "fetch_public_page",
        lambda page_num: requested.append(page_num) or _payload(),
    )

    jobs = ByteDanceSeedCampusAdapter(clock=lambda: OBSERVED_AT).fetch_jobs()

    assert requested == [1]
    assert len(jobs) == 2


def test_default_registry_includes_bytedance_seed():
    assert {
        "bytedance-seed-campus",
        "bytedance-campus-frontier-2027",
    } <= {
        adapter.source_slug for adapter in default_adapters()
    }
    assert {
        "bytedance-mainland-social",
        "bytedance-mainland-campus",
    } == {
        adapter.source_slug
        for adapter in default_resumable_adapters()
    }


def test_mainland_scopes_use_verified_public_portals():
    assert BYTEDANCE_MAINLAND_SOCIAL.portal_type == "2"
    assert BYTEDANCE_MAINLAND_SOCIAL.recruitment_type == "experienced"
    assert BYTEDANCE_MAINLAND_CAMPUS.portal_type == "3"
    assert BYTEDANCE_MAINLAND_CAMPUS.recruitment_type == "campus"


def test_filter_metadata_builds_only_mainland_city_shards():
    payload = {
        "code": 0,
        "data": {
            "city_list": [
                {"code": "CT_11", "name": "北京"},
                {"code": "CT_125", "name": "上海"},
                {"code": "CT_163", "name": "新加坡"},
                {"code": "CT_159", "name": "中国香港"},
            ],
            "job_type_list": [
                {"id": "6704215862603155720", "name": "研发"}
            ],
        },
    }

    metadata = parse_bytedance_filter_metadata(payload)

    assert metadata["mainland_cities"] == [
        {"code": "CT_11", "name": "北京"},
        {"code": "CT_125", "name": "上海"},
    ]
    assert metadata["categories"] == [
        {"id": "6704215862603155720", "name": "研发"}
    ]


def test_scope_parser_maps_social_job_without_project_constraint():
    page = parse_bytedance_scope_listing(
        _payload(),
        observed_at=OBSERVED_AT,
        scope=BYTEDANCE_MAINLAND_SOCIAL,
        allowed_city_names={"北京", "深圳"},
    )

    assert page.total == 2
    assert page.jobs[0].recruitment_type == "experienced"
    assert "/experienced/position/" in page.jobs[0].source_url


def test_mainland_adapter_creates_one_shard_per_public_city():
    adapter = ByteDanceMainlandAdapter(
        BYTEDANCE_MAINLAND_SOCIAL,
        fetch_filters=lambda _scope: {
            "code": 0,
            "data": {
                "city_list": [
                    {"code": "CT_11", "name": "北京"},
                    {"code": "CT_163", "name": "新加坡"},
                ],
                "job_type_list": [],
            },
        },
        fetch_page=lambda *_args: _payload(),
    )

    assert adapter.initial_shards() == [
        {
            "shard_key": "location:CT_11",
            "filters": {
                "location_code": "CT_11",
                "location_name": "北京",
                "category_id": None,
            },
        }
    ]


def test_mainland_adapter_prefers_non_overlapping_category_shards():
    adapter = ByteDanceMainlandAdapter(
        BYTEDANCE_MAINLAND_SOCIAL,
        fetch_filters=lambda _scope: {
            "code": 0,
            "data": {
                "city_list": [
                    {"code": "CT_11", "name": "北京"},
                ],
                "job_type_list": [
                    {"id": "category-rd", "name": "研发"},
                    {"id": "category-product", "name": "产品"},
                ],
            },
        },
        fetch_page=lambda *_args: _payload(),
    )

    assert adapter.initial_shards() == [
        {
            "shard_key": "category:category-rd",
            "filters": {
                "location_code": None,
                "location_name": None,
                "category_id": "category-rd",
            },
        },
        {
            "shard_key": "category:category-product",
            "filters": {
                "location_code": None,
                "location_name": None,
                "category_id": "category-product",
            },
        },
    ]


def test_mainland_adapter_parses_one_browser_batch():
    adapter = ByteDanceMainlandAdapter(
        BYTEDANCE_MAINLAND_SOCIAL,
        fetch_filters=lambda _scope: {
            "code": 0,
            "data": {
                "city_list": [{"code": "CT_11", "name": "北京"}],
                "job_type_list": [],
            },
        },
        fetch_page=lambda *_args: _payload(),
        fetch_pages=lambda _scope, _filters, _offset, _limit: [
            _payload()
        ],
        clock=lambda: OBSERVED_AT,
    )

    pages = adapter.fetch_pages(
        {
            "location_code": "CT_11",
            "location_name": "北京",
            "category_id": None,
        },
        0,
        20,
    )

    assert len(pages) == 1
    assert pages[0].complete is True
    assert pages[0].next_offset == 10


def test_bytedance_detail_text_classifies_only_explicit_states():
    assert classify_bytedance_detail_text(
        "该职位已下线\n查看工作机会"
    ) == "offline"
    assert classify_bytedance_detail_text(
        "AI 工程师\n职位描述\n负责模型训练\n职位要求\n本科以上"
    ) == "active"
    assert classify_bytedance_detail_text("登录\n请稍后重试") == "unknown"


def test_mainland_adapter_delegates_stale_detail_verification():
    calls = []
    job = parse_bytedance_scope_listing(
        _payload(),
        observed_at=OBSERVED_AT,
        scope=BYTEDANCE_MAINLAND_SOCIAL,
        allowed_city_names={"北京"},
    ).jobs[0]

    def verify_details(scope, snapshots):
        calls.append((scope, snapshots))
        return {snapshots[0].external_job_id: "active"}

    adapter = ByteDanceMainlandAdapter(
        BYTEDANCE_MAINLAND_SOCIAL,
        fetch_filters=lambda _scope: {"code": 0, "data": {}},
        fetch_page=lambda *_args: _payload(),
        verify_details=verify_details,
    )

    result = adapter.verify_stale_jobs([job])

    assert result == {job.external_job_id: "active"}
    assert calls == [(BYTEDANCE_MAINLAND_SOCIAL, [job])]


def test_mainland_response_matcher_requires_exact_public_filter():
    url = (
        "https://jobs.bytedance.com/api/v1/search/job/posts"
        "?keyword=&limit=10&offset=20"
        "&job_category_id_list=category-1"
        "&location_code_list=CT_11"
        "&subject_id_list=&recruitment_id_list="
        "&portal_type=2&job_function_id_list="
        "&storefront_id_list=&portal_entrance=1"
        "&_signature=official"
    )
    response = SimpleNamespace(
        url=url,
        status=200,
        request=SimpleNamespace(method="POST"),
    )
    filters = {
        "location_code": "CT_11",
        "location_name": "北京",
        "category_id": "category-1",
    }

    assert bytedance._mainland_response_matches(
        response,
        BYTEDANCE_MAINLAND_SOCIAL,
        filters,
        20,
    )
    assert not bytedance._mainland_response_matches(
        response,
        BYTEDANCE_MAINLAND_CAMPUS,
        filters,
        20,
    )


def test_frontier_project_adapter_uses_project_descriptor():
    payload = json.loads(FRONTIER_FIXTURE.read_text())
    adapter = ByteDanceCampusProjectAdapter(
        BYTEDANCE_FRONTIER_PROJECT,
        fetch_pages=lambda _: [payload],
        clock=lambda: OBSERVED_AT,
    )

    jobs = adapter.fetch_jobs()

    assert len(jobs) == 2
    assert adapter.source_slug == "bytedance-campus-frontier-2027"
    assert adapter.descriptor.scope_key == (
        "project:7624064258157889845"
    )
    assert "2027届前沿技术领域人才校招" in jobs[0].description_raw


def test_fixture_adapter_creates_jobs_through_existing_pipeline(tmp_path):
    adapter = ByteDanceSeedCampusAdapter(
        fetch_page=lambda _: _payload(),
        clock=lambda: OBSERVED_AT,
    )
    config = CareerConfig(data_dir=tmp_path / "career")

    result = CrawlerService(config, adapters=[adapter]).crawl_registered_source(
        "bytedance-seed-campus"
    )

    assert result.status == "succeeded"
    assert result.transitions == {"created": 2}


def test_public_fetch_runs_playwright_off_asyncio_thread(monkeypatch):
    caller_thread = threading.get_ident()
    worker_threads: list[int] = []

    def fake_sync_fetch(page_num: int) -> dict:
        worker_threads.append(threading.get_ident())
        return _payload()

    monkeypatch.setattr(bytedance, "_fetch_public_page_sync", fake_sync_fetch)

    async def call() -> dict:
        return bytedance.fetch_public_page(1)

    result = asyncio.run(call())

    assert result["code"] == 0
    assert worker_threads and worker_threads[0] != caller_thread
