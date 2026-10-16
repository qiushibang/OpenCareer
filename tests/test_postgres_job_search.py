from extensions.career_mcp.database.postgres_catalog_repository import (
    PostgresCatalogRepository,
    normalize_search_query,
)
from extensions.career_mcp.domain.models import JobSearchFilters


class _Rows:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> _Rows:
        compact = " ".join(sql.split())
        self.calls.append((compact, params))
        if compact.startswith("SELECT COUNT(*)"):
            return _Rows([(0,)])
        return _Rows([])


def test_normalize_search_query_preserves_chinese_and_collapses_space() -> None:
    assert normalize_search_query("  AI   产品经理  ") == "AI 产品经理"
    assert normalize_search_query(" \n\t ") == ""


def test_postgres_search_combines_full_text_and_exact_filters() -> None:
    connection = _Connection()
    repository = PostgresCatalogRepository(connection)

    jobs, total = repository.search_jobs(
        JobSearchFilters(
            query=" AI  产品经理 ",
            company_slugs=["tencent"],
            locations=["北京", "上海"],
            recruitment_types=["experienced"],
            statuses=["active"],
            first_seen_after="2026-08-01T00:00:00Z",
            limit=25,
            offset=50,
        )
    )

    assert jobs == []
    assert total == 0
    count_sql, count_params = connection.calls[0]
    select_sql, select_params = connection.calls[1]
    assert "j.search_document @@ websearch_to_tsquery('simple', %s)" in count_sql
    assert "j.title ILIKE %s" in count_sql
    assert "c.slug = ANY(%s)" in count_sql
    assert "j.locations ?| %s" in count_sql
    assert "j.recruitment_type = ANY(%s)" in count_sql
    assert "j.status = ANY(%s)" in count_sql
    assert "j.first_seen_at >= %s" in count_sql
    assert count_params == (
        "AI 产品经理",
        "%AI 产品经理%",
        "%AI 产品经理%",
        "%AI 产品经理%",
        ["tencent"],
        ["北京", "上海"],
        ["experienced"],
        ["active"],
        "2026-08-01T00:00:00Z",
    )
    assert "ORDER BY j.first_seen_at DESC, j.id ASC" in select_sql
    assert select_params[-2:] == (25, 50)


def test_postgres_schema_has_job_full_text_index() -> None:
    from pathlib import Path

    sql = (
        Path(__file__).resolve().parents[1]
        / "coworker/storage/postgres/sql/0001_initial.sql"
    ).read_text(encoding="utf-8")

    assert "search_document TSVECTOR GENERATED ALWAYS AS" in sql
    assert "USING GIN (search_document)" in sql


def test_postgres_search_joins_tenant_tracking_filters() -> None:
    connection = _Connection()
    repository = PostgresCatalogRepository(connection)

    repository.search_jobs(
        JobSearchFilters(
            favorite_only=True,
            application_status="interviewing",
        )
    )

    count_sql = connection.calls[0][0]
    assert "LEFT JOIN career.job_tracking" in count_sql
    assert "tracking.user_id = current_setting('app.user_id', true)" in count_sql
    assert "tracking.data->>'is_favorite' = 'true'" in count_sql
    assert "tracking.data->>'application_status'" in count_sql
    assert "'not_started') = %s" in count_sql


class _DetailConnection:
    def __init__(self) -> None:
        self.calls = []
        self.responses = [
            _Rows(
                [
                    (
                        "job-1",
                        "example",
                        "Example",
                        "AI Engineer",
                        "北京",
                        ["北京"],
                        "experienced",
                        "active",
                        "Build AI",
                        ["Build"],
                        ["Python"],
                        "https://jobs.example/1",
                        "2026-08-01T00:00:00Z",
                        "2026-08-19T00:00:00Z",
                        "2026-08-19T00:00:00Z",
                    )
                ]
            ),
            _Rows([(2, "b" * 64, "2026-08-19T00:00:00Z")]),
            _Rows([("changed", "Updated", ["requirements"], "2026-08-19T00:00:00Z")]),
            _Rows(
                [
                    ("company", "example", "Example", 1),
                    ("location", "北京", "北京", 1),
                    (
                        "recruitment_type",
                        "experienced",
                        "experienced",
                        1,
                    ),
                    ("status", "active", "active", 1),
                ]
            ),
            _Rows([(1,)]),
        ]

    def execute(self, sql: str, params: tuple = ()) -> _Rows:
        self.calls.append((" ".join(sql.split()), params))
        return self.responses.pop(0)


def test_postgres_catalog_returns_detail_versions_events_and_filters() -> None:
    connection = _DetailConnection()
    repository = PostgresCatalogRepository(connection)

    detail = repository.get_job("job-1")
    filters = repository.get_job_filters()

    assert detail is not None
    assert detail["id"] == "job-1"
    assert detail["versions"][0]["version_number"] == 2
    assert detail["events"][0]["event_type"] == "changed"
    assert filters == {
        "companies": [
            {"slug": "example", "name": "Example", "count": 1}
        ],
        "locations": [{"value": "北京", "count": 1}],
        "recruitment_types": [
            {"value": "experienced", "count": 1}
        ],
        "statuses": [{"value": "active", "count": 1}],
        "favorite_count": 1,
    }
    assert any(
        "FROM career.job_tracking" in sql
        for sql, _ in connection.calls
    )
