"""Official Moonshot/Kimi social-recruitment browser adapter."""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Mapping
from urllib.parse import urlparse
from uuid import UUID

from ..domain.crawler import JobSnapshot, SourceDescriptor
from ..domain.manual_jd import utc_now_iso

ENTRY_URL = "https://app.mokahr.com/apply/moonshot/148506#/jobs"
PAGE_SIZE = 30
MAX_PAGES = 20
KNOWN_CATEGORIES = {
    "算法类",
    "技术类",
    "产品类",
    "设计类",
    "市场类",
    "运营类",
    "职能类",
    "管理类",
}


class MoonshotDataError(ValueError):
    """The public Moonshot page violated its verified data contract."""


class MoonshotSocialAdapter:
    source_slug = "moonshot-social"
    descriptor = SourceDescriptor(
        source_slug=source_slug,
        source_name="月之暗面社会招聘",
        company_slug="moonshot",
        company_name="月之暗面",
        scope_key="social-all-public",
        adapter_type="playwright-rendered-dom",
        base_url=ENTRY_URL,
    )

    def __init__(
        self,
        *,
        fetch_dataset: Callable[[], list[Mapping[str, object]]] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._fetch_dataset = fetch_dataset or fetch_moonshot_dataset
        self._clock = clock or utc_now_iso

    def fetch_jobs(self) -> list[JobSnapshot]:
        pages = self._fetch_dataset()
        if not pages:
            raise MoonshotDataError("Moonshot dataset has no pages")
        page_count = _required_int(pages[0], "page_count")
        if not 1 <= page_count <= MAX_PAGES or len(pages) != page_count:
            raise MoonshotDataError("Moonshot page count is invalid")

        observed_at = self._clock()
        jobs: list[JobSnapshot] = []
        seen: set[str] = set()
        for expected_page, page in enumerate(pages, start=1):
            if _required_int(page, "page") != expected_page:
                raise MoonshotDataError("Moonshot pages are not sequential")
            if _required_int(page, "page_count") != page_count:
                raise MoonshotDataError("Moonshot page count changed during crawl")
            if _required_int(page, "page_size") != PAGE_SIZE:
                raise MoonshotDataError("Moonshot page size changed")
            raw_jobs = page.get("jobs")
            if not isinstance(raw_jobs, list):
                raise MoonshotDataError("Moonshot jobs must be a list")
            if expected_page < page_count and len(raw_jobs) != PAGE_SIZE:
                raise MoonshotDataError("Moonshot non-final page must contain 30 jobs")
            if expected_page == page_count and not 1 <= len(raw_jobs) <= PAGE_SIZE:
                raise MoonshotDataError("Moonshot final page is empty or oversized")
            for raw in raw_jobs:
                if not isinstance(raw, dict):
                    raise MoonshotDataError("Moonshot job must be an object")
                job = parse_moonshot_card(raw, observed_at=observed_at)
                if job.external_job_id in seen:
                    raise MoonshotDataError("duplicate Moonshot UUID")
                seen.add(job.external_job_id)
                jobs.append(job)
        if len(jobs) > MAX_PAGES * PAGE_SIZE:
            raise MoonshotDataError("Moonshot job count exceeds safety limit")
        return jobs


def parse_moonshot_card(
    raw: Mapping[str, object],
    *,
    observed_at: str,
) -> JobSnapshot:
    href = _required_text(raw, "href")
    prefix = "#/job/"
    if not href.startswith(prefix):
        raise MoonshotDataError("Moonshot href must contain a UUID")
    job_id = href.removeprefix(prefix)
    try:
        parsed_id = UUID(job_id)
    except ValueError as exc:
        raise MoonshotDataError("Moonshot href must contain a UUID") from exc
    if str(parsed_id) != job_id:
        raise MoonshotDataError("Moonshot UUID must be canonical")

    metadata = raw.get("metadata")
    if (
        not isinstance(metadata, list)
        or not 1 <= len(metadata) <= 3
        or any(not isinstance(value, str) or not value.strip() for value in metadata)
    ):
        raise MoonshotDataError("Moonshot metadata is invalid")
    values = [value.strip() for value in metadata]
    if values[0] != "全职":
        raise MoonshotDataError("Moonshot job escaped full-time recruitment")

    category: str | None = None
    location: str | None = None
    if len(values) == 3:
        category, location = values[1], values[2]
        if category not in KNOWN_CATEGORIES:
            raise MoonshotDataError("unknown Moonshot category")
    elif len(values) == 2:
        if values[1] in KNOWN_CATEGORIES:
            category = values[1]
        elif _looks_like_location(values[1]):
            location = values[1]
        else:
            raise MoonshotDataError("ambiguous Moonshot metadata")

    published_at = _required_text(raw, "published_at")
    if not published_at.startswith("发布于 "):
        raise MoonshotDataError("Moonshot published_at is invalid")
    description = _required_text(raw, "description")
    fields = [f"发布日期：{published_at.removeprefix('发布于 ').strip()}"]
    if category is not None:
        fields.append(f"职类：{category}")
    fields.append(f"职位描述：\n{description}")
    return JobSnapshot(
        external_job_id=job_id,
        title=_required_text(raw, "title"),
        description_raw="\n\n".join(fields),
        source_url=(
            "https://app.mokahr.com/apply/moonshot/148506"
            f"#/job/{job_id}"
        ),
        observed_at=observed_at,
        location_raw=location,
        recruitment_type="experienced",
    )


def fetch_moka_dom_pages(
    entry_url: str,
) -> list[Mapping[str, object]]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _fetch_moka_dom_pages_sync(entry_url)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_fetch_moka_dom_pages_sync, entry_url).result()


