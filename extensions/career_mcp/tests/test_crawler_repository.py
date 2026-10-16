import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[3]))

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.crawler.adapters import FakeAdapter
from extensions.career_mcp.database import migrations
from extensions.career_mcp.database.repository import JobRepository
from extensions.career_mcp.domain.crawler import JobSnapshot, SourceDescriptor
from extensions.career_mcp.services.crawler import CrawlerService


def test_version_two_creates_crawl_tables_and_preserves_manual_tables(tmp_path):
    connection = migrations.connect(tmp_path / "career.sqlite3")
    try:
        migrations.migrate(connection)

        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        assert migrations.schema_version(connection) == migrations.SCHEMA_VERSION
        assert {
            "crawl_sources",
            "crawl_runs",
            "crawl_cycles",
            "crawl_cycle_shards",
            "crawl_cycle_jobs",
            "jobs",
            "job_events",
        } <= tables
    finally:
        connection.close()


def test_crawl_cycle_checkpoints_and_rejects_conflicting_job(
    tmp_path,
):
    connection = migrations.connect(tmp_path / "career.sqlite3")
    repository = JobRepository(connection)
    source = repository.ensure_crawl_source(
        SourceDescriptor(
            source_slug="bytedance-mainland-social",
            source_name="字节跳动中国大陆社招",
            company_slug="bytedance",
            company_name="字节跳动",
            scope_key="mainland-social",
            adapter_type="playwright-json-resumable",
            base_url="https://jobs.bytedance.com/experienced/position",
        )
    )
    shards = [
        {
            "shard_key": "location:beijing",
            "filters": {"location_code": "CT_11"},
        }
    ]

    cycle = repository.get_or_create_crawl_cycle(
        str(source["crawl_source_id"]),
        shards,
    )
    resumed = repository.get_or_create_crawl_cycle(
        str(source["crawl_source_id"]),
        shards,
    )
    repository.checkpoint_cycle_shard(
        cycle["id"],
        "location:beijing",
        expected_count=20,
        next_offset=10,
        status="running",
        last_page_fingerprint="page-1",
    )

    assert resumed["id"] == cycle["id"]
    assert repository.list_cycle_shards(cycle["id"])[0][
        "next_offset"
    ] == 10
    assert repository.stage_cycle_job(
        cycle["id"],
        external_job_id="job-1",
        snapshot={"title": "AI Engineer"},
        content_hash="a" * 64,
        pass_number=1,
        observed_at="2026-08-20T00:00:00Z",
    ) == "created"
    assert repository.stage_cycle_job(
        cycle["id"],
        external_job_id="job-1",
        snapshot={"title": "AI Engineer"},
        content_hash="a" * 64,
        pass_number=1,
        observed_at="2026-08-20T00:00:00Z",
    ) == "unchanged"
    with pytest.raises(ValueError, match="conflicting snapshot"):
        repository.stage_cycle_job(
            cycle["id"],
            external_job_id="job-1",
            snapshot={"title": "Changed"},
            content_hash="b" * 64,
            pass_number=1,
            observed_at="2026-08-20T00:00:00Z",
        )
    connection.close()


def test_crawl_cycle_accepts_changed_job_in_later_pass(tmp_path):
    connection = migrations.connect(tmp_path / "career.sqlite3")
    repository = JobRepository(connection)
    source = repository.ensure_crawl_source(
        SourceDescriptor(
            source_slug="bytedance-mainland-social",
            source_name="字节跳动中国大陆社招",
            company_slug="bytedance",
            company_name="字节跳动",
            scope_key="mainland-social",
            adapter_type="playwright-json-resumable",
            base_url="https://jobs.bytedance.com/experienced/position",
        )
    )
    cycle = repository.get_or_create_crawl_cycle(
        str(source["crawl_source_id"]),
        [{"shard_key": "category:1", "filters": {"category_code": "1"}}],
    )
    repository.stage_cycle_job(
        cycle["id"],
        external_job_id="job-1",
        snapshot={"title": "旧标题"},
        content_hash="a" * 64,
        pass_number=1,
        observed_at="2026-08-20T00:00:00Z",
    )

    result = repository.stage_cycle_job(
        cycle["id"],
        external_job_id="job-1",
        snapshot={"title": "新标题"},
        content_hash="b" * 64,
        pass_number=2,
        observed_at="2026-08-20T01:00:00Z",
    )

    assert result == "changed"
    staged = repository.list_cycle_jobs(cycle["id"])[0]
    assert staged["snapshot"]["title"] == "新标题"
    assert staged["content_hash"] == "b" * 64
    assert staged["last_pass"] == 2
    with pytest.raises(ValueError, match="conflicting snapshot"):
        repository.stage_cycle_job(
            cycle["id"],
            external_job_id="job-1",
            snapshot={"title": "同遍再次变化"},
            content_hash="c" * 64,
            pass_number=2,
            observed_at="2026-08-20T01:01:00Z",
        )
    connection.close()


