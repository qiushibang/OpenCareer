"""Public JSON adapter primitives for Xiaomi official recruitment."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from ..domain.crawler import JobSnapshot, SourceDescriptor
from ..domain.manual_jd import utc_now_iso


class XiaomiApiError(ValueError):
    """The public Xiaomi response did not satisfy the verified contract."""


class XiaomiAccessRestricted(RuntimeError):
    """The public Xiaomi API cannot be safely fetched."""


@dataclass(frozen=True)
class XiaomiListingPage:
    jobs: list[JobSnapshot]
    page_num: int
    page_size: int
    page_total: int
    total: int


class XiaomiPublicApiAdapter:
    """Fetch Xiaomi's public recruitment JSON pages serially."""

    source_slug = "xiaomi-careers"
    descriptor = SourceDescriptor(
        source_slug=source_slug,
        source_name="小米官方招聘",
        company_slug="xiaomi",
        company_name="小米",
        scope_key="all-public-jobs",
        adapter_type="public-json-api",
        base_url="https://hr.xiaomi.com/website/opportunities.html",
    )
    page_size = 100
    max_pages = 300

    def __init__(
        self,
        fetch_page: Callable[[int], Mapping[str, object]] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._fetch_page = fetch_page or fetch_public_page
        self._clock = clock or utc_now_iso

    def fetch_jobs(self) -> list[JobSnapshot]:
        observed_at = self._clock()
        first = parse_xiaomi_listing(self._fetch_page(1), observed_at=observed_at)
        if first.page_num != 1:
            raise XiaomiApiError("Xiaomi API first response pageNum must be 1")
        if first.page_size != self.page_size:
            raise XiaomiApiError(
                f"Xiaomi API pageSize must be {self.page_size}, got {first.page_size}"
            )
        if first.page_total > self.max_pages:
            raise XiaomiApiError(
                f"Xiaomi API pageTotal {first.page_total} exceeds {self.max_pages}"
            )
        if first.total > 0 and not first.jobs:
            raise XiaomiApiError("Xiaomi API returned an empty page for a positive total")

        jobs = list(first.jobs)
        seen_ids = {job.external_job_id for job in jobs}
        for page_num in range(2, first.page_total + 1):
            page = parse_xiaomi_listing(
                self._fetch_page(page_num),
                observed_at=observed_at,
            )
            if (
                page.page_num != page_num
                or page.page_size != first.page_size
                or page.page_total != first.page_total
                or page.total != first.total
            ):
                raise XiaomiApiError("Xiaomi API pagination changed during crawl")
            if page.total > 0 and not page.jobs:
                raise XiaomiApiError(
                    "Xiaomi API returned an empty page for a positive total"
                )
            for job in page.jobs:
                if job.external_job_id in seen_ids:
                    raise XiaomiApiError("duplicate jobId across pages")
                seen_ids.add(job.external_job_id)
                jobs.append(job)
        return jobs


def fetch_public_page(page_num: int) -> Mapping[str, object]:
    """Fetch one unauthenticated Xiaomi listing page with bounded settings."""
    if page_num < 1:
        raise ValueError("page_num must be positive")
    query = urlencode(
        {
            "keyword": "",
            "cityZhNames": "",
            "pageSize": XiaomiPublicApiAdapter.page_size,
            "pageNum": page_num,
        }
    )
    url = f"https://hr.xiaomi.com/website/api/agent/searchJobPage?{query}"
    request = Request(
        url,
        headers={"User-Agent": "OpenWorker-Career/0.1 (+local job research)"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            final_url = response.url
            content_type = response.headers.get_content_type()
            body = response.read(2_000_001)
    except HTTPError as exc:
        raise XiaomiAccessRestricted(f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise XiaomiAccessRestricted(f"network error: {exc.reason}") from exc

    if status != 200:
        raise XiaomiAccessRestricted(f"HTTP {status}")
    if urlparse(final_url).hostname != "hr.xiaomi.com":
        raise XiaomiAccessRestricted("unexpected redirect host")
    if content_type != "application/json":
        raise XiaomiAccessRestricted(f"unexpected content type: {content_type}")
    if len(body) > 2_000_000:
        raise XiaomiAccessRestricted("response body exceeds 2 MB")
    text = body.decode("utf-8", errors="replace")
    lowered = text.lower()
    if "captcha" in lowered or "need-login" in lowered:
        raise XiaomiAccessRestricted("access restriction response")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise XiaomiAccessRestricted("response is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise XiaomiAccessRestricted("response JSON must be an object")
    return payload


def parse_xiaomi_listing(
    payload: Mapping[str, object],
    *,
    observed_at: str,
) -> XiaomiListingPage:
    """Parse one verified public API page without inferring missing fields."""
    code = payload.get("code")
    if code != 0:
        raise XiaomiApiError(f"Xiaomi API returned code {code}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise XiaomiApiError("Xiaomi API data must be an object")
    entries = data.get("list")
    if not isinstance(entries, list):
        raise XiaomiApiError("Xiaomi API data.list must be a list")

    jobs: list[JobSnapshot] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise XiaomiApiError("Xiaomi API job must be an object")
        job_id = _required_text(entry, "jobId")
        if job_id in seen_ids:
            raise XiaomiApiError("duplicate jobId in Xiaomi API response")
        seen_ids.add(job_id)
        title = _required_text(entry, "title")
        source_url = _validated_detail_url(_required_text(entry, "url"))
        jobs.append(
            JobSnapshot(
                external_job_id=job_id,
                title=title,
                description_raw=_description_raw(entry),
                source_url=source_url,
                observed_at=observed_at,
                location_raw=_location_raw(entry.get("cityZhNames")),
                recruitment_type=_recruitment_type(entry.get("type")),
            )
        )

    return XiaomiListingPage(
        jobs=jobs,
        page_num=_required_int(data, "pageNum"),
        page_size=_required_int(data, "pageSize"),
        page_total=_required_int(data, "pageTotal"),
        total=_required_int(data, "total"),
    )


def _required_text(entry: Mapping[str, object], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise XiaomiApiError(f"Xiaomi API job {field} must be non-empty")
    return value.strip()


def _required_int(entry: Mapping[str, object], field: str) -> int:
    value = entry.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise XiaomiApiError(f"Xiaomi API {field} must be a non-negative integer")
    return value


def _validated_detail_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "https":
        raise XiaomiApiError("Xiaomi detail URL must use HTTPS")
    if parsed.hostname != "xiaomi.jobs.f.mioffice.cn":
        raise XiaomiApiError("Xiaomi detail URL uses an unexpected host")
    return value


def _location_raw(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    locations = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return "、".join(locations) or None


def _recruitment_type(value: object) -> str | None:
    return {1: "experienced", 2: "campus", 3: "internship"}.get(value)


def _description_raw(entry: Mapping[str, object]) -> str:
    fields = (
        ("部门", entry.get("levelOneDeptName")),
        ("岗位职责", entry.get("description")),
        ("任职要求", entry.get("requirement")),
        ("发布日期", entry.get("publishTime")),
        ("岗位编码", entry.get("larkJobCode")),
    )
    return "\n\n".join(
        f"{label}：{value.strip()}"
        for label, value in fields
        if isinstance(value, str) and value.strip()
    )
