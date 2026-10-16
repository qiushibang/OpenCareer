import json
import sys
from pathlib import Path
from urllib.error import URLError

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.crawler import meituan
from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler.adapters import default_adapters
from extensions.career_mcp.crawler.meituan import (
    MeituanApiError,
    MeituanSocialAdapter,
    fetch_meituan_page,
    parse_meituan_listing,
    parse_overseas_city_names,
)
from extensions.career_mcp.services.crawler import CrawlerService

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "meituan-social"
OBSERVED_AT = "2026-08-06T00:00:00Z"


def _json(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_parse_overseas_city_names_uses_official_country_tree():
    names = parse_overseas_city_names(_json("overseas_cities.json"))

    assert {"沙特", "利雅得", "巴西", "圣保罗", "阿联酋", "迪拜", "多哈"} <= names
    assert "北京" not in names


def test_parse_listing_maps_complete_domestic_jobs():
    metadata = _json("metadata.json")
    page = parse_meituan_listing(
        _json("listing_page_1.json"),
        observed_at=OBSERVED_AT,
        overseas_city_names=parse_overseas_city_names(
            _json("overseas_cities.json")
        ),
    )

    assert page.total == 2
    assert page.raw_count == 2
    assert [job.external_job_id for job in page.jobs] == metadata[
        "expected_job_ids"
    ]
    assert page.jobs[0].location_raw == "南京市"
    assert page.jobs[0].recruitment_type == "experienced"
    assert page.jobs[0].source_url == (
        "https://hr.meituan.com/web/position/detail"
        "?jobUnionId=4612117869&highlightType=social"
    )
    assert "岗位职责：" in page.jobs[0].description_raw
    assert "岗位要求：" in page.jobs[0].description_raw
    assert "部门：核心本地商业-美团平台" in page.jobs[0].description_raw


def test_parse_listing_excludes_only_overseas_jobs():
    payload = _json("listing_page_1.json")
    jobs = payload["data"]["list"]
    jobs[0]["cityList"] = [{"name": "迪拜"}]
    jobs[1]["cityList"] = [{"name": "北京"}, {"name": "迪拜"}]

    page = parse_meituan_listing(
        payload,
        observed_at=OBSERVED_AT,
        overseas_city_names={"迪拜"},
    )

    assert page.raw_count == 2
    assert [job.external_job_id for job in page.jobs] == ["4672329717"]


def test_parse_listing_rejects_missing_requirement():
    payload = _json("listing_page_1.json")
    payload["data"]["list"][0]["jobRequirement"] = ""

    with pytest.raises(MeituanApiError, match="jobRequirement"):
        parse_meituan_listing(
            payload,
            observed_at=OBSERVED_AT,
            overseas_city_names=set(),
        )


def _page(total: int, page_no: int, job_ids: list[str]) -> dict:
    template = _json("listing_page_1.json")["data"]["list"][0]
    entries = [
        {
            **template,
            "jobUnionId": job_id,
            "name": f"Job {job_id}",
        }
        for job_id in job_ids
    ]
    return {
        "status": 1,
        "message": "成功",
        "data": {
            "list": entries,
            "page": {
                "pageNo": page_no,
                "pageSize": 100,
                "totalPage": 2,
                "totalCount": total,
            },
        },
    }


def test_adapter_validates_raw_count_before_overseas_filter():
    post_ids = [str(1000 + index) for index in range(101)]
    pages = {
        1: _page(101, 1, post_ids[:100]),
        2: _page(101, 2, post_ids[100:]),
    }
    pages[2]["data"]["list"][0]["cityList"] = [{"name": "迪拜"}]
    requested: list[object] = []

    adapter = MeituanSocialAdapter(
        fetch_page=lambda page_num: requested.append(page_num) or pages[page_num],
        fetch_overseas_cities=lambda: (
            requested.append("overseas") or _json("overseas_cities.json")
        ),
        clock=lambda: OBSERVED_AT,
    )

    jobs = adapter.fetch_jobs()

    assert requested == ["overseas", 1, 2]
    assert len(jobs) == 100
    assert {job.external_job_id for job in jobs} == set(post_ids[:100])
    assert {job.observed_at for job in jobs} == {OBSERVED_AT}
    assert adapter.descriptor.company_slug == "meituan"


def test_adapter_rejects_pagination_total_change():
    first_ids = [str(1000 + index) for index in range(100)]
    pages = {
        1: _page(101, 1, first_ids),
        2: _page(102, 2, ["1100"]),
    }
    adapter = MeituanSocialAdapter(
        fetch_page=lambda page_num: pages[page_num],
        fetch_overseas_cities=lambda: _json("overseas_cities.json"),
        clock=lambda: OBSERVED_AT,
    )

    with pytest.raises(MeituanApiError, match="pagination changed"):
        adapter.fetch_jobs()


def test_adapter_recovers_live_pagination_drift_with_bounded_union():
    ids = [str(1000 + index) for index in range(101)]
    first_pass = [
        _page(101, 1, ids[:100]),
        _page(101, 2, [ids[99]]),
    ]
    second_pass = [
        _page(101, 1, ids[:100]),
        _page(101, 2, [ids[100]]),
    ]
    responses = iter(first_pass + second_pass)
    adapter = MeituanSocialAdapter(
        fetch_page=lambda _: next(responses),
        fetch_overseas_cities=lambda: _json("overseas_cities.json"),
        clock=lambda: OBSERVED_AT,
    )

    jobs = adapter.fetch_jobs()

    assert len(jobs) == 101
    assert {job.external_job_id for job in jobs} == set(ids)


class _Headers:
    def get_content_type(self) -> str:
        return "application/json"


class _Response:
    def __init__(self, body: bytes, *, url: str) -> None:
        self.status = 200
        self.url = url
        self.headers = _Headers()
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, _: int) -> bytes:
        return self._body


