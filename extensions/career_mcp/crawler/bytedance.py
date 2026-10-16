"""Bounded parser and adapter for ByteDance's Seed campus project."""

from __future__ import annotations

import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from math import ceil
from typing import Callable, Mapping
from urllib.parse import parse_qs, urlencode, urlparse

from ..domain.crawler import JobSnapshot, SourceDescriptor
from ..domain.manual_jd import utc_now_iso

PROJECT_ID = "7621018151002507573"
PROJECT_NAME = "2027届Seed大模型人才校招"
DETAIL_PREFIX = "https://jobs.bytedance.com/campus/position"
SOCIAL_DETAIL_PREFIX = "https://jobs.bytedance.com/experienced/position"


class ByteDanceApiError(ValueError):
    """A ByteDance listing response violated the verified project contract."""


class ByteDanceAccessRestricted(RuntimeError):
    """The public ByteDance project page cannot be fetched safely."""


@dataclass(frozen=True)
class ByteDanceListingPage:
    jobs: list[JobSnapshot]
    total: int


@dataclass(frozen=True)
class ResumableListingPage:
    jobs: list[JobSnapshot]
    total: int
    next_offset: int
    complete: bool
    fingerprint: str


@dataclass(frozen=True)
class ByteDanceMainlandScope:
    source_slug: str
    source_name: str
    portal_type: str
    page_url: str
    recruitment_type: str


BYTEDANCE_MAINLAND_SOCIAL = ByteDanceMainlandScope(
    source_slug="bytedance-mainland-social",
    source_name="字节跳动中国大陆社招",
    portal_type="2",
    page_url=SOCIAL_DETAIL_PREFIX,
    recruitment_type="experienced",
)
BYTEDANCE_MAINLAND_CAMPUS = ByteDanceMainlandScope(
    source_slug="bytedance-mainland-campus",
    source_name="字节跳动中国大陆校招",
    portal_type="3",
    page_url=DETAIL_PREFIX,
    recruitment_type="campus",
)

_MAINLAND_CITY_NAMES = {
    "北京", "上海", "深圳", "杭州", "成都", "广州", "西安", "武汉",
    "重庆", "珠海", "郑州", "南京", "青岛", "济南", "合肥", "苏州",
    "厦门", "长沙", "天津", "福州", "昆明", "太原", "南昌", "无锡",
    "贵阳", "哈尔滨", "宁波", "常州", "温州", "沈阳", "三亚",
    "石家庄", "南宁", "东莞", "海口", "潍坊", "泉州", "佛山",
    "宜春", "兰州", "金华", "绍兴", "滁州", "惠州", "长春", "洛阳",
    "烟台", "呼和浩特", "大连", "徐州", "丽水", "鄂尔多斯", "南充",
    "乌鲁木齐", "济宁", "安阳", "龙岩", "临沂",
}
_NON_MAINLAND_CITY_NAMES = {
    "中国香港", "中国澳门", "中国台湾", "新加坡", "圣何塞", "西雅图",
    "塔吉格", "伦敦", "迪拜", "东京", "圣保罗", "曼谷", "吉隆坡",
    "雅加达", "纽约", "利雅得", "洛杉矶", "阿什本", "古来",
    "胡志明市", "帕西格市", "春武里", "墨西哥城", "首尔",
    "南雅加达行政市", "阿姆斯特丹", "马德里", "都柏林", "河内",
    "圣地亚哥", "慕尼黑", "古尔冈",
}


