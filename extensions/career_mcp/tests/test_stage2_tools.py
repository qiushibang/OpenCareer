import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp import server


RAW_JD = """职位：AI 产品经理实习生
公司：示例 AI 公司
工作地点：北京
岗位职责：
1. 调研
任职要求：
1. 熟悉大模型
"""


def test_import_manual_jd_preview_uses_envelope_without_writing(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))

    result = server.import_manual_jd(raw_text=RAW_JD)

    assert result["ok"] is True
    assert result["data"]["confirmation_required"] is True
    assert result["data"]["preview"]["title"] == "AI 产品经理实习生"
    assert len(result["data"]["preview_hash"]) == 64
    assert result["warnings"] == []
    assert "generated_at" in result["meta"]
    assert not (tmp_path / "career" / "career.sqlite3").exists()


def test_import_then_get_and_search_return_traceable_data(tmp_path, monkeypatch):
    monkeypatch.setenv("CAREER_DATA_DIR", str(tmp_path / "career"))

    preview = server.import_manual_jd(raw_text=RAW_JD)
    imported = server.import_manual_jd(
        raw_text=RAW_JD,
        preview_hash=preview["data"]["preview_hash"],
        confirmed=True,
    )
    job_id = imported["data"]["job_id"]

    detail = server.get_job(job_id=job_id)
    search = server.search_jobs(query="大模型", locations=["北京"])

    assert imported["data"]["created"] is True
    assert detail["data"]["source_url"].startswith("manual://")
    assert search["data"]["total"] == 1
    assert search["data"]["jobs"][0]["id"] == job_id


def test_import_manual_jd_uses_configured_job_service(monkeypatch):
    calls = []

    class FakeService:
        def import_manual_jd(self, **values):
            calls.append(values)
            return {"confirmation_required": True, "preview": {}}

    monkeypatch.setattr(server, "_job_service", lambda: FakeService())

    result = server.import_manual_jd(raw_text=RAW_JD)

    assert result["ok"] is True
    assert calls == [
        {
            "raw_text": RAW_JD,
            "source_url": None,
            "company_name": None,
            "title": None,
            "preview_hash": None,
            "confirmed": False,
        }
    ]


def test_preview_public_job_url_uses_guarded_service(monkeypatch):
    calls = []

    class FakeService:
        def preview(self, url):
            calls.append(url)
            return {
                "final_url": url,
                "content_type": "text/html",
                "truncated": False,
                "text": "公开岗位正文" * 20,
            }

    monkeypatch.setattr(
        server,
        "PublicJobUrlService",
        lambda: FakeService(),
    )

    result = server.preview_public_job_url(
        "https://careers.example.com/jobs/1"
    )

    assert result["ok"] is True
    assert calls == ["https://careers.example.com/jobs/1"]
