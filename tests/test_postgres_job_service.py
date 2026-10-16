from contextlib import contextmanager

from extensions.career_mcp.services.jobs import JobService


class _Repository:
    def __init__(self):
        self.created = []

    def ensure_manual_source(self, company_name):
        assert company_name == "示例 AI 公司"
        return "company-1", "source-1"

    def find_by_source_and_hash(self, source_id, content_hash):
        assert source_id == "source-1"
        assert len(content_hash) == 64
        return None

    def create_manual_job(self, **values):
        self.created.append(values)
        return "manual-job-1"

    def search_jobs(self, filters):
        return (
            [
                {
                    "id": "job-1",
                    "title": "AI Engineer",
                    "tracking": {
                        "is_favorite": True,
                        "application_status": "interviewing",
                        "version": 2,
                        "updated_at": "2026-08-19T00:00:00Z",
                    },
                }
            ],
            1,
        )

    def get_job(self, job_id):
        return {"id": job_id, "title": "AI Engineer"}

    def get_job_filters(self):
        return {"companies": [], "locations": []}


class _Tracking:
    def get(self, job_id):
        return {
            "job_id": job_id,
            "is_favorite": True,
            "application_status": "interviewing",
            "version": 2,
            "events": [],
        }


def test_job_service_uses_injected_cloud_repositories() -> None:
    repository = _Repository()
    sessions = []

    @contextmanager
    def repository_session(*, write=False):
        sessions.append(write)
        yield repository

    service = JobService(
        repository_session=repository_session,
        tracking_service=_Tracking(),
    )

    result = service.search_jobs(
        favorite_only=True,
        application_status="interviewing",
    )
    detail = service.get_job("job-1")
    filters = service.get_job_filters()

    assert result["total"] == 1
    assert result["jobs"][0]["tracking"]["version"] == 2
    assert detail["tracking"]["application_status"] == "interviewing"
    assert filters == {"companies": [], "locations": []}
    assert sessions == [False, False, False]


def test_manual_jd_confirmation_uses_injected_write_repository() -> None:
    repository = _Repository()
    sessions = []

    @contextmanager
    def repository_session(*, write=False):
        sessions.append(write)
        yield repository

    service = JobService(
        repository_session=repository_session,
        tracking_service=_Tracking(),
    )
    preview = service.import_manual_jd(
        raw_text=(
            "职位：AI 产品经理实习生\n"
            "公司：示例 AI 公司\n"
            "岗位职责：\n1. 参与产品调研\n"
            "任职要求：\n1. 熟悉大模型"
        ),
        confirmed=False,
    )

    result = service.import_manual_jd(
        raw_text=preview["preview"]["raw_text"],
        preview_hash=preview["preview_hash"],
        confirmed=True,
    )

    assert result == {
        "job_id": "manual-job-1",
        "created": True,
        "duplicate": False,
    }
    assert sessions == [True]
    assert repository.created[0]["company_id"] == "company-1"
