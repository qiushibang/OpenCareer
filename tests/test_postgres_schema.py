from pathlib import Path

import pytest

from coworker.storage.postgres.migrations import (
    Migration,
    apply_migrations,
    discover_migrations,
)


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    ROOT
    / "coworker"
    / "storage"
    / "postgres"
    / "sql"
    / "0001_initial.sql"
)
PACKET_INTEGRITY_MIGRATION = (
    ROOT
    / "coworker"
    / "storage"
    / "postgres"
    / "sql"
    / "0004_application_packet_blob_integrity.sql"
)
TAILORED_EXPORT_MIGRATION = (
    ROOT
    / "coworker"
    / "storage"
    / "postgres"
    / "sql"
    / "0005_tailored_resume_exports.sql"
)
MANUAL_JOB_OWNERSHIP_MIGRATION = (
    ROOT
    / "coworker"
    / "storage"
    / "postgres"
    / "sql"
    / "0006_manual_job_ownership.sql"
)
CRAWL_CYCLES_MIGRATION = (
    ROOT
    / "coworker"
    / "storage"
    / "postgres"
    / "sql"
    / "0007_crawl_cycles.sql"
)
INBOX_RESOLUTION_CASCADE_MIGRATION = (
    ROOT
    / "coworker"
    / "storage"
    / "postgres"
    / "sql"
    / "0009_inbox_resolution_cascade.sql"
)
AUTHING_IDENTITY_MIGRATION = (
    ROOT
    / "coworker"
    / "storage"
    / "postgres"
    / "sql"
    / "0010_authing_identity.sql"
)


