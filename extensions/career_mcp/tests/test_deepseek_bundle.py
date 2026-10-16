import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.crawler.deepseek import (
    DeepSeekAccessRestricted,
    DeepSeekBundleError,
    DeepSeekStaticBundleAdapter,
    extract_bundle_url,
    extract_json_parse_values,
    fetch_public_text,
    html_to_text,
    parse_deepseek_dataset,
    select_deepseek_dataset,
)
from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler.adapters import default_adapters
from extensions.career_mcp.services.crawler import CrawlerService

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "deepseek-careers"
ENTRY_URL = "https://talent.deepseek.com/"
OBSERVED_AT = "2026-08-05T00:00:00Z"


def _entry_html() -> str:
    return (FIXTURE_DIR / "index.html").read_text(encoding="utf-8")


def _main_js() -> str:
    return (FIXTURE_DIR / "main.js").read_text(encoding="utf-8")


def test_extract_bundle_url_requires_one_same_origin_main_script():
    assert extract_bundle_url(_entry_html(), ENTRY_URL) == (
        "https://talent.deepseek.com/static/main.264ac482b7.js"
    )


def test_extract_bundle_url_rejects_foreign_or_duplicate_scripts():
    foreign = '<script src="https://example.com/static/main.abc.js"></script>'
    duplicate = (
        '<script src="/static/main.abc.js"></script>'
        '<script src="/static/main.def.js"></script>'
    )

    with pytest.raises(DeepSeekBundleError, match="exactly one"):
        extract_bundle_url(foreign, ENTRY_URL)
    with pytest.raises(DeepSeekBundleError, match="exactly one"):
        extract_bundle_url(duplicate, ENTRY_URL)


def test_extract_json_parse_values_handles_escaped_quotes():
    script = r"""var data=JSON.parse('{"text":"DeepSeek\'s Agent"}');"""

    assert extract_json_parse_values(script) == [{"text": "DeepSeek's Agent"}]


def test_extract_json_parse_values_reads_fixture_objects():
    values = extract_json_parse_values(_main_js())

    assert values[0] == {"theme": "dark"}
    assert values[1]["sourceUrl"].endswith("/high-flyer/140576#/")


@pytest.mark.parametrize(
    "script",
    [
        r"""JSON.parse('{"bad":"\q"}')""",
        r"""JSON.parse('{"bad":"unfinished}');""",
    ],
)
def test_extract_json_parse_values_rejects_invalid_literals(script):
    with pytest.raises(DeepSeekBundleError):
        extract_json_parse_values(script)


def test_parse_fixture_maps_uuid_locations_and_complete_jd():
    metadata = json.loads((FIXTURE_DIR / "metadata.json").read_text(encoding="utf-8"))

    dataset = select_deepseek_dataset(_main_js())
    jobs = parse_deepseek_dataset(dataset, observed_at=OBSERVED_AT)

    assert [job.external_job_id for job in jobs] == metadata["expected_job_ids"]
    assert jobs[0].source_url.endswith(f"/job/{jobs[0].external_job_id}")
    assert jobs[0].location_raw == "北京市 海淀区、浙江 拱墅区"
    assert "【团队使命】" in jobs[0].description_raw
    assert "<p>" not in jobs[0].description_raw
    assert jobs[0].recruitment_type is None
    assert {job.observed_at for job in jobs} == {OBSERVED_AT}


def test_html_to_text_preserves_block_boundaries():
    assert html_to_text("<p>第一段<br>第二行</p><p><strong>第三段</strong></p>") == (
        "第一段\n第二行\n第三段"
    )


def test_select_deepseek_dataset_rejects_wrong_or_duplicate_tenants():
    wrong = """JSON.parse('{"sourceUrl":"https://example.com/","jobs":[],"total":0}')"""
    duplicate = _main_js() + _main_js()

    with pytest.raises(DeepSeekBundleError, match="exactly one"):
        select_deepseek_dataset(wrong)
    with pytest.raises(DeepSeekBundleError, match="exactly one"):
        select_deepseek_dataset(duplicate)


def test_parse_deepseek_dataset_rejects_total_mismatch():
    dataset = select_deepseek_dataset(_main_js())
    dataset["total"] = 3

    with pytest.raises(DeepSeekBundleError, match="total"):
        parse_deepseek_dataset(dataset, observed_at=OBSERVED_AT)


