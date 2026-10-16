"""Official Xiaohongshu social-recruitment browser adapter."""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Mapping
from urllib.parse import urlparse

from ..domain.crawler import JobSnapshot, SourceDescriptor
from ..domain.manual_jd import utc_now_iso

ENTRY_URL = "https://job.xiaohongshu.com/social/position"
TARGET_PATH = "/websiterecruit/position/pageQueryPosition"
MAX_JOBS = 1_000


class XiaohongshuDataError(ValueError):
    pass


@dataclass(frozen=True)
class XiaohongshuPage:
    jobs: list[JobSnapshot]
    total: int
    page: int
    total_pages: int


class XiaohongshuSocialAdapter:
    source_slug = "xiaohongshu-social-cn"
    descriptor = SourceDescriptor(
        source_slug=source_slug,
        source_name="小红书社会招聘",
        company_slug="xiaohongshu",
        company_name="小红书",
        scope_key="social-all-public",
        adapter_type="playwright-signed-page-json",
        base_url=ENTRY_URL,
    )

    def __init__(
        self,
        *,
        fetch_pages: Callable[[], list[Mapping[str, object]]] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._fetch_pages = fetch_pages or fetch_xiaohongshu_pages
        self._clock = clock or utc_now_iso

    def fetch_jobs(self) -> list[JobSnapshot]:
        payloads = self._fetch_pages()
        if not payloads:
            raise XiaohongshuDataError("Xiaohongshu dataset has no pages")
        observed_at = self._clock()
        pages = [
            parse_xiaohongshu_page(payload, observed_at=observed_at)
            for payload in payloads
        ]
        total = pages[0].total
        total_pages = pages[0].total_pages
        if not 1 <= total <= MAX_JOBS:
            raise XiaohongshuDataError("Xiaohongshu total exceeds safety limit")
        if len(pages) % total_pages != 0 or len(pages) > total_pages * 4:
            raise XiaohongshuDataError("Xiaohongshu page count is invalid")

        jobs_by_id: dict[str, JobSnapshot] = {}
        for index, page in enumerate(pages):
            expected_page = index % total_pages + 1
            if (
                page.total != total
                or page.total_pages != total_pages
                or page.page != expected_page
            ):
                raise XiaohongshuDataError(
                    "Xiaohongshu pagination changed during crawl"
                )
            for job in page.jobs:
                existing = jobs_by_id.get(job.external_job_id)
                if existing is not None and existing != job:
                    raise XiaohongshuDataError(
                        "Xiaohongshu job changed between pagination passes"
                    )
                jobs_by_id[job.external_job_id] = job
        if len(jobs_by_id) != total:
            raise XiaohongshuDataError(
                "Xiaohongshu job count does not match total"
            )
        return list(jobs_by_id.values())


def parse_xiaohongshu_page(
    payload: Mapping[str, object],
    *,
    observed_at: str,
) -> XiaohongshuPage:
    if payload.get("success") is not True or payload.get("statusCode") != 200:
        raise XiaohongshuDataError("Xiaohongshu API returned an error")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise XiaohongshuDataError("Xiaohongshu data must be an object")
    entries = data.get("list")
    if not isinstance(entries, list):
        raise XiaohongshuDataError("Xiaohongshu data.list must be a list")
    jobs: list[JobSnapshot] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise XiaohongshuDataError("Xiaohongshu job must be an object")
        job_id = _required_text(entry, "positionId")
        if not job_id.isdigit() or job_id in seen:
            raise XiaohongshuDataError(
                "invalid or duplicate Xiaohongshu positionId"
            )
        seen.add(job_id)
        if _required_text(entry, "recruitStatus") != "in_recruitment":
            raise XiaohongshuDataError("Xiaohongshu job is not recruiting")
        job_type = _required_text(entry, "jobType")
        jobs.append(
            JobSnapshot(
                external_job_id=job_id,
                title=_required_text(entry, "positionName"),
                description_raw="\n\n".join(
                    [
                        f"职类：{job_type}",
                        f"发布日期：{_required_text(entry, 'publishTime')}",
                        f"岗位职责：\n{_required_text(entry, 'duty')}",
                        f"岗位要求：\n{_required_text(entry, 'qualification')}",
                    ]
                ),
                source_url=(
                    "https://job.xiaohongshu.com/social/position/"
                    f"{job_id}/apply"
                ),
                observed_at=observed_at,
                location_raw=_optional_text(entry.get("workplace")),
                recruitment_type="experienced",
            )
        )
    return XiaohongshuPage(
        jobs=jobs,
        total=_required_int(data, "total"),
        page=_required_int(data, "pageNum"),
        total_pages=_required_int(data, "totalPage"),
    )


def fetch_xiaohongshu_pages() -> list[Mapping[str, object]]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _fetch_xiaohongshu_pages_sync()
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_fetch_xiaohongshu_pages_sync).result()


