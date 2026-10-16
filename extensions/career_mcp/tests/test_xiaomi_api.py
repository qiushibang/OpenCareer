import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.crawler.xiaomi import (
    XiaomiAccessRestricted,
    XiaomiApiError,
    XiaomiPublicApiAdapter,
    fetch_public_page,
    parse_xiaomi_listing,
)
from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler.adapters import default_adapters
from extensions.career_mcp.services.crawler import CrawlerService

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "xiaomi-careers"
OBSERVED_AT = "2026-08-05T00:00:00Z"


def _fixture_payload() -> dict:
    return json.loads(
        (FIXTURE_DIR / "listing_page_1.json").read_text(encoding="utf-8")
    )


def test_parse_xiaomi_fixture_maps_stable_ids_and_complete_jd():
    metadata = json.loads((FIXTURE_DIR / "metadata.json").read_text(encoding="utf-8"))

    page = parse_xiaomi_listing(_fixture_payload(), observed_at=OBSERVED_AT)

    assert [job.external_job_id for job in page.jobs] == metadata["expected_job_ids"]
    assert page.page_num == 1
    assert page.page_total == 253
    assert page.total == 2522
    assert page.jobs[0].source_url.endswith("/7621150010131400998/detail")
    assert page.jobs[0].location_raw == "北京"
    assert page.jobs[0].recruitment_type == "internship"
    assert "岗位职责：" in page.jobs[0].description_raw
    assert "任职要求：" in page.jobs[0].description_raw


def test_parse_xiaomi_listing_rejects_duplicate_job_ids():
    payload = _fixture_payload()
    payload["data"]["list"][1]["jobId"] = payload["data"]["list"][0]["jobId"]

    with pytest.raises(XiaomiApiError, match="duplicate jobId"):
        parse_xiaomi_listing(payload, observed_at=OBSERVED_AT)


def test_parse_xiaomi_listing_rejects_api_error():
    payload = {"code": 500, "message": "failed", "data": None}

    with pytest.raises(XiaomiApiError, match="code 500"):
        parse_xiaomi_listing(payload, observed_at=OBSERVED_AT)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("jobId", "", "jobId"),
        ("title", "", "title"),
        ("url", "http://example.com/job", "HTTPS"),
    ],
)
def test_parse_xiaomi_listing_rejects_invalid_required_job_fields(
    field, value, message
):
    payload = _fixture_payload()
    payload["data"]["list"][0][field] = value

    with pytest.raises(XiaomiApiError, match=message):
        parse_xiaomi_listing(payload, observed_at=OBSERVED_AT)


def _page(page_num: int, page_total: int, job_id: str) -> dict:
    payload = _fixture_payload()
    payload["data"]["list"] = [payload["data"]["list"][0]]
    payload["data"]["list"][0]["jobId"] = job_id
    payload["data"]["pageNum"] = page_num
    payload["data"]["pageSize"] = 100
    payload["data"]["pageTotal"] = page_total
    payload["data"]["total"] = page_total
    return payload


def test_adapter_fetches_pages_serially_with_one_observed_at():
    requested: list[int] = []
    pages = {
        1: _page(1, 2, "job-1"),
        2: _page(2, 2, "job-2"),
    }

    def fetch_page(page_num: int) -> dict:
        requested.append(page_num)
        return pages[page_num]

    adapter = XiaomiPublicApiAdapter(
        fetch_page=fetch_page,
        clock=lambda: OBSERVED_AT,
    )

    jobs = adapter.fetch_jobs()

    assert requested == [1, 2]
    assert [job.external_job_id for job in jobs] == ["job-1", "job-2"]
    assert {job.observed_at for job in jobs} == {OBSERVED_AT}


def test_adapter_rejects_duplicate_ids_across_pages():
    pages = {
        1: _page(1, 2, "same"),
        2: _page(2, 2, "same"),
    }
    adapter = XiaomiPublicApiAdapter(
        fetch_page=lambda page_num: pages[page_num],
        clock=lambda: OBSERVED_AT,
    )

    with pytest.raises(XiaomiApiError, match="duplicate jobId across pages"):
        adapter.fetch_jobs()


def test_adapter_rejects_unbounded_page_count():
    adapter = XiaomiPublicApiAdapter(
        fetch_page=lambda _: _page(1, 301, "job-1"),
        clock=lambda: OBSERVED_AT,
    )

    with pytest.raises(XiaomiApiError, match="exceeds 300"):
        adapter.fetch_jobs()