def test_parse_deepseek_dataset_rejects_duplicate_or_invalid_uuid():
    duplicate = select_deepseek_dataset(_main_js())
    duplicate["jobs"][1]["id"] = duplicate["jobs"][0]["id"]
    invalid = select_deepseek_dataset(_main_js())
    invalid["jobs"][0]["id"] = "not-a-uuid"

    with pytest.raises(DeepSeekBundleError, match="duplicate"):
        parse_deepseek_dataset(duplicate, observed_at=OBSERVED_AT)
    with pytest.raises(DeepSeekBundleError, match="UUID"):
        parse_deepseek_dataset(invalid, observed_at=OBSERVED_AT)


def test_adapter_fetches_entry_then_discovered_bundle():
    requested: list[tuple[str, str]] = []
    fixtures = {"entry": _entry_html(), "bundle": _main_js()}

    def fetch_text(url: str, kind: str) -> str:
        requested.append((url, kind))
        return fixtures[kind]

    adapter = DeepSeekStaticBundleAdapter(
        fetch_text=fetch_text,
        clock=lambda: OBSERVED_AT,
    )

    jobs = adapter.fetch_jobs()

    assert adapter.source_slug == "deepseek-careers"
    assert requested == [
        ("https://talent.deepseek.com/", "entry"),
        ("https://talent.deepseek.com/static/main.264ac482b7.js", "bundle"),
    ]
    assert len(jobs) == 2


class _Headers:
    def __init__(self, content_type: str) -> None:
        self._content_type = content_type

    def get_content_type(self) -> str:
        return self._content_type


class _Response:
    def __init__(
        self,
        body: bytes,
        *,
        url: str,
        content_type: str,
    ) -> None:
        self.status = 200
        self.url = url
        self.headers = _Headers(content_type)
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return None

    def read(self, _: int) -> bytes:
        return self._body


def test_fetch_public_text_applies_kind_specific_contract(monkeypatch):
    requested = []

    def fake_urlopen(request, timeout):
        requested.append((request.full_url, request.headers, timeout))
        return _Response(
            _entry_html().encode(),
            url=request.full_url,
            content_type="text/html",
        )

    monkeypatch.setattr(
        "extensions.career_mcp.crawler.deepseek.urlopen",
        fake_urlopen,
    )

    text = fetch_public_text(ENTRY_URL, "entry")

    assert text.startswith("<!doctype html>")
    assert requested[0][2] == 15
    assert "Cookie" not in requested[0][1]


def test_fetch_public_text_rejects_foreign_redirect(monkeypatch):
    monkeypatch.setattr(
        "extensions.career_mcp.crawler.deepseek.urlopen",
        lambda *_args, **_kwargs: _Response(
            _entry_html().encode(),
            url="https://example.com/login",
            content_type="text/html",
        ),
    )

    with pytest.raises(DeepSeekAccessRestricted, match="redirect host"):
        fetch_public_text(ENTRY_URL, "entry")


def test_default_registry_enables_deepseek_and_xiaomi():
    slugs = {adapter.source_slug for adapter in default_adapters()}

    assert {"deepseek-careers", "xiaomi-careers"} <= slugs


def test_fixture_adapter_drives_existing_state_machine(tmp_path):
    fixtures = {"entry": _entry_html(), "bundle": _main_js()}
    adapter = DeepSeekStaticBundleAdapter(
        fetch_text=lambda _url, kind: fixtures[kind],
        clock=lambda: OBSERVED_AT,
    )
    service = CrawlerService(
        CareerConfig(data_dir=tmp_path / "career"),
        adapters=[adapter],
    )

    created = service.crawl_registered_source("deepseek-careers")
    unchanged = service.crawl_registered_source("deepseek-careers")
    fixtures["bundle"] = fixtures["bundle"].replace(
        "在这里，你将深入公司核心业务",
        "在这里，你将深入 DeepSeek 核心业务",
        1,
    )
    changed = service.crawl_registered_source("deepseek-careers")

    assert created.transitions == {"created": 2}
    assert unchanged.transitions == {"unchanged": 2}
    assert changed.transitions == {"changed": 1, "unchanged": 1}
