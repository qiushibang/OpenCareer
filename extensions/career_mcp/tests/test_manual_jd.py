import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.domain.manual_jd import (
    clean_manual_jd,
    company_slug,
    manual_content_hash,
    parse_manual_jd,
)


RAW_JD = """
AI 产品经理实习生

公司：示例 AI 公司
工作地点： 北京
岗位职责：
1. 参与 AI 产品调研
2. 支持需求分析

任职要求：
1. 熟悉大模型产品
2. 每周实习 4 天
"""


def test_parse_manual_jd_extracts_explicit_fields_without_guessing():
    parsed = parse_manual_jd(clean_manual_jd(RAW_JD))

    assert parsed.title == "AI 产品经理实习生"
    assert parsed.company_name == "示例 AI 公司"
    assert parsed.location_raw == "北京"
    assert parsed.locations == ["北京"]
    assert parsed.recruitment_type == "internship"
    assert parsed.responsibilities == ["参与 AI 产品调研", "支持需求分析"]
    assert parsed.requirements == ["熟悉大模型产品", "每周实习 4 天"]
    assert parsed.missing_fields == []


def test_parse_manual_jd_reports_missing_fields_instead_of_inventing_values():
    parsed = parse_manual_jd("岗位职责：\n- 整理资料")

    assert parsed.title is None
    assert parsed.company_name is None
    assert parsed.location_raw is None
    assert parsed.recruitment_type is None
    assert parsed.requirements == []
    assert {"title", "company_name", "location", "recruitment_type", "requirements"} <= set(
        parsed.missing_fields
    )


def test_manual_text_normalization_and_identity_are_stable():
    cleaned = clean_manual_jd(" 职位：测试实习生  \n\n\n 工作地点：北京 ")

    assert cleaned == "职位：测试实习生\n\n工作地点：北京"
    assert clean_manual_jd(cleaned) == cleaned
    assert manual_content_hash(cleaned) == manual_content_hash(cleaned)
    assert company_slug("示例 AI 公司") == company_slug("示例 AI 公司")
    assert company_slug("示例公司").startswith("manual-company-")