def _fetch_xiaohongshu_pages_sync() -> list[Mapping[str, object]]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is unavailable; install the OpenWorker browser extra"
        ) from exc

    started = time.monotonic()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.set_default_timeout(15_000)

                def block_heavy(route: object) -> None:
                    if route.request.resource_type in {"image", "media", "font"}:
                        route.abort()
                    else:
                        route.continue_()

                page.route("**/*", block_heavy)
                payloads: list[Mapping[str, object]] = []
                jobs_by_id: dict[str, str] = {}
                expected_total: int | None = None
                for _ in range(4):
                    if time.monotonic() - started > 110:
                        raise RuntimeError(
                            "Xiaohongshu browser crawl exceeded 110 seconds"
                        )
                    with page.expect_response(
                        lambda response: TARGET_PATH in response.url,
                        timeout=30_000,
                    ) as first_info:
                        page.goto(
                            ENTRY_URL,
                            wait_until="domcontentloaded",
                            timeout=30_000,
                        )
                    parsed = urlparse(page.url)
                    if (
                        parsed.scheme != "https"
                        or parsed.hostname != "job.xiaohongshu.com"
                    ):
                        raise RuntimeError("unexpected Xiaohongshu redirect")
                    first = first_info.value.json()
                    if not isinstance(first, dict):
                        raise XiaohongshuDataError(
                            "Xiaohongshu response must be an object"
                        )
                    current_pass = [first]
                    first_data = first.get("data")
                    if not isinstance(first_data, dict):
                        raise XiaohongshuDataError(
                            "Xiaohongshu data must be an object"
                        )
                    total = _required_int(first_data, "total")
                    total_pages = _required_int(first_data, "totalPage")
                    if expected_total is None:
                        expected_total = total
                    elif total != expected_total:
                        raise XiaohongshuDataError(
                            "Xiaohongshu total changed during crawl"
                        )
                    for page_number in range(2, total_pages + 1):
                        if time.monotonic() - started > 110:
                            raise RuntimeError(
                                "Xiaohongshu browser crawl exceeded 110 seconds"
                            )
                        with page.expect_response(
                            lambda response: TARGET_PATH in response.url,
                            timeout=10_000,
                        ) as page_info:
                            page.locator("li.ant-pagination-next").click()
                        payload = page_info.value.json()
                        if not isinstance(payload, dict):
                            raise XiaohongshuDataError(
                                "Xiaohongshu response must be an object"
                            )
                        data = payload.get("data")
                        if (
                            not isinstance(data, dict)
                            or _required_int(data, "pageNum") != page_number
                        ):
                            raise XiaohongshuDataError(
                                "Xiaohongshu page number changed"
                            )
                        current_pass.append(payload)
                    payloads.extend(current_pass)
                    for payload in current_pass:
                        data = payload.get("data")
                        if not isinstance(data, dict):
                            continue
                        entries = data.get("list")
                        if not isinstance(entries, list):
                            continue
                        for entry in entries:
                            if not isinstance(entry, dict):
                                continue
                            job_id = _required_text(entry, "positionId")
                            canonical = repr(sorted(entry.items()))
                            if (
                                job_id in jobs_by_id
                                and jobs_by_id[job_id] != canonical
                            ):
                                raise XiaohongshuDataError(
                                    "Xiaohongshu job changed between passes"
                                )
                            jobs_by_id[job_id] = canonical
                    if len(jobs_by_id) == expected_total:
                        break
                return payloads
            finally:
                browser.close()
    except XiaohongshuDataError:
        raise
    except (PlaywrightTimeoutError, PlaywrightError) as exc:
        raise RuntimeError(
            "Xiaohongshu public page did not produce the expected dataset"
        ) from exc


def _required_text(entry: Mapping[str, object], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, (str, int)) or not str(value).strip():
        raise XiaohongshuDataError(
            f"Xiaohongshu {field} must be non-empty"
        )
    return str(value).strip()


def _required_int(entry: Mapping[str, object], field: str) -> int:
    value = entry.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise XiaohongshuDataError(
            f"Xiaohongshu {field} must be a non-negative integer"
        )
    return value


def _optional_text(value: object) -> str | None:
    return str(value).strip() if value is not None and str(value).strip() else None
