import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp import server
from extensions.career_mcp.services.job_tracking import (
    JobTrackingServiceError,
)
from extensions.career_mcp.services.resumes import ResumeService


TEXT = """Zhang San
Phone: 13800001234
Email: zhang@example.com
AI Engineer with Python experience
"""
PROPOSAL = {
    "basic": {
        "name": "Zhang San",
        "phone": "13800001234",
        "email": "zhang@example.com",
        "location": "Beijing",
        "summary": "AI Engineer",
    },
    "education": [],
    "experience": [],
    "project": [],
    "skill": [],
    "missing_fields": [],
    "warnings": [],
}


def _stage(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))
    monkeypatch.setenv("CAREER_PRIVATE_DIR", str(tmp_path / "private"))
    return ResumeService().stage_resume(
        filename="resume.txt",
        mime="text/plain",
        text=TEXT,
    )


def test_resume_mcp_preview_confirm_and_masked_profile(
    tmp_path,
    monkeypatch,
):
    staged = _stage(tmp_path, monkeypatch)

    imported = server.get_resume_import_text(staged["upload_token"])
    preview = server.preview_resume_import(
        staged["upload_token"],
        PROPOSAL,
    )
    confirmed = server.confirm_resume_sections(
        preview["data"]["preview_token"],
        ["basic"],
        {},
    )
    profile = server.get_candidate_profile()

    assert imported["ok"] is True
    assert imported["data"]["text"] == TEXT.strip()
    assert imported["data"]["extraction_method"] == "native"
    assert imported["data"]["review_required"] is False
    assert imported["data"]["warnings"] == []
    assert imported["data"]["extraction_metadata"]["engine"] is None
    assert imported["data"]["extraction_metadata"]["ocr_pages"] == []
    serialized = str(imported["data"])
    for forbidden in (
        "private_path",
        "model_path",
        "polygon",
        "page_image",
    ):
        assert forbidden not in serialized
    assert preview["ok"] is True
    assert confirmed["data"]["version"] == 1
    assert profile["data"]["sections"]["basic"]["phone"] == "*******1234"


def test_resume_mcp_returns_stable_private_error(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))
    monkeypatch.setenv("CAREER_PRIVATE_DIR", str(tmp_path / "private"))

    result = server.get_resume_import_text("missing-token")

    assert result["ok"] is False
    assert result["error"]["code"] == "UPLOAD_NOT_FOUND"
    assert "private" not in result["error"]["message"].lower()


def test_get_confirmed_resume_returns_only_selected_masked_document(
    tmp_path,
    monkeypatch,
):
    staged = _stage(tmp_path, monkeypatch)
    preview = server.preview_resume_import(
        staged["upload_token"],
        PROPOSAL,
    )
    server.confirm_resume_sections(
        preview["data"]["preview_token"],
        ["basic"],
        {},
    )
    resume_id = server.list_confirmed_resumes()["data"]["resumes"][0]["id"]

    result = server.get_confirmed_resume(resume_id)

    assert result["ok"] is True
    assert result["data"]["id"] == resume_id
    assert result["data"]["sections"]["basic"]["phone"] == "*******1234"
    assert result["data"]["sections"]["basic"]["email"] == "z***@example.com"
    serialized = str(result["data"])
    assert "private_path" not in serialized
    assert "upload_token" not in serialized


def test_get_confirmed_resume_returns_stable_not_found_error(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))
    monkeypatch.setenv("CAREER_PRIVATE_DIR", str(tmp_path / "private"))

    result = server.get_confirmed_resume("missing-resume")

    assert result["ok"] is False
    assert result["error"]["code"] == "RESUME_NOT_FOUND"
    assert "private" not in result["error"]["message"].lower()


def test_resume_mcp_discard_and_delete_require_valid_state(
    tmp_path,
    monkeypatch,
):
    staged = _stage(tmp_path, monkeypatch)
    preview = server.preview_resume_import(
        staged["upload_token"],
        PROPOSAL,
    )

    discarded = server.discard_resume_import(
        preview["data"]["preview_token"]
    )
    missing = server.get_resume_import_text(staged["upload_token"])
    denied = server.delete_candidate_profile("delete")

    assert discarded["ok"] is True
    assert missing["error"]["code"] == "UPLOAD_NOT_FOUND"
    assert denied["error"]["code"] == "CONFIRMATION_REQUIRED"


def test_job_tracking_mcp_tools_use_shared_services(monkeypatch):
    calls = []
    tracking = SimpleNamespace(
        get=lambda job_id: calls.append(("get", job_id)) or {
            "job_id": job_id,
            "version": 0,
        },
        update=lambda job_id, patch: (
            calls.append(("update", job_id, patch))
            or {"job_id": job_id, "version": 1}
        ),
    )
    jobs = SimpleNamespace(
        search_jobs=lambda **filters: (
            calls.append(("list", filters))
            or {
                "jobs": [],
                "total": 0,
                "limit": 20,
                "offset": 0,
            }
        )
    )
    monkeypatch.setattr(
        server,
        "_job_tracking_service",
        lambda: tracking,
        raising=False,
    )
    monkeypatch.setattr(
        server,
        "_job_service",
        lambda: jobs,
        raising=False,
    )

    read = server.get_job_tracking("job-1")
    listed = server.list_tracked_jobs(
        True,
        "preparing",
        20,
        0,
    )
    updated = server.update_job_tracking(
        "job-1",
        0,
        True,
        "preparing",
        "准备材料",
    )

    assert read["data"]["version"] == 0
    assert listed["data"]["total"] == 0
    assert updated["data"]["version"] == 1
    assert calls == [
        ("get", "job-1"),
        (
            "list",
            {
                "favorite_only": True,
                "application_status": "preparing",
                "limit": 20,
                "offset": 0,
            },
        ),
        (
            "update",
            "job-1",
            {
                "expected_version": 0,
                "is_favorite": True,
                "application_status": "preparing",
                "note": "准备材料",
            },
        ),
    ]


def test_job_tracking_mcp_returns_stable_conflict(monkeypatch):
    def fail(_job_id, _patch):
        raise JobTrackingServiceError(
            "VERSION_CONFLICT",
            "tracking record changed",
        )

    monkeypatch.setattr(
        server,
        "_job_tracking_service",
        lambda: SimpleNamespace(update=fail),
        raising=False,
    )

    result = server.update_job_tracking(
        "job-1",
        0,
        application_status="applied",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "VERSION_CONFLICT"
    assert result["error"]["retryable"] is False


def test_list_tracked_jobs_returns_invalid_status(monkeypatch):
    def fail(**_filters):
        raise JobTrackingServiceError(
            "INVALID_STATUS",
            "unsupported application status",
        )

    monkeypatch.setattr(
        server,
        "_job_service",
        lambda: SimpleNamespace(search_jobs=fail),
    )

    result = server.list_tracked_jobs(
        application_status="unknown",
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_STATUS"
