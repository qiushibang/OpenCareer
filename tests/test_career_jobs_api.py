from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from coworker.server.app import create_app
from coworker.server.manager import SessionManager
from extensions.career_mcp.services.jobs import JobService


JD = """职位：大模型算法工程师
公司：DeepSeek
工作地点：北京
岗位职责：
1. 负责大模型训练与评测
任职要求：
1. 熟悉 Python
"""
def _client_with_jobs(tmp_path, monkeypatch) -> tuple[TestClient, str]:
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))
    service = JobService()
    values = {
        "raw_text": JD,
        "source_url": "https://careers.deepseek.com/jobs/one",
        "company_name": "DeepSeek",
        "title": "大模型算法工程师",
    }
    preview = service.import_manual_jd(**values, confirmed=False)
    created = service.import_manual_jd(
        **values,
        preview_hash=preview["preview_hash"],
        confirmed=True,
    )
    return (
        TestClient(create_app(SessionManager(data_dir=tmp_path / "state"))),
        created["job_id"],
    )

def test_jobs_api_defaults_to_active_and_supports_combined_filters(
    tmp_path,
    monkeypatch,
):
    client, job_id = _client_with_jobs(tmp_path, monkeypatch)

    response = client.get("/v1/career/jobs")
    filtered = client.get(
        "/v1/career/jobs",
        params={
            "query": "大模型",
            "company_slug": "deepseek",
            "location": "北京",
            "recruitment_type": "social",
            "status": "active",
            "limit": 20,
            "offset": 0,
        },
    )

    assert response.status_code == 200
    assert response.json()["jobs"][0]["id"] == job_id
    assert all(job["status"] == "active" for job in response.json()["jobs"])
    assert "description_raw" not in response.json()["jobs"][0]
    assert "responsibilities" not in response.json()["jobs"][0]
    assert "requirements" not in response.json()["jobs"][0]
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 0


def test_jobs_api_returns_detail_and_filter_options(tmp_path, monkeypatch):
    client, job_id = _client_with_jobs(tmp_path, monkeypatch)

    detail = client.get(f"/v1/career/jobs/{job_id}")
    filters = client.get("/v1/career/jobs/filters")

    assert detail.status_code == 200
    assert detail.json()["job"]["source_url"].startswith("https://")
    assert detail.json()["job"]["versions"][0]["version_number"] == 1
    assert detail.json()["job"]["events"][0]["event_type"] == "created"
    assert filters.status_code == 200
    assert filters.json()["filters"]["companies"] == [
        {"slug": "deepseek", "name": "DeepSeek", "count": 1}
    ]


def test_jobs_api_returns_stable_not_found_error(tmp_path, monkeypatch):
    client, _ = _client_with_jobs(tmp_path, monkeypatch)

    response = client.get("/v1/career/jobs/missing-job")

    assert response.status_code == 404
    assert response.json()["error"] == {
        "code": "JOB_NOT_FOUND",
        "message": "岗位不存在或已被删除。",
    }


def test_job_tracking_api_updates_and_filters(tmp_path, monkeypatch):
    client, job_id = _client_with_jobs(tmp_path, monkeypatch)

    initial = client.get(f"/v1/career/jobs/{job_id}/tracking")
    updated = client.patch(
        f"/v1/career/jobs/{job_id}/tracking",
        json={
            "expected_version": 0,
            "is_favorite": True,
            "application_status": "preparing",
            "note": "准备申请",
        },
    )
    filtered = client.get(
        "/v1/career/jobs",
        params={"favorite_only": "true", "status": ""},
    )

    assert initial.status_code == 200
    assert initial.json()["tracking"]["version"] == 0
    assert updated.status_code == 200
    assert updated.json()["tracking"]["version"] == 1
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["jobs"][0]["id"] == job_id


def test_job_tracking_api_returns_stable_errors(tmp_path, monkeypatch):
    client, job_id = _client_with_jobs(tmp_path, monkeypatch)
    created = client.patch(
        f"/v1/career/jobs/{job_id}/tracking",
        json={"expected_version": 0, "is_favorite": True},
    )
    invalid = client.patch(
        f"/v1/career/jobs/{job_id}/tracking",
        json={
            "expected_version": 1,
            "application_status": "unknown",
        },
    )
    stale = client.patch(
        f"/v1/career/jobs/{job_id}/tracking",
        json={
            "expected_version": 0,
            "application_status": "applied",
        },
    )
    missing = client.get("/v1/career/jobs/missing/tracking")
    invalid_filter = client.get(
        "/v1/career/jobs",
        params={"application_status": "unknown"},
    )

    assert created.status_code == 200
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_STATUS"
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "VERSION_CONFLICT"
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "JOB_NOT_FOUND"
    assert invalid_filter.status_code == 400
    assert invalid_filter.json()["error"]["code"] == "INVALID_STATUS"
    assert "sqlite" not in str(stale.json()).lower()


@pytest.mark.parametrize("payload", [None, [], "invalid", 1, True])
def test_job_tracking_api_rejects_non_object_json(
    tmp_path,
    monkeypatch,
    payload,
):
    client, job_id = _client_with_jobs(tmp_path, monkeypatch)

    response = client.patch(
        f"/v1/career/jobs/{job_id}/tracking",
        json=payload,
    )

    assert response.status_code == 400
    assert response.json() == {
        "ok": False,
        "error": {
            "code": "INVALID_INPUT",
            "message": "岗位跟踪参数无效。",
        },
    }
