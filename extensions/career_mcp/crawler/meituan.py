"""Official Meituan social-recruitment JSON parsing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import ceil
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import httpx

from ..domain.crawler import JobSnapshot, SourceDescriptor
from ..domain.manual_jd import utc_now_iso

LISTING_API = "https://hr.meituan.com/api/official/job/getJobList"
OVERSEAS_CITY_API = "https://hr.meituan.com/api/official/en/city/search"
DETAIL_PAGE = "https://hr.meituan.com/web/position/detail"


class MeituanApiError(ValueError):
    """A Meituan careers response violated the verified public contract."""


@dataclass(frozen=True)
class MeituanListingPage:
    jobs: list[JobSnapshot]
    raw_job_ids: list[str]
    raw_count: int
    page_no: int
    page_size: int
    page_total: int
    total: int


class MeituanSocialAdapter:
    source_slug = "meituan-social-cn"
    page_size = 100
    descriptor = SourceDescriptor(
        source_slug=source_slug,
        source_name="美团国内社会招聘",
        company_slug="meituan",
        company_name="美团",
        scope_key="social-cn-public-jobs",
        adapter_type="public-json-api",
        base_url="https://hr.meituan.com/web/social",
    )

    def __init__(
        self,
        *,
        fetch_page: Callable[[int], Mapping[str, object]] | None = None,
        fetch_overseas_cities: Callable[[], Mapping[str, object]] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._fetch_page = fetch_page
        self._fetch_overseas_cities = fetch_overseas_cities
        self._clock = clock or utc_now_iso

    def fetch_jobs(self) -> list[JobSnapshot]:
        if self._fetch_page is None and self._fetch_overseas_cities is None:
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                return self._fetch_jobs(
                    lambda page_num: fetch_meituan_page(
                        page_num,
                        client=client,
                    ),
                    lambda: fetch_meituan_overseas_cities(client=client),
                )
        return self._fetch_jobs(
            self._fetch_page or fetch_meituan_page,
            self._fetch_overseas_cities or fetch_meituan_overseas_cities,
        )

    def _fetch_jobs(
        self,
        fetch_page: Callable[[int], Mapping[str, object]],
        fetch_overseas_cities: Callable[[], Mapping[str, object]],
    ) -> list[JobSnapshot]:
        overseas_names = parse_overseas_city_names(
            fetch_overseas_cities()
        )
        observed_at = self._clock()
        expected_total: int | None = None
        expected_pages: int | None = None
        raw_ids: set[str] = set()
        jobs_by_id: dict[str, JobSnapshot] = {}
        for _ in range(3):
            first = parse_meituan_listing(
                fetch_page(1),
                observed_at=observed_at,
                overseas_city_names=overseas_names,
            )
            if first.page_no != 1 or first.page_size != self.page_size:
                raise MeituanApiError("Meituan first page metadata is invalid")
            current_pages = (
                ceil(first.total / self.page_size) if first.total else 1
            )
            if first.page_total != current_pages:
                raise MeituanApiError(
                    "Meituan page total does not match total count"
                )
            if expected_total is None:
                expected_total = first.total
                expected_pages = current_pages
            elif (
                first.total != expected_total
                or current_pages != expected_pages
            ):
                raise MeituanApiError(
                    "Meituan pagination changed during crawl"
                )
            pages = [first]
            for page_num in range(2, current_pages + 1):
                page = parse_meituan_listing(
                    fetch_page(page_num),
                    observed_at=observed_at,
                    overseas_city_names=overseas_names,
                )
                if (
                    page.page_no != page_num
                    or page.page_size != first.page_size
                    or page.page_total != current_pages
                    or page.total != expected_total
                ):
                    raise MeituanApiError(
                        "Meituan pagination changed during crawl"
                    )
                if not page.raw_job_ids:
                    raise MeituanApiError(
                        "Meituan returned an empty middle page"
                    )
                pages.append(page)
            for page in pages:
                raw_ids.update(page.raw_job_ids)
                for job in page.jobs:
                    existing = jobs_by_id.get(job.external_job_id)
                    if existing is not None and existing != job:
                        raise MeituanApiError(
                            "Meituan job changed between pagination passes"
                        )
                    jobs_by_id[job.external_job_id] = job
            if len(raw_ids) == expected_total:
                break
        if len(raw_ids) != expected_total:
            raise MeituanApiError("Meituan raw job count does not match total")
        return list(jobs_by_id.values())


def fetch_meituan_page(
    page_num: int,
    *,
    client: httpx.Client | None = None,
) -> Mapping[str, object]:
    if page_num < 1:
        raise ValueError("page_num must be positive")
    return _post_meituan_json(
        LISTING_API,
        {
            "page": {
                "pageNo": page_num,
                "pageSize": MeituanSocialAdapter.page_size,
            },
            "jobShareType": "1",
            "keywords": "",
            "cityList": [],
            "department": [],
            "jfJgList": [],
            "jobType": [{"code": "3", "subCode": []}],
            "typeCode": [],
            "specialCode": [],
        },
        max_bytes=10_000_000,
        client=client,
    )


def fetch_meituan_overseas_cities(
    *,
    client: httpx.Client | None = None,
) -> Mapping[str, object]:
    return _post_meituan_json(
        OVERSEAS_CITY_API,
        {},
        max_bytes=5_000_000,
        client=client,
    )


def _post_meituan_json(
    url: str,
    payload: Mapping[str, object],
    *,
    max_bytes: int,
    client: httpx.Client | None = None,
) -> Mapping[str, object]:
    request_body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "OpenWorker-Career/0.1 (+local job research)",
    }
    if client is not None:
        for attempt in range(3):
            try:
                response = client.post(
                    url,
                    content=request_body,
                    headers=headers,
                )
                break
            except httpx.TransportError as exc:
                if attempt == 2:
                    raise RuntimeError(
                        f"Meituan network error: {exc}"
                    ) from exc
        status = response.status_code
        final_url = str(response.url)
        content_type = response.headers.get("content-type", "").split(
            ";",
            1,
        )[0]
        body = response.content
        return _parse_meituan_response(
            status=status,
            final_url=final_url,
            content_type=content_type,
            body=body,
            max_bytes=max_bytes,
        )

    request = Request(
        url,
        data=request_body,
        headers=headers,
        method="POST",
    )
    for attempt in range(3):
        try:
            with urlopen(request, timeout=15) as response:
                status = response.status
                final_url = response.url
                content_type = response.headers.get_content_type()
                body = response.read(max_bytes + 1)
            break
        except HTTPError as exc:
            raise RuntimeError(f"Meituan HTTP {exc.code}") from exc
        except URLError as exc:
            if attempt == 2:
                raise RuntimeError(
                    f"Meituan network error: {exc.reason}"
                ) from exc

    return _parse_meituan_response(
        status=status,
        final_url=final_url,
        content_type=content_type,
        body=body,
        max_bytes=max_bytes,
    )


def _parse_meituan_response(
    *,
    status: int,
    final_url: str,
    content_type: str,
    body: bytes,
    max_bytes: int,
) -> Mapping[str, object]:
    if status != 200:
        raise RuntimeError(f"Meituan HTTP {status}")
    parsed = urlparse(final_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "hr.meituan.com"
        or not parsed.path.startswith("/api/official/")
    ):
        raise RuntimeError("unexpected Meituan redirect")
    if content_type != "application/json":
        raise RuntimeError(f"unexpected content type: {content_type}")
    if len(body) > max_bytes:
        raise RuntimeError("Meituan response body exceeds size limit")
    try:
        result = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Meituan response is not valid JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Meituan response JSON must be an object")
    return result


def parse_overseas_city_names(payload: Mapping[str, object]) -> set[str]:
    if payload.get("status") != 1:
        raise MeituanApiError(
            f"Meituan city API returned status {payload.get('status')}"
        )
    entries = payload.get("data")
    if not isinstance(entries, list) or not entries:
        raise MeituanApiError("Meituan overseas city data must be a non-empty list")
    names: set[str] = set()
    for country in entries:
        if not isinstance(country, dict):
            raise MeituanApiError("Meituan overseas country must be an object")
        names.add(_required_text(country, "name"))
        children = country.get("children")
        if not isinstance(children, list):
            raise MeituanApiError("Meituan overseas country children must be a list")
        for city in children:
            if not isinstance(city, dict):
                raise MeituanApiError("Meituan overseas city must be an object")
            names.add(_required_text(city, "name"))
    return names


def parse_meituan_listing(
    payload: Mapping[str, object],
    *,
    observed_at: str,
    overseas_city_names: set[str],
) -> MeituanListingPage:
    if payload.get("status") != 1:
        raise MeituanApiError(
            f"Meituan job API returned status {payload.get('status')}"
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        raise MeituanApiError("Meituan data must be an object")
    entries = data.get("list")
    page = data.get("page")
    if not isinstance(entries, list):
        raise MeituanApiError("Meituan data.list must be a list")
    if not isinstance(page, dict):
        raise MeituanApiError("Meituan data.page must be an object")

    jobs: list[JobSnapshot] = []
    raw_ids: list[str] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise MeituanApiError("Meituan job must be an object")
        job_id = _required_text(entry, "jobUnionId")
        if not job_id.isdigit():
            raise MeituanApiError("Meituan jobUnionId must be numeric")
        if job_id in seen_ids:
            raise MeituanApiError("duplicate Meituan jobUnionId")
        seen_ids.add(job_id)
        raw_ids.append(job_id)
        if _required_text(entry, "jobType") != "3":
            raise MeituanApiError("Meituan source returned a non-social job")
        if _required_text(entry, "jobStatus") != "000":
            raise MeituanApiError("Meituan source returned an inactive job")

        location_names = _name_list(entry.get("cityList"), "cityList")
        duty = _required_text(entry, "jobDuty")
        requirement = _required_text(entry, "jobRequirement")
        departments = _name_list(entry.get("department"), "department")
        fields = (
            ("部门", "、".join(departments)),
            ("职类", entry.get("jobFamily")),
            ("职类分组", entry.get("jobFamilyGroup")),
            ("岗位职责", duty),
            ("岗位要求", requirement),
            ("优先条件", entry.get("precedence")),
            ("岗位亮点", entry.get("highLight")),
            ("部门介绍", entry.get("departmentIntro")),
            ("更新时间戳", entry.get("refreshTime")),
        )
        if all(name in overseas_city_names for name in location_names):
            continue
        description = "\n\n".join(
            f"{label}：{str(value).strip()}"
            for label, value in fields
            if value is not None and str(value).strip()
        )
        jobs.append(
            JobSnapshot(
                external_job_id=job_id,
                title=_required_text(entry, "name"),
                description_raw=description,
                source_url=(
                    f"{DETAIL_PAGE}?jobUnionId={job_id}&highlightType=social"
                ),
                observed_at=observed_at,
                location_raw="、".join(location_names),
                recruitment_type="experienced",
            )
        )

    return MeituanListingPage(
        jobs=jobs,
        raw_job_ids=raw_ids,
        raw_count=len(raw_ids),
        page_no=_required_int(page, "pageNo"),
        page_size=_required_int(page, "pageSize"),
        page_total=_required_int(page, "totalPage"),
        total=_required_int(page, "totalCount"),
    )


def _name_list(value: object, field: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise MeituanApiError(f"Meituan {field} must be a non-empty list")
    names: list[str] = []
    for item in value:
        if not isinstance(item, dict):
            raise MeituanApiError(f"Meituan {field} item must be an object")
        names.append(_required_text(item, "name"))
    return names


def _required_text(entry: Mapping[str, object], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, (str, int)) or not str(value).strip():
        raise MeituanApiError(f"Meituan {field} must be non-empty")
    return str(value).strip()


def _required_int(entry: Mapping[str, object], field: str) -> int:
    value = entry.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise MeituanApiError(f"Meituan {field} must be a non-negative integer")
    return value
