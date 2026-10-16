import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.database.migrations import connect
from extensions.career_mcp.services.job_tracking import JobTrackingService
from extensions.career_mcp.services.jobs import JobService


RAW_JD = """职位：AI 产品经理实习生
公司：示例 AI 公司
工作地点：北京
岗位职责：
1. 参与产品调研
任职要求：
1. 熟悉大模型
"""


def _confirm(
    service: JobService,
    *,
    raw_text: str = RAW_JD,
    **values,
):
    preview = service.import_manual_jd(
        raw_text=raw_text,
        confirmed=False,
        **values,
    )
    return service.import_manual_jd(
        raw_text=raw_text,
        preview_hash=preview["preview_hash"],
        confirmed=True,
        **values,
    )


def test_manual_jd_preview_does_not_create_database(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    service = JobService(config)

    result = service.import_manual_jd(raw_text=RAW_JD, confirmed=False)

    assert result["confirmation_required"] is True
    assert result["preview"]["title"] == "AI 产品经理实习生"
    assert len(result["preview_hash"]) == 64
    assert not config.database_path.exists()


def test_manual_jd_confirmation_rejects_changed_preview(tmp_path):
    service = JobService(CareerConfig(data_dir=tmp_path / "career"))
    preview = service.import_manual_jd(raw_text=RAW_JD, confirmed=False)

    with pytest.raises(ValueError, match="preview changed"):
        service.import_manual_jd(
            raw_text=RAW_JD + "\n额外要求：熟悉评测",
            preview_hash=preview["preview_hash"],
            confirmed=True,
        )


def test_confirmed_manual_jd_is_idempotent_and_searchable(tmp_path):
    service = JobService(CareerConfig(data_dir=tmp_path / "career"))

    created = _confirm(
        service,
        source_url="https://careers.example.com/jobs/ai-product",
    )
    repeated = _confirm(service)

    assert created["created"] is True
    assert created["duplicate"] is False
    assert repeated == {
        "job_id": created["job_id"],
        "created": False,
        "duplicate": True,
    }
    detail = service.get_job(created["job_id"])
    assert detail["source_url"] == "https://careers.example.com/jobs/ai-product"
    assert detail["description_raw"] == RAW_JD.strip()
    assert len(detail["versions"]) == 1
    assert [event["event_type"] for event in detail["events"]] == ["created"]
    results = service.search_jobs(
        query="大模型",
        locations=["北京"],
        recruitment_types=["internship"],
    )
    assert results["total"] == 1
    assert results["jobs"][0]["id"] == created["job_id"]


def test_job_search_filters_tracking_before_pagination(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    jobs = JobService(config)
    tracking = JobTrackingService(config)
    job_ids = []
    for index in range(3):
        created = _confirm(
            jobs,
            raw_text=RAW_JD + f"\n序号：{index}",
            source_url=f"https://careers.example.com/jobs/{index}",
            company_name="示例 AI 公司",
            title=f"AI 产品经理 {index}",
        )
        job_ids.append(created["job_id"])
    favorite_job_id = job_ids[1]
    applied_job_id = job_ids[2]
    tracking.update(
        favorite_job_id,
        {"expected_version": 0, "is_favorite": True},
    )
    tracking.update(
        applied_job_id,
        {
            "expected_version": 0,
            "application_status": "applied",
        },
    )

    favorite = jobs.search_jobs(
        favorite_only=True,
        limit=1,
        offset=0,
    )
    applied = jobs.search_jobs(application_status="applied")
    not_started = jobs.search_jobs(
        application_status="not_started",
        limit=1,
        offset=0,
    )

    assert favorite["total"] == 1
    assert [job["id"] for job in favorite["jobs"]] == [
        favorite_job_id
    ]
    assert [job["id"] for job in applied["jobs"]] == [
        applied_job_id
    ]
    assert not_started["total"] == 2
    assert len(not_started["jobs"]) == 1
    assert not_started["jobs"][0]["tracking"][
        "application_status"
    ] == "not_started"
    assert favorite["jobs"][0]["tracking"]["is_favorite"] is True
    detail = jobs.get_job(applied_job_id)
    assert detail["tracking"]["events"][0]["to_status"] == "applied"


def test_job_search_rejects_unknown_application_status(tmp_path):
    service = JobService(CareerConfig(data_dir=tmp_path / "career"))

    with pytest.raises(ValueError):
        service.search_jobs(application_status="unknown")


def test_job_filters_are_derived_from_persisted_jobs(tmp_path):
    config = CareerConfig(data_dir=tmp_path / "career")
    service = JobService(config)
    _confirm(
        service,
        source_url="https://careers.example.com/jobs/one",
        company_name="小米",
        title="大模型工程师",
    )
    connection = connect(config.database_path)
    try:
        company_id = connection.execute(
            "SELECT id FROM companies WHERE name = '小米'"
        ).fetchone()["id"]
        connection.execute(
            "UPDATE companies SET slug = 'xiaomi' WHERE id = ?",
            (company_id,),
        )
        source_id = connection.execute(
            "SELECT id FROM job_sources WHERE company_id = ?",
            (company_id,),
        ).fetchone()["id"]
        template = connection.execute(
            "SELECT * FROM jobs LIMIT 1"
        ).fetchone()
        values = dict(template)
        values.update(
            {
                "id": "xiaomi-inactive",
                "canonical_url": "https://careers.example.com/jobs/two",
                "title": "平台工程师",
                "locations_json": '["上海"]',
                "location_raw": "上海",
                "recruitment_type": "social",
                "status": "inactive",
                "content_hash": "xiaomi-inactive",
            }
        )
        columns = list(values)
        connection.execute(
            f"INSERT INTO jobs({','.join(columns)}) "
            f"VALUES ({','.join('?' for _ in columns)})",
            [values[column] for column in columns],
        )
        connection.execute(
            """
            INSERT INTO companies(id, slug, name, created_at)
            VALUES ('deepseek-id', 'deepseek', 'DeepSeek', '2026-08-08T00:00:00Z')
            """
        )
        connection.execute(
            """
            INSERT INTO job_sources(id, company_id, slug, source_type, base_url, created_at)
            VALUES (
                'deepseek-source', 'deepseek-id', 'manual', 'manual', NULL,
                '2026-08-08T00:00:00Z'
            )
            """
        )
        values.update(
            {
                "id": "deepseek-active",
                "company_id": "deepseek-id",
                "source_id": "deepseek-source",
                "canonical_url": "https://careers.example.com/jobs/three",
                "title": "算法工程师",
                "locations_json": '["北京市、上海市、深圳市"]',
                "location_raw": "北京市、上海市、深圳市",
                "recruitment_type": "campus",
                "status": "active",
                "content_hash": "deepseek-active",
            }
        )
        connection.execute(
            f"INSERT INTO jobs({','.join(columns)}) "
            f"VALUES ({','.join('?' for _ in columns)})",
            [values[column] for column in columns],
        )
        connection.execute(
            """
            INSERT INTO job_tracking(
                job_id, is_favorite, favorited_at,
                application_status, version, created_at, updated_at
            ) VALUES (
                'deepseek-active', 1, '2026-08-08T00:00:00Z',
                'not_started', 1,
                '2026-08-08T00:00:00Z', '2026-08-08T00:00:00Z'
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    filters = service.get_job_filters()

    assert filters["companies"] == [
        {"slug": "deepseek", "name": "DeepSeek", "count": 1},
        {"slug": "xiaomi", "name": "小米", "count": 2},
    ]
    assert filters["locations"] == [
        {"value": "上海", "count": 2},
        {"value": "北京", "count": 2},
        {"value": "深圳", "count": 1},
    ]
    assert all("、" not in item["value"] for item in filters["locations"])
    assert filters["recruitment_types"] == [
        {"value": "campus", "count": 1},
        {"value": "internship", "count": 1},
        {"value": "social", "count": 1},
    ]
    assert filters["statuses"] == [
        {"value": "active", "count": 2},
        {"value": "inactive", "count": 1},
    ]
    assert filters["favorite_count"] == 1
    for location in ("北京", "上海", "深圳"):
        results = service.search_jobs(
            company_slugs=["deepseek"],
            locations=[location],
        )
        assert results["total"] == 1
        assert results["jobs"][0]["id"] == "deepseek-active"