class ByteDanceMainlandAdapter:
    page_size = 10

    def __init__(
        self,
        scope: ByteDanceMainlandScope,
        *,
        fetch_filters: Callable[
            [ByteDanceMainlandScope], Mapping[str, object]
        ]
        | None = None,
        fetch_page: Callable[
            [ByteDanceMainlandScope, Mapping[str, object], int],
            Mapping[str, object],
        ]
        | None = None,
        fetch_pages: Callable[
            [
                ByteDanceMainlandScope,
                Mapping[str, object],
                int,
                int,
            ],
            list[Mapping[str, object]],
        ]
        | None = None,
        verify_details: Callable[
            [ByteDanceMainlandScope, list[JobSnapshot]],
            dict[str, str],
        ]
        | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.scope = scope
        self.source_slug = scope.source_slug
        self.descriptor = SourceDescriptor(
            source_slug=scope.source_slug,
            source_name=scope.source_name,
            company_slug="bytedance",
            company_name="字节跳动",
            scope_key=scope.source_slug.removeprefix("bytedance-"),
            adapter_type="playwright-json-resumable",
            base_url=scope.page_url,
        )
        self._fetch_filters = fetch_filters or fetch_mainland_filters
        self._fetch_page = fetch_page or fetch_mainland_page
        self._fetch_pages = fetch_pages or fetch_mainland_pages
        self._verify_details = (
            verify_details or verify_mainland_job_details
        )
        self._clock = clock or utc_now_iso

    def initial_shards(self) -> list[dict]:
        metadata = parse_bytedance_filter_metadata(
            self._fetch_filters(self.scope)
        )
        if metadata["categories"]:
            return [
                {
                    "shard_key": f"category:{category['id']}",
                    "filters": {
                        "location_code": None,
                        "location_name": None,
                        "category_id": category["id"],
                    },
                }
                for category in metadata["categories"]
            ]
        return [
            {
                "shard_key": f"location:{city['code']}",
                "filters": {
                    "location_code": city["code"],
                    "location_name": city["name"],
                    "category_id": None,
                },
            }
            for city in metadata["mainland_cities"]
        ]

    def fetch_page(
        self,
        filters: Mapping[str, object],
        offset: int,
    ) -> ResumableListingPage:
        payload = self._fetch_page(self.scope, filters, offset)
        return self._parse_page(
            payload,
            filters,
            offset,
            observed_at=self._clock(),
        )

    def fetch_pages(
        self,
        filters: Mapping[str, object],
        offset: int,
        limit: int,
    ) -> list[ResumableListingPage]:
        observed_at = self._clock()
        payloads = self._fetch_pages(
            self.scope,
            filters,
            offset,
            limit,
        )
        pages = []
        for index, payload in enumerate(payloads):
            page = self._parse_page(
                payload,
                filters,
                offset + index * self.page_size,
                observed_at=observed_at,
            )
            pages.append(page)
            if page.complete:
                break
        return pages

    def verify_stale_jobs(
        self,
        snapshots: list[JobSnapshot],
    ) -> dict[str, str]:
        return self._verify_details(self.scope, snapshots)

    def _parse_page(
        self,
        payload: Mapping[str, object],
        filters: Mapping[str, object],
        offset: int,
        *,
        observed_at: str,
    ) -> ResumableListingPage:
        page = parse_bytedance_scope_listing(
            payload,
            observed_at=observed_at,
            scope=self.scope,
            allowed_city_names=(
                {str(filters["location_name"])}
                if filters.get("location_name")
                else set(_MAINLAND_CITY_NAMES)
            ),
        )
        next_offset = offset + self.page_size
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "total": page.total,
                    "ids": [
                        job.external_job_id for job in page.jobs
                    ],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return ResumableListingPage(
            jobs=page.jobs,
            total=page.total,
            next_offset=next_offset,
            complete=next_offset >= page.total,
            fingerprint=fingerprint,
        )


@dataclass(frozen=True)
class ByteDanceCampusProject:
    source_slug: str
    source_name: str
    project_id: str
    project_name: str
    max_jobs: int


BYTEDANCE_SEED_PROJECT = ByteDanceCampusProject(
    source_slug="bytedance-seed-campus",
    source_name="字节跳动 2027 Seed 大模型人才校招",
    project_id=PROJECT_ID,
    project_name=PROJECT_NAME,
    max_jobs=200,
)
BYTEDANCE_FRONTIER_PROJECT = ByteDanceCampusProject(
    source_slug="bytedance-campus-frontier-2027",
    source_name="字节跳动 2027 前沿技术领域人才校招",
    project_id="7624064258157889845",
    project_name="2027届前沿技术领域人才校招",
    max_jobs=200,
)


class ByteDanceCampusProjectAdapter:
    page_size = 10
    max_pages = 20

    def __init__(
        self,
        project: ByteDanceCampusProject,
        *,
        fetch_pages: Callable[
            [ByteDanceCampusProject], list[Mapping[str, object]]
        ]
        | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.project = project
        self.source_slug = project.source_slug
        self.descriptor = SourceDescriptor(
            source_slug=project.source_slug,
            source_name=project.source_name,
            company_slug="bytedance",
            company_name="字节跳动",
            scope_key=f"project:{project.project_id}",
            adapter_type="playwright-json",
            base_url=DETAIL_PREFIX,
        )
        self._fetch_pages = fetch_pages or fetch_project_pages
        self._clock = clock or utc_now_iso

    def fetch_jobs(self) -> list[JobSnapshot]:
        payloads = self._fetch_pages(self.project)
        if not payloads:
            raise ByteDanceApiError("ByteDance project has no pages")
        observed_at = self._clock()
        pages = [
            parse_bytedance_listing(
                payload,
                observed_at=observed_at,
                project=self.project,
            )
            for payload in payloads
        ]
        total = pages[0].total
        if total > self.project.max_jobs:
            raise ByteDanceApiError(
                f"ByteDance project total {total} exceeds "
                f"{self.project.max_jobs}"
            )
        expected_pages = ceil(total / self.page_size) if total else 1
        if expected_pages > self.max_pages or len(pages) != expected_pages:
            raise ByteDanceApiError("ByteDance project page count is invalid")
        jobs: list[JobSnapshot] = []
        seen: set[str] = set()
        for page in pages:
            if page.total != total:
                raise ByteDanceApiError(
                    "ByteDance project total changed during crawl"
                )
            for job in page.jobs:
                if job.external_job_id in seen:
                    raise ByteDanceApiError(
                        "duplicate ByteDance job id across pages"
                    )
                seen.add(job.external_job_id)
                jobs.append(job)
        if len(jobs) != total:
            raise ByteDanceApiError(
                "ByteDance final job count does not match total"
            )
        return jobs


class ByteDanceSeedCampusAdapter:
    """Fetch the bounded Seed campus project through an injected page transport."""

    source_slug = "bytedance-seed-campus"
    descriptor = SourceDescriptor(
        source_slug=source_slug,
        source_name="字节跳动 2027 Seed 大模型人才校招",
        company_slug="bytedance",
        company_name="字节跳动",
        scope_key=f"project:{PROJECT_ID}",
        adapter_type="playwright-json",
        base_url=DETAIL_PREFIX,
    )
    page_size = 10
    max_pages = 20
    max_jobs = 200

    def __init__(
        self,
        fetch_page: Callable[[int], Mapping[str, object]] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._fetch_page = fetch_page or fetch_public_page
        self._clock = clock or utc_now_iso

    def fetch_jobs(self) -> list[JobSnapshot]:
        observed_at = self._clock()
        first = parse_bytedance_listing(
            self._fetch_page(1), observed_at=observed_at
        )
        if first.total > self.max_jobs:
            raise ByteDanceApiError(
                f"ByteDance project total {first.total} exceeds {self.max_jobs}"
            )
        page_total = ceil(first.total / self.page_size) if first.total else 1
        if page_total > self.max_pages:
            raise ByteDanceApiError(
                f"ByteDance page total {page_total} exceeds {self.max_pages}"
            )

        jobs = list(first.jobs)
        seen_ids = {job.external_job_id for job in jobs}
        for page_num in range(2, page_total + 1):
            page = parse_bytedance_listing(
                self._fetch_page(page_num), observed_at=observed_at
            )
            if page.total != first.total:
                raise ByteDanceApiError("ByteDance project total changed during crawl")
            for job in page.jobs:
                if job.external_job_id in seen_ids:
                    raise ByteDanceApiError("duplicate ByteDance job id across pages")
                seen_ids.add(job.external_job_id)
                jobs.append(job)
        if len(jobs) != first.total:
            raise ByteDanceApiError("ByteDance final job count does not match total")
        return jobs


def build_project_page_url(page_num: int) -> str:
    return _build_project_page_url(BYTEDANCE_SEED_PROJECT, page_num)


def _build_project_page_url(
    project: ByteDanceCampusProject,
    page_num: int,
) -> str:
    if page_num < 1:
        raise ValueError("page_num must be positive")
    return (
        f"{DETAIL_PREFIX}?keywords=&category=&location="
        f"&project={project.project_id}"
        f"&type=&job_hot_flag=&current={page_num}&limit=10"
        "&functionCategory=&tag="
    )


def _project_response_matches(
    response: object,
    project: ByteDanceCampusProject,
    expected_offset: int,
) -> bool:
    parsed = urlparse(getattr(response, "url", ""))
    request = getattr(response, "request", None)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "jobs.bytedance.com"
        or parsed.path != "/api/v1/search/job/posts"
        or getattr(request, "method", "") != "POST"
        or getattr(response, "status", None) != 200
    ):
        return False
    query = parse_qs(parsed.query)
    return (
        query.get("portal_type") == ["3"]
        and query.get("subject_id_list") == [project.project_id]
        and query.get("limit") == ["10"]
        and query.get("offset") == [str(expected_offset)]
    )


def _mainland_response_matches(
    response: object,
    scope: ByteDanceMainlandScope,
    filters: Mapping[str, object],
    expected_offset: int,
) -> bool:
    parsed = urlparse(getattr(response, "url", ""))
    request = getattr(response, "request", None)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "jobs.bytedance.com"
        or parsed.path != "/api/v1/search/job/posts"
        or getattr(request, "method", "") != "POST"
        or getattr(response, "status", None) != 200
    ):
        return False
    query = parse_qs(parsed.query)
    return (
        query.get("portal_type") == [scope.portal_type]
        and query.get("limit") == ["10"]
        and query.get("offset") == [str(expected_offset)]
        and query.get("location_code_list")
        == (
            [str(filters["location_code"])]
            if filters.get("location_code")
            else None
        )
        and query.get("job_category_id_list")
        == (
            [str(filters["category_id"])]
            if filters.get("category_id")
            else None
        )
    )


def _build_mainland_page_url(
    scope: ByteDanceMainlandScope,
    filters: Mapping[str, object],
    offset: int,
) -> str:
    if offset < 0 or offset % 10:
        raise ValueError("ByteDance offset must be a non-negative multiple of 10")
    query = urlencode(
        {
            "keywords": "",
            "category": filters.get("category_id") or "",
            "location": filters.get("location_code") or "",
            "current": offset // 10 + 1,
            "limit": 10,
        }
    )
    return f"{scope.page_url}?{query}"


def fetch_project_pages(
    project: ByteDanceCampusProject,
) -> list[Mapping[str, object]]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _fetch_project_pages_sync(project)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_fetch_project_pages_sync, project).result()


