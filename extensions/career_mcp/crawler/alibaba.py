"""Alibaba business-site adapter using a fresh first-party browser context."""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Mapping
from urllib.parse import urlparse

from ..domain.crawler import JobSnapshot, SourceDescriptor
from ..domain.manual_jd import utc_now_iso


class AlibabaDataError(ValueError):
    pass


@dataclass(frozen=True)
class AlibabaScope:
    source_slug: str
    source_name: str
    base_url: str
    route: str
    max_jobs: int


@dataclass(frozen=True)
class AlibabaPage:
    jobs: list[JobSnapshot]
    total: int
    page: int


ALIBABA_TONGYI_SCOPE = AlibabaScope(
    source_slug="alibaba-token-foundry-social",
    source_name="阿里巴巴 Token Foundry 社会招聘",
    base_url="https://careers-tongyi.alibaba.com",
    route="/off-campus/position-list?lang=zh",
    max_jobs=100,
)


class AlibabaCareersAdapter:
    def __init__(
        self,
        scope: AlibabaScope,
        *,
        fetch_pages: Callable[
            [AlibabaScope], list[Mapping[str, object]]
        ] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.scope = scope
        self.source_slug = scope.source_slug
        self.descriptor = SourceDescriptor(
            source_slug=scope.source_slug,
            source_name=scope.source_name,
            company_slug="alibaba",
            company_name="阿里巴巴",
            scope_key=f"business:{scope.source_slug}",
            adapter_type="playwright-first-party-json",
            base_url=scope.base_url + scope.route,
        )
        self._fetch_pages = fetch_pages or fetch_alibaba_pages
        self._clock = clock or utc_now_iso

    def fetch_jobs(self) -> list[JobSnapshot]:
        payloads = self._fetch_pages(self.scope)
        if not payloads:
            raise AlibabaDataError("Alibaba dataset has no pages")
        observed_at = self._clock()
        pages = [
            parse_alibaba_page(
                payload,
                scope=self.scope,
                observed_at=observed_at,
            )
            for payload in payloads
        ]
        total = pages[0].total
        if total > self.scope.max_jobs:
            raise AlibabaDataError("Alibaba total exceeds scope safety limit")
        jobs: list[JobSnapshot] = []
        seen: set[str] = set()
        for expected_page, page in enumerate(pages, start=1):
            if page.total != total or page.page != expected_page:
                raise AlibabaDataError("Alibaba pagination changed during crawl")
            for job in page.jobs:
                if job.external_job_id in seen:
                    raise AlibabaDataError("duplicate Alibaba position id")
                seen.add(job.external_job_id)
                jobs.append(job)
        if len(jobs) != total:
            raise AlibabaDataError("Alibaba job count does not match total")
        return jobs


def parse_alibaba_page(
    payload: Mapping[str, object],
    *,
    scope: AlibabaScope,
    observed_at: str,
) -> AlibabaPage:
    if payload.get("success") is not True:
        raise AlibabaDataError("Alibaba API returned an error")
    content = payload.get("content")
    if not isinstance(content, dict):
        raise AlibabaDataError("Alibaba content must be an object")
    entries = content.get("datas")
    if not isinstance(entries, list):
        raise AlibabaDataError("Alibaba content.datas must be a list")
    jobs: list[JobSnapshot] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise AlibabaDataError("Alibaba job must be an object")
        job_id = _required_text(entry, "id")
        if not job_id.isdigit():
            raise AlibabaDataError("Alibaba id must be numeric")
        categories = _text_list(entry.get("categories"), "categories")
        locations = _text_list(entry.get("workLocations"), "workLocations")
        description = _required_text(entry, "description")
        requirement = _required_text(entry, "requirement")
        fields = []
        if categories:
            fields.append(f"职类：{'、'.join(categories)}")
        department = entry.get("department")
        if department is not None and str(department).strip():
            fields.append(f"部门：{str(department).strip()}")
        fields.extend(
            [
                f"岗位职责：\n{description}",
                f"岗位要求：\n{requirement}",
            ]
        )
        jobs.append(
            JobSnapshot(
                external_job_id=job_id,
                title=_required_text(entry, "name"),
                description_raw="\n\n".join(fields),
                source_url=(
                    f"{scope.base_url}/off-campus/position-detail"
                    f"?positionId={job_id}"
                ),
                observed_at=observed_at,
                location_raw="、".join(locations) if locations else None,
                recruitment_type="experienced",
            )
        )
    return AlibabaPage(
        jobs=jobs,
        total=_required_int(content, "totalCount"),
        page=_required_int(content, "currentPage"),
    )


def fetch_alibaba_pages(
    scope: AlibabaScope,
) -> list[Mapping[str, object]]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _fetch_alibaba_pages_sync(scope)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_fetch_alibaba_pages_sync, scope).result()


