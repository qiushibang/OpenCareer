import os
from pathlib import Path
from uuid import uuid4

import pytest

from coworker.server.identity import Principal
from coworker.storage.postgres.database import CloudDatabase
from deploy.test_database import validated_test_database_url
from extensions.career_mcp.database.postgres_catalog_repository import (
    PostgresCatalogRepository,
)
from extensions.career_mcp.domain.models import JobSearchFilters

ROOT = Path(__file__).resolve().parents[1]


class _Rows:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _SearchConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> _Rows:
        compact = " ".join(sql.split())
        self.calls.append((compact, params))
        if compact.startswith("SELECT COUNT(*)"):
            return _Rows([(29612,)])
        common = (
            "job-1",
            "bytedance",
            "字节跳动",
            "AI Engineer",
            "北京",
            ["北京"],
            "experienced",
            "active",
        )
        if "j.description_raw" in compact:
            return _Rows(
                [
                    common
                    + (
                        "Build AI",
                        ["Build"],
                        ["Python"],
                        "https://jobs.bytedance.com/experienced/position/1/detail",
                        "2026-08-21T00:00:00Z",
                        "2026-08-21T01:00:00Z",
                        "2026-08-21T01:00:00Z",
                        None,
                        0,
                    )
                ]
            )
        return _Rows(
            [
                common
                + (
                    "https://jobs.bytedance.com/experienced/position/1/detail",
                    "2026-08-21T00:00:00Z",
                    "2026-08-21T01:00:00Z",
                    "2026-08-21T01:00:00Z",
                    None,
                    0,
                )
            ]
        )


class _FilterConnection:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute(self, sql: str, params: tuple = ()) -> _Rows:
        compact = " ".join(sql.split())
        self.calls.append(compact)
        if "WITH visible AS MATERIALIZED" in compact:
            return _Rows(
                [
                    ("company", "example", "Example", 2),
                    ("location", "北京", "北京", 2),
                    (
                        "recruitment_type",
                        "experienced",
                        "experienced",
                        2,
                    ),
                    ("status", "active", "active", 2),
                ]
            )
        if "JOIN career.visible_jobs" in compact:
            return _Rows([("example", "Example", 2)])
        if "jsonb_array_elements_text" in compact:
            return _Rows([("北京", 2)])
        if "recruitment_type" in compact:
            return _Rows([("experienced", 2)])
        if "status" in compact:
            return _Rows([("active", 2)])
        return _Rows([(1,)])


def test_job_feed_uses_lightweight_visible_projection() -> None:
    connection = _SearchConnection()
    repository = PostgresCatalogRepository(connection)

    jobs, total = repository.search_jobs(
        JobSearchFilters(
            statuses=["active"],
            limit=20,
            offset=0,
        )
    )

    sql = "\n".join(call[0] for call in connection.calls)
    select_sql = connection.calls[1][0]
    assert "career.job_visible_to_user" not in sql
    assert "j.description_raw" not in select_sql
    assert "j.responsibilities" not in select_sql
    assert "j.requirements" not in select_sql
    assert total == 29612
    assert jobs[0]["id"] == "job-1"
    assert "description_raw" not in jobs[0]
    assert jobs[0]["tracking"]["is_favorite"] is False


def test_job_feed_without_filters_omits_empty_where_clause() -> None:
    connection = _SearchConnection()
    repository = PostgresCatalogRepository(connection)

    repository.search_jobs(JobSearchFilters())

    count_sql, select_sql = (call[0] for call in connection.calls)
    assert not count_sql.endswith(" WHERE")
    assert " WHERE ORDER BY" not in select_sql


def test_job_filters_scan_visible_jobs_once() -> None:
    connection = _FilterConnection()
    repository = PostgresCatalogRepository(connection)

    filters = repository.get_job_filters()

    assert len(connection.calls) == 2
    assert "WITH visible AS MATERIALIZED" in connection.calls[0]
    assert "career.job_visible_to_user" not in connection.calls[0]
    assert filters == {
        "companies": [
            {"slug": "example", "name": "Example", "count": 2}
        ],
        "locations": [{"value": "北京", "count": 2}],
        "recruitment_types": [
            {"value": "experienced", "count": 2}
        ],
        "statuses": [{"value": "active", "count": 2}],
        "favorite_count": 1,
    }