def _fetch_project_pages_sync(
    project: ByteDanceCampusProject,
) -> list[Mapping[str, object]]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ByteDanceAccessRestricted(
            "Playwright is unavailable; install the OpenWorker browser extra"
        ) from exc

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.set_default_timeout(20_000)

                def block_heavy(route: object) -> None:
                    if route.request.resource_type in {"image", "media", "font"}:
                        route.abort()
                    else:
                        route.continue_()

                page.route("**/*", block_heavy)

                def load(page_num: int) -> Mapping[str, object]:
                    offset = (page_num - 1) * 10
                    with page.expect_response(
                        lambda response: _project_response_matches(
                            response,
                            project,
                            offset,
                        ),
                        timeout=20_000,
                    ) as response_info:
                        page.goto(
                            _build_project_page_url(project, page_num),
                            wait_until="domcontentloaded",
                            timeout=20_000,
                        )
                    response = response_info.value
                    if response.status != 200:
                        raise ByteDanceAccessRestricted(
                            f"ByteDance listing returned HTTP {response.status}"
                        )
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise ByteDanceAccessRestricted(
                            "ByteDance response JSON must be an object"
                        )
                    return payload

                first = load(1)
                data = first.get("data")
                if not isinstance(data, dict):
                    raise ByteDanceApiError(
                        "ByteDance API data must be an object"
                    )
                total = _required_int(data, "count")
                if total > project.max_jobs:
                    raise ByteDanceApiError(
                        f"ByteDance project total {total} exceeds "
                        f"{project.max_jobs}"
                    )
                page_count = ceil(total / 10) if total else 1
                if page_count > 20:
                    raise ByteDanceApiError(
                        "ByteDance page total exceeds 20"
                    )
                return [
                    first,
                    *(load(number) for number in range(2, page_count + 1)),
                ]
            finally:
                browser.close()
    except (ByteDanceApiError, ByteDanceAccessRestricted):
        raise
    except (PlaywrightTimeoutError, PlaywrightError) as exc:
        raise ByteDanceAccessRestricted(
            "ByteDance public page did not produce the expected listing response"
        ) from exc