def test_initial_postgres_migration_covers_all_data_domains() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")

    for schema in ("identity", "catalog", "career", "agent", "blob"):
        assert f"CREATE SCHEMA IF NOT EXISTS {schema}" in sql

    for table in (
        "identity.users",
        "identity.auth_credentials",
        "identity.deployment_origins",
        "catalog.jobs",
        "catalog.job_versions",
        "catalog.crawl_runs",
        "career.resume_imports",
        "career.interview_sessions",
        "career.interview_turns",
        "agent.conversations",
        "agent.messages",
        "agent.compactions",
        "agent.context_manifests",
        "agent.session_skills",
        "agent.workspaces",
        "agent.memories",
        "agent.inbox_items",
        "agent.automations",
        "blob.objects",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql


def test_initial_postgres_migration_enforces_identity_and_rls() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    compact = " ".join(sql.split())

    assert "UNIQUE (crawl_source_id, external_job_id)" in sql
    assert "PRIMARY KEY (user_id, id)" in sql
    assert "UNIQUE (user_id, conversation_id, sequence)" in sql
    assert "UNIQUE (user_id, conversation_id, tool_call_id)" in sql
    assert "PRIMARY KEY (user_id, id)" in sql
    assert (
        "FOREIGN KEY (user_id, inbox_item_id) "
        "REFERENCES agent.inbox_items(user_id, id)"
    ) in compact
    assert (
        "FOREIGN KEY (user_id, automation_id) "
        "REFERENCES agent.automations(user_id, id)"
    ) in compact
    assert "enabled BOOLEAN NOT NULL" in sql
    assert "next_run DOUBLE PRECISION" in sql
    assert "sha256 TEXT NOT NULL" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "current_setting('app.user_id', true)" in sql
    assert (
        "FOREIGN KEY (user_id, conversation_id) "
        "REFERENCES agent.conversations(user_id, id) ON DELETE CASCADE"
    ) in compact
    assert (
        "REFERENCES agent.conversations(user_id, id) "
        "ON DELETE SET NULL (conversation_id)"
    ) in compact
    assert "state JSONB NOT NULL" in sql


def test_postgres_sql_is_included_in_the_python_package() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"storage/postgres/sql/*.sql"' in pyproject


def test_postgres_migrations_are_ordered_and_have_content_hashes() -> None:
    migrations = discover_migrations()

    assert [migration.version for migration in migrations] == [
        1,
        2,
        3,
        4,
        5,
        6,
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
    ]
    assert migrations[0].name == "initial"
    assert migrations[1].name == "career_tenant_integrity"
    assert migrations[2].name == "data_migration_ledger"
    assert migrations[3].name == "application_packet_blob_integrity"
    assert migrations[4].name == "tailored_resume_exports"
    assert migrations[5].name == "manual_job_ownership"
    assert migrations[6].name == "crawl_cycles"
    assert migrations[7].name == "job_radar_query_performance"
    assert migrations[8].name == "inbox_resolution_cascade"
    assert migrations[9].name == "authing_identity"
    assert all(len(migration.sha256) == 64 for migration in migrations)
    assert migrations[0].sql.startswith("CREATE SCHEMA")


def test_authing_identity_keeps_raw_tokens_out_of_postgres() -> None:
    sql = AUTHING_IDENTITY_MIGRATION.read_text(encoding="utf-8")
    compact = " ".join(sql.split())

    assert "CREATE TABLE identity.external_identities" in sql
    assert "UNIQUE (issuer, subject)" in sql
    assert "CREATE TABLE identity.auth_sessions" in sql
    assert "token_sha256 TEXT NOT NULL UNIQUE" in sql
    assert "expires_at TIMESTAMPTZ NOT NULL" in sql
    assert "revoked_at TIMESTAMPTZ" in sql
    assert "access_token" not in compact
    assert "refresh_token" not in compact
    assert "id_token" not in compact


def test_application_packet_blob_uses_tenant_composite_foreign_key() -> None:
    sql = PACKET_INTEGRITY_MIGRATION.read_text(encoding="utf-8")
    compact = " ".join(sql.split())

    assert "ADD COLUMN blob_id UUID" in compact
    assert "UNIQUE (user_id, id)" in compact
    assert (
        "FOREIGN KEY (user_id, blob_id) "
        "REFERENCES blob.objects(user_id, id)"
    ) in compact


def test_tailored_exports_use_tenant_composite_foreign_keys() -> None:
    sql = (
        (
            ROOT
            / "coworker"
            / "storage"
            / "postgres"
            / "sql"
            / "0002_career_tenant_integrity.sql"
        ).read_text(encoding="utf-8")
        + TAILORED_EXPORT_MIGRATION.read_text(encoding="utf-8")
    )
    compact = " ".join(sql.split())

    assert "ADD COLUMN snapshot_id TEXT" in compact
    assert "CREATE TABLE career.tailored_resume_exports" in compact
    assert "docx_blob_id UUID NOT NULL" in compact
    assert "pdf_blob_id UUID NOT NULL" in compact
    for expected in (
        "FOREIGN KEY (user_id, resume_import_id) "
        "REFERENCES career.resume_imports(user_id, id)",
        "FOREIGN KEY (user_id, snapshot_id) "
        "REFERENCES career.job_resume_matches(user_id, id)",
        "FOREIGN KEY (user_id, draft_id) "
        "REFERENCES career.tailored_resume_drafts(user_id, id)",
        "FOREIGN KEY (user_id, docx_blob_id) "
        "REFERENCES blob.objects(user_id, id)",
        "FOREIGN KEY (user_id, pdf_blob_id) "
        "REFERENCES blob.objects(user_id, id)",
    ):
        assert expected in compact


def test_manual_jobs_have_database_enforced_tenant_visibility() -> None:
    sql = MANUAL_JOB_OWNERSHIP_MIGRATION.read_text(encoding="utf-8")
    compact = " ".join(sql.split())

    assert "CREATE TABLE career.manual_job_owners" in compact
    assert "UNIQUE (job_id)" in compact
    assert "ENABLE ROW LEVEL SECURITY" in compact
    assert "FORCE ROW LEVEL SECURITY" in compact
    assert "current_setting('app.user_id', true)" in compact
    assert "CREATE FUNCTION career.job_visible_to_user" in compact
    assert "SECURITY DEFINER" in compact
    for table in (
        "career.job_tracking",
        "career.job_application_events",
        "career.job_resume_matches",
        "career.application_packets",
        "career.tailored_resume_drafts",
        "career.interview_sessions",
    ):
        assert f"ON {table}" in compact


def test_resumable_crawl_cycles_have_staging_constraints() -> None:
    sql = CRAWL_CYCLES_MIGRATION.read_text(encoding="utf-8")
    compact = " ".join(sql.split())

    for table in (
        "catalog.crawl_cycles",
        "catalog.crawl_cycle_shards",
        "catalog.crawl_cycle_jobs",
    ):
        assert f"CREATE TABLE {table}" in compact
    assert "WHERE status = 'running'" in compact
    assert "PRIMARY KEY (cycle_id, shard_key)" in compact
    assert "PRIMARY KEY (cycle_id, external_job_id)" in compact


def test_inbox_resolutions_are_deleted_with_their_parent_items() -> None:
    sql = INBOX_RESOLUTION_CASCADE_MIGRATION.read_text(encoding="utf-8")
    compact = " ".join(sql.split())

    assert (
        "DROP CONSTRAINT inbox_resolutions_user_id_inbox_item_id_fkey"
    ) in compact
    assert (
        "FOREIGN KEY (user_id, inbox_item_id) "
        "REFERENCES agent.inbox_items(user_id, id) ON DELETE CASCADE"
    ) in compact


class _Rows:
    def __init__(self, rows: list[tuple[int, str]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[tuple[int, str]]:
        return self._rows


class _Connection:
    def __init__(self, applied: list[tuple[int, str]]) -> None:
        self.applied = applied
        self.statements: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = None) -> _Rows:
        self.statements.append((sql, params))
        if "SELECT version, sha256" in sql:
            return _Rows(self.applied)
        return _Rows([])


def test_apply_migrations_skips_an_identical_applied_version() -> None:
    migration = Migration(1, "initial", "SELECT 1", "a" * 64)
    connection = _Connection([(1, "a" * 64)])

    assert apply_migrations(connection, migrations=(migration,)) == ()
    assert not any(sql == "SELECT 1" for sql, _ in connection.statements)


def test_apply_migrations_rejects_changed_applied_sql() -> None:
    migration = Migration(1, "initial", "SELECT 1", "b" * 64)
    connection = _Connection([(1, "a" * 64)])

    with pytest.raises(RuntimeError, match="checksum"):
        apply_migrations(connection, migrations=(migration,))