def test_migration_8_optimizes_visibility_and_feed_index() -> None:
    sql = (
        ROOT
        / "coworker/storage/postgres/sql"
        / "0008_job_radar_query_performance.sql"
    ).read_text(encoding="utf-8")
    compact = " ".join(sql.split())
    function_body = compact.split(
        "CREATE OR REPLACE VIEW career.visible_jobs",
        maxsplit=1,
    )[0]
    view_body = compact.split(
        "CREATE OR REPLACE VIEW career.visible_jobs",
        maxsplit=1,
    )[1].split("CREATE INDEX IF NOT EXISTS jobs_active_feed", maxsplit=1)[0]

    assert "ADD COLUMN IF NOT EXISTS visibility_user_id TEXT" in compact
    assert "UPDATE catalog.jobs jobs" in compact
    assert "FROM career.manual_job_owners owner" in compact
    assert (
        "CREATE OR REPLACE FUNCTION "
        "career.sync_manual_job_visibility()"
    ) in compact
    assert "CREATE TRIGGER sync_manual_job_visibility" in compact
    assert "CREATE OR REPLACE FUNCTION career.job_visible_to_user" in compact
    assert "jobs.visibility_user_id IS NULL" in function_body
    assert "CREATE OR REPLACE VIEW career.visible_jobs" in compact
    assert "WITH (security_barrier = true)" in compact
    assert "jobs.visibility_user_id IS NULL" in view_body
    assert (
        "jobs.visibility_user_id = current_setting('app.user_id', true)"
        in view_body
    )
    assert "career.job_visible_to_user(" not in view_body
    assert "career.manual_job_owners" not in view_body
    assert "CREATE INDEX IF NOT EXISTS jobs_active_feed" in compact
    assert "WHERE status = 'active'" in compact


def test_migration_8_preserves_shared_and_owned_job_visibility() -> None:
    url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("TEST_DATABASE_URL is required")
    database = CloudDatabase.from_url(
        validated_test_database_url(url),
        min_size=1,
        max_size=1,
    )
    database.migrate()
    suffix = uuid4().hex
    alice = Principal(f"alice-{suffix}", "test")
    bob = Principal(f"bob-{suffix}", "test")
    company_id = f"radar-company-{suffix}"
    source_id = f"radar-source-{suffix}"
    shared_job_id = f"radar-shared-{suffix}"
    manual_job_id = f"radar-manual-{suffix}"
    try:
        assert database.migrate() == ()
        with database.shared_transaction() as connection:
            connection.execute(
                """
                INSERT INTO identity.users(id)
                VALUES (%s), (%s)
                """,
                (alice.user_id, bob.user_id),
            )
            connection.execute(
                """
                INSERT INTO catalog.companies(
                    id, slug, name, created_at
                ) VALUES (%s, %s, 'Radar Test', now())
                """,
                (company_id, company_id),
            )
            connection.execute(
                """
                INSERT INTO catalog.job_sources(
                    id, company_id, slug, source_type,
                    base_url, created_at
                ) VALUES (
                    %s, %s, %s, 'test',
                    'https://jobs.example.com', now()
                )
                """,
                (source_id, company_id, source_id),
            )
            for job_id in (shared_job_id, manual_job_id):
                connection.execute(
                    """
                    INSERT INTO catalog.jobs(
                        id, company_id, source_id, canonical_url,
                        title, locations, description_raw,
                        responsibilities, requirements, status,
                        content_hash, first_seen_at, last_seen_at,
                        last_changed_at, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, 'Radar Test Job',
                        '[]'::jsonb, 'Test', '[]'::jsonb,
                        '[]'::jsonb, 'active', %s,
                        now(), now(), now(), now(), now()
                    )
                    """,
                    (
                        job_id,
                        company_id,
                        source_id,
                        f"https://jobs.example.com/{job_id}",
                        suffix * 2,
                    ),
                )
        with database.transaction(alice) as connection:
            connection.execute(
                """
                INSERT INTO career.manual_job_owners(
                    user_id, job_id
                ) VALUES (%s, %s)
                """,
                (alice.user_id, manual_job_id),
            )

        def visible_ids(principal: Principal) -> set[str]:
            with database.transaction(principal) as connection:
                return {
                    str(row[0])
                    for row in connection.execute(
                        """
                        SELECT id
                        FROM career.visible_jobs
                        WHERE id = ANY(%s)
                        """,
                        ([shared_job_id, manual_job_id],),
                    ).fetchall()
                }

        assert visible_ids(alice) == {shared_job_id, manual_job_id}
        assert visible_ids(bob) == {shared_job_id}
    finally:
        with database.transaction(alice) as connection:
            connection.execute(
                """
                DELETE FROM career.manual_job_owners
                WHERE job_id = %s
                """,
                (manual_job_id,),
            )
        with database.shared_transaction() as connection:
            connection.execute(
                "DELETE FROM catalog.jobs WHERE source_id = %s",
                (source_id,),
            )
            connection.execute(
                "DELETE FROM catalog.job_sources WHERE id = %s",
                (source_id,),
            )
            connection.execute(
                "DELETE FROM catalog.companies WHERE id = %s",
                (company_id,),
            )
            connection.execute(
                "DELETE FROM identity.users WHERE id = ANY(%s)",
                ([alice.user_id, bob.user_id],),
            )
        database.close()