def _fetch_alibaba_pages_sync(
    scope: AlibabaScope,
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
                page = context.new_page()
                requests = []
                page.on(
                    "request",
                    lambda request: requests.append(request)
                    if "/position/search?" in request.url
                    else None,
                )
                page.goto(
                    scope.base_url + scope.route,
                    wait_until="networkidle",
                    timeout=30_000,
                )
                parsed = urlparse(page.url)
                expected = urlparse(scope.base_url)
                if parsed.scheme != "https" or parsed.hostname != expected.hostname:
                    raise RuntimeError("unexpected Alibaba redirect")
                if not requests:
                    raise AlibabaDataError(
                        "Alibaba page did not issue a position request"
                    )
                initial = requests[-1]
                body = dict(initial.post_data_json)
                body["pageSize"] = 500
                body["pageIndex"] = 1
                payloads: list[Mapping[str, object]] = []
                observed = 0
                while True:
                    if time.monotonic() - started > 110:
                        raise RuntimeError(
                            "Alibaba browser crawl exceeded 110 seconds"
                        )
                    response = context.request.post(
                        initial.url,
                        data=body,
                        headers={"Referer": page.url},
                        timeout=20_000,
                    )
                    if response.status != 200:
                        raise RuntimeError(
                            f"Alibaba API returned HTTP {response.status}"
                        )
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise AlibabaDataError(
                            "Alibaba response must be an object"
                        )
                    payloads.append(payload)
                    content = payload.get("content")
                    if not isinstance(content, dict):
                        raise AlibabaDataError(
                            "Alibaba content must be an object"
                        )
                    rows = content.get("datas")
                    if not isinstance(rows, list):
                        raise AlibabaDataError(
                            "Alibaba content.datas must be a list"
                        )
                    observed += len(rows)
                    total = _required_int(content, "totalCount")
                    if total > scope.max_jobs:
                        raise AlibabaDataError(
                            "Alibaba total exceeds scope safety limit"
                        )
                    if observed >= total:
                        break
                    if not rows:
                        raise AlibabaDataError(
                            "Alibaba pagination ended before total"
                        )
                    body["pageIndex"] = int(body["pageIndex"]) + 1
                return payloads
            finally:
                browser.close()
    except AlibabaDataError:
        raise
    except (PlaywrightTimeoutError, PlaywrightError) as exc:
        raise RuntimeError(
            "Alibaba public page did not produce the expected dataset"
        ) from exc


def _required_text(entry: Mapping[str, object], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, (str, int)) or not str(value).strip():
        raise AlibabaDataError(f"Alibaba {field} must be non-empty")
    return str(value).strip()


def _required_int(entry: Mapping[str, object], field: str) -> int:
    value = entry.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AlibabaDataError(
            f"Alibaba {field} must be a non-negative integer"
        )
    return value


def _text_list(value: object, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise AlibabaDataError(f"Alibaba {field} must be a text list")
    return [item.strip() for item in value]
