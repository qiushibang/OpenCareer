import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.database import migrations
from extensions.career_mcp.database.migrations import connect, migrate, schema_version


def test_migration_creates_versioned_schema_idempotently(tmp_path):
    connection = connect(tmp_path / "career.sqlite3")
    try:
        migrate(connection)
        migrate(connection)

        assert schema_version(connection) == migrations.SCHEMA_VERSION
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "schema_migrations",
            "companies",
            "job_sources",
            "jobs",
            "job_versions",
            "job_events",
            "crawl_sources",
            "crawl_runs",
        } <= tables
        crawl_source_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(crawl_sources)")
        }
        assert {"company_id", "scope_key", "adapter_type", "base_url"} <= (
            crawl_source_columns
        )
    finally:
        connection.close()
