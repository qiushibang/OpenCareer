import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.services.jobs import JobService


def test_manual_jd_confirm_then_query_preserves_traceability(tmp_path):
    service = JobService(CareerConfig(data_dir=tmp_path / "career"))
    raw_text = """职位：Agent 全栈开发实习生
公司：示例公司
工作地点：北京
岗位职责：
1. 开发 Agent 应用
任职要求：
1. 熟悉工具调用
"""

    values = {
        "raw_text": raw_text,
        "source_url": "https://jobs.example.com/agent-intern",
    }
    preview = service.import_manual_jd(**values, confirmed=False)
    created = service.import_manual_jd(
        **values,
        preview_hash=preview["preview_hash"],
        confirmed=True,
    )
    detail = service.get_job(created["job_id"])
    result = service.search_jobs(
        query="工具调用",
        locations=["北京"],
        recruitment_types=["internship"],
        statuses=["active"],
    )

    assert detail["source_url"] == "https://jobs.example.com/agent-intern"
    assert detail["first_seen_at"].endswith("Z")
    assert detail["last_seen_at"].endswith("Z")
    assert detail["versions"][0]["version_number"] == 1
    assert detail["events"][0]["event_type"] == "created"
    assert result["total"] == 1
