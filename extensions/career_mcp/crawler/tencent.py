"""Official Tencent careers JSON parsing and bounded source scopes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import ceil
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from ..domain.crawler import JobSnapshot, SourceDescriptor
from ..domain.manual_jd import utc_now_iso

LISTING_API = "https://careers.tencent.com/tencentcareer/api/post/Query"
DETAIL_API = "https://careers.tencent.com/tencentcareer/api/post/ByPostId"
DETAIL_PAGE = "https://careers.tencent.com/jobdesc.html"


class TencentApiError(ValueError):
    """A Tencent careers response violated the verified public contract."""


class TencentAccessRestricted(RuntimeError):
    """The Tencent public careers API cannot be fetched safely."""


@dataclass(frozen=True)
class TencentScope:
    source_slug: str
    source_name: str
    bg_code: str
    bg_name: str
    max_jobs: int
    parent_category_id: str | None = None
    category_id: str | None = None

    @property
    def descriptor(self) -> SourceDescriptor:
        scope_parts = [f"bg:{self.bg_code}"]
        if self.parent_category_id:
            scope_parts.append(f"parent-category:{self.parent_category_id}")
        if self.category_id:
            scope_parts.append(f"category:{self.category_id}")
        return SourceDescriptor(
            source_slug=self.source_slug,
            source_name=self.source_name,
            company_slug="tencent",
            company_name="腾讯",
            scope_key=";".join(scope_parts),
            adapter_type="public-json-api-with-detail",
            base_url="https://careers.tencent.com/zh-cn/search.html",
        )


TENCENT_CDG_SCOPE = TencentScope(
    source_slug="tencent-cdg-experienced",
    source_name="腾讯 CDG 社会招聘",
    bg_code="953",
    bg_name="CDG",
    max_jobs=150,
)

TENCENT_PRODUCTION_SCOPES = (
    TENCENT_CDG_SCOPE,
    TencentScope(
        "tencent-csig-experienced",
        "腾讯 CSIG 社会招聘",
        "29294",
        "CSIG",
        450,
    ),
    TencentScope(
        "tencent-ieg-admin-experienced",
        "腾讯 IEG 行政支持社会招聘",
        "956",
        "IEG",
        30,
        parent_category_id="40010",
    ),
    TencentScope(
        "tencent-ieg-content-experienced",
        "腾讯 IEG 内容社会招聘",
        "956",
        "IEG",
        30,
        parent_category_id="40006",
    ),
    TencentScope(
        "tencent-ieg-design-experienced",
        "腾讯 IEG 设计社会招聘",
        "956",
        "IEG",
        100,
        parent_category_id="40002",
        category_id="40002001",
    ),
    TencentScope(
        "tencent-ieg-game-art-experienced",
        "腾讯 IEG 游戏美术社会招聘",
        "956",
        "IEG",
        320,
        parent_category_id="40002",
        category_id="40002002",
    ),
    TencentScope(
        "tencent-ieg-game-product-experienced",
        "腾讯 IEG 游戏产品社会招聘",
        "956",
        "IEG",
        450,
        parent_category_id="40003",
        category_id="40003002",
    ),
    TencentScope(
        "tencent-ieg-marketing-pr-experienced",
        "腾讯 IEG 营销与公关社会招聘",
        "956",
        "IEG",
        120,
        parent_category_id="40004",
    ),
    TencentScope(
        "tencent-ieg-product-experienced",
        "腾讯 IEG 产品社会招聘",
        "956",
        "IEG",
        80,
        parent_category_id="40003",
        category_id="40003001",
    ),
    TencentScope(
        "tencent-ieg-project-experienced",
        "腾讯 IEG 项目社会招聘",
        "956",
        "IEG",
        80,
        parent_category_id="40003",
        category_id="40003003",
    ),
    TencentScope(
        "tencent-ieg-sales-support-experienced",
        "腾讯 IEG 销售服务支持社会招聘",
        "956",
        "IEG",
        60,
        parent_category_id="40005",
    ),
    TencentScope(
        "tencent-ieg-strategy-investment-experienced",
        "腾讯 IEG 战略与投资社会招聘",
        "956",
        "IEG",
        60,
        parent_category_id="40011",
    ),
    TencentScope(
        "tencent-ieg-tech-ai-data-experienced",
        "腾讯 IEG AI算法与大数据社会招聘",
        "956",
        "IEG",
        120,
        parent_category_id="40001",
        category_id="40001005",
    ),
    TencentScope(
        "tencent-ieg-tech-operations-experienced",
        "腾讯 IEG 技术运营社会招聘",
        "956",
        "IEG",
        30,
        parent_category_id="40001",
        category_id="40001003",
    ),
    TencentScope(
        "tencent-ieg-tech-quality-experienced",
        "腾讯 IEG 质量管理社会招聘",
        "956",
        "IEG",
        30,
        parent_category_id="40001",
        category_id="40001002",
    ),
    TencentScope(
        "tencent-ieg-tech-rd-experienced",
        "腾讯 IEG 技术研发社会招聘",
        "956",
        "IEG",
        260,
        parent_category_id="40001",
        category_id="40001001",
    ),
    TencentScope(
        "tencent-ieg-tech-security-experienced",
        "腾讯 IEG 安全技术社会招聘",
        "956",
        "IEG",
        30,
        parent_category_id="40001",
        category_id="40001004",
    ),
    TencentScope(
        "tencent-pcg-experienced",
        "腾讯 PCG 社会招聘",
        "29292",
        "PCG",
        100,
    ),
    TencentScope(
        "tencent-s1-experienced",
        "腾讯 S1 职能线社会招聘",
        "78",
        "S1",
        50,
    ),
    TencentScope(
        "tencent-s2-experienced",
        "腾讯 S2 财经线社会招聘",
        "2233",
        "S2",
        50,
    ),
    TencentScope(
        "tencent-s3-experienced",
        "腾讯 S3 HR与管理线社会招聘",
        "2234",
        "S3",
        50,
    ),
    TencentScope(
        "tencent-teg-experienced",
        "腾讯 TEG 社会招聘",
        "958",
        "TEG",
        300,
    ),
    TencentScope(
        "tencent-wxg-experienced",
        "腾讯 WXG 社会招聘",
        "14129",
        "WXG",
        350,
    ),
)


@dataclass(frozen=True)
class TencentListingPost:
    post_id: str
    title: str


@dataclass(frozen=True)
class TencentListingPage:
    posts: list[TencentListingPost]
    total: int


class TencentCareersAdapter:
    page_size = 500

    def __init__(
        self,
        scope: TencentScope,
        *,
        fetch_listing: Callable[[TencentScope, int], Mapping[str, object]] | None = None,
        fetch_detail: Callable[[str], Mapping[str, object]] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.scope = scope
        self.descriptor = scope.descriptor
        self.source_slug = scope.source_slug
        self._fetch_listing = fetch_listing or fetch_tencent_listing
        self._fetch_detail = fetch_detail or fetch_tencent_detail
        self._clock = clock or utc_now_iso

    def fetch_jobs(self) -> list[JobSnapshot]:
        first = parse_tencent_listing(
            self._fetch_listing(self.scope, 1),
            scope=self.scope,
        )
        if first.total > self.scope.max_jobs:
            raise TencentApiError(
                f"Tencent scope total {first.total} exceeds "
                f"{self.scope.max_jobs}"
            )
        if first.total > 0 and not first.posts:
            raise TencentApiError(
                "Tencent listing returned an empty page for a positive total"
            )

        posts = list(first.posts)
        seen_ids = {post.post_id for post in posts}
        page_total = ceil(first.total / self.page_size) if first.total else 1
        for page_num in range(2, page_total + 1):
            page = parse_tencent_listing(
                self._fetch_listing(self.scope, page_num),
                scope=self.scope,
            )
            if page.total != first.total:
                raise TencentApiError("Tencent listing total changed during crawl")
            if not page.posts:
                raise TencentApiError("Tencent listing returned an empty middle page")
            for post in page.posts:
                if post.post_id in seen_ids:
                    raise TencentApiError("duplicate Tencent PostId across pages")
                seen_ids.add(post.post_id)
                posts.append(post)
        if len(posts) != first.total:
            raise TencentApiError("Tencent listing count does not match total")

        observed_at = self._clock()
        jobs: list[JobSnapshot] = []
        for post in posts:
            job = parse_tencent_detail(
                self._fetch_detail(post.post_id),
                scope=self.scope,
                expected_post_id=post.post_id,
                observed_at=observed_at,
            )
            if job.title != post.title:
                raise TencentApiError("Tencent detail title does not match listing")
            jobs.append(job)
        return jobs


def build_tencent_listing_url(scope: TencentScope, page_num: int) -> str:
    if page_num < 1:
        raise ValueError("page_num must be positive")
    query = urlencode(
        {
            "countryId": "",
            "cityId": "",
            "bgIds": scope.bg_code,
            "productId": "",
            "categoryId": scope.category_id or "",
            "parentCategoryId": scope.parent_category_id or "",
            "attrId": "",
            "keyword": "",
            "pageIndex": page_num,
            "pageSize": TencentCareersAdapter.page_size,
            "language": "zh-cn",
            "area": "cn",
        }
    )
    return f"{LISTING_API}?{query}"


def build_tencent_detail_url(post_id: str) -> str:
    if not post_id.isdigit():
        raise ValueError("post_id must be numeric")
    return f"{DETAIL_API}?{urlencode({'postId': post_id, 'language': 'zh-cn'})}"


def fetch_tencent_listing(
    scope: TencentScope,
    page_num: int,
) -> Mapping[str, object]:
    return _fetch_tencent_json(
        build_tencent_listing_url(scope, page_num),
        max_bytes=5_000_000,
    )


def fetch_tencent_detail(post_id: str) -> Mapping[str, object]:
    return _fetch_tencent_json(
        build_tencent_detail_url(post_id),
        max_bytes=2_000_000,
    )


def _fetch_tencent_json(url: str, *, max_bytes: int) -> Mapping[str, object]:
    request = Request(
        url,
        headers={"User-Agent": "OpenWorker-Career/0.1 (+local job research)"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            final_url = response.url
            content_type = response.headers.get_content_type()
            body = response.read(max_bytes + 1)
    except HTTPError as exc:
        raise TencentAccessRestricted(f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise TencentAccessRestricted(f"network error: {exc.reason}") from exc

    if status != 200:
        raise TencentAccessRestricted(f"HTTP {status}")
    parsed = urlparse(final_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "careers.tencent.com"
        or not parsed.path.startswith("/tencentcareer/api/")
    ):
        raise TencentAccessRestricted("unexpected Tencent redirect")
    if content_type != "application/json":
        raise TencentAccessRestricted(f"unexpected content type: {content_type}")
    if len(body) > max_bytes:
        raise TencentAccessRestricted("Tencent response body exceeds size limit")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TencentAccessRestricted("Tencent response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise TencentAccessRestricted("Tencent response JSON must be an object")
    return payload


def parse_tencent_listing(
    payload: Mapping[str, object],
    *,
    scope: TencentScope,
) -> TencentListingPage:
    data = _response_data(payload)
    total = _required_int(data, "Count")
    entries = data.get("Posts")
    if not isinstance(entries, list):
        raise TencentApiError("Tencent Data.Posts must be a list")

    posts: list[TencentListingPost] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise TencentApiError("Tencent listing post must be an object")
        post_id = _required_text(entry, "PostId")
        if not post_id.isdigit():
            raise TencentApiError("Tencent PostId must be numeric")
        if post_id in seen_ids:
            raise TencentApiError("duplicate Tencent PostId")
        seen_ids.add(post_id)
        bg_name = _required_text(entry, "BGName")
        if bg_name != scope.bg_name:
            raise TencentApiError("Tencent listing escaped the requested 事业群")
        posts.append(
            TencentListingPost(
                post_id=post_id,
                title=_required_text(entry, "RecruitPostName"),
            )
        )
    return TencentListingPage(posts=posts, total=total)


def parse_tencent_detail(
    payload: Mapping[str, object],
    *,
    scope: TencentScope,
    expected_post_id: str,
    observed_at: str,
) -> JobSnapshot:
    data = _response_data(payload)
    post_id = _required_text(data, "PostId")
    if post_id != expected_post_id:
        raise TencentApiError("Tencent detail PostId does not match listing")
    if _required_text(data, "BGName") != scope.bg_name:
        raise TencentApiError("Tencent detail escaped the requested 事业群")
    if scope.category_id:
        category_id = _required_text(data, "OuterPostTypeID")
        if category_id != scope.category_id:
            raise TencentApiError("Tencent detail escaped the requested category")

    title = _required_text(data, "RecruitPostName")
    responsibility = _required_text(data, "Responsibility")
    requirement = _required_text(data, "Requirement")
    fields = (
        ("事业群", data.get("BGName")),
        ("产品", data.get("ProductName")),
        ("职类", data.get("CategoryName")),
        ("工作年限", data.get("RequireWorkYearsName")),
        ("岗位职责", responsibility),
        ("岗位要求", requirement),
        ("部门介绍", data.get("DepartmentIntroduction")),
        ("更新时间", data.get("LastUpdateTime")),
        ("职位编码", data.get("RecruitPostId")),
    )
    description = "\n\n".join(
        f"{label}：{str(value).strip()}"
        for label, value in fields
        if value is not None and str(value).strip()
    )
    return JobSnapshot(
        external_job_id=post_id,
        title=title,
        description_raw=description,
        source_url=f"{DETAIL_PAGE}?postId={post_id}",
        observed_at=observed_at,
        location_raw=_required_text(data, "LocationName"),
        recruitment_type="experienced",
    )


def _response_data(payload: Mapping[str, object]) -> dict:
    if payload.get("Code") != 200:
        raise TencentApiError(f"Tencent API returned Code {payload.get('Code')}")
    data = payload.get("Data")
    if not isinstance(data, dict):
        raise TencentApiError("Tencent Data must be an object")
    return data


def _required_text(entry: Mapping[str, object], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, (str, int)) or not str(value).strip():
        raise TencentApiError(f"Tencent {field} must be non-empty")
    return str(value).strip()


def _required_int(entry: Mapping[str, object], field: str) -> int:
    value = entry.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TencentApiError(f"Tencent {field} must be a non-negative integer")
    return value
