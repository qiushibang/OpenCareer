"""Static bundle parsing for DeepSeek's official recruitment site."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from html.parser import HTMLParser
from uuid import UUID
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from ..domain.crawler import JobSnapshot, SourceDescriptor
from ..domain.manual_jd import utc_now_iso


DEEPSEEK_MOKA_BASE = (
    "https://app.mokahr.com/social-recruitment/high-flyer/140576#/"
)


class DeepSeekBundleError(ValueError):
    """The official DeepSeek bundle did not satisfy the verified contract."""


class DeepSeekAccessRestricted(RuntimeError):
    """The DeepSeek public source cannot be safely fetched."""


class DeepSeekStaticBundleAdapter:
    """Fetch and parse the official DeepSeek static recruitment dataset."""

    source_slug = "deepseek-careers"
    entry_url = "https://talent.deepseek.com/"
    descriptor = SourceDescriptor(
        source_slug=source_slug,
        source_name="DeepSeek 官方招聘",
        company_slug="deepseek",
        company_name="DeepSeek",
        scope_key="all-public-jobs",
        adapter_type="static-javascript-bundle",
        base_url=entry_url,
    )

    def __init__(
        self,
        fetch_text: Callable[[str, str], str] | None = None,
        clock: Callable[[], str] | None = None,
    ) -> None:
        self._fetch_text = fetch_text or fetch_public_text
        self._clock = clock or utc_now_iso

    def fetch_jobs(self) -> list[JobSnapshot]:
        entry_html = self._fetch_text(self.entry_url, "entry")
        bundle_url = extract_bundle_url(entry_html, self.entry_url)
        bundle = self._fetch_text(bundle_url, "bundle")
        dataset = select_deepseek_dataset(bundle)
        return parse_deepseek_dataset(dataset, observed_at=self._clock())


def fetch_public_text(url: str, kind: str) -> str:
    """Fetch one bounded, unauthenticated DeepSeek entry or bundle response."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "talent.deepseek.com":
        raise DeepSeekAccessRestricted("unexpected request host")
    if kind == "entry":
        if url != DeepSeekStaticBundleAdapter.entry_url:
            raise DeepSeekAccessRestricted("unexpected entry URL")
        expected_types = {"text/html"}
        max_bytes = 256_000
    elif kind == "bundle":
        if not re.fullmatch(r"/static/main\.[A-Za-z0-9_-]+\.js", parsed.path):
            raise DeepSeekAccessRestricted("unexpected bundle path")
        expected_types = {"text/javascript", "application/javascript"}
        max_bytes = 2_000_000
    else:
        raise ValueError("kind must be entry or bundle")

    request = Request(
        url,
        headers={"User-Agent": "OpenWorker-Career/0.1 (+local job research)"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            status = response.status
            final_url = response.url
            content_type = response.headers.get_content_type()
            body = response.read(max_bytes + 1)
    except HTTPError as exc:
        raise DeepSeekAccessRestricted(f"HTTP {exc.code}") from exc
    except URLError as exc:
        raise DeepSeekAccessRestricted(f"network error: {exc.reason}") from exc

    if status != 200:
        raise DeepSeekAccessRestricted(f"HTTP {status}")
    if urlparse(final_url).hostname != "talent.deepseek.com":
        raise DeepSeekAccessRestricted("unexpected redirect host")
    if content_type not in expected_types:
        raise DeepSeekAccessRestricted(f"unexpected content type: {content_type}")
    if len(body) > max_bytes:
        raise DeepSeekAccessRestricted("response body exceeds size limit")
    text = body.decode("utf-8", errors="replace")
    lowered = text.lower()
    if "captcha" in lowered or "need-login" in lowered:
        raise DeepSeekAccessRestricted("access restriction response")
    return text


class _ScriptCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "script":
            return
        source = dict(attrs).get("src")
        if source:
            self.sources.append(source)


def extract_bundle_url(html: str, entry_url: str) -> str:
    """Return the one same-origin hashed main bundle referenced by the entry page."""
    collector = _ScriptCollector()
    collector.feed(html)
    entry_host = urlparse(entry_url).hostname
    matches = []
    for source in collector.sources:
        absolute = urljoin(entry_url, source)
        parsed = urlparse(absolute)
        if (
            parsed.scheme == "https"
            and parsed.hostname == entry_host == "talent.deepseek.com"
            and re.fullmatch(r"/static/main\.[A-Za-z0-9_-]+\.js", parsed.path)
        ):
            matches.append(absolute)
    if len(matches) != 1:
        raise DeepSeekBundleError("expected exactly one same-origin DeepSeek main bundle")
    return matches[0]


def extract_json_parse_values(script: str) -> list[object]:
    """Decode quoted JSON.parse arguments without executing JavaScript."""
    marker = "JSON.parse("
    values: list[object] = []
    position = 0
    while True:
        position = script.find(marker, position)
        if position < 0:
            return values
        start = position + len(marker)
        while start < len(script) and script[start].isspace():
            start += 1
        if start >= len(script) or script[start] not in {"'", '"'}:
            position = start
            continue
        raw, position = _scan_js_string(script, start)
        decoded = _decode_js_string(raw)
        try:
            values.append(json.loads(decoded))
        except json.JSONDecodeError as exc:
            raise DeepSeekBundleError("JSON.parse string is not valid JSON") from exc


def select_deepseek_dataset(script: str) -> dict:
    """Select exactly one decoded dataset for the verified DeepSeek Moka tenant."""
    matches = [
        value
        for value in extract_json_parse_values(script)
        if isinstance(value, dict)
        and value.get("sourceUrl") == DEEPSEEK_MOKA_BASE
        and isinstance(value.get("jobs"), list)
    ]
    if len(matches) != 1:
        raise DeepSeekBundleError("expected exactly one DeepSeek recruitment dataset")
    return matches[0]


def parse_deepseek_dataset(
    dataset: dict,
    *,
    observed_at: str,
) -> list[JobSnapshot]:
    """Validate and map one DeepSeek bundle dataset into crawler snapshots."""
    entries = dataset.get("jobs")
    total = dataset.get("total")
    if not isinstance(entries, list):
        raise DeepSeekBundleError("DeepSeek jobs must be a list")
    if (
        not isinstance(total, int)
        or isinstance(total, bool)
        or total < 0
        or total != len(entries)
    ):
        raise DeepSeekBundleError("DeepSeek total must equal the jobs length")

    jobs: list[JobSnapshot] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise DeepSeekBundleError("DeepSeek job must be an object")
        job_id = _required_text(entry, "id")
        try:
            canonical_id = str(UUID(job_id))
        except ValueError as exc:
            raise DeepSeekBundleError("DeepSeek job id must be a UUID") from exc
        if canonical_id != job_id.lower():
            raise DeepSeekBundleError("DeepSeek job id must be a canonical UUID")
        if canonical_id in seen_ids:
            raise DeepSeekBundleError("duplicate DeepSeek job UUID")
        seen_ids.add(canonical_id)

        title = _required_text(entry, "title")
        description = html_to_text(_required_text(entry, "descriptionHtml"))
        if not description:
            raise DeepSeekBundleError("DeepSeek job description must be non-empty")
        locations = entry.get("locations")
        if not isinstance(locations, list) or any(
            not isinstance(location, str) for location in locations
        ):
            raise DeepSeekBundleError("DeepSeek job locations must be a string list")
        location_values = [location.strip() for location in locations if location.strip()]
        source_url = f"{DEEPSEEK_MOKA_BASE}job/{canonical_id}"
        detail_url = entry.get("detailUrl")
        if detail_url is not None and detail_url != source_url:
            raise DeepSeekBundleError("DeepSeek detail URL does not match its UUID")

        jobs.append(
            JobSnapshot(
                external_job_id=canonical_id,
                title=title,
                description_raw=description,
                source_url=source_url,
                observed_at=observed_at,
                location_raw="、".join(location_values) or None,
                recruitment_type=_recruitment_type(description),
            )
        )
    return jobs


class _TextExtractor(HTMLParser):
    block_tags = {
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "ol",
        "p",
        "section",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(html: str) -> str:
    """Convert source HTML to deterministic line-oriented text."""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    return "\n".join(
        line
        for line in (re.sub(r"\s+", " ", part).strip() for part in "".join(parser.parts).splitlines())
        if line
    )


def _required_text(entry: dict, field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise DeepSeekBundleError(f"DeepSeek job {field} must be non-empty")
    return value.strip()


def _recruitment_type(description: str) -> str | None:
    compact = re.sub(r"\s+", "", description).lower()
    has_internship = "实习" in compact or "intern" in compact
    has_full_time = "全职" in compact or "full-time" in compact or "fulltime" in compact
    if has_internship and not has_full_time:
        return "internship"
    if has_full_time and not has_internship:
        return "experienced"
    if "校招" in compact or "校园招聘" in compact or "campus" in compact:
        return "campus"
    return None


def _scan_js_string(script: str, start: int) -> tuple[str, int]:
    quote = script[start]
    escaped = False
    chars: list[str] = []
    for index in range(start + 1, len(script)):
        char = script[index]
        if escaped:
            chars.append("\\")
            chars.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == quote:
            return "".join(chars), index + 1
        else:
            chars.append(char)
    raise DeepSeekBundleError("JSON.parse string literal is incomplete")


def _decode_js_string(raw: str) -> str:
    escapes = {
        "\\": "\\",
        "/": "/",
        "'": "'",
        '"': '"',
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
    }
    decoded: list[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char != "\\":
            decoded.append(char)
            index += 1
            continue
        index += 1
        if index >= len(raw):
            raise DeepSeekBundleError("JavaScript escape is incomplete")
        escape = raw[index]
        if escape in escapes:
            decoded.append(escapes[escape])
            index += 1
            continue
        if escape in {"x", "u"}:
            width = 2 if escape == "x" else 4
            digits = raw[index + 1 : index + 1 + width]
            if len(digits) != width or not re.fullmatch(r"[0-9A-Fa-f]+", digits):
                raise DeepSeekBundleError("JavaScript hex escape is invalid")
            decoded.append(chr(int(digits, 16)))
            index += width + 1
            continue
        raise DeepSeekBundleError(f"unsupported JavaScript escape: \\{escape}")
    return "".join(decoded)
