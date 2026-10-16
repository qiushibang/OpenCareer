"""Official Zhipu AI Moka rendered-DOM adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping
from uuid import UUID

from ..domain.crawler import JobSnapshot, SourceDescriptor
from ..domain.manual_jd import utc_now_iso
from .moonshot import fetch_moka_dom_pages


class ZhipuDataError(ValueError):
    pass


@dataclass(frozen=True)
class ZhipuScope:
    source_slug: str
    source_name: str
    entry_url: str
    recruitment_type: str
    max_jobs: int


ZHIPU_SOCIAL_SCOPE = ZhipuScope(
    source_slug="zhipu-social",
    source_name="智谱 AI 社会招聘",
    entry_url=(
        "https://app.mokahr.com/social-recruitment/zphz/148983#/jobs"
    ),
    recruitment_type="experienced",
    max_jobs=180,
)
ZHIPU_CAMPUS_SCOPE = ZhipuScope(
    source_slug="zhipu-campus",
    source_name="智谱 AI 校园招聘",
    entry_url=(
        "https://app.mokahr.com/campus-recruitment/zphz/148984#/jobs"
    ),
    recruitment_type="campus",
    max_jobs=30,
)
ZHIPU_PRODUCTION_SCOPES = (ZHIPU_CAMPUS_SCOPE,)


class ZhipuMokaAdapter:
    def __init__(
        self,
        scope: ZhipuScope,
        *,
        fetch_dataset: Callable[
            [ZhipuScope], list[Mapping[str, object]]
        ] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self.scope = scope
        self.source_slug = scope.source_slug
        self.descriptor = SourceDescriptor(
            source_slug=scope.source_slug,
            source_name=scope.source_name,
            company_slug="zhipu",
            company_name="智谱 AI",
            scope_key=scope.recruitment_type,
            adapter_type="playwright-rendered-dom",
            base_url=scope.entry_url,
        )
        self._fetch_dataset = fetch_dataset or (
            lambda selected: fetch_moka_dom_pages(selected.entry_url)
        )
        self._clock = clock or utc_now_iso

    def fetch_jobs(self) -> list[JobSnapshot]:
        pages = self._fetch_dataset(self.scope)
        if not pages:
            raise ZhipuDataError("Zhipu dataset has no pages")
        page_count = _required_int(pages[0], "page_count")
        if not 1 <= page_count <= 20 or len(pages) != page_count:
            raise ZhipuDataError("Zhipu page count is invalid")
        jobs: list[JobSnapshot] = []
        seen: set[str] = set()
        observed_at = self._clock()
        for expected_page, page in enumerate(pages, start=1):
            if (
                _required_int(page, "page") != expected_page
                or _required_int(page, "page_count") != page_count
                or _required_int(page, "page_size") != 30
            ):
                raise ZhipuDataError("Zhipu pagination changed during crawl")
            entries = page.get("jobs")
            if not isinstance(entries, list):
                raise ZhipuDataError("Zhipu jobs must be a list")
            if expected_page < page_count and len(entries) != 30:
                raise ZhipuDataError("Zhipu non-final page must contain 30 jobs")
            if expected_page == page_count and not 1 <= len(entries) <= 30:
                raise ZhipuDataError("Zhipu final page is empty or oversized")
            for raw in entries:
                if not isinstance(raw, dict):
                    raise ZhipuDataError("Zhipu job must be an object")
                job = parse_zhipu_card(
                    raw,
                    scope=self.scope,
                    observed_at=observed_at,
                )
                if job.external_job_id in seen:
                    raise ZhipuDataError("duplicate Zhipu UUID")
                seen.add(job.external_job_id)
                jobs.append(job)
        if len(jobs) > self.scope.max_jobs:
            raise ZhipuDataError("Zhipu total exceeds scope safety limit")
        return jobs


def parse_zhipu_card(
    raw: Mapping[str, object],
    *,
    scope: ZhipuScope,
    observed_at: str,
) -> JobSnapshot:
    href = _required_text(raw, "href")
    if not href.startswith("#/job/"):
        raise ZhipuDataError("Zhipu href must contain a UUID")
    job_id = href.removeprefix("#/job/")
    try:
        parsed = UUID(job_id)
    except ValueError as exc:
        raise ZhipuDataError("Zhipu href must contain a UUID") from exc
    if str(parsed) != job_id:
        raise ZhipuDataError("Zhipu UUID must be canonical")
    metadata = raw.get("metadata")
    if not isinstance(metadata, list) or any(
        not isinstance(value, str) or not value.strip() for value in metadata
    ):
        raise ZhipuDataError("Zhipu metadata is invalid")
    values = [value.strip() for value in metadata]
    employment_types = {"全职", "实习", "其它"}
    if values[0] in employment_types:
        team = None
        employment_type = values[0]
        details = values[1:]
    elif len(values) >= 2 and values[1] in employment_types:
        team = values[0]
        employment_type = values[1]
        details = values[2:]
    else:
        raise ZhipuDataError("Zhipu metadata shape is invalid")
    if len(details) > 2:
        raise ZhipuDataError("Zhipu metadata shape is invalid")
    fields = [f"职位类型：{employment_type}"]
    if team is not None:
        fields.insert(0, f"团队：{team}")
    location: str | None = None
    if len(details) == 1:
        if _looks_like_location(details[0]):
            location = details[0]
        else:
            fields.append(f"职类：{details[0]}")
    elif len(details) == 2:
        if not _looks_like_location(details[1]):
            raise ZhipuDataError("Zhipu metadata shape is invalid")
        fields.append(f"职类：{details[0]}")
        location = details[1]
    recruitment_type = (
        "internship"
        if employment_type == "实习"
        else scope.recruitment_type
    )
    fields.extend(
        [
            f"发布日期：{_required_text(raw, 'published_at')}",
            f"职位描述：\n{_required_text(raw, 'description')}",
        ]
    )
    return JobSnapshot(
        external_job_id=job_id,
        title=_required_text(raw, "title"),
        description_raw="\n\n".join(fields),
        source_url=scope.entry_url.replace("#/jobs", f"#/job/{job_id}"),
        observed_at=observed_at,
        location_raw=location,
        recruitment_type=recruitment_type,
    )


def _required_text(entry: Mapping[str, object], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ZhipuDataError(f"Zhipu {field} must be non-empty")
    return value.strip()


def _required_int(entry: Mapping[str, object], field: str) -> int:
    value = entry.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ZhipuDataError(
            f"Zhipu {field} must be a non-negative integer"
        )
    return value


def _looks_like_location(value: str) -> bool:
    return any(
        marker in value
        for marker in ("市", "省", "自治区", "香港", "澳门", "美国", "新加坡")
    )