def test_adapter_rejects_page_size_mismatch():
    payload = _page(1, 1, "job-1")
    payload["data"]["pageSize"] = 10
    adapter = XiaomiPublicApiAdapter(
        fetch_page=lambda _: payload,
        clock=lambda: OBSERVED_AT,
    )

    with pytest.raises(XiaomiApiError, match="pageSize"):
        adapter.fetch_jobs()


def test_adapter_rejects_total_change_during_pagination():
    pages = {
        1: _page(1, 2, "job-1"),
        2: _page(2, 2, "job-2"),
    }
    pages[2]["data"]["total"] = 3
    adapter = XiaomiPublicApiAdapter(
        fetch_page=lambda page_num: pages[page_num],
        clock=lambda: OBSERVED_AT,
    )

    with pytest.raises(XiaomiApiError, match="pagination changed"):
        adapter.fetch_jobs()


def test_adapter_rejects_empty_page_when_total_is_positive():
    payload = _page(1, 1, "job-1")
    payload["data"]["list"] = []
    adapter = XiaomiPublicApiAdapter(
        fetch_page=lambda _: payload,
        clock=lambda: OBSERVED_AT,
    )

    with pytest.raises(XiaomiApiError, match="empty page"):
        adapter.fetch_jobs()


def test_default_registry_includes_xiaomi():
    assert "xiaomi-careers" in {
        adapter.source_slug for adapter in default_adapters()
    }


def test_fixture_adapter_creates_jobs_through_existing_pipeline(tmp_path):
    payload = _fixture_payload()
    payload["data"]["pageSize"] = 100
    payload["data"]["pageTotal"] = 1
    adapter = XiaomiPublicApiAdapter(
        fetch_page=lambda _: payload,
        clock=lambda: OBSERVED_AT,
    )
    config = CareerConfig(data_dir=tmp_path / "career")

    result = CrawlerService(config, adapters=[adapter]).crawl_registered_source(
        "xiaomi-careers"
    )

    assert result.status == "succeeded"
    assert result.transitions == {"created": 2}

    connection = __import__("sqlite3").connect(config.database_path)
    try:
        rows = connection.execute(
            "SELECT external_job_id, canonical_url FROM jobs ORDER BY external_job_id"
        ).fetchall()
    finally:
        connection.close()
    assert rows == [
        (
            "7621150010131237158",
            "https://xiaomi.jobs.f.mioffice.cn/internship/position/"
            "7621150010131400998/detail",
        ),
        (
            "7621736061081504041",
            "https://xiaomi.jobs.f.mioffice.cn/internship/position/"
            "7621736061081667881/detail",
        ),
    ]


class _Headers:
    def __init__(self, content_type: str) -> None:
        self._content_type = content_type

    def get_content_type(self) -> str:
        return self._content_type


class _Response:
    def __init__(
        self,
        body: bytes,
        *,
        url: str,
        content_type: str = "application/json",
    ) -> None:
        self.status = 200
        self.url = url
        self.headers = _Headers(content_type)
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, _: int) -> bytes:
        return self._body


def test_fetch_public_page_uses_verified_public_url(monkeypatch):
    requested = []
    body = json.dumps(_fixture_payload()).encode()

    def fake_urlopen(request, timeout):
        requested.append((request.full_url, request.headers, timeout))
        return _Response(body, url=request.full_url)

    monkeypatch.setattr(
        "extensions.career_mcp.crawler.xiaomi.urlopen",
        fake_urlopen,
    )

    payload = fetch_public_page(2)

    assert payload["code"] == 0
    assert requested[0][0] == (
        "https://hr.xiaomi.com/website/api/agent/searchJobPage"
        "?keyword=&cityZhNames=&pageSize=100&pageNum=2"
    )
    assert requested[0][2] == 15
    assert "Cookie" not in requested[0][1]


def test_fetch_public_page_rejects_unexpected_redirect_host(monkeypatch):
    body = json.dumps(_fixture_payload()).encode()
    monkeypatch.setattr(
        "extensions.career_mcp.crawler.xiaomi.urlopen",
        lambda *_args, **_kwargs: _Response(
            body,
            url="https://example.com/login",
        ),
    )

    with pytest.raises(XiaomiAccessRestricted, match="redirect host"):
        fetch_public_page(1)