def fetch_mainland_filters(
    scope: ByteDanceMainlandScope,
) -> Mapping[str, object]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _fetch_mainland_filters_sync(scope)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(
            _fetch_mainland_filters_sync,
            scope,
        ).result()


def fetch_mainland_page(
    scope: ByteDanceMainlandScope,
    filters: Mapping[str, object],
    offset: int,
) -> Mapping[str, object]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _fetch_mainland_page_sync(scope, filters, offset)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(
            _fetch_mainland_page_sync,
            scope,
            filters,
            offset,
        ).result()


def fetch_mainland_pages(
    scope: ByteDanceMainlandScope,
    filters: Mapping[str, object],
    offset: int,
    limit: int,
) -> list[Mapping[str, object]]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _fetch_mainland_pages_sync(
            scope,
            filters,
            offset,
            limit,
        )
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(
            _fetch_mainland_pages_sync,
            scope,
            filters,
            offset,
            limit,
        ).result()


def classify_bytedance_detail_text(text: str) -> str:
    if "该职位已下线" in text:
        return "offline"
    if "职位描述" in text and "职位要求" in text:
        return "active"
    return "unknown"


def verify_mainland_job_details(
    scope: ByteDanceMainlandScope,
    snapshots: list[JobSnapshot],
) -> dict[str, str]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _verify_mainland_job_details_sync(scope, snapshots)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(
            _verify_mainland_job_details_sync,
            scope,
            snapshots,
        ).result()


