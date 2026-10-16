"""Public SSR parsing primitives for Baidu official recruitment pages."""

from __future__ import annotations

import json
from collections.abc import Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ..domain.crawler import JobSnapshot, SourceDescriptor
from ..domain.manual_jd import utc_now_iso


class BaiduSsrParseError(ValueError):
    """The public SSR page did not expose a usable job state."""


class AccessRestricted(RuntimeError):
    """The official public page cannot be safely fetched without restriction."""


class BaiduSsrHtmlAdapter:
    """Fetch and parse the public Baidu social-recruitment SSR page."""

    source_slug = "baidu-careers"
    social_url = "https://talent.baidu.com/jobs/social"
    descriptor = SourceDescriptor(
        source_slug=source_slug,
        source_name="百度官方招聘",
        company_slug="baidu",
        company_name="百度",
        scope_key="social-public-jobs",
        adapter_type="ssr-html",
        base_url=social_url,
    )

    def __init__(self, fetch_html: Callable[[str], str] | None = None) -> None:
        self._fetch_html = fetch_html or fetch_public_html

    def fetch_jobs(self) -> list[JobSnapshot]:
        return parse_baidu_social_html(
            self._fetch_html(self.social_url),
            self.social_url,
        )


def fetch_public_html(url: str) -> str:
    """Fetch one public HTML page with bounded, unauthenticated request settings."""
    request = Request(
        url,
        headers={"User-Agent": "OpenWorker-Career/0.1 (+local job research)"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            content_type = response.headers.get_content_type()
            final_url = response.url.lower()
            body = response.read(2_000_001)
    except HTTPError as exc:
        raise AccessRestricted(f"HTTP {exc.code}") from exc
    if status in {401, 403, 429, 500, 502, 503, 504}:
        raise AccessRestricted(f"HTTP {status}")
    if "login" in final_url:
        raise AccessRestricted("login redirect")
    if content_type != "text/html":
        raise AccessRestricted(f"unexpected content type: {content_type}")
    if len(body) > 2_000_000:
        raise AccessRestricted("response body exceeds 2 MB")
    html = body.decode("utf-8", errors="replace")
    if "captcha" in html.lower() or "need-login" in html.lower():
        raise AccessRestricted("access restriction page")
    return html


def extract_initial_data(html: str) -> dict:
    """Extract the balanced JSON object assigned to window.__INITIAL_DATA__."""
    marker = "window.__INITIAL_DATA__"
    start = html.find(marker)
    if start < 0:
        raise BaiduSsrParseError("window.__INITIAL_DATA__ was not found")
    brace = html.find("{", start)
    if brace < 0:
        raise BaiduSsrParseError("window.__INITIAL_DATA__ has no JSON object")

    depth = 0
    quoted = False
    escaped = False
    for index in range(brace, len(html)):
        char = html[index]
        if quoted:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                try:
                    value = json.loads(html[brace : index + 1])
                except json.JSONDecodeError as exc:
                    raise BaiduSsrParseError(
                        "window.__INITIAL_DATA__ is invalid JSON"
                    ) from exc
                if not isinstance(value, dict):
                    raise BaiduSsrParseError(
                        "window.__INITIAL_DATA__ must be a JSON object"
                    )
                return value
    raise BaiduSsrParseError("window.__INITIAL_DATA__ JSON is incomplete")


def recruitment_type(*values: object) -> str | None:
    """Map explicit Baidu recruitment labels without inferring missing values."""
    text = " ".join(str(value) for value in values if value).lower()
    if "实习" in text or "intern" in text:
        return "internship"
    if "校招" in text or "校园" in text or "campus" in text:
        return "campus"
    if "社招" in text or "社会招聘" in text or "social" in text:
        return "experienced"
    return None


def parse_baidu_social_html(html: str, source_url: str) -> list[JobSnapshot]:
    """Parse public SSR list entries into stable crawler snapshots."""
    state = extract_initial_data(html)
    list_data = state.get("listData")
    if not isinstance(list_data, dict):
        raise BaiduSsrParseError("listData is missing")
    entries = list_data.get("listDetailData")
    if not isinstance(entries, list):
        raise BaiduSsrParseError("listData.listDetailData is missing")

    snapshots: list[JobSnapshot] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        job_id = entry.get("jobId")
        title = entry.get("name")
        if not isinstance(job_id, str) or not job_id.strip():
            continue
        if not isinstance(title, str) or not title.strip():
            continue
        if job_id in seen_ids:
            raise BaiduSsrParseError("duplicate jobId in listData.listDetailData")
        seen_ids.add(job_id)
        location = entry.get("workPlace")
        location_raw = location.strip() if isinstance(location, str) and location.strip() else None
        description = _description_raw(entry, title.strip(), location_raw)
        snapshots.append(
            JobSnapshot(
                external_job_id=job_id,
                title=title.strip(),
                description_raw=description,
                source_url=source_url,
                observed_at=utc_now_iso(),
                location_raw=location_raw,
                recruitment_type=recruitment_type(
                    entry.get("recruitType"),
                    entry.get("projectType"),
                    entry.get("postType"),
                ),
            )
        )
    if not snapshots:
        raise BaiduSsrParseError("listData.listDetailData has no valid jobs")
    return snapshots


def _description_raw(entry: dict, title: str, location: str | None) -> str:
    fields = (
        ("职位", title),
        ("组织", entry.get("orgName")),
        ("地点", location),
        ("岗位职责", entry.get("workContent")),
        ("任职要求", entry.get("serviceCondition")),
        ("学历要求", entry.get("education")),
        ("工作年限", entry.get("workYears")),
    )
    return "\n\n".join(
        f"{label}：{value.strip()}"
        for label, value in fields
        if isinstance(value, str) and value.strip()
    )