def test_crawl_cycle_reconciles_verified_stale_tail_atomically(tmp_path):
    connection = migrations.connect(tmp_path / "career.sqlite3")
    repository = JobRepository(connection)
    source = repository.ensure_crawl_source(
        SourceDescriptor(
            source_slug="bytedance-mainland-social",
            source_name="字节跳动中国大陆社招",
            company_slug="bytedance",
            company_name="字节跳动",
            scope_key="mainland-social",
            adapter_type="playwright-json-resumable",
            base_url="https://jobs.bytedance.com/experienced/position",
        )
    )
    cycle = repository.get_or_create_crawl_cycle(
        str(source["crawl_source_id"]),
        [{"shard_key": "category:1", "filters": {"category_id": "1"}}],
    )
    for job_id in ("active-1", "active-2", "off-1", "off-2", "off-3", "off-4"):
        repository.stage_cycle_job(
            cycle["id"],
            external_job_id=job_id,
            snapshot={"title": job_id},
            content_hash=job_id,
            pass_number=1,
            observed_at="2026-08-20T00:00:00Z",
        )

    result = repository.reconcile_cycle_tail(
        cycle["id"],
        active_ids={"active-1", "active-2"},
        offline_ids={"off-1", "off-2", "off-3", "off-4"},
        pass_number=3,
        observed_at="2026-08-21T00:00:00Z",
    )

    assert result == {"active": 2, "offline": 4}
    remaining = repository.list_cycle_jobs(cycle["id"])
    assert {row["external_job_id"] for row in remaining} == {
        "active-1",
        "active-2",
    }
    assert {row["last_pass"] for row in remaining} == {3}

    with pytest.raises(ValueError, match="do not match stale rows"):
        repository.reconcile_cycle_tail(
            cycle["id"],
            active_ids={"missing"},
            offline_ids=set(),
            pass_number=3,
            observed_at="2026-08-21T00:00:00Z",
        )
    assert len(repository.list_cycle_jobs(cycle["id"])) == 2
    connection.close()