def _verify_mainland_job_details_sync(
    scope: ByteDanceMainlandScope,
    snapshots: list[JobSnapshot],
) -> dict[str, str]:
    if not 1 <= len(snapshots) <= 20:
        raise ValueError(
            "ByteDance stale detail verification requires 1 to 20 jobs"
        )
    if any(not job.external_job_id.isdigit() for job in snapshots):
        raise ByteDanceApiError(
            "ByteDance detail verification requires numeric job ids"
        )
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ByteDanceAccessRestricted(
            "Playwright is unavailable; install the OpenWorker browser extra"
        ) from exc

    results: dict[str, str] = {}
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.set_default_timeout(20_000)

                def block_heavy(route: object) -> None:
                    if route.request.resource_type in {
                        "image",
                        "media",
                        "font",
                    }:
                        route.abort()
                    else:
                        route.continue_()

                page.route("**/*", block_heavy)
                for snapshot in snapshots:
                    detail_url = (
                        f"{scope.page_url}/"
                        f"{snapshot.external_job_id}/detail"
                    )
                    page.goto(
                        detail_url,
                        wait_until="domcontentloaded",
                        timeout=20_000,
                    )
                    parsed = urlparse(page.url)
                    if (
                        parsed.scheme != "https"
                        or parsed.hostname != "jobs.bytedance.com"
                        or parsed.path
                        != urlparse(detail_url).path
                    ):
                        raise ByteDanceAccessRestricted(
                            "unexpected ByteDance detail redirect"
                        )
                    page.wait_for_function(
                        """
                        () => {
                          const text = document.body?.innerText || "";
                          return text.includes("该职位已下线")
                            || (
                              text.includes("职位描述")
                              && text.includes("职位要求")
                            );
                        }
                        """,
                        timeout=20_000,
                    )
                    status = classify_bytedance_detail_text(
                        page.locator("body").inner_text()
                    )
                    if status == "unknown":
                        raise ByteDanceAccessRestricted(
                            "ByteDance detail page could not be classified"
                        )
                    results[snapshot.external_job_id] = status
            finally:
                browser.close()
    except (ByteDanceApiError, ByteDanceAccessRestricted):
        raise
    except Exception as exc:
        raise ByteDanceAccessRestricted(
            "ByteDance stale detail verification did not complete"
        ) from exc
    return results


def _fetch_mainland_filters_sync(
    scope: ByteDanceMainlandScope,
) -> Mapping[str, object]:
    expected_path = f"/api/v1/config/job/filters/{scope.portal_type}"

    def matches(response: object) -> bool:
        parsed = urlparse(getattr(response, "url", ""))
        request = getattr(response, "request", None)
        return (
            parsed.scheme == "https"
            and parsed.hostname == "jobs.bytedance.com"
            and parsed.path == expected_path
            and getattr(request, "method", "") == "GET"
            and getattr(response, "status", None) == 200
        )

    return _fetch_mainland_browser_response(
        scope.page_url,
        matches,
    )


