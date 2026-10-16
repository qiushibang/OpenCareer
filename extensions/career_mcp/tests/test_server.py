import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.server import get_mock_jobs, health_check


def test_health_check_reports_stage2_database_status(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))
    result = health_check()

    assert result["ok"] is True
    assert result["data"]["service"] == "career-mcp"
    assert result["data"]["mode"] == "stage2"
    assert result["data"]["database"]["schema_version"] == 0
    assert result["warnings"] == []
    assert "generated_at" in result["meta"]


def test_get_mock_jobs_returns_two_traceable_jobs():
    result = get_mock_jobs()

    assert result["ok"] is True
    jobs = result["data"]["jobs"]
    assert [job["id"] for job in jobs] == [
        "mock-ai-product-intern",
        "mock-agent-fullstack-intern",
    ]
    assert all(job["source_url"].startswith("https://") for job in jobs)