def fetch_moonshot_dataset() -> list[Mapping[str, object]]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _fetch_moonshot_dataset_sync()
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_fetch_moonshot_dataset_sync).result()


def _fetch_moonshot_dataset_sync() -> list[Mapping[str, object]]:
    return _fetch_moka_dom_pages_sync(ENTRY_URL)


def _fetch_moka_dom_pages_sync(
    entry_url: str,
) -> list[Mapping[str, object]]:
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

                def load_page(page_number: int) -> dict[str, object]:
                    if time.monotonic() - started > 110:
                        raise RuntimeError(
                            "Moonshot browser crawl exceeded 110 seconds"
                        )
                    page = context.new_page()
                    try:
                        page.set_default_timeout(15_000)

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
                        page.goto(
                            f"{entry_url}?page={page_number}"
                            "&anchorName=jobsList",
                            wait_until="networkidle",
                            timeout=30_000,
                        )
                        parsed = urlparse(page.url)
                        if (
                            parsed.scheme != "https"
                            or parsed.hostname != "app.mokahr.com"
                        ):
                            raise RuntimeError("unexpected Moonshot redirect")
                        page.wait_for_selector(
                            'a[href*="/job/"] div[class*="card-content"]',
                            timeout=15_000,
                        )
                        page_buttons = page.locator(
                            'ul[class^="sd-Pagination-ul"] '
                            "button[data-page]"
                        )
                        page_numbers = [
                            int(page_buttons.nth(index).get_attribute("data-page"))
                            for index in range(page_buttons.count())
                        ]
                        if (
                            not page_numbers
                            or page_numbers != list(
                                range(1, max(page_numbers) + 1)
                            )
                        ):
                            raise MoonshotDataError(
                                "Moonshot pagination controls are invalid"
                            )

                        cards = page.locator('a[href*="/job/"]').filter(
                            has=page.locator('div[class*="card-content"]')
                        )
                        jobs = cards.evaluate_all(
                            """cards => cards.map(card => ({
                                href: card.getAttribute("href"),
                                title: card.querySelector(
                                    'span[class^="title-"]'
                                )?.innerText.trim() ?? "",
                                published_at: card.querySelector(
                                    'span[class^="published-at-"]'
                                )?.innerText.trim() ?? "",
                                metadata: Array.from(card.querySelectorAll(
                                    'div[class^="info-"] div.no-adaptive-tooltip'
                                )).map(node => node.innerText.trim()),
                                description: card.querySelector(
                                    'div[class^="job-description-"]'
                                )?.innerText.trim() ?? ""
                            }))"""
                        )
                        return {
                            "page": page_number,
                            "page_count": max(page_numbers),
                            "page_size": PAGE_SIZE,
                            "jobs": jobs,
                        }
                    finally:
                        page.close()

                first = load_page(1)
                page_count = _required_int(first, "page_count")
                if not 1 <= page_count <= MAX_PAGES:
                    raise MoonshotDataError("Moonshot page count is invalid")
                return [
                    first,
                    *(load_page(number) for number in range(2, page_count + 1)),
                ]
            finally:
                browser.close()
    except MoonshotDataError:
        raise
    except (PlaywrightTimeoutError, PlaywrightError) as exc:
        raise RuntimeError(
            "Moonshot public page did not produce the expected dataset"
        ) from exc


def _looks_like_location(value: str) -> bool:
    return any(
        marker in value
        for marker in ("市", "省", "自治区", "美国", "新加坡", "香港", "澳门")
    )


def _required_text(entry: Mapping[str, object], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise MoonshotDataError(f"Moonshot {field} must be non-empty")
    return value.strip()


def _required_int(entry: Mapping[str, object], field: str) -> int:
    value = entry.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise MoonshotDataError(
            f"Moonshot {field} must be a non-negative integer"
        )
    return value
