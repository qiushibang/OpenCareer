import json
import sys
from pathlib import Path

import pytest
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.crawler import tencent
from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler.adapters import default_adapters
from extensions.career_mcp.crawler.tencent import (
    TencentApiError,
    TencentCareersAdapter,
    TENCENT_PRODUCTION_SCOPES,
    TencentScope,
    build_tencent_detail_url,
    build_tencent_listing_url,
    fetch_tencent_listing,
    parse_tencent_detail,
    parse_tencent_listing,
)
from extensions.career_mcp.services.crawler import CrawlerService

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "tencent-careers"
OBSERVED_AT = "2026-08-05T00:00:00Z"


def _json(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _scope() -> TencentScope:
    return TencentScope(
        source_slug="tencent-cdg-experienced",
        source_name="腾讯 CDG 社会招聘",
        bg_code="953",
        bg_name="CDG",
        max_jobs=150,
    )


def test_parse_listing_maps_stable_ids_and_total():
    page = parse_tencent_listing(_json("listing_page_1.json"), scope=_scope())

    assert page.total == 2
    assert [post.post_id for post in page.posts] == [
        "2041515867862368256",
        "2084148412080635904",
    ]
    assert page.posts[0].title == "腾讯营销-资深行业策略产品-线索方向"


def test_parse_detail_maps_complete_jd_and_canonical_url():
    job = parse_tencent_detail(
        _json("detail_1.json"),
        scope=_scope(),
        expected_post_id="2041515867862368256",
        observed_at=OBSERVED_AT,
    )

    assert job.external_job_id == "2041515867862368256"
    assert job.location_raw == "北京"
    assert job.recruitment_type == "experienced"
    assert job.source_url == (
        "https://careers.tencent.com/jobdesc.html"
        "?postId=2041515867862368256"
    )
    assert "岗位职责：" in job.description_raw
    assert "岗位要求：" in job.description_raw
    assert "事业群：CDG" in job.description_raw
    assert "产品：腾讯广告" in job.description_raw


def test_parse_detail_rejects_wrong_scope():
    payload = _json("detail_1.json")
    payload["Data"]["BGName"] = "IEG"

    with pytest.raises(TencentApiError, match="事业群"):
        parse_tencent_detail(
            payload,
            scope=_scope(),
            expected_post_id="2041515867862368256",
            observed_at=OBSERVED_AT,
        )


def test_parse_detail_rejects_missing_requirement():
    payload = _json("detail_1.json")
    payload["Data"]["Requirement"] = ""

    with pytest.raises(TencentApiError, match="Requirement"):
        parse_tencent_detail(
            payload,
            scope=_scope(),
            expected_post_id="2041515867862368256",
            observed_at=OBSERVED_AT,
        )


def _listing(total: int, post_ids: list[str]) -> dict:
    template = _json("listing_page_1.json")["Data"]["Posts"][0]
    return {
        "Code": 200,
        "Data": {
            "Count": total,
            "Posts": [
                {
                    **template,
                    "PostId": post_id,
                    "RecruitPostName": f"Job {post_id}",
                    "PostURL": (
                        "http://careers.tencent.com/jobdesc.html"
                        f"?postId={post_id}"
                    ),
                }
                for post_id in post_ids
            ],
        },
    }


def _detail(post_id: str) -> dict:
    data = dict(_json("detail_1.json")["Data"])
    data["PostId"] = post_id
    data["RecruitPostName"] = f"Job {post_id}"
    data["PostURL"] = (
        f"http://careers.tencent.com/jobdesc.html?postId={post_id}"
    )
    return {"Code": 200, "Data": data}


def test_adapter_fetches_all_pages_then_details_serially():
    scope = TencentScope(
        source_slug="tencent-cdg-experienced",
        source_name="腾讯 CDG 社会招聘",
        bg_code="953",
        bg_name="CDG",
        max_jobs=600,
    )
    post_ids = [str(1000 + index) for index in range(501)]
    requested_pages: list[int] = []
    requested_details: list[str] = []

    def fetch_listing(_: TencentScope, page_num: int) -> dict:
        requested_pages.append(page_num)
        if page_num == 1:
            return _listing(501, post_ids[:500])
        return _listing(501, post_ids[500:])

    def fetch_detail(post_id: str) -> dict:
        requested_details.append(post_id)
        return _detail(post_id)

    adapter = TencentCareersAdapter(
        scope,
        fetch_listing=fetch_listing,
        fetch_detail=fetch_detail,
        clock=lambda: OBSERVED_AT,
    )

    jobs = adapter.fetch_jobs()

    assert requested_pages == [1, 2]
    assert requested_details == post_ids
    assert [job.external_job_id for job in jobs] == post_ids
    assert {job.observed_at for job in jobs} == {OBSERVED_AT}
    assert adapter.descriptor.company_slug == "tencent"


def test_adapter_rejects_scope_over_safety_limit():
    scope = TencentScope(
        source_slug="tencent-small",
        source_name="Tencent small",
        bg_code="953",
        bg_name="CDG",
        max_jobs=10,
    )
    adapter = TencentCareersAdapter(
        scope,
        fetch_listing=lambda *_: _listing(11, ["1000"]),
        fetch_detail=lambda post_id: _detail(post_id),
        clock=lambda: OBSERVED_AT,
    )

    with pytest.raises(TencentApiError, match="exceeds"):
        adapter.fetch_jobs()


def test_listing_url_contains_exact_scope_and_pagination():
    scope = TencentScope(
        source_slug="tencent-ieg-ai",
        source_name="Tencent IEG AI",
        bg_code="956",
        bg_name="IEG",
        parent_category_id="40001",
        category_id="40001005",
        max_jobs=100,
    )

    parsed = urlparse(build_tencent_listing_url(scope, page_num=2))
    query = parse_qs(parsed.query, keep_blank_values=True)

    assert (parsed.scheme, parsed.hostname, parsed.path) == (
        "https",
        "careers.tencent.com",
        "/tencentcareer/api/post/Query",
    )
    assert query["bgIds"] == ["956"]
    assert query["parentCategoryId"] == ["40001"]
    assert query["categoryId"] == ["40001005"]
    assert query["pageIndex"] == ["2"]
    assert query["pageSize"] == ["500"]


def test_detail_url_uses_stable_post_id():
    assert build_tencent_detail_url("2041515867862368256") == (
        "https://careers.tencent.com/tencentcareer/api/post/ByPostId"
        "?postId=2041515867862368256&language=zh-cn"
    )


class _Headers:
    def __init__(self, content_type: str = "application/json") -> None:
        self._content_type = content_type

    def get_content_type(self) -> str:
        return self._content_type


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


def test_fetch_listing_uses_bounded_public_request(monkeypatch):
    requested = []
    body = json.dumps(_json("listing_page_1.json")).encode()

    def fake_urlopen(request, timeout):
        requested.append((request.full_url, request.headers, timeout))
        return _Response(body, url=request.full_url)

    monkeypatch.setattr(tencent, "urlopen", fake_urlopen)

    result = fetch_tencent_listing(_scope(), 1)

    assert result["Code"] == 200
    assert requested[0][2] == 15
    assert "Cookie" not in requested[0][1]


def test_fetch_listing_rejects_foreign_redirect(monkeypatch):
    body = json.dumps(_json("listing_page_1.json")).encode()

    def fake_urlopen(request, timeout):
        return _Response(body, url="https://example.com/jobs")

    monkeypatch.setattr(tencent, "urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="redirect"):
        fetch_tencent_listing(_scope(), 1)


def test_fixture_adapter_creates_jobs_through_existing_pipeline(tmp_path):
    details = {
        "2041515867862368256": _json("detail_1.json"),
        "2084148412080635904": _json("detail_2.json"),
    }
    adapter = TencentCareersAdapter(
        _scope(),
        fetch_listing=lambda *_: _json("listing_page_1.json"),
        fetch_detail=lambda post_id: details[post_id],
        clock=lambda: OBSERVED_AT,
    )
    config = CareerConfig(data_dir=tmp_path / "career")
    service = CrawlerService(config, adapters=[adapter])

    created = service.crawl_registered_source(adapter.source_slug)
    unchanged = service.crawl_registered_source(adapter.source_slug)

    assert created.transitions == {"created": 2}
    assert unchanged.transitions == {"unchanged": 2}
    connection = __import__("sqlite3").connect(config.database_path)
    try:
        company = connection.execute(
            "SELECT slug, name FROM companies WHERE slug = 'tencent'"
        ).fetchone()
    finally:
        connection.close()
    assert company == ("tencent", "腾讯")


def test_default_registry_includes_live_accepted_tencent_cdg():
    slugs = [adapter.source_slug for adapter in default_adapters()]

    assert {"bytedance-seed-campus", "deepseek-careers"} <= set(slugs)
    assert [slug for slug in slugs if slug.startswith("tencent-")] == [
        scope.source_slug for scope in TENCENT_PRODUCTION_SCOPES
    ]
    assert "xiaomi-careers" in slugs


def test_production_scopes_cover_all_live_accepted_tencent_partitions():
    assert [scope.source_slug for scope in TENCENT_PRODUCTION_SCOPES] == [
        "tencent-cdg-experienced",
        "tencent-csig-experienced",
        "tencent-ieg-admin-experienced",
        "tencent-ieg-content-experienced",
        "tencent-ieg-design-experienced",
        "tencent-ieg-game-art-experienced",
        "tencent-ieg-game-product-experienced",
        "tencent-ieg-marketing-pr-experienced",
        "tencent-ieg-product-experienced",
        "tencent-ieg-project-experienced",
        "tencent-ieg-sales-support-experienced",
        "tencent-ieg-strategy-investment-experienced",
        "tencent-ieg-tech-ai-data-experienced",
        "tencent-ieg-tech-operations-experienced",
        "tencent-ieg-tech-quality-experienced",
        "tencent-ieg-tech-rd-experienced",
        "tencent-ieg-tech-security-experienced",
        "tencent-pcg-experienced",
        "tencent-s1-experienced",
        "tencent-s2-experienced",
        "tencent-s3-experienced",
        "tencent-teg-experienced",
        "tencent-wxg-experienced",
    ]
    assert {
        scope.descriptor.company_slug for scope in TENCENT_PRODUCTION_SCOPES
    } == {"tencent"}
