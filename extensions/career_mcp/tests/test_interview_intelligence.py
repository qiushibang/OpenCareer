from extensions.career_mcp.domain.interview_intelligence import (
    build_evidence_cards,
    build_probe_plan,
)


def test_evidence_cards_prioritize_experience_and_filter_secrets():
    cards = build_evidence_cards(
        {
            "project": [
                {
                    "name": "OpenCareer",
                    "highlights": [
                        "使用 Python 构建岗位匹配服务",
                        "设计 CAS 并发控制",
                    ],
                }
            ],
            "basic": {
                "summary": "求职 Agent 产品与工程经验",
                "email": "secret@example.com",
            },
        }
    )

    assert cards[0] == {
        "fact_path": "project[0].highlights[0]",
        "section": "project",
        "group_path": "project[0]",
        "excerpt": "使用 Python 构建岗位匹配服务",
    }
    assert "secret@example.com" not in str(cards)
    assert all(len(card["excerpt"]) <= 300 for card in cards)


def test_evidence_cards_are_unique_and_bounded():
    sections = {
        "project": [
            {"highlights": [f"项目证据 {index}"]}
            for index in range(20)
        ]
    }

    cards = build_evidence_cards(sections)

    assert len(cards) == 16
    assert len({card["fact_path"] for card in cards}) == 16


def test_standard_engineering_probe_prioritizes_core_project():
    plan = build_probe_plan(
        role_tracks=["engineering"],
        requirements=[
            {
                "requirement_id": "requirement-1",
                "category": "hard",
                "evidence_status": "direct",
                "evidence_paths": ["project[0].highlights[0]"],
            }
        ],
        evidence_cards=[
            {
                "fact_path": "project[0].highlights[0]",
                "section": "project",
                "group_path": "project[0]",
                "excerpt": "设计 CAS 并发控制",
                "requirement_ids": ["requirement-1"],
            }
        ],
        difficulty="standard",
        question_budget=8,
    )

    assert plan[0]["target_id"] == "project[0]"
    assert plan[0]["target_type"] == "resume_project"
    assert plan[0]["max_depth"] == 3
    assert {"implementation", "concurrency", "reliability"} <= set(
        plan[0]["dimensions"]
    )


def test_product_missing_requirement_has_safe_targets():
    plan = build_probe_plan(
        role_tracks=["product"],
        requirements=[
            {
                "requirement_id": "requirement-2",
                "category": "hard",
                "evidence_status": "none",
                "evidence_paths": [],
            }
        ],
        evidence_cards=[],
        difficulty="simple",
        question_budget=5,
    )

    assert plan[0]["target_type"] == "job_requirement"
    assert plan[0]["refs"] == ["requirement-2"]
    assert plan[0]["max_depth"] == 1
    assert "feature_design" in plan[0]["dimensions"]
    assert {item["target_type"] for item in plan} >= {
        "job_requirement",
        "role_scenario",
        "reflection",
    }


def test_direct_requirement_without_visible_card_degrades_to_job_target():
    plan = build_probe_plan(
        role_tracks=["engineering"],
        requirements=[
            {
                "requirement_id": "requirement-1",
                "category": "hard",
                "evidence_status": "direct",
                "evidence_paths": ["project[0].private_note"],
            }
        ],
        evidence_cards=[],
        difficulty="standard",
        question_budget=8,
    )

    assert plan[0]["target_type"] == "job_requirement"
    assert plan[0]["refs"] == ["requirement-1"]
