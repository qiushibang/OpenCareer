import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler.adapters import default_adapters
from extensions.career_mcp.crawler.zhipu import (
    ZHIPU_CAMPUS_SCOPE,
    ZHIPU_SOCIAL_SCOPE,
    ZhipuMokaAdapter,
    parse_zhipu_card,
)
from extensions.career_mcp.services.crawler import CrawlerService

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "zhipu-moka"
OBSERVED_AT = "2026-08-06T00:00:00Z"


def _json(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_parse_social_card_maps_scope_metadata():
    job = parse_zhipu_card(
        _json("social_page_1.json")["jobs"][0],
        scope=ZHIPU_SOCIAL_SCOPE,
        observed_at=OBSERVED_AT,
    )

    assert job.external_job_id == "ddf2a8a2-4d14-42aa-ac43-848be23c7cd2"
    assert job.recruitment_type == "experienced"
    assert job.location_raw is None
    assert "团队：张笑涵全职员工组" in job.description_raw


def test_parse_campus_card_maps_scope_metadata():
    job = parse_zhipu_card(
        _json("campus_page_1.json")["jobs"][0],
        scope=ZHIPU_CAMPUS_SCOPE,
        observed_at=OBSERVED_AT,
    )

    assert job.recruitment_type == "campus"
    assert job.location_raw == "北京市"
    assert "团队：数据工程团队" in job.description_raw
    assert "职类：算法研究" in job.description_raw


@pytest.mark.parametrize(
    ("metadata", "recruitment_type", "location", "category"),
    [
        (["实习"], "internship", None, None),
        (["全职", "北京市"], "campus", "北京市", None),
        (["其它", "算法研究", "北京市"], "campus", "北京市", "算法研究"),
    ],
)
def test_parse_campus_card_accepts_current_metadata_without_team(
    metadata,
    recruitment_type,
    location,
    category,
):
    raw = {**_json("campus_page_1.json")["jobs"][0], "metadata": metadata}

    job = parse_zhipu_card(
        raw,
        scope=ZHIPU_CAMPUS_SCOPE,
        observed_at=OBSERVED_AT,
    )

    assert job.recruitment_type == recruitment_type
    assert job.location_raw == location
    assert ("职类：" + category in job.description_raw) if category else (
        "职类：" not in job.description_raw
    )
    assert "团队：" not in job.description_raw


def test_fixture_scopes_create_jobs_through_pipeline(tmp_path):
    social = ZhipuMokaAdapter(
        ZHIPU_SOCIAL_SCOPE,
        fetch_dataset=lambda _: [_json("social_page_1.json")],
        clock=lambda: OBSERVED_AT,
    )
    campus = ZhipuMokaAdapter(
        ZHIPU_CAMPUS_SCOPE,
        fetch_dataset=lambda _: [_json("campus_page_1.json")],
        clock=lambda: OBSERVED_AT,
    )
    service = CrawlerService(
        CareerConfig(data_dir=tmp_path / "career"),
        adapters=[social, campus],
    )

    assert service.crawl_registered_source(social.source_slug).transitions == {
        "created": 1
    }
    assert service.crawl_registered_source(campus.source_slug).transitions == {
        "created": 1
    }


def test_default_registry_includes_only_live_accepted_zhipu_campus():
    slugs = {adapter.source_slug for adapter in default_adapters()}

    assert ZHIPU_CAMPUS_SCOPE.source_slug in slugs
    assert ZHIPU_SOCIAL_SCOPE.source_slug not in slugs