def _fetch_mainland_page_sync(
    scope: ByteDanceMainlandScope,
    filters: Mapping[str, object],
    offset: int,
) -> Mapping[str, object]:
    return _fetch_mainland_browser_response(
        _build_mainland_page_url(scope, filters, offset),
        lambda response: _mainland_response_matches(
            response,
            scope,
            filters,
            offset,
        ),
    )


def _fetch_mainland_pages_sync(
    scope: ByteDanceMainlandScope,
    filters: Mapping[str, object],
    offset: int,
    limit: int,
) -> list[Mapping[str, object]]:
    if not 1 <= limit <= 100:
        raise ValueError(
            "ByteDance browser batch limit must be between 1 and 100"
        )
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ByteDanceAccessRestricted(
            "Playwright is unavailable; install the OpenWorker browser extra"
        ) from exc
    payloads: list[Mapping[str, object]] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()

                def block_heavy(route: object) -> None:
                    if route.request.resource_type in {
                        "image",
                        "media",
                        "font",
                    }:
                        route.abort()
                    else:
                        route.continue_()

                page.route("**/*", block_heavy)
                for index in range(limit):
                    current_offset = offset + index * 10
                    with page.expect_response(
                        lambda response, expected=current_offset: (
                            _mainland_response_matches(
                                response,
                                scope,
                                filters,
                                expected,
                            )
                        ),
                        timeout=20_000,
                    ) as response_info:
                        page.goto(
                            _build_mainland_page_url(
                                scope,
                                filters,
                                current_offset,
                            ),
                            wait_until="domcontentloaded",
                            timeout=20_000,
                        )
                    payload = response_info.value.json()
                    if not isinstance(payload, dict):
                        raise ByteDanceAccessRestricted(
                            "ByteDance response JSON must be an object"
                        )
                    payloads.append(payload)
                    data = payload.get("data")
                    if not isinstance(data, dict):
                        raise ByteDanceApiError(
                            "ByteDance API data must be an object"
                        )
                    total = _required_int(data, "count")
                    if current_offset + 10 >= total:
                        break
            finally:
                browser.close()
    except (ByteDanceApiError, ByteDanceAccessRestricted):
        raise
    except Exception as exc:
        raise ByteDanceAccessRestricted(
            "ByteDance public page batch did not complete"
        ) from exc
    return payloads


def _fetch_mainland_browser_response(
    page_url: str,
    response_matcher: Callable[[object], bool],
) -> Mapping[str, object]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ByteDanceAccessRestricted(
            "Playwright is unavailable; install the OpenWorker browser extra"
        ) from exc
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()

                def block_heavy(route: object) -> None:
                    resource_type = route.request.resource_type
                    if resource_type in {"image", "media", "font"}:
                        route.abort()
                    else:
                        route.continue_()

                page.route("**/*", block_heavy)
                with page.expect_response(
                    response_matcher,
                    timeout=20_000,
                ) as response_info:
                    page.goto(
                        page_url,
                        wait_until="domcontentloaded",
                        timeout=20_000,
                    )
                response = response_info.value
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ByteDanceAccessRestricted(
                        "ByteDance response JSON must be an object"
                    )
                return payload
            finally:
                browser.close()
    except (ByteDanceApiError, ByteDanceAccessRestricted):
        raise
    except Exception as exc:
        raise ByteDanceAccessRestricted(
            "ByteDance public page did not produce the expected response"
        ) from exc


