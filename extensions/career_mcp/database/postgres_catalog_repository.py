"""PostgreSQL repository for the shared cloud Job Catalog."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone

from ..domain.crawler import NormalizedJob, SourceDescriptor
from ..domain.manual_jd import company_slug
from ..domain.models import JobSearchFilters, ManualJDPreview

_SPACE = re.compile(r"\s+")


def normalize_search_query(value: str) -> str:
    return _SPACE.sub(" ", value).strip()


class PostgresCatalogRepository:
    def __init__(
        self,
        connection,
        *,
        clock=None,
        principal_user_id: str | None = None,
    ) -> None:
        self.connection = connection
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._principal_user_id = principal_user_id

    def acquire_source_lock(self, source_slug: str) -> bool:
        row = self.connection.execute(
            """
            SELECT pg_try_advisory_xact_lock(
                hashtextextended(%s, 0)
            )
            """,
            (source_slug,),
        ).fetchone()
        return bool(row and row[0])

    def get_or_create_crawl_cycle(
        self,
        crawl_source_id: str,
        shards: list[dict],
    ) -> dict:
        row = self.connection.execute(
            """
            SELECT id, source_id, status, pass_number,
                   expected_total, started_at, updated_at,
                   completed_at, error_summary
            FROM catalog.crawl_cycles
            WHERE source_id = %s AND status = 'running'
            """,
            (crawl_source_id,),
        ).fetchone()
        if row is not None:
            return _cycle_row(row)
        now = self._now()
        cycle_id = str(uuid.uuid4())
        self.connection.execute(
            """
            INSERT INTO catalog.crawl_cycles(
                id, source_id, status, pass_number,
                expected_total, started_at, updated_at
            ) VALUES (%s, %s, 'running', 1, NULL, %s, %s)
            """,
            (cycle_id, crawl_source_id, now, now),
        )
        for shard in shards:
            self.connection.execute(
                """
                INSERT INTO catalog.crawl_cycle_shards(
                    cycle_id, shard_key, filters_json,
                    expected_count, next_offset, status,
                    last_page_fingerprint, updated_at
                ) VALUES (
                    %s, %s, %s::jsonb, NULL, 0,
                    'pending', NULL, %s
                )
                """,
                (
                    cycle_id,
                    str(shard["shard_key"]),
                    json.dumps(
                        shard.get("filters", {}),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    now,
                ),
            )
        return {
            "id": cycle_id,
            "source_id": crawl_source_id,
            "status": "running",
            "pass_number": 1,
            "expected_total": None,
            "started_at": now,
            "updated_at": now,
            "completed_at": None,
            "error_summary": None,
        }

    def list_cycle_shards(self, cycle_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT cycle_id, shard_key, filters_json,
                   expected_count, next_offset, status,
                   last_page_fingerprint, updated_at
            FROM catalog.crawl_cycle_shards
            WHERE cycle_id = %s
            ORDER BY shard_key
            """,
            (cycle_id,),
        ).fetchall()
        return [
            {
                "cycle_id": str(row[0]),
                "shard_key": str(row[1]),
                "filters": dict(row[2] or {}),
                "expected_count": row[3],
                "next_offset": int(row[4]),
                "status": str(row[5]),
                "last_page_fingerprint": row[6],
                "updated_at": row[7],
            }
            for row in rows
        ]

    def checkpoint_cycle_shard(
        self,
        cycle_id: str,
        shard_key: str,
        *,
        expected_count: int,
        next_offset: int,
        status: str,
        last_page_fingerprint: str | None,
    ) -> None:
        self.connection.execute(
            """
            UPDATE catalog.crawl_cycle_shards
            SET expected_count = %s, next_offset = %s,
                status = %s, last_page_fingerprint = %s,
                updated_at = %s
            WHERE cycle_id = %s AND shard_key = %s
            """,
            (
                expected_count,
                next_offset,
                status,
                last_page_fingerprint,
                self._now(),
                cycle_id,
                shard_key,
            ),
        )

    def stage_cycle_job(
        self,
        cycle_id: str,
        *,
        external_job_id: str,
        snapshot: dict,
        content_hash: str,
        pass_number: int,
        observed_at: str,
    ) -> str:
        row = self.connection.execute(
            """
            SELECT content_hash, last_pass
            FROM catalog.crawl_cycle_jobs
            WHERE cycle_id = %s AND external_job_id = %s
            """,
            (cycle_id, external_job_id),
        ).fetchone()
        if row is not None:
            if str(row[0]) != content_hash:
                if pass_number > int(row[1]):
                    self.connection.execute(
                        """
                        UPDATE catalog.crawl_cycle_jobs
                        SET snapshot_json = %s::jsonb, content_hash = %s,
                            last_pass = %s, observed_at = %s
                        WHERE cycle_id = %s AND external_job_id = %s
                        """,
                        (
                            json.dumps(
                                snapshot,
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            content_hash,
                            pass_number,
                            observed_at,
                            cycle_id,
                            external_job_id,
                        ),
                    )
                    return "changed"
                raise ValueError(
                    "conflicting snapshot for ByteDance job id"
                )
            self.connection.execute(
                """
                UPDATE catalog.crawl_cycle_jobs
                SET last_pass = %s, observed_at = %s
                WHERE cycle_id = %s AND external_job_id = %s
                """,
                (
                    pass_number,
                    observed_at,
                    cycle_id,
                    external_job_id,
                ),
            )
            return "unchanged"
        self.connection.execute(
            """
            INSERT INTO catalog.crawl_cycle_jobs(
                cycle_id, external_job_id, snapshot_json,
                content_hash, first_pass, last_pass, observed_at
            ) VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s)
            """,
            (
                cycle_id,
                external_job_id,
                json.dumps(
                    snapshot,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                content_hash,
                pass_number,
                pass_number,
                observed_at,
            ),
        )
        return "created"

    def list_cycle_jobs(self, cycle_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT cycle_id, external_job_id, snapshot_json,
                   content_hash, first_pass, last_pass, observed_at
            FROM catalog.crawl_cycle_jobs
            WHERE cycle_id = %s
            ORDER BY external_job_id
            """,
            (cycle_id,),
        ).fetchall()
        return [
            {
                "cycle_id": str(row[0]),
                "external_job_id": str(row[1]),
                "snapshot": dict(row[2] or {}),
                "content_hash": str(row[3]),
                "first_pass": int(row[4]),
                "last_pass": int(row[5]),
                "observed_at": str(row[6]),
            }
            for row in rows
        ]

    def reconcile_cycle_tail(
        self,
        cycle_id: str,
        *,
        active_ids: set[str],
        offline_ids: set[str],
        pass_number: int,
        observed_at: str,
    ) -> dict[str, int]:
        if active_ids & offline_ids:
            raise ValueError(
                "active and offline ByteDance job ids overlap"
            )
        requested = sorted(active_ids | offline_ids)
        if not requested:
            raise ValueError("ByteDance stale tail is empty")
        placeholders = ",".join("%s" for _ in requested)
        rows = self.connection.execute(
            f"""
            SELECT external_job_id
            FROM catalog.crawl_cycle_jobs
            WHERE cycle_id = %s
              AND last_pass < %s
              AND external_job_id IN ({placeholders})
            """,
            (cycle_id, pass_number, *requested),
        ).fetchall()
        if {str(row[0]) for row in rows} != set(requested):
            raise ValueError(
                "verified ByteDance job ids do not match stale rows"
            )
        if active_ids:
            active = sorted(active_ids)
            active_placeholders = ",".join("%s" for _ in active)
            self.connection.execute(
                f"""
                UPDATE catalog.crawl_cycle_jobs
                SET last_pass = %s, observed_at = %s
                WHERE cycle_id = %s
                  AND last_pass < %s
                  AND external_job_id IN ({active_placeholders})
                """,
                (
                    pass_number,
                    observed_at,
                    cycle_id,
                    pass_number,
                    *active,
                ),
            )
        if offline_ids:
            offline = sorted(offline_ids)
            offline_placeholders = ",".join("%s" for _ in offline)
            self.connection.execute(
                f"""
                DELETE FROM catalog.crawl_cycle_jobs
                WHERE cycle_id = %s
                  AND last_pass < %s
                  AND external_job_id IN ({offline_placeholders})
                """,
                (cycle_id, pass_number, *offline),
            )
        return {
            "active": len(active_ids),
            "offline": len(offline_ids),
        }

    def advance_cycle_pass(
        self,
        cycle_id: str,
        pass_number: int,
        *,
        reset_expected_counts: bool = False,
    ) -> None:
        now = self._now()
        self.connection.execute(
            """
            UPDATE catalog.crawl_cycles
            SET pass_number = %s, updated_at = %s
            WHERE id = %s AND status = 'running'
            """,
            (pass_number, now, cycle_id),
        )
        self.connection.execute(
            """
            UPDATE catalog.crawl_cycle_shards
            SET expected_count = CASE
                    WHEN %s THEN NULL
                    ELSE expected_count
                END,
                next_offset = 0, status = 'pending',
                last_page_fingerprint = NULL, updated_at = %s
            WHERE cycle_id = %s
            """,
            (reset_expected_counts, now, cycle_id),
        )

    def complete_cycle(
        self,
        cycle_id: str,
        *,
        status: str,
        error_summary: str | None = None,
    ) -> None:
        self.connection.execute(
            """
            UPDATE catalog.crawl_cycles
            SET status = %s, error_summary = %s,
                completed_at = %s, updated_at = %s
            WHERE id = %s
            """,
            (
                status,
                error_summary,
                self._now(),
                self._now(),
                cycle_id,
            ),
        )

    def ensure_crawl_source(
        self,
        descriptor: SourceDescriptor,
        *,
        missing_threshold: int = 2,
    ) -> dict[str, str | int]:
        if missing_threshold < 1:
            raise ValueError("missing_threshold must be positive")
        company_row = self.connection.execute(
            "SELECT id FROM catalog.companies WHERE slug = %s",
            (descriptor.company_slug,),
        ).fetchone()
        if company_row is None:
            company_row = self.connection.execute(
                """
                INSERT INTO catalog.companies(
                    id, slug, name, created_at
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (slug)
                DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (
                    str(uuid.uuid4()),
                    descriptor.company_slug,
                    descriptor.company_name,
                    self._now(),
                ),
            ).fetchone()
        if company_row is None:
            raise RuntimeError("failed to persist crawl company")
        company_id = str(company_row[0])
        source_id = str(uuid.uuid4())
        source_row = self.connection.execute(
            """
            INSERT INTO catalog.crawl_sources(
                id, company_id, slug, name, scope_key, adapter_type,
                base_url, missing_threshold, enabled, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, TRUE, %s, %s
            )
            ON CONFLICT (slug)
            DO UPDATE SET
                name = EXCLUDED.name,
                scope_key = EXCLUDED.scope_key,
                adapter_type = EXCLUDED.adapter_type,
                base_url = EXCLUDED.base_url,
                updated_at = EXCLUDED.updated_at
            RETURNING id, missing_threshold
            """,
            (
                source_id,
                company_id,
                descriptor.source_slug,
                descriptor.source_name,
                descriptor.scope_key,
                descriptor.adapter_type,
                descriptor.base_url,
                missing_threshold,
                self._now(),
                self._now(),
            ),
        ).fetchone()
        if source_row is None:
            raise RuntimeError("failed to persist crawl source")
        return {
            "crawl_source_id": str(source_row[0]),
            "company_id": company_id,
            "source_slug": descriptor.source_slug,
            "missing_threshold": int(source_row[1]),
        }

    def start_crawl_run(self, crawl_source_id: str) -> str:
        run_id = str(uuid.uuid4())
        row = self.connection.execute(
            """
            INSERT INTO catalog.crawl_runs(
                id, source_id, status, started_at,
                observed_count, invalid_count
            ) VALUES (%s, %s, 'running', %s, 0, 0)
            RETURNING id
            """,
            (run_id, crawl_source_id, self._now()),
        ).fetchone()
        return str(row[0]) if row is not None else run_id

    def complete_crawl_run(
        self,
        run_id: str,
        *,
        status: str,
        observed_count: int,
        error_summary: str | None = None,
    ) -> None:
        self.connection.execute(
            """
            UPDATE catalog.crawl_runs
            SET status = %s, completed_at = %s,
                observed_count = %s, error_summary = %s
            WHERE id = %s
            """,
            (
                status,
                self._now(),
                observed_count,
                error_summary,
                run_id,
            ),
        )

    def store_raw_snapshot(
        self,
        source_id: str,
        run_id: str,
        *,
        url: str,
        payload: bytes,
        fetched_at,
    ) -> dict[str, str]:
        blob_id = str(uuid.uuid4())
        snapshot_id = str(uuid.uuid4())
        digest = hashlib.sha256(payload).hexdigest()
        self.connection.execute(
            """
            INSERT INTO blob.objects(
                id, scope, user_id, kind, media_type, original_name,
                size_bytes, sha256, content
            ) VALUES (
                %s, 'shared', NULL, 'crawl_snapshot',
                'application/json', NULL, %s, %s, %s
            )
            """,
            (blob_id, len(payload), digest, payload),
        )
        self.connection.execute(
            """
            INSERT INTO catalog.raw_snapshots(
                id, source_id, crawl_run_id, blob_id, url, fetched_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                snapshot_id,
                source_id,
                run_id,
                blob_id,
                url,
                fetched_at,
            ),
        )
        return {
            "id": snapshot_id,
            "blob_id": blob_id,
            "sha256": digest,
        }

    def ensure_manual_source(
        self,
        company_name: str,
    ) -> tuple[str, str]:
        company_row = self.connection.execute(
            """
            INSERT INTO catalog.companies(id, slug, name, created_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (slug)
            DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (
                str(uuid.uuid4()),
                company_slug(company_name),
                company_name,
                self._now(),
            ),
        ).fetchone()
        if company_row is None:
            raise RuntimeError("failed to persist manual job company")
        company_id = str(company_row[0])
        source_row = self.connection.execute(
            """
            INSERT INTO catalog.job_sources(
                id, company_id, slug, source_type, base_url, created_at
            ) VALUES (%s, %s, 'manual', 'manual', NULL, %s)
            ON CONFLICT (company_id, slug)
            DO UPDATE SET source_type = EXCLUDED.source_type
            RETURNING id
            """,
            (str(uuid.uuid4()), company_id, self._now()),
        ).fetchone()
        if source_row is None:
            raise RuntimeError("failed to persist manual job source")
        return company_id, str(source_row[0])

    def find_by_source_and_hash(
        self,
        source_id: str,
        content_hash: str,
    ) -> str | None:
        user_id = self._require_principal()
        row = self.connection.execute(
            """
            SELECT job.id
            FROM catalog.jobs job
            JOIN career.manual_job_owners owner
              ON owner.job_id = job.id
            WHERE job.source_id = %s
              AND job.content_hash = %s
              AND owner.user_id = %s
            """,
            (source_id, content_hash, user_id),
        ).fetchone()
        return str(row[0]) if row is not None else None

    def create_manual_job(
        self,
        *,
        company_id: str,
        source_id: str,
        content_hash: str,
        canonical_url: str,
        preview: ManualJDPreview,
    ) -> str:
        user_id = self._require_principal()
        now = self._now()
        job_id = str(uuid.uuid4())
        job_row = self.connection.execute(
            """
            INSERT INTO catalog.jobs(
                id, company_id, source_id, external_job_id,
                canonical_url, title, location_raw, locations,
                recruitment_type, description_raw, responsibilities,
                requirements, status, content_hash, missing_count,
                first_seen_at, last_seen_at, last_changed_at,
                created_at, updated_at
            ) VALUES (
                %s, %s, %s, NULL, %s, %s, %s, %s::jsonb, %s, %s,
                %s::jsonb, %s::jsonb, 'active', %s, 0,
                %s, %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                job_id,
                company_id,
                source_id,
                canonical_url,
                preview.title,
                preview.location_raw,
                json.dumps(preview.locations, ensure_ascii=False),
                preview.recruitment_type,
                preview.raw_text,
                json.dumps(preview.responsibilities, ensure_ascii=False),
                json.dumps(preview.requirements, ensure_ascii=False),
                content_hash,
                now,
                now,
                now,
                now,
                now,
            ),
        ).fetchone()
        if job_row is None:
            raise RuntimeError("failed to persist manual job")
        job_id = str(job_row[0])
        self.connection.execute(
            """
            INSERT INTO career.manual_job_owners(
                user_id, job_id, created_at
            ) VALUES (%s, %s, %s)
            """,
            (user_id, job_id, now),
        )
        snapshot = {
            "id": job_id,
            "canonical_url": canonical_url,
            "title": preview.title,
            "location_raw": preview.location_raw,
            "locations": preview.locations,
            "recruitment_type": preview.recruitment_type,
            "description_raw": preview.raw_text,
            "responsibilities": preview.responsibilities,
            "requirements": preview.requirements,
        }
        self.connection.execute(
            """
            INSERT INTO catalog.job_versions(
                id, job_id, version_number, content_hash,
                snapshot, field_diff, captured_at
            ) VALUES (%s, %s, 1, %s, %s::jsonb, '{}'::jsonb, %s)
            """,
            (
                str(uuid.uuid4()),
                job_id,
                content_hash,
                json.dumps(snapshot, ensure_ascii=False),
                now,
            ),
        )
        self.connection.execute(
            """
            INSERT INTO catalog.job_events(
                id, job_id, event_type, summary,
                changed_fields, occurred_at
            ) VALUES (
                %s, %s, 'created', 'Manual JD imported',
                '[]'::jsonb, %s
            )
            """,
            (str(uuid.uuid4()), job_id, now),
        )
        return job_id

    def _require_principal(self) -> str:
        if not self._principal_user_id:
            raise RuntimeError(
                "manual job operations require a tenant principal"
            )
        return self._principal_user_id

    def find_crawled_job(
        self,
        crawl_source_id: str,
        external_job_id: str,
    ):
        row = self.connection.execute(
            """
            SELECT id, status, content_hash, missing_count
            FROM catalog.jobs
            WHERE crawl_source_id = %s AND external_job_id = %s
            """,
            (crawl_source_id, external_job_id),
        ).fetchone()
        return _job_state(row) if row is not None else None

    def create_crawled_job(
        self,
        source: dict[str, str | int],
        job: NormalizedJob,
    ) -> str:
        source_row = self.connection.execute(
            """
            INSERT INTO catalog.job_sources(
                id, company_id, slug, source_type, base_url, created_at
            ) VALUES (%s, %s, %s, 'crawler', %s, %s)
            ON CONFLICT (company_id, slug)
            DO UPDATE SET base_url = EXCLUDED.base_url
            RETURNING id
            """,
            (
                str(uuid.uuid4()),
                source["company_id"],
                source["source_slug"],
                job.source_url,
                self._now(),
            ),
        ).fetchone()
        if source_row is None:
            raise RuntimeError("failed to persist job source")
        job_row = self.connection.execute(
            """
            INSERT INTO catalog.jobs(
                id, company_id, source_id, crawl_source_id,
                external_job_id, canonical_url, title, location_raw,
                locations, recruitment_type, description_raw,
                responsibilities, requirements, status, content_hash,
                missing_count, first_seen_at, last_seen_at,
                last_changed_at, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s,
                %s, '[]'::jsonb, '[]'::jsonb, 'active', %s, 0,
                %s, %s, %s, %s, %s
            )
            RETURNING id
            """,
            (
                str(uuid.uuid4()),
                source["company_id"],
                source_row[0],
                source["crawl_source_id"],
                job.external_job_id,
                job.source_url,
                job.title,
                job.locations[0] if job.locations else None,
                json.dumps(job.locations, ensure_ascii=False),
                job.recruitment_type,
                job.description_raw,
                job.content_hash,
                job.observed_at,
                job.observed_at,
                job.observed_at,
                self._now(),
                self._now(),
            ),
        ).fetchone()
        if job_row is None:
            raise RuntimeError("failed to persist crawled job")
        job_id = str(job_row[0])
        self._add_version(job_id, 1, job)
        self._add_event(
            job_id,
            "created",
            "Job first observed",
            [],
            job.observed_at,
        )
        return job_id

    def mark_seen(self, job_id: str, observed_at: str) -> None:
        self.connection.execute(
            """
            UPDATE catalog.jobs
            SET last_seen_at = %s, missing_count = 0, updated_at = %s
            WHERE id = %s
            """,
            (observed_at, self._now(), job_id),
        )

    def mark_changed(self, job_id: str, job: NormalizedJob) -> None:
        self._update_job(job_id, job, status="active")
        row = self.connection.execute(
            """
            SELECT COALESCE(MAX(version_number), 0) + 1
            FROM catalog.job_versions
            WHERE job_id = %s
            """,
            (job_id,),
        ).fetchone()
        self._add_version(job_id, int(row[0]), job)
        self._add_event(
            job_id,
            "changed",
            "Job content changed",
            ["content"],
            job.observed_at,
        )

    def reopen_job(
        self,
        job_id: str,
        job: NormalizedJob,
        *,
        changed: bool,
    ) -> None:
        self._update_job(job_id, job, status="active")
        if changed:
            row = self.connection.execute(
                """
                SELECT COALESCE(MAX(version_number), 0) + 1
                FROM catalog.job_versions
                WHERE job_id = %s
                """,
                (job_id,),
            ).fetchone()
            self._add_version(job_id, int(row[0]), job)
        self._add_event(
            job_id,
            "reopened",
            "Job observed again",
            [],
            job.observed_at,
        )

    def mark_absent(self, row, *, threshold: int) -> str:
        job_id = str(row["id"])
        result = self.connection.execute(
            """
            UPDATE catalog.jobs
            SET missing_count = missing_count + 1, updated_at = %s
            WHERE id = %s
            RETURNING missing_count
            """,
            (self._now(), job_id),
        ).fetchone()
        missing_count = int(result[0])
        if missing_count >= threshold:
            self.connection.execute(
                """
                UPDATE catalog.jobs
                SET status = 'inactive', updated_at = %s
                WHERE id = %s
                """,
                (self._now(), job_id),
            )
            transition = "offline"
            summary = "Job was absent for the threshold"
        else:
            transition = "missing"
            summary = "Job was not observed"
        self._add_event(
            job_id,
            transition,
            summary,
            [],
            self._now(),
        )
        return transition

    def active_crawled_jobs(self, crawl_source_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT id, external_job_id, missing_count
            FROM catalog.jobs
            WHERE crawl_source_id = %s AND status = 'active'
            """,
            (crawl_source_id,),
        ).fetchall()
        return [
            {
                "id": str(row[0]),
                "external_job_id": str(row[1]),
                "missing_count": int(row[2]),
            }
            for row in rows
        ]

    def find_crawl_source(self, source_slug: str):
        row = self.connection.execute(
            """
            SELECT id, slug, missing_threshold
            FROM catalog.crawl_sources
            WHERE slug = %s
            """,
            (source_slug,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": str(row[0]),
            "slug": str(row[1]),
            "missing_threshold": int(row[2]),
        }

    def _update_job(
        self,
        job_id: str,
        job: NormalizedJob,
        *,
        status: str,
    ) -> None:
        self.connection.execute(
            """
            UPDATE catalog.jobs
            SET canonical_url = %s, title = %s, location_raw = %s,
                locations = %s::jsonb, recruitment_type = %s,
                description_raw = %s, content_hash = %s, status = %s,
                missing_count = 0, last_seen_at = %s,
                last_changed_at = %s, updated_at = %s
            WHERE id = %s
            """,
            (
                job.source_url,
                job.title,
                job.locations[0] if job.locations else None,
                json.dumps(job.locations, ensure_ascii=False),
                job.recruitment_type,
                job.description_raw,
                job.content_hash,
                status,
                job.observed_at,
                job.observed_at,
                self._now(),
                job_id,
            ),
        )

    def _add_version(
        self,
        job_id: str,
        version_number: int,
        job: NormalizedJob,
    ) -> None:
        snapshot = {
            "external_job_id": job.external_job_id,
            "title": job.title,
            "description_raw": job.description_raw,
            "source_url": job.source_url,
            "locations": job.locations,
            "recruitment_type": job.recruitment_type,
        }
        self.connection.execute(
            """
            INSERT INTO catalog.job_versions(
                id, job_id, version_number, content_hash,
                snapshot, captured_at
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                str(uuid.uuid4()),
                job_id,
                version_number,
                job.content_hash,
                json.dumps(snapshot, ensure_ascii=False),
                job.observed_at,
            ),
        )

    def _add_event(
        self,
        job_id: str,
        event_type: str,
        summary: str,
        changed_fields: list[str],
        occurred_at,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO catalog.job_events(
                id, job_id, event_type, summary,
                changed_fields, occurred_at
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                str(uuid.uuid4()),
                job_id,
                event_type,
                summary,
                json.dumps(changed_fields, ensure_ascii=False),
                occurred_at,
            ),
        )

    def _now(self):
        value = self._clock()
        if value.tzinfo is None:
            raise ValueError("clock must be timezone-aware")
        return value.astimezone(timezone.utc)

    def catalog_records(self, prefilters: list[dict] | None = None) -> list[dict]:
        """Keep the principal-scoped visible_jobs boundary for portable queries."""
        clauses, params = ["TRUE"], []
        for item in prefilters or []:
            field, values, op = item["field"], item["values"], item["op"]
            if field == "company" and op == "in":
                values = [v.casefold() for v in values]
                clauses.append("(LOWER(c.slug)=ANY(%s) OR LOWER(c.name)=ANY(%s))")
                params.extend([values, values])
            elif field == "locations" and op == "in":
                values = [part.casefold() for value in values for part in (value.removesuffix("市"), value.removesuffix("市") + "市")]
                clauses.append("EXISTS (SELECT 1 FROM unnest(j.locations) l(value) WHERE LOWER(l.value)=ANY(%s))")
                params.append(values)
            elif field in {"status", "recruitment_type"} and op == "in":
                clauses.append(f"LOWER(j.{field})=ANY(%s)")
                params.append([v.casefold() for v in values])
            elif field in {"first_seen_at", "last_seen_at"} and op == "between":
                clauses.append(f"j.{field}>=%s::timestamptz AND j.{field}<%s::timestamptz")
                params.extend(values)
        rows = self.connection.execute("""SELECT j.id,c.slug,c.name,j.title,j.location_raw,j.locations,
            j.recruitment_type,j.status,j.description_raw,j.responsibilities,j.requirements,
            j.canonical_url,j.first_seen_at,j.last_seen_at,j.last_changed_at,tracking.data,tracking.version,
            reopened.reopened_at
            FROM career.visible_jobs j JOIN catalog.companies c ON c.id=j.company_id
            LEFT JOIN career.job_tracking tracking ON tracking.job_id=j.id AND tracking.user_id=current_setting('app.user_id', true)
            LEFT JOIN (SELECT job_id,MAX(occurred_at) AS reopened_at FROM catalog.job_events WHERE event_type='reopened' GROUP BY job_id) reopened ON reopened.job_id=j.id
            WHERE """ + " AND ".join(clauses), params).fetchall()
        return [{**self._job_row(row), "reopened_at": str(row[17]) if row[17] else None} for row in rows]

    def search_jobs(
        self,
        filters: JobSearchFilters,
    ) -> tuple[list[dict], int]:
        clauses: list[str] = []
        params: list[object] = []
        query = normalize_search_query(filters.query or "")
        if query:
            pattern = f"%{query}%"
            clauses.append(
                "("
                "j.search_document @@ websearch_to_tsquery('simple', %s) "
                "OR j.title ILIKE %s "
                "OR j.description_raw ILIKE %s "
                "OR j.requirements::text ILIKE %s"
                ")"
            )
            params.extend((query, pattern, pattern, pattern))
        for clause, values in (
            ("c.slug = ANY(%s)", filters.company_slugs),
            ("j.locations ?| %s", filters.locations),
            (
                "j.recruitment_type = ANY(%s)",
                filters.recruitment_types,
            ),
            ("j.status = ANY(%s)", filters.statuses),
        ):
            if values:
                clauses.append(clause)
                params.append(list(values))
        if filters.first_seen_after:
            clauses.append("j.first_seen_at >= %s")
            params.append(filters.first_seen_after)
        if filters.favorite_only:
            clauses.append("tracking.data->>'is_favorite' = 'true'")
        if filters.application_status:
            clauses.append(
                "COALESCE("
                "tracking.data->>'application_status', 'not_started'"
                ") = %s"
            )
            params.append(filters.application_status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        base = (
            " FROM career.visible_jobs j"
            " JOIN catalog.companies c ON c.id = j.company_id"
            " LEFT JOIN career.job_tracking tracking"
            " ON tracking.job_id = j.id"
            " AND tracking.user_id = "
            "current_setting('app.user_id', true)"
        )
        total_row = self.connection.execute(
            "SELECT COUNT(*)" + base + where,
            tuple(params),
        ).fetchone()
        rows = self.connection.execute(
            """
            SELECT
                j.id, c.slug, c.name, j.title, j.location_raw,
                j.locations, j.recruitment_type, j.status,
                j.canonical_url, j.first_seen_at, j.last_seen_at,
                j.last_changed_at, tracking.data, tracking.version
            """
            + base
            + where
            + " ORDER BY j.first_seen_at DESC, j.id ASC LIMIT %s OFFSET %s",
            (*params, filters.limit, filters.offset),
        ).fetchall()
        return [
            self._job_summary_row(row) for row in rows
        ], int(total_row[0])

    def get_job(self, job_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT
                j.id, c.slug, c.name, j.title, j.location_raw,
                j.locations, j.recruitment_type, j.status,
                j.description_raw, j.responsibilities, j.requirements,
                j.canonical_url, j.first_seen_at, j.last_seen_at,
                j.last_changed_at
            FROM career.visible_jobs j
            JOIN catalog.companies c ON c.id = j.company_id
            WHERE j.id = %s
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        detail = self._job_row(row)
        versions = self.connection.execute(
            """
            SELECT version_number, content_hash, captured_at
            FROM catalog.job_versions
            WHERE job_id = %s
            ORDER BY version_number DESC
            """,
            (job_id,),
        ).fetchall()
        events = self.connection.execute(
            """
            SELECT event_type, summary, changed_fields, occurred_at
            FROM catalog.job_events
            WHERE job_id = %s
            ORDER BY occurred_at DESC, id DESC
            """,
            (job_id,),
        ).fetchall()
        detail["versions"] = [
            {
                "version_number": int(version[0]),
                "content_hash": str(version[1]),
                "captured_at": str(version[2]),
            }
            for version in versions
        ]
        detail["events"] = [
            {
                "event_type": str(event[0]),
                "summary": str(event[1]),
                "changed_fields": list(event[2] or []),
                "occurred_at": str(event[3]),
            }
            for event in events
        ]
        return detail

    def get_interview_input(self, job_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT
                j.id, j.title, j.status, j.canonical_url,
                j.content_hash, j.description_raw, j.requirements,
                c.slug, c.name
            FROM career.visible_jobs j
            JOIN catalog.companies c ON c.id = j.company_id
            WHERE j.id = %s
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": str(row[0]),
            "title": row[1],
            "status": str(row[2]),
            "source_url": str(row[3]),
            "content_hash": str(row[4]),
            "description_raw": str(row[5]),
            "requirements": list(row[6] or []),
            "company": {"slug": str(row[7]), "name": str(row[8])},
        }

    def get_job_filters(self) -> dict:
        facet_rows = self.connection.execute(
            """
            WITH visible AS MATERIALIZED (
                SELECT
                    id, company_id, locations,
                    recruitment_type, status
                FROM career.visible_jobs
            ),
            facets AS (
                SELECT
                    'company'::text AS facet_type,
                    c.slug AS value,
                    c.name AS label,
                    COUNT(v.id) AS count
                FROM catalog.companies c
                JOIN visible v ON v.company_id = c.id
                GROUP BY c.id, c.slug, c.name

                UNION ALL

                SELECT
                    'location', location.value,
                    location.value, COUNT(*)
                FROM visible v
                CROSS JOIN LATERAL jsonb_array_elements_text(
                    v.locations
                ) AS location(value)
                GROUP BY location.value

                UNION ALL

                SELECT
                    'recruitment_type', recruitment_type,
                    recruitment_type, COUNT(*)
                FROM visible
                WHERE recruitment_type IS NOT NULL
                  AND BTRIM(recruitment_type) <> ''
                GROUP BY recruitment_type

                UNION ALL

                SELECT 'status', status, status, COUNT(*)
                FROM visible
                WHERE status IS NOT NULL
                  AND BTRIM(status) <> ''
                GROUP BY status
            )
            SELECT facet_type, value, label, count
            FROM facets
            """
        ).fetchall()
        favorite_row = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM career.job_tracking
            WHERE data->>'is_favorite' = 'true'
            """
        ).fetchone()
        companies = sorted(
            (
                {
                    "slug": str(row[1]),
                    "name": str(row[2]),
                    "count": int(row[3]),
                }
                for row in facet_rows
                if row[0] == "company"
            ),
            key=lambda item: (item["name"], item["slug"]),
        )
        locations = sorted(
            (
                {"value": str(row[1]), "count": int(row[3])}
                for row in facet_rows
                if row[0] == "location"
            ),
            key=lambda item: (-item["count"], item["value"]),
        )

        def grouped(facet_type: str) -> list[dict]:
            return sorted(
                (
                    {"value": str(row[1]), "count": int(row[3])}
                    for row in facet_rows
                    if row[0] == facet_type
                ),
                key=lambda item: item["value"],
            )

        return {
            "companies": companies,
            "locations": locations,
            "recruitment_types": grouped("recruitment_type"),
            "statuses": grouped("status"),
            "favorite_count": int(
                favorite_row[0] if favorite_row else 0
            ),
        }

    @staticmethod
    def _job_summary_row(row) -> dict:
        tracking = row[12] or {}
        return {
            "id": str(row[0]),
            "company": {"slug": str(row[1]), "name": str(row[2])},
            "title": row[3],
            "location_raw": row[4],
            "locations": list(row[5] or []),
            "recruitment_type": row[6],
            "status": str(row[7]),
            "source_url": str(row[8]),
            "first_seen_at": str(row[9]),
            "last_seen_at": str(row[10]),
            "last_changed_at": str(row[11]),
            "tracking": {
                "is_favorite": bool(
                    tracking.get("is_favorite", False)
                ),
                "application_status": tracking.get(
                    "application_status",
                    "not_started",
                ),
                "version": int(row[13] or 0),
                "updated_at": tracking.get("updated_at"),
            },
        }

    @staticmethod
    def _job_row(row) -> dict:
        tracking = row[15] if len(row) > 15 and row[15] else {}
        tracking_version = row[16] if len(row) > 16 else 0
        return {
            "id": str(row[0]),
            "company": {"slug": str(row[1]), "name": str(row[2])},
            "title": row[3],
            "location_raw": row[4],
            "locations": list(row[5] or []),
            "recruitment_type": row[6],
            "status": str(row[7]),
            "description_raw": str(row[8]),
            "responsibilities": list(row[9] or []),
            "requirements": list(row[10] or []),
            "source_url": str(row[11]),
            "first_seen_at": str(row[12]),
            "last_seen_at": str(row[13]),
            "last_changed_at": str(row[14]),
            "tracking": {
                "is_favorite": bool(
                    tracking.get("is_favorite", False)
                ),
                "application_status": tracking.get(
                    "application_status",
                    "not_started",
                ),
                "version": int(tracking_version or 0),
                "updated_at": tracking.get("updated_at"),
            },
        }


def _job_state(row) -> dict:
    return {
        "id": str(row[0]),
        "status": str(row[1]),
        "content_hash": str(row[2]),
        "missing_count": int(row[3]),
    }


def _cycle_row(row) -> dict:
    return {
        "id": str(row[0]),
        "source_id": str(row[1]),
        "status": str(row[2]),
        "pass_number": int(row[3]),
        "expected_total": row[4],
        "started_at": row[5],
        "updated_at": row[6],
        "completed_at": row[7],
        "error_summary": row[8],
    }