def test_version_three_links_source_to_canonical_company_without_data_loss(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "career" / "career.sqlite3"
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 2)
    connection = migrations.connect(database_path)
    try:
        migrations.migrate(connection)
        now = "2026-08-05T00:00:00Z"
        connection.execute(
            "INSERT INTO companies(id, slug, name, created_at) VALUES (?, ?, ?, ?)",
            ("company-1", "xiaomi-careers", "xiaomi-careers", now),
        )
        connection.execute(
            """
            INSERT INTO job_sources(id, company_id, slug, source_type, base_url, created_at)
            VALUES (?, ?, ?, 'crawler', NULL, ?)
            """,
            ("job-source-1", "company-1", "xiaomi-careers:xiaomi-42", now),
        )
        connection.execute(
            """
            INSERT INTO crawl_sources(
                id, slug, name, missing_threshold, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, 2, 1, ?, ?)
            """,
            ("crawl-source-1", "xiaomi-careers", "xiaomi-careers", now, now),
        )
        connection.execute(
            """
            INSERT INTO jobs(
                id, company_id, source_id, external_job_id, canonical_url, title,
                location_raw, locations_json, recruitment_type, description_raw,
                responsibilities_json, requirements_json, status, content_hash,
                first_seen_at, last_seen_at, last_changed_at, created_at, updated_at,
                crawl_source_id, missing_count
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', 'active', ?,
                ?, ?, ?, ?, ?, ?, 0
            )
            """,
            (
                "job-1",
                "company-1",
                "job-source-1",
                "xiaomi-42",
                "https://hr.xiaomi.com/jobs/42",
                "AI Engineer",
                "北京",
                '["北京"]',
                "experienced",
                "Build AI systems",
                "hash-1",
                now,
                now,
                now,
                now,
                now,
                "crawl-source-1",
            ),
        )
        connection.execute(
            """
            INSERT INTO job_versions(
                id, job_id, version_number, content_hash, snapshot_json, captured_at
            ) VALUES ('version-1', 'job-1', 1, 'hash-1', '{}', ?)
            """,
            (now,),
        )
        connection.execute(
            """
            INSERT INTO job_events(
                id, job_id, event_type, summary, changed_fields_json, occurred_at
            ) VALUES ('event-1', 'job-1', 'created', 'created', '[]', ?)
            """,
            (now,),
        )
        connection.execute(
            """
            INSERT INTO crawl_runs(
                id, source_id, status, started_at, completed_at,
                observed_count, invalid_count, error_summary
            ) VALUES ('run-1', 'crawl-source-1', 'succeeded', ?, ?, 1, 0, NULL)
            """,
            (now, now),
        )
        connection.commit()
        before = {
            table: [
                tuple(row)
                for row in connection.execute(
                    f"SELECT * FROM {table} ORDER BY id"
                ).fetchall()
            ]
            for table in ("jobs", "job_versions", "job_events", "crawl_runs")
        }
        monkeypatch.setattr(migrations, "SCHEMA_VERSION", 3)

        migrations.migrate(connection)

        assert migrations.schema_version(connection) == 3
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(crawl_sources)")
        }
        assert {"company_id", "scope_key", "adapter_type", "base_url"} <= columns
        company = connection.execute(
            """
            SELECT c.id, c.slug, c.name
            FROM crawl_sources cs
            JOIN companies c ON c.id = cs.company_id
            WHERE cs.slug = 'xiaomi-careers'
            """
        ).fetchone()
        assert (company["slug"], company["name"]) == ("xiaomi", "小米")
        source = connection.execute(
            """
            SELECT name, scope_key, adapter_type, base_url
            FROM crawl_sources WHERE slug = 'xiaomi-careers'
            """
        ).fetchone()
        assert tuple(source) == (
            "小米官方招聘",
            "all-public-jobs",
            "public-json-api",
            "https://hr.xiaomi.com/website/opportunities.html",
        )
        after = {
            table: [
                tuple(row)
                for row in connection.execute(
                    f"SELECT * FROM {table} ORDER BY id"
                ).fetchall()
            ]
            for table in ("jobs", "job_versions", "job_events", "crawl_runs")
        }
        assert after == before
    finally:
        connection.close()


