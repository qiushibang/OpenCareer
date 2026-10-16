"""Pure parsing for Kuaishou's public domestic social-recruitment data."""

from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from math import ceil
from typing import Callable, Mapping

from ..domain.crawler import JobSnapshot, SourceDescriptor
from ..domain.manual_jd import utc_now_iso

ENTRY_URL = (
    "https://zhaopin.kuaishou.cn/recruit/#/official/social/"
    "?workLocationCode=domestic"
)
_BROWSER_CRAWL_TIMEOUT_SECONDS = 280


class KuaishouDataError(ValueError):
    """Kuaishou public data violated the verified page contract."""


@dataclass(frozen=True)
class KuaishouDictionary:
    locations: dict[str, str]
    categories: dict[str, str]
    experiences: dict[str, str]


@dataclass(frozen=True)
class KuaishouPage:
    jobs: list[JobSnapshot]
    total: int


def _require_crawl_time_remaining(
    started: float,
    *,
    current: float,
) -> None:
    if current - started > _BROWSER_CRAWL_TIMEOUT_SECONDS:
        raise RuntimeError(
            "Kuaishou browser crawl exceeded 280 seconds"
        )


class KuaishouBrowserAdapter:
    source_slug = "kuaishou-social-cn"
    page_size = 10
    descriptor = SourceDescriptor(
        source_slug=source_slug,
        source_name="快手国内社会招聘",
        company_slug="kuaishou",
        company_name="快手",
        scope_key="social-domestic",
        adapter_type="playwright-json",
        base_url=ENTRY_URL,
    )

    def __init__(
        self,
        *,
        fetch_dataset: Callable[
            [], tuple[Mapping[str, object], list[Mapping[str, object]]]
        ]
        | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._fetch_dataset = fetch_dataset or fetch_kuaishou_dataset
        self._clock = clock or utc_now_iso

    def fetch_jobs(self) -> list[JobSnapshot]:
        dictionary_payload, page_payloads = self._fetch_dataset()
        if not page_payloads:
            raise KuaishouDataError("Kuaishou dataset has no pages")
        dictionary = parse_kuaishou_dictionary(dictionary_payload)
        observed_at = self._clock()
        pages = [
            parse_kuaishou_page(
                payload,
                dictionary=dictionary,
                observed_at=observed_at,
            )
            for payload in page_payloads
        ]
        total = pages[0].total
        expected_pages = ceil(total / self.page_size) if total else 1
        if len(pages) not in {
            expected_pages,
            expected_pages * 2,
            expected_pages * 3,
            expected_pages * 4,
        }:
            raise KuaishouDataError("Kuaishou page count does not match total")

        jobs_by_id: dict[str, JobSnapshot] = {}
        for page in pages:
            if page.total != total:
                raise KuaishouDataError("Kuaishou total changed during crawl")
            for job in page.jobs:
                existing = jobs_by_id.get(job.external_job_id)
                if existing is not None and existing != job:
                    raise KuaishouDataError(
                        "Kuaishou job changed between pagination passes"
                    )
                jobs_by_id[job.external_job_id] = job
        if len(jobs_by_id) != total:
            raise KuaishouDataError("Kuaishou job count does not match total")
        return list(jobs_by_id.values())


def fetch_kuaishou_dataset(
) -> tuple[Mapping[str, object], list[Mapping[str, object]]]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _fetch_kuaishou_dataset_sync()
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(_fetch_kuaishou_dataset_sync).result()


def _fetch_kuaishou_dataset_sync(
) -> tuple[Mapping[str, object], list[Mapping[str, object]]]:
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
                with page.expect_response(
                    lambda response: "/api/v1/dictionary/batch?" in response.url,
                    timeout=20_000,
                ) as dictionary_info:
                    with page.expect_response(
                        lambda response: (
                            "/api/v1/open/positions/simple?" in response.url
                            and "pageNum=1&" in response.url
                            and "workLocationCode=domestic" in response.url
                        ),
                        timeout=20_000,
                    ) as first_page_info:
                        page.goto(
                            ENTRY_URL,
                            wait_until="domcontentloaded",
                            timeout=20_000,
                        )
                dictionary = dictionary_info.value.json()
                first_page = first_page_info.value.json()

                def collect_pass(
                    initial: Mapping[str, object],
                ) -> list[Mapping[str, object]]:
                    result = initial.get("result")
                    if not isinstance(result, dict):
                        raise KuaishouDataError(
                            "Kuaishou first page result must be an object"
                        )
                    total = _required_int(result, "total")
                    page_total = ceil(total / KuaishouBrowserAdapter.page_size)
                    collected: list[Mapping[str, object]] = [initial]
                    for page_num in range(2, page_total + 1):
                        _require_crawl_time_remaining(
                            started,
                            current=time.monotonic(),
                        )
                        with page.expect_response(
                            lambda response, expected=page_num: (
                                "/api/v1/open/positions/simple?" in response.url
                                and f"pageNum={expected}&" in response.url
                                and "workLocationCode=domestic" in response.url
                            ),
                            timeout=10_000,
                        ) as page_info:
                            page.locator("li.ant-pagination-next").click()
                        collected.append(page_info.value.json())
                    return collected

                pages = collect_pass(first_page)

                def collected_ids() -> set[str]:
                    ids: set[str] = set()
                    for payload in pages:
                        result = payload.get("result")
                        if not isinstance(result, dict):
                            continue
                        entries = result.get("list")
                        if not isinstance(entries, list):
                            continue
                        ids.update(
                            str(entry.get("id"))
                            for entry in entries
                            if isinstance(entry, dict) and entry.get("id") is not None
                        )
                    return ids

                first_result = first_page.get("result")
                if not isinstance(first_result, dict):
                    raise KuaishouDataError(
                        "Kuaishou first page result must be an object"
                    )
                expected_total = _required_int(first_result, "total")
                for _ in range(3):
                    if len(collected_ids()) == expected_total:
                        break
                    with page.expect_response(
                        lambda response: (
                            "/api/v1/open/positions/simple?" in response.url
                            and "pageNum=1&" in response.url
                            and "workLocationCode=domestic" in response.url
                        ),
                        timeout=20_000,
                    ) as next_first_info:
                        page.goto(
                            ENTRY_URL,
                            wait_until="domcontentloaded",
                            timeout=20_000,
                        )
                    pages.extend(collect_pass(next_first_info.value.json()))
            finally:
                browser.close()
    except KuaishouDataError:
        raise
    except (PlaywrightTimeoutError, PlaywrightError) as exc:
        raise RuntimeError(
            "Kuaishou public page did not produce the expected dataset"
        ) from exc
    return dictionary, pages


def parse_kuaishou_dictionary(
    payload: Mapping[str, object],
) -> KuaishouDictionary:
    result = _result(payload)
    return KuaishouDictionary(
        locations=_dictionary_map(
            result.get("workLocation"),
            "workLocation",
            exclude_parent="foreign",
        ),
        categories=_dictionary_map(
            result.get("positionCategory"),
            "positionCategory",
        ),
        experiences=_dictionary_map(
            result.get("positionExperience"),
            "positionExperience",
        ),
    )


def parse_kuaishou_page(
    payload: Mapping[str, object],
    *,
    dictionary: KuaishouDictionary,
    observed_at: str,
) -> KuaishouPage:
    result = _result(payload)
    total = _required_int(result, "total")
    entries = result.get("list")
    if not isinstance(entries, list):
        raise KuaishouDataError("Kuaishou result.list must be a list")

    jobs: list[JobSnapshot] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise KuaishouDataError("Kuaishou job must be an object")
        job_id = _required_text(entry, "id")
        if not job_id.isdigit():
            raise KuaishouDataError("Kuaishou id must be numeric")
        if job_id in seen_ids:
            raise KuaishouDataError("duplicate Kuaishou id")
        seen_ids.add(job_id)
        if _required_text(entry, "recruitProjectCode") not in {
            "socialr",
            "epiboly",
        }:
            raise KuaishouDataError("Kuaishou job escaped social project")
        if _required_text(entry, "positionNatureCode") != "C001":
            raise KuaishouDataError("Kuaishou job escaped social nature")

        locations = _mapped_codes(
            entry.get("workLocationsCode"),
            dictionary.locations,
            "location",
        )
        category_code = _required_text(entry, "positionCategoryCode")
        experience_code = _required_text(entry, "workExperienceCode")
        try:
            category = dictionary.categories[category_code]
        except KeyError as exc:
            raise KuaishouDataError("unknown Kuaishou category code") from exc
        try:
            experience = dictionary.experiences[experience_code]
        except KeyError as exc:
            raise KuaishouDataError("unknown Kuaishou experience code") from exc
        description = _required_text(entry, "description")
        requirement = _required_text(entry, "positionDemand")
        fields = (
            ("职类", category),
            ("工作经验", experience),
            ("岗位职责", description),
            ("岗位要求", requirement),
            ("更新时间", entry.get("updateTime")),
        )
        jobs.append(
            JobSnapshot(
                external_job_id=job_id,
                title=_required_text(entry, "name"),
                description_raw="\n\n".join(
                    f"{label}：{str(value).strip()}"
                    for label, value in fields
                    if value is not None and str(value).strip()
                ),
                source_url=ENTRY_URL,
                observed_at=observed_at,
                location_raw="、".join(locations),
                recruitment_type="experienced",
            )
        )
    return KuaishouPage(jobs=jobs, total=total)


def _result(payload: Mapping[str, object]) -> dict:
    if payload.get("code") != 0:
        raise KuaishouDataError(
            f"Kuaishou API returned code {payload.get('code')}"
        )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise KuaishouDataError("Kuaishou result must be an object")
    return result


def _dictionary_map(
    value: object,
    field: str,
    *,
    exclude_parent: str | None = None,
) -> dict[str, str]:
    if not isinstance(value, list) or not value:
        raise KuaishouDataError(f"Kuaishou {field} must be a non-empty list")
    result: dict[str, str] = {}
    for entry in value:
        if not isinstance(entry, dict):
            raise KuaishouDataError(f"Kuaishou {field} item must be an object")
        if exclude_parent and entry.get("parentCode") == exclude_parent:
            continue
        result[_required_text(entry, "code")] = _required_text(entry, "name")
    return result


def _mapped_codes(
    value: object,
    mapping: Mapping[str, str],
    field: str,
) -> list[str]:
    if not isinstance(value, list) or not value:
        raise KuaishouDataError(f"Kuaishou {field} codes must be non-empty")
    names: list[str] = []
    for code in value:
        if not isinstance(code, str) or code not in mapping:
            raise KuaishouDataError(f"unknown Kuaishou {field} code")
        names.append(mapping[code])
    return names


def _required_text(entry: Mapping[str, object], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, (str, int)) or not str(value).strip():
        raise KuaishouDataError(f"Kuaishou {field} must be non-empty")
    return str(value).strip()


def _required_int(entry: Mapping[str, object], field: str) -> int:
    value = entry.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise KuaishouDataError(
            f"Kuaishou {field} must be a non-negative integer"
        )
    return value
