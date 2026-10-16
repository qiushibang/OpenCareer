from __future__ import annotations

import logging
import subprocess
import sys

from fastapi.testclient import TestClient

from coworker.server.app import create_app
from coworker.server.manager import SessionManager
from extensions.career_mcp.services.resumes import ResumeService


RESUME_TEXT = """Zhang San
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
    "skill": [{"name": "Python", "level": None, "evidence": None}],
    "missing_fields": [],
    "warnings": [],
}


def _client_with_profile(
    tmp_path,
    monkeypatch,
    *,
    filename: str = "candidate-resume.txt",
) -> TestClient:
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))
    monkeypatch.setenv("CAREER_PRIVATE_DIR", str(tmp_path / "private"))
    service = ResumeService()
    staged = service.stage_resume(
        filename=filename,
        mime="text/plain",
        text=RESUME_TEXT,
    )
    preview = service.preview_resume_import(staged["upload_token"], PROPOSAL)
    service.confirm_resume_sections(
        preview["preview_token"],
        ["basic", "skill"],
        corrections={},
    )
    return TestClient(create_app(SessionManager(data_dir=tmp_path / "state")))


def test_profile_api_masks_profile_and_lists_versions(tmp_path, monkeypatch):
    client = _client_with_profile(tmp_path, monkeypatch)

    profile = client.get("/v1/career/profile")
    versions = client.get("/v1/career/profile/versions")
    original = client.get("/v1/career/profile/original")

    assert profile.status_code == 200
    assert profile.json()["profile"]["sections"]["basic"]["phone"] == "*******1234"
    assert versions.json()["versions"][0]["confirmed_sections"] == ["basic", "skill"]
    assert original.json()["original"] == {
        "filename": "candidate-resume.txt",
        "source_kind": "text",
        "size": len(RESUME_TEXT.strip().encode()),
        "preview_kind": "text",
    }
    assert "private_path" not in str(original.json())


def test_profile_original_content_and_download_are_private_file_bytes(
    tmp_path,
    monkeypatch,
):
    client = _client_with_profile(tmp_path, monkeypatch)

    content = client.get("/v1/career/profile/original/content")
    download = client.get("/v1/career/profile/original/download")

    assert content.status_code == 200
    assert content.headers["content-type"].startswith("text/plain")
    assert content.content == RESUME_TEXT.strip().encode()
    assert download.content == RESUME_TEXT.strip().encode()
    assert (
        download.headers["content-disposition"]
        == 'attachment; filename="candidate-resume.txt"'
    )


def test_profile_original_supports_non_ascii_filename(tmp_path, monkeypatch):
    client = _client_with_profile(
        tmp_path,
        monkeypatch,
        filename="邱仕邦-简历.txt",
    )

    content = client.get("/v1/career/profile/original/content")
    download = client.get("/v1/career/profile/original/download")

    assert content.status_code == 200
    assert download.status_code == 200
    assert (
        "filename*=UTF-8''%E9%82%B1%E4%BB%95%E9%82%A6-%E7%AE%80%E5%8E%86.txt"
        in download.headers["content-disposition"]
    )


def test_resume_library_api_selects_each_confirmed_resume_by_id(
    tmp_path,
    monkeypatch,
):
    client = _client_with_profile(tmp_path, monkeypatch)
    service = ResumeService()
    staged = service.stage_resume(
        filename="产品经理简历.txt",
        mime="text/plain",
        text=f"{RESUME_TEXT}\nProduct manager version",
    )
    preview = service.preview_resume_import(
        staged["upload_token"],
        {
            **PROPOSAL,
            "basic": {
                **PROPOSAL["basic"],
                "summary": "Product manager version",
            },
        },
    )
    service.confirm_resume_sections(
        preview["preview_token"],
        ["basic"],
        corrections={},
    )

    listing = client.get("/v1/career/resumes")
    documents = listing.json()["resumes"]
    selected = next(
        item for item in documents if item["filename"] == "产品经理简历.txt"
    )
    detail = client.get(f"/v1/career/resumes/{selected['id']}")
    versions = client.get(
        f"/v1/career/resumes/{selected['id']}/versions"
    )
    original = client.get(
        f"/v1/career/resumes/{selected['id']}/original"
    )
    content = client.get(
        f"/v1/career/resumes/{selected['id']}/original/content"
    )
    missing = client.get("/v1/career/resumes/missing")

    assert listing.status_code == 200
    assert {item["filename"] for item in documents} == {
        "candidate-resume.txt",
        "产品经理简历.txt",
    }
    assert detail.json()["resume"]["sections"]["basic"]["phone"] == "*******1234"
    assert versions.json()["versions"]
    assert original.json()["original"]["filename"] == "产品经理简历.txt"
    assert "private_path" not in str(original.json())
    assert content.content.endswith(b"Product manager version")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RESUME_NOT_FOUND"


def test_resume_metadata_update_and_single_delete_api(
    tmp_path,
    monkeypatch,
):
    client = _client_with_profile(tmp_path, monkeypatch)
    resume = client.get("/v1/career/resumes").json()["resumes"][0]

    invalid = client.patch(
        f"/v1/career/resumes/{resume['id']}",
        json={"display_name": "", "target_roles": []},
    )
    updated = client.patch(
        f"/v1/career/resumes/{resume['id']}",
        json={
            "display_name": "AI 产品经理简历",
            "target_roles": ["AI 产品经理", "Agent 产品经理"],
        },
    )
    denied = client.request(
        "DELETE",
        f"/v1/career/resumes/{resume['id']}",
        json={"confirm_name": "错误名称"},
    )
    deleted = client.request(
        "DELETE",
        f"/v1/career/resumes/{resume['id']}",
        json={"confirm_name": "AI 产品经理简历"},
    )

    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_INPUT"
    assert updated.status_code == 200
    assert updated.json()["resume"]["display_name"] == "AI 产品经理简历"
    assert updated.json()["resume"]["target_roles"] == [
        "AI 产品经理",
        "Agent 产品经理",
    ]
    assert "private_path" not in str(updated.json())
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert deleted.status_code == 200
    assert deleted.json()["deleted"]["resume_id"] == resume["id"]
    assert deleted.json()["deleted"]["original_removed"] is True
    assert client.get(f"/v1/career/resumes/{resume['id']}").status_code == 404
    assert client.get("/v1/career/profile").status_code == 200


def test_profile_delete_requires_exact_confirmation(tmp_path, monkeypatch):
    client = _client_with_profile(tmp_path, monkeypatch)

    denied = client.request(
        "DELETE",
        "/v1/career/profile",
        json={"confirm_text": "删除"},
    )
    deleted = client.request(
        "DELETE",
        "/v1/career/profile",
        json={"confirm_text": "DELETE MY CAREER PROFILE"},
    )
    missing = client.get("/v1/career/profile")

    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert deleted.status_code == 200
    assert deleted.json()["deleted"]["profiles"] == 1
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PROFILE_NOT_FOUND"


def test_profile_api_logs_unexpected_errors_without_exposing_them(
    tmp_path,
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(
        ResumeService,
        "get_candidate_profile",
        lambda self, **kwargs: (_ for _ in ()).throw(
            RuntimeError("private database detail")
        ),
    )
    client = TestClient(create_app(SessionManager(data_dir=tmp_path / "state")))

    with caplog.at_level(logging.ERROR, logger="coworker.server"):
        response = client.get("/v1/career/profile")

    assert response.status_code == 409
    assert response.json()["error"] == {
        "code": "PERSISTENCE_ERROR",
        "message": "本地求职档案读取失败。",
    }
    assert "private database detail" not in response.text
    assert "private database detail" in caplog.text


def test_installed_server_can_import_career_extension_outside_repo(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from extensions.career_mcp.services.resumes import ResumeService",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