def test_job_radar_digest_aggregates_full_window_and_latest_source_health(
    tmp_path,
):
    config = CareerConfig(data_dir=tmp_path / "career")
    alpha = SourceDescriptor(
        source_slug="alpha-jobs",
        source_name="Alpha Jobs",
        company_slug="alpha",
        company_name="Alpha",
        scope_key="all",
        adapter_type="fixture",
        base_url="https://alpha.example/jobs",
    )
    beta = SourceDescriptor(
        source_slug="beta-jobs",
        source_name="Beta Jobs",
        company_slug="beta",
        company_name="Beta",
        scope_key="all",
        adapter_type="fixture",
        base_url="https://beta.example/jobs",
    )
    service = CrawlerService(config)
    service.crawl(
        FakeAdapter(
            alpha.source_slug,
            [
                JobSnapshot(
                    external_job_id="alpha-1",
                    title="Alpha Engineer",
                    description_raw="Build alpha",
                    source_url="https://alpha.example/jobs/1",
                    observed_at="2026-08-06T00:00:00Z",
                ),
                JobSnapshot(
                    external_job_id="alpha-2",
                    title="Alpha Product",
                    description_raw="Plan alpha",
                    source_url="https://alpha.example/jobs/2",
                    observed_at="2026-08-06T00:00:00Z",
                ),
            ],
            descriptor=alpha,
        )
    )
    service.crawl(
        FakeAdapter(
            beta.source_slug,
            [
                JobSnapshot(
                    external_job_id="beta-1",
                    title="Beta Engineer",
                    description_raw="Build beta",
                    source_url="https://beta.example/jobs/1",
                    observed_at="2026-08-06T00:00:00Z",
                )
            ],
            descriptor=beta,
        )
    )

    class FailingBetaAdapter:
        source_slug = beta.source_slug
        descriptor = beta

        def fetch_jobs(self):
            raise RuntimeError("beta unavailable")

    service.crawl(FailingBetaAdapter())

    connection = migrations.connect(config.database_path)
    try:
        repository = JobRepository(connection)
        jobs = {
            row["external_job_id"]: row["id"]
            for row in connection.execute(
                "SELECT id, external_job_id FROM jobs"
            )
        }
        connection.execute(
            "UPDATE jobs SET status = 'inactive' WHERE id = ?",
            (jobs["alpha-2"],),
        )
        connection.execute("DELETE FROM job_events")
        connection.executemany(
            """
            INSERT INTO job_events(
                id, job_id, event_type, summary, changed_fields_json, occurred_at
            ) VALUES (?, ?, ?, ?, '[]', ?)
            """,
            [
                (
                    "event-created",
                    jobs["alpha-1"],
                    "created",
                    "created",
                    "2026-08-05T02:00:00Z",
                ),
                (
                    "event-changed-alpha",
                    jobs["alpha-1"],
                    "changed",
                    "changed",
                    "2026-08-05T03:00:00Z",
                ),
                (
                    "event-missing",
                    jobs["alpha-2"],
                    "missing",
                    "missing",
                    "2026-08-05T04:00:00Z",
                ),
                (
                    "event-changed-beta",
                    jobs["beta-1"],
                    "changed",
                    "changed",
                    "2026-08-05T05:00:00Z",
                ),
                (
                    "event-old",
                    jobs["beta-1"],
                    "created",
                    "old",
                    "2026-08-04T23:00:00Z",
                ),
            ],
        )
        connection.commit()

        digest = repository.get_job_radar_digest_data(
            occurred_after="2026-08-05T01:00:00Z",
            sample_limit=2,
        )

        assert digest["jobs"] == {
            "total": 3,
            "active": 2,
            "inactive": 1,
        }
        assert digest["events"]["total"] == 4
        assert digest["events"]["by_type"] == {
            "changed": 2,
            "created": 1,
            "missing": 1,
        }
        assert len(digest["events"]["samples"]) == 2
        assert digest["events"]["by_company"][0] == {
            "company_slug": "alpha",
            "company_name": "Alpha",
            "total": 3,
            "changed": 1,
            "created": 1,
            "missing": 1,
        }
        assert digest["sources"]["configured"] == 2
        assert digest["sources"]["healthy"] == 1
        assert digest["sources"]["failed"] == 1
        assert digest["sources"]["pending"] == 0
        assert [
            source["source_slug"]
            for source in digest["sources"]["items"]
        ] == ["beta-jobs"]
        beta_health = digest["sources"]["items"][0]
        assert beta_health["last_run_status"] == "failed"
        assert beta_health["last_error"] == "beta unavailable"
    finally:
        connection.close()


def test_version_four_adds_resume_vault_without_changing_existing_jobs(
    tmp_path,
    monkeypatch,
):
    database_path = tmp_path / "career" / "career.sqlite3"
    monkeypatch.setattr(migrations, "SCHEMA_VERSION", 3)
    connection = migrations.connect(database_path)
    try:
        migrations.migrate(connection)
        now = "2026-08-06T00:00:00Z"
        connection.execute(
            "INSERT INTO companies(id, slug, name, created_at) VALUES (?, ?, ?, ?)",
            ("company-1", "example", "Example", now),
        )
        connection.execute(
            """
            INSERT INTO job_sources(
                id, company_id, slug, source_type, base_url, created_at
            ) VALUES (?, ?, ?, 'manual', NULL, ?)
            """,
            ("source-1", "company-1", "manual", now),
        )
        connection.execute(
            """
            INSERT INTO jobs(
                id, company_id, source_id, external_job_id, canonical_url,
                title, location_raw, locations_json, recruitment_type,
                description_raw, responsibilities_json, requirements_json,
                status, content_hash, first_seen_at, last_seen_at,
                last_changed_at, created_at, updated_at, crawl_source_id,
                missing_count
            ) VALUES (
                'job-1', 'company-1', 'source-1', NULL, 'manual://job-1',
                'Engineer', '北京', '["北京"]', 'experienced',
                'Build systems', '[]', '[]', 'active', 'hash-1',
                ?, ?, ?, ?, ?, NULL, 0
            )
            """,
            (now, now, now, now, now),
        )
        connection.commit()
        before = [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM jobs ORDER BY id"
            )
        ]
        monkeypatch.setattr(migrations, "SCHEMA_VERSION", 4)

        migrations.migrate(connection)

        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert migrations.schema_version(connection) == 4
        assert {
            "resume_imports",
            "candidate_profile",
            "candidate_facts",
            "profile_versions",
            "resume_previews",
        } <= tables
        assert [
            tuple(row)
            for row in connection.execute(
                "SELECT * FROM jobs ORDER BY id"
            )
        ] == before
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
