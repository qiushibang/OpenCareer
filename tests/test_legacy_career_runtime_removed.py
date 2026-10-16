from fastapi.testclient import TestClient

from coworker.server import alpha
from coworker.server.app import create_app
from coworker.server.manager import SessionManager
from extensions.career_mcp import server as career_server


RETIRED_MCP_TOOLS = {
    "list_job_match_candidates",
    "match_job_to_profile",
    "create_application_packet",
    "validate_application_packet",
    "prepare_tailored_resume",
    "submit_tailored_resume_proposals",
}


def test_retired_mcp_tools_are_not_registered():
    names = set(career_server.mcp._tool_manager._tools)

    assert names.isdisjoint(RETIRED_MCP_TOOLS)


def test_alpha_allowlist_excludes_retired_tools():
    names = alpha.conversation_tools()

    assert names.isdisjoint(
        {f"mcp__career__{name}" for name in RETIRED_MCP_TOOLS}
    )


def test_retired_http_routes_return_404(tmp_path, monkeypatch):
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))
    client = TestClient(
        create_app(SessionManager(data_dir=tmp_path / "state"))
    )

    requests = (
        ("GET", "/v1/career/jobs/job-1/matches"),
        ("POST", "/v1/career/jobs/job-1/matches"),
        ("GET", "/v1/career/jobs/job-1/tailored-resumes"),
        ("GET", "/v1/career/tailored-resumes/draft-1"),
        ("PATCH", "/v1/career/tailored-resumes/draft-1"),
        ("POST", "/v1/career/tailored-resumes/draft-1/confirm"),
        ("POST", "/v1/career/tailored-resumes/draft-1/export"),
        (
            "GET",
            "/v1/career/tailored-resume-exports/export-1/docx",
        ),
        (
            "GET",
            "/v1/career/tailored-resume-exports/export-1/pdf",
        ),
    )

    for method, path in requests:
        assert client.request(method, path, json={}).status_code == 404