class _HttpxResponse:
    def __init__(self, body: bytes, *, url: str) -> None:
        self.status_code = 200
        self.url = url
        self.headers = {"content-type": "application/json"}
        self.content = body


def test_fetch_page_uses_public_body_without_query_tracking_ids(monkeypatch):
    requested = []
    body = json.dumps(_json("listing_page_1.json")).encode()

    def fake_urlopen(request, timeout):
        requested.append((request, timeout))
        return _Response(body, url=request.full_url)

    monkeypatch.setattr(meituan, "urlopen", fake_urlopen)

    result = fetch_meituan_page(2)

    request, timeout = requested[0]
    request_body = json.loads(request.data)
    assert result["status"] == 1
    assert timeout == 15
    assert request_body["page"] == {"pageNo": 2, "pageSize": 100}
    assert request_body["jobType"] == [{"code": "3", "subCode": []}]
    assert "u_query_id" not in request_body
    assert "r_query_id" not in request_body
    assert "Cookie" not in request.headers


def test_fetch_page_rejects_foreign_redirect(monkeypatch):
    body = json.dumps(_json("listing_page_1.json")).encode()

    def fake_urlopen(request, timeout):
        return _Response(body, url="https://example.com/jobs")

    monkeypatch.setattr(meituan, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="redirect"):
        fetch_meituan_page(1)


def test_fetch_page_retries_transient_network_errors(monkeypatch):
    body = json.dumps(_json("listing_page_1.json")).encode()
    attempts = 0

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise URLError(TimeoutError("TLS handshake timed out"))
        return _Response(body, url=request.full_url)

    monkeypatch.setattr(meituan, "urlopen", fake_urlopen)

    result = fetch_meituan_page(1)

    assert result["status"] == 1
    assert attempts == 3


def test_default_adapter_reuses_one_http_client(monkeypatch):
    calls = []
    clients = []

    class FakeClient:
        def __init__(self, **kwargs):
            clients.append(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def post(self, url, *, content, headers):
            calls.append((url, json.loads(content), headers))
            fixture = (
                "overseas_cities.json"
                if url == meituan.OVERSEAS_CITY_API
                else "listing_page_1.json"
            )
            return _HttpxResponse(
                json.dumps(_json(fixture)).encode(),
                url=url,
            )

    monkeypatch.setattr(meituan.httpx, "Client", FakeClient)

    jobs = MeituanSocialAdapter(clock=lambda: OBSERVED_AT).fetch_jobs()

    assert len(jobs) == 2
    assert len(clients) == 1
    assert [call[0] for call in calls] == [
        meituan.OVERSEAS_CITY_API,
        meituan.LISTING_API,
    ]


def test_fixture_adapter_creates_jobs_through_existing_pipeline(tmp_path):
    adapter = MeituanSocialAdapter(
        fetch_page=lambda _: _json("listing_page_1.json"),
        fetch_overseas_cities=lambda: _json("overseas_cities.json"),
        clock=lambda: OBSERVED_AT,
    )
    config = CareerConfig(data_dir=tmp_path / "career")
    service = CrawlerService(config, adapters=[adapter])

    created = service.crawl_registered_source(adapter.source_slug)
    unchanged = service.crawl_registered_source(adapter.source_slug)

    assert created.transitions == {"created": 2}
    assert unchanged.transitions == {"unchanged": 2}


def test_default_registry_includes_live_accepted_meituan():
    assert "meituan-social-cn" in {
        adapter.source_slug for adapter in default_adapters()
    }