def fetch_public_page(page_num: int) -> Mapping[str, object]:
    """Keep sync Playwright off a FastMCP asyncio event-loop thread."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _fetch_public_page_sync(page_num)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_fetch_public_page_sync, page_num).result()


def _fetch_public_page_sync(page_num: int) -> Mapping[str, object]:
    """Load one public project page and consume its first-party listing response."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise ByteDanceAccessRestricted(
            "Playwright is unavailable; install the OpenWorker browser extra"
        ) from exc

    page_url = build_project_page_url(page_num)
    expected_offset = (page_num - 1) * ByteDanceSeedCampusAdapter.page_size

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.set_default_timeout(20_000)

                def block_heavy(route: object) -> None:
                    resource_type = route.request.resource_type
                    if resource_type in {"image", "media", "font"}:
                        route.abort()
                    else:
                        route.continue_()

                page.route("**/*", block_heavy)
                with page.expect_response(
                    lambda response: _project_response_matches(
                        response,
                        BYTEDANCE_SEED_PROJECT,
                        expected_offset,
                    ),
                    timeout=20_000,
                ) as response_info:
                    page.goto(page_url, wait_until="domcontentloaded", timeout=20_000)
                response = response_info.value
                if response.status != 200:
                    raise ByteDanceAccessRestricted(
                        f"ByteDance listing returned HTTP {response.status}"
                    )
                if urlparse(page.url).hostname != "jobs.bytedance.com":
                    raise ByteDanceAccessRestricted("unexpected ByteDance redirect host")
                title = page.title().lower()
                if "captcha" in title or "登录" == page.title().strip():
                    raise ByteDanceAccessRestricted("ByteDance access restriction page")
                payload = response.json()
            finally:
                browser.close()
    except ByteDanceAccessRestricted:
        raise
    except (PlaywrightTimeoutError, PlaywrightError) as exc:
        raise ByteDanceAccessRestricted(
            "ByteDance public page did not produce the expected listing response"
        ) from exc

    if not isinstance(payload, dict):
        raise ByteDanceAccessRestricted("ByteDance response JSON must be an object")
    return payload


