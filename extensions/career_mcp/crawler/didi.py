"""Official Didi China social-recruitment adapter."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import ceil
from typing import Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ..domain.crawler import JobSnapshot, SourceDescriptor
from ..domain.manual_jd import utc_now_iso

API_BASE = "https://talent.didiglobal.com/recruit-portal-service/api/job"


class DidiApiError(ValueError):
    pass


@dataclass(frozen=True)
class DidiListingPost:
    jd_id: str
    jd_no: str
    title: str


@dataclass(frozen=True)
class DidiListingPage:
    posts: list[DidiListingPost]
    total: int
    page: int
    size: int


class DidiSocialAdapter:
    source_slug = "didi-social-cn"
    page_size = 16
    descriptor = SourceDescriptor(
        source_slug=source_slug,
        source_name="滴滴中国社会招聘",
        company_slug="didi",
        company_name="滴滴出行",
        scope_key="social-cn",
        adapter_type="public-json-api-with-detail",
        base_url="https://talent.didiglobal.com/m?jobType=1",
    )

    def __init__(
        self,
        *,
        fetch_listing: Callable[[int], Mapping[str, object]] | None = None,
        fetch_detail: Callable[[str], Mapping[str, object]] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._fetch_listing = fetch_listing or fetch_didi_listing
        self._fetch_detail = fetch_detail or fetch_didi_detail
        self._clock = clock or utc_now_iso

    def fetch_jobs(self) -> list[JobSnapshot]:
        first = parse_didi_listing(self._fetch_listing(1))
        if first.page != 1 or first.size != self.page_size:
            raise DidiApiError("Didi first page metadata is invalid")
        posts = list(first.posts)
        seen = {post.jd_id for post in posts}
        for page_num in range(2, ceil(first.total / first.size) + 1):
            page = parse_didi_listing(self._fetch_listing(page_num))
            if page.page != page_num or page.size != first.size or page.total != first.total:
                raise DidiApiError("Didi pagination changed during crawl")
            for post in page.posts:
                if post.jd_id in seen:
                    raise DidiApiError("duplicate Didi jdId across pages")
                seen.add(post.jd_id)
                posts.append(post)
        if len(posts) != first.total:
            raise DidiApiError("Didi listing count does not match total")

        observed_at = self._clock()
        return [
            parse_didi_detail(
                self._fetch_detail(post.jd_id),
                expected_jd_id=post.jd_id,
                expected_jd_no=post.jd_no,
                observed_at=observed_at,
            )
            for post in posts
        ]


def parse_didi_listing(payload: Mapping[str, object]) -> DidiListingPage:
    data = _data(payload)
    entries = data.get("items")
    if not isinstance(entries, list):
        raise DidiApiError("Didi data.items must be a list")
    posts: list[DidiListingPost] = []
    seen: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise DidiApiError("Didi listing item must be an object")
        jd_id = _required_text(entry, "jdId")
        if not jd_id.isdigit() or jd_id in seen:
            raise DidiApiError("invalid or duplicate Didi jdId")
        seen.add(jd_id)
        if entry.get("jobType") != 1:
            raise DidiApiError("Didi listing escaped social jobs")
        posts.append(
            DidiListingPost(
                jd_id=jd_id,
                jd_no=_required_text(entry, "jdNo"),
                title=_required_text(entry, "jobName"),
            )
        )
    return DidiListingPage(
        posts=posts,
        total=_required_int(data, "total"),
        page=_required_int(data, "page"),
        size=_required_int(data, "size"),
    )


def parse_didi_detail(
    payload: Mapping[str, object],
    *,
    expected_jd_id: str,
    expected_jd_no: str,
    observed_at: str,
) -> JobSnapshot:
    data = _data(payload)
    if _required_text(data, "jdNo") != expected_jd_no:
        raise DidiApiError("Didi detail jdNo does not match listing")
    if _required_text(data, "recruitType") != "1":
        raise DidiApiError("Didi detail escaped social recruitment")
    fields = (
        ("部门", data.get("deptName")),
        ("职类", data.get("jobType")),
        ("岗位职责", _required_text(data, "jobDesc")),
        ("岗位要求", _required_text(data, "qualification")),
        ("招聘人数", data.get("recruitNum")),
        ("更新时间", data.get("refreshTime")),
        ("职位编码", expected_jd_no),
    )
    return JobSnapshot(
        external_job_id=expected_jd_id,
        title=_required_text(data, "jobName"),
        description_raw="\n\n".join(
            f"{label}：{str(value).strip()}"
            for label, value in fields
            if value is not None and str(value).strip()
        ),
        source_url=f"https://talent.didiglobal.com/social/p/{expected_jd_id}",
        observed_at=observed_at,
        location_raw=_required_text(data, "workArea"),
        recruitment_type="experienced",
    )


def fetch_didi_listing(page: int) -> Mapping[str, object]:
    return _fetch_json(
        f"{API_BASE}/front/list?jobType=1&page={page}&recruitType=1&size=10",
        referer="https://talent.didiglobal.com/m?jobType=1",
    )


def fetch_didi_detail(jd_id: str) -> Mapping[str, object]:
    return _fetch_json(
        f"{API_BASE}/front/view/{jd_id}",
        referer=f"https://talent.didiglobal.com/social/p/{jd_id}",
    )


def _fetch_json(url: str, *, referer: str) -> Mapping[str, object]:
    request = Request(
        url,
        headers={
            "User-Agent": "OpenWorker-Career/0.1 (+local job research)",
            "Referer": referer,
        },
    )
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            final_url = response.url
            content_type = response.headers.get_content_type()
            body = response.read(2_000_001)
    except HTTPError as exc:
        raise RuntimeError(f"Didi HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Didi network error: {exc.reason}") from exc
    parsed = urlparse(final_url)
    if status != 200:
        raise RuntimeError(f"Didi HTTP {status}")
    if parsed.scheme != "https" or parsed.hostname != "talent.didiglobal.com":
        raise RuntimeError("unexpected Didi redirect")
    if content_type != "application/json" or len(body) > 2_000_000:
        raise RuntimeError("invalid Didi response")
    result = json.loads(body.decode())
    if not isinstance(result, dict):
        raise RuntimeError("Didi response JSON must be an object")
    return result


def _data(payload: Mapping[str, object]) -> dict:
    meta = payload.get("meta")
    if not isinstance(meta, dict) or meta.get("code") != 0:
        raise DidiApiError("Didi API returned an error")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise DidiApiError("Didi data must be an object")
    return data


def _required_text(entry: Mapping[str, object], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, (str, int)) or not str(value).strip():
        raise DidiApiError(f"Didi {field} must be non-empty")
    return str(value).strip()


def _required_int(entry: Mapping[str, object], field: str) -> int:
    value = entry.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise DidiApiError(f"Didi {field} must be a non-negative integer")
    return value