def parse_bytedance_listing(
    payload: Mapping[str, object],
    *,
    observed_at: str,
    project: ByteDanceCampusProject = BYTEDANCE_SEED_PROJECT,
) -> ByteDanceListingPage:
    """Parse one public Seed project response without browser dependencies."""
    if payload.get("code") != 0:
        raise ByteDanceApiError(f"ByteDance API returned code {payload.get('code')}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ByteDanceApiError("ByteDance API data must be an object")
    entries = data.get("job_post_list")
    if not isinstance(entries, list):
        raise ByteDanceApiError("ByteDance job_post_list must be a list")
    total = _required_int(data, "count")

    jobs: list[JobSnapshot] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ByteDanceApiError("ByteDance job must be an object")
        job_id = _required_text(entry, "id")
        if not job_id.isdigit():
            raise ByteDanceApiError("ByteDance job id must be numeric")
        if job_id in seen_ids:
            raise ByteDanceApiError("duplicate ByteDance job id")
        seen_ids.add(job_id)
        _validate_project(entry.get("job_subject"), project)
        description = _required_text(entry, "description")
        requirement = _required_text(entry, "requirement")
        code = _required_text(entry, "code")
        jobs.append(
            JobSnapshot(
                external_job_id=job_id,
                title=_required_text(entry, "title"),
                description_raw=(
                    f"职位描述：{description}\n\n"
                    f"职位要求：{requirement}\n\n"
                    f"职位 ID：{code}\n\n"
                    f"招聘项目：{project.project_name}"
                ),
                source_url=f"{DETAIL_PREFIX}/{job_id}/detail",
                observed_at=observed_at,
                location_raw=_locations(entry.get("city_list")),
                recruitment_type=_recruitment_type(entry.get("recruit_type")),
            )
        )
    return ByteDanceListingPage(jobs=jobs, total=total)


def parse_bytedance_filter_metadata(
    payload: Mapping[str, object],
) -> dict[str, list[dict[str, str]]]:
    if payload.get("code") != 0:
        raise ByteDanceApiError(
            f"ByteDance filter API returned code {payload.get('code')}"
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ByteDanceApiError(
            "ByteDance filter API data must be an object"
        )
    cities = data.get("city_list")
    categories = data.get("job_type_list")
    if not isinstance(cities, list) or not isinstance(categories, list):
        raise ByteDanceApiError(
            "ByteDance filter metadata lists are invalid"
        )
    mainland: list[dict[str, str]] = []
    for city in cities:
        if not isinstance(city, dict):
            raise ByteDanceApiError(
                "ByteDance filter city must be an object"
            )
        code = _required_text(city, "code")
        name = _required_text(city, "name")
        if name in _MAINLAND_CITY_NAMES:
            mainland.append({"code": code, "name": name})
        elif name not in _NON_MAINLAND_CITY_NAMES:
            raise ByteDanceApiError(
                f"ByteDance city classification is unknown: {name}"
            )
    parsed_categories = []
    for category in categories:
        if not isinstance(category, dict):
            raise ByteDanceApiError(
                "ByteDance filter category must be an object"
            )
        parsed_categories.append(
            {
                "id": _required_text(category, "id"),
                "name": _required_text(category, "name"),
            }
        )
    if not mainland:
        raise ByteDanceApiError(
            "ByteDance filter metadata has no mainland cities"
        )
    return {
        "mainland_cities": mainland,
        "categories": parsed_categories,
    }


def parse_bytedance_scope_listing(
    payload: Mapping[str, object],
    *,
    observed_at: str,
    scope: ByteDanceMainlandScope,
    allowed_city_names: set[str],
) -> ByteDanceListingPage:
    if payload.get("code") != 0:
        raise ByteDanceApiError(
            f"ByteDance API returned code {payload.get('code')}"
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ByteDanceApiError("ByteDance API data must be an object")
    entries = data.get("job_post_list")
    if not isinstance(entries, list):
        raise ByteDanceApiError(
            "ByteDance job_post_list must be a list"
        )
    total = _required_int(data, "count")
    jobs: list[JobSnapshot] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ByteDanceApiError("ByteDance job must be an object")
        job_id = _required_text(entry, "id")
        if not job_id.isdigit():
            raise ByteDanceApiError(
                "ByteDance job id must be numeric"
            )
        if job_id in seen_ids:
            raise ByteDanceApiError("duplicate ByteDance job id")
        seen_ids.add(job_id)
        description = _required_text(entry, "description")
        requirement = _required_text(entry, "requirement")
        code = _required_text(entry, "code")
        locations = _scope_locations(
            entry.get("city_list"),
            allowed_city_names,
        )
        if not locations:
            continue
        recruit_type = entry.get("recruit_type")
        if not isinstance(recruit_type, dict):
            raise ByteDanceApiError(
                "ByteDance recruit_type must be an object"
            )
        recruitment_type = (
            "internship"
            if recruit_type.get("name") == "实习"
            else scope.recruitment_type
        )
        jobs.append(
            JobSnapshot(
                external_job_id=job_id,
                title=_required_text(entry, "title"),
                description_raw=(
                    f"职位描述：{description}\n\n"
                    f"职位要求：{requirement}\n\n"
                    f"职位 ID：{code}"
                ),
                source_url=(
                    f"{scope.page_url}/{job_id}/detail"
                ),
                observed_at=observed_at,
                location_raw="、".join(locations),
                recruitment_type=recruitment_type,
            )
        )
    return ByteDanceListingPage(jobs=jobs, total=total)


def _scope_locations(
    value: object,
    allowed_city_names: set[str],
) -> list[str]:
    if not isinstance(value, list):
        raise ByteDanceApiError("ByteDance city_list must be a list")
    names = []
    for city in value:
        if not isinstance(city, dict):
            raise ByteDanceApiError(
                "ByteDance city must be an object"
            )
        name = _required_text(city, "name")
        names.append(name)
    if not set(names) & allowed_city_names:
        return []
    return names


def _required_text(entry: Mapping[str, object], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ByteDanceApiError(f"ByteDance job {field} must be non-empty")
    return value.strip()


def _required_int(entry: Mapping[str, object], field: str) -> int:
    value = entry.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ByteDanceApiError(f"ByteDance {field} must be a non-negative integer")
    return value


def _validate_project(
    value: object,
    project: ByteDanceCampusProject,
) -> None:
    if not isinstance(value, dict) or value.get("id") != project.project_id:
        raise ByteDanceApiError("ByteDance job uses an unexpected project")
    name = value.get("name")
    if (
        not isinstance(name, dict)
        or name.get("zh_cn") != project.project_name
    ):
        raise ByteDanceApiError("ByteDance job uses an unexpected project name")


def _locations(value: object) -> str | None:
    if not isinstance(value, list):
        raise ByteDanceApiError("ByteDance city_list must be a list")
    names: list[str] = []
    for city in value:
        if not isinstance(city, dict):
            raise ByteDanceApiError("ByteDance city must be an object")
        name = city.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ByteDanceApiError("ByteDance city name must be non-empty")
        names.append(name.strip())
    return "、".join(names) or None


def _recruitment_type(value: object) -> str:
    if not isinstance(value, dict):
        raise ByteDanceApiError("ByteDance recruit_type must be an object")
    name = value.get("name")
    if name == "实习":
        return "internship"
    if name == "正式":
        return "campus"
    raise ByteDanceApiError("ByteDance recruitment type is unsupported")
