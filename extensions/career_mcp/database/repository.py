"""Repository boundary for persisted Career jobs."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from uuid import uuid4

from ..domain.crawler import NormalizedJob, SourceDescriptor
from ..domain.locations import split_job_locations
from ..domain.manual_jd import company_slug, utc_now_iso
from ..domain.models import JobSearchFilters, ManualJDPreview
from .migrations import migrate


class JobRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        migrate(connection)

    def acquire_source_lock(self, source_slug: str) -> bool:
        return True

    def get_or_create_crawl_cycle(
        self,
        crawl_source_id: str,
        shards: list[dict],
    ) -> dict:
        row = self.connection.execute(
            """
            SELECT *
            FROM crawl_cycles
            WHERE source_id = ? AND status = 'running'
            """,
            (crawl_source_id,),
        ).fetchone()
        if row is not None:
            return dict(row)
        now = utc_now_iso()
        cycle_id = str(uuid4())
        self.connection.execute(
            """
            INSERT INTO crawl_cycles(
                id, source_id, status, pass_number,
                expected_total, started_at, updated_at
            ) VALUES (?, ?, 'running', 1, NULL, ?, ?)
            """,
            (cycle_id, crawl_source_id, now, now),
        )
        for shard in shards:
            self.connection.execute(
                """
                INSERT INTO crawl_cycle_shards(
                    cycle_id, shard_key, filters_json,
                    expected_count, next_offset, status,
                    last_page_fingerprint, updated_at
                ) VALUES (?, ?, ?, NULL, 0, 'pending', NULL, ?)
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
        return dict(
            self.connection.execute(
                "SELECT * FROM crawl_cycles WHERE id = ?",
                (cycle_id,),
            ).fetchone()
        )

    def list_cycle_shards(self, cycle_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM crawl_cycle_shards
            WHERE cycle_id = ?
            ORDER BY shard_key
            """,
            (cycle_id,),
        ).fetchall()
        return [
            {
                **dict(row),
                "filters": json.loads(row["filters_json"]),
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
            UPDATE crawl_cycle_shards
            SET expected_count = ?, next_offset = ?, status = ?,
                last_page_fingerprint = ?, updated_at = ?
            WHERE cycle_id = ? AND shard_key = ?
            """,
            (
                expected_count,
                next_offset,
                status,
                last_page_fingerprint,
                utc_now_iso(),
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
            FROM crawl_cycle_jobs
            WHERE cycle_id = ? AND external_job_id = ?
            """,
            (cycle_id, external_job_id),
        ).fetchone()
        if row is not None:
            if str(row["content_hash"]) != content_hash:
                if pass_number > int(row["last_pass"]):
                    self.connection.execute(
                        """
                        UPDATE crawl_cycle_jobs
                        SET snapshot_json = ?, content_hash = ?,
                            last_pass = ?, observed_at = ?
                        WHERE cycle_id = ? AND external_job_id = ?
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
                UPDATE crawl_cycle_jobs
                SET last_pass = ?, observed_at = ?
                WHERE cycle_id = ? AND external_job_id = ?
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
            INSERT INTO crawl_cycle_jobs(
                cycle_id, external_job_id, snapshot_json,
                content_hash, first_pass, last_pass, observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
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
            SELECT *
            FROM crawl_cycle_jobs
            WHERE cycle_id = ?
            ORDER BY external_job_id
            """,
            (cycle_id,),
        ).fetchall()
        return [
            {
                **dict(row),
                "snapshot": json.loads(row["snapshot_json"]),
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
        placeholders = ",".join("?" for _ in requested)
        rows = self.connection.execute(
            f"""
            SELECT external_job_id
            FROM crawl_cycle_jobs
            WHERE cycle_id = ?
              AND last_pass < ?
              AND external_job_id IN ({placeholders})
            """,
            (cycle_id, pass_number, *requested),
        ).fetchall()
        if {str(row["external_job_id"]) for row in rows} != set(requested):
            raise ValueError(
                "verified ByteDance job ids do not match stale rows"
            )
        if active_ids:
            active = sorted(active_ids)
            active_placeholders = ",".join("?" for _ in active)
            self.connection.execute(
                f"""
                UPDATE crawl_cycle_jobs
                SET last_pass = ?, observed_at = ?
                WHERE cycle_id = ?
                  AND last_pass < ?
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
            offline_placeholders = ",".join("?" for _ in offline)
            self.connection.execute(
                f"""
                DELETE FROM crawl_cycle_jobs
                WHERE cycle_id = ?
                  AND last_pass < ?
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
        now = utc_now_iso()
        self.connection.execute(
            """
            UPDATE crawl_cycles
            SET pass_number = ?, updated_at = ?
            WHERE id = ? AND status = 'running'
            """,
            (pass_number, now, cycle_id),
        )
        self.connection.execute(
            """
            UPDATE crawl_cycle_shards
            SET expected_count = CASE WHEN ? THEN NULL ELSE expected_count END,
                next_offset = 0, status = 'pending',
                last_page_fingerprint = NULL, updated_at = ?
            WHERE cycle_id = ?
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
            UPDATE crawl_cycles
            SET status = ?, error_summary = ?,
                completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                error_summary,
                utc_now_iso(),
                utc_now_iso(),
                cycle_id,
            ),
        )

    def ensure_manual_source(self, company_name: str) -> tuple[str, str]:
        slug = company_slug(company_name)
        row = self.connection.execute(
            "SELECT id FROM companies WHERE slug = ?", (slug,)
        ).fetchone()
        now = utc_now_iso()
        if row is None:
            company_id = str(uuid4())
            self.connection.execute(
                "INSERT INTO companies(id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                (company_id, slug, company_name, now),
            )
        else:
            company_id = row["id"]
        row = self.connection.execute(
            "SELECT id FROM job_sources WHERE company_id = ? AND slug = 'manual'",
            (company_id,),
        ).fetchone()
        if row is None:
            source_id = str(uuid4())
            self.connection.execute(
                "INSERT INTO job_sources(id, company_id, slug, source_type, base_url, created_at) "
                "VALUES (?, ?, 'manual', 'manual', NULL, ?)",
                (source_id, company_id, now),
            )
        else:
            source_id = row["id"]
        return company_id, source_id

    def find_by_source_and_hash(self, source_id: str, content_hash: str) -> str | None:
        row = self.connection.execute(
            "SELECT id FROM jobs WHERE source_id = ? AND content_hash = ?",
            (source_id, content_hash),
        ).fetchone()
        return row["id"] if row else None

    def create_manual_job(
        self,
        *,
        company_id: str,
        source_id: str,
        content_hash: str,
        canonical_url: str,
        preview: ManualJDPreview,
    ) -> str:
        now = utc_now_iso()
        job_id = str(uuid4())
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
            INSERT INTO jobs(
                id, company_id, source_id, external_job_id, canonical_url, title,
                location_raw, locations_json, recruitment_type, description_raw,
                responsibilities_json, requirements_json, status, content_hash,
                first_seen_at, last_seen_at, last_changed_at, created_at, updated_at
            ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
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
        )
        self.connection.execute(
            "INSERT INTO job_versions(id, job_id, version_number, content_hash, snapshot_json, captured_at) "
            "VALUES (?, ?, 1, ?, ?, ?)",
            (str(uuid4()), job_id, content_hash, json.dumps(snapshot, ensure_ascii=False), now),
        )
        self.connection.execute(
            "INSERT INTO job_events(id, job_id, event_type, summary, changed_fields_json, occurred_at) "
            "VALUES (?, ?, 'created', 'Manual JD imported', '[]', ?)",
            (str(uuid4()), job_id, now),
        )
        return job_id

    def get_job(self, job_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT j.*, c.slug AS company_slug, c.name AS company_name, s.source_type,
                   s.slug AS source_slug
            FROM jobs j
            JOIN companies c ON c.id = j.company_id
            JOIN job_sources s ON s.id = j.source_id
            WHERE j.id = ?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        detail = self._job_row(row)
        detail["source_url"] = row["canonical_url"]
        detail["versions"] = [
            {
                "version_number": version["version_number"],
                "content_hash": version["content_hash"],
                "captured_at": version["captured_at"],
            }
            for version in self.connection.execute(
                "SELECT version_number, content_hash, captured_at FROM job_versions "
                "WHERE job_id = ? ORDER BY version_number DESC",
                (job_id,),
            )
        ]
        detail["events"] = [
            {
                "event_type": event["event_type"],
                "summary": event["summary"],
                "changed_fields": json.loads(event["changed_fields_json"]),
                "occurred_at": event["occurred_at"],
            }
            for event in self.connection.execute(
                "SELECT event_type, summary, changed_fields_json, occurred_at FROM job_events "
                "WHERE job_id = ? ORDER BY occurred_at DESC",
                (job_id,),
            )
        ]
        return detail

    def get_interview_input(self, job_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT j.id, j.title, j.status, j.canonical_url,
                   j.content_hash, j.description_raw, j.requirements_json,
                   c.slug AS company_slug, c.name AS company_name
            FROM jobs j
            JOIN companies c ON c.id = j.company_id
            WHERE j.id = ?
            """,
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "title": row["title"],
            "company": {
                "slug": str(row["company_slug"]),
                "name": str(row["company_name"]),
            },
            "status": str(row["status"]),
            "source_url": str(row["canonical_url"]),
            "content_hash": str(row["content_hash"]),
            "description_raw": str(row["description_raw"]),
            "requirements": json.loads(row["requirements_json"]),
        }

    def catalog_records(self, prefilters: list[dict] | None = None) -> list[dict]:
        """One consistent local snapshot for evidence-bearing domain queries."""
        clauses, params = ["1=1"], []
        for item in prefilters or []:
            field, values, op = item["field"], item["values"], item["op"]
            if field == "company" and op == "in":
                values = [v.casefold() for v in values]
                marks = ",".join("?" for _ in values)
                clauses.append(f"(LOWER(c.slug) IN ({marks}) OR LOWER(c.name) IN ({marks}))")
                params.extend(values + values)
            elif field == "locations" and op == "in":
                values = [part.casefold() for value in values for part in (value.removesuffix("市"), value.removesuffix("市") + "市")]
                clauses.append("EXISTS (SELECT 1 FROM json_each(j.locations_json) l WHERE LOWER(l.value) IN (" + ",".join("?" for _ in values) + "))")
                params.extend(values)
            elif field in {"status", "recruitment_type"} and op == "in":
                clauses.append(f"LOWER(j.{field}) IN (" + ",".join("?" for _ in values) + ")")
                params.extend(v.casefold() for v in values)
            elif field in {"first_seen_at", "last_seen_at"} and op == "between":
                clauses.append(f"julianday(j.{field})>=julianday(?) AND julianday(j.{field})<julianday(?)")
                params.extend(values)
        rows = self.connection.execute("""SELECT j.*, c.slug AS company_slug, c.name AS company_name,
            tracking.is_favorite AS tracking_is_favorite, tracking.application_status AS tracking_application_status,
            tracking.version AS tracking_version, tracking.updated_at AS tracking_updated_at,
            reopened.reopened_at
            FROM jobs j JOIN companies c ON c.id=j.company_id LEFT JOIN job_tracking tracking ON tracking.job_id=j.id
            LEFT JOIN (SELECT job_id,MAX(occurred_at) AS reopened_at FROM job_events WHERE event_type='reopened' GROUP BY job_id) reopened ON reopened.job_id=j.id
            WHERE """ + " AND ".join(clauses), params).fetchall()
        return [{**self._job_row(row), "reopened_at": row["reopened_at"]} for row in rows]

    def search_jobs(self, filters: JobSearchFilters) -> tuple[list[dict], int]:
        clauses = ["1 = 1"]
        params: list[object] = []
        if filters.query:
            clauses.append(
                "(j.title LIKE ? OR j.description_raw LIKE ? OR j.requirements_json LIKE ?)"
            )
            params.extend([f"%{filters.query}%"] * 3)
        for column, values in (
            ("c.slug", filters.company_slugs),
            ("j.recruitment_type", filters.recruitment_types),
            ("j.status", filters.statuses),
        ):
            if values:
                clauses.append(f"{column} IN ({','.join('?' for _ in values)})")
                params.extend(values)
        if filters.locations:
            clauses.append(
                "(" + " OR ".join("j.locations_json LIKE ?" for _ in filters.locations) + ")"
            )
            params.extend(f"%{location}%" for location in filters.locations)
        if filters.first_seen_after:
            clauses.append("j.first_seen_at >= ?")
            params.append(filters.first_seen_after)
        if filters.favorite_only:
            clauses.append("tracking.is_favorite = 1")
        if filters.application_status:
            clauses.append(
                "COALESCE(tracking.application_status, 'not_started') = ?"
            )
            params.append(filters.application_status)
        where = " AND ".join(clauses)
        base = (
            " FROM jobs j"
            " JOIN companies c ON c.id = j.company_id"
            " LEFT JOIN job_tracking tracking ON tracking.job_id = j.id"
        )
        total = self.connection.execute(
            "SELECT COUNT(*)" + base + " WHERE " + where, params
        ).fetchone()[0]
        rows = self.connection.execute(
            "SELECT j.*, c.slug AS company_slug, c.name AS company_name,"
            " tracking.is_favorite AS tracking_is_favorite,"
            " tracking.application_status AS tracking_application_status,"
            " tracking.version AS tracking_version,"
            " tracking.updated_at AS tracking_updated_at"
            + base
            + " WHERE "
            + where
            + " ORDER BY j.first_seen_at DESC, j.id ASC LIMIT ? OFFSET ?",
            [*params, filters.limit, filters.offset],
        ).fetchall()
        return [self._job_row(row) for row in rows], int(total)

    def get_job_filters(self) -> dict:
        companies = [
            {
                "slug": str(row["slug"]),
                "name": str(row["name"]),
                "count": int(row["job_count"]),
            }
            for row in self.connection.execute(
                """
                SELECT c.slug, c.name, COUNT(j.id) AS job_count
                FROM companies c
                JOIN jobs j ON j.company_id = c.id
                GROUP BY c.id, c.slug, c.name
                ORDER BY c.name ASC, c.slug ASC
                """
            )
        ]
        location_counts: Counter[str] = Counter()
        for row in self.connection.execute(
            "SELECT locations_json FROM jobs"
        ):
            location_counts.update(
                split_job_locations(json.loads(row["locations_json"]))
            )

        def grouped_values(column: str) -> list[dict]:
            return [
                {
                    "value": str(row["value"]),
                    "count": int(row["job_count"]),
                }
                for row in self.connection.execute(
                    f"""
                    SELECT {column} AS value, COUNT(*) AS job_count
                    FROM jobs
                    WHERE {column} IS NOT NULL AND TRIM({column}) != ''
                    GROUP BY {column}
                    ORDER BY {column} ASC
                    """
                )
            ]

        favorite_row = self.connection.execute(
            """
            SELECT COUNT(*) AS favorite_count
            FROM job_tracking
            WHERE is_favorite = 1
            """
        ).fetchone()
        return {
            "companies": companies,
            "locations": [
                {"value": value, "count": count}
                for value, count in sorted(
                    location_counts.items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
            "recruitment_types": grouped_values("recruitment_type"),
            "statuses": grouped_values("status"),
            "favorite_count": int(
                favorite_row["favorite_count"] if favorite_row else 0
            ),
        }

    def ensure_crawl_source(
        self, descriptor: SourceDescriptor, *, missing_threshold: int = 2
    ) -> dict[str, str | int]:
        if missing_threshold < 1:
            raise ValueError("missing_threshold must be positive")
        now = utc_now_iso()
        company = self.connection.execute(
            "SELECT id FROM companies WHERE slug = ?", (descriptor.company_slug,)
        ).fetchone()
        if company is None:
            company_id = str(uuid4())
            self.connection.execute(
                "INSERT INTO companies(id, slug, name, created_at) VALUES (?, ?, ?, ?)",
                (
                    company_id,
                    descriptor.company_slug,
                    descriptor.company_name,
                    now,
                ),
            )
        else:
            company_id = str(company["id"])
            self.connection.execute(
                "UPDATE companies SET name = ? WHERE id = ?",
                (descriptor.company_name, company_id),
            )

        row = self.connection.execute(
            "SELECT id, company_id, missing_threshold FROM crawl_sources WHERE slug = ?",
            (descriptor.source_slug,),
        ).fetchone()
        if row is None:
            crawl_source_id = str(uuid4())
            self.connection.execute(
                """
                INSERT INTO crawl_sources(
                    id, slug, name, missing_threshold, enabled, created_at, updated_at,
                    company_id, scope_key, adapter_type, base_url
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)
                """,
                (
                    crawl_source_id,
                    descriptor.source_slug,
                    descriptor.source_name,
                    missing_threshold,
                    now,
                    now,
                    company_id,
                    descriptor.scope_key,
                    descriptor.adapter_type,
                    descriptor.base_url,
                ),
            )
        else:
            crawl_source_id = str(row["id"])
            if str(row["company_id"]) != company_id:
                raise ValueError("crawl source belongs to a different company")
            missing_threshold = int(row["missing_threshold"])
            self.connection.execute(
                """
                UPDATE crawl_sources
                SET name = ?, scope_key = ?, adapter_type = ?, base_url = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    descriptor.source_name,
                    descriptor.scope_key,
                    descriptor.adapter_type,
                    descriptor.base_url,
                    now,
                    crawl_source_id,
                ),
            )
        return {
            "crawl_source_id": crawl_source_id,
            "company_id": company_id,
            "source_slug": descriptor.source_slug,
            "missing_threshold": missing_threshold,
        }

    def start_crawl_run(self, crawl_source_id: str) -> str:
        run_id = str(uuid4())
        self.connection.execute(
            """
            INSERT INTO crawl_runs(
                id, source_id, status, started_at, completed_at,
                observed_count, invalid_count, error_summary
            ) VALUES (?, ?, 'running', ?, NULL, 0, 0, NULL)
            """,
            (run_id, crawl_source_id, utc_now_iso()),
        )
        return run_id

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
            UPDATE crawl_runs
            SET status = ?, completed_at = ?, observed_count = ?, error_summary = ?
            WHERE id = ?
            """,
            (status, utc_now_iso(), observed_count, error_summary, run_id),
        )

    def find_crawled_job(
        self, crawl_source_id: str, external_job_id: str
    ) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT * FROM jobs
            WHERE crawl_source_id = ? AND external_job_id = ?
            """,
            (crawl_source_id, external_job_id),
        ).fetchone()

    def find_crawl_source(self, source_slug: str) -> sqlite3.Row | None:
        return self.connection.execute(
            """
            SELECT id, slug, missing_threshold
            FROM crawl_sources
            WHERE slug = ?
            """,
            (source_slug,),
        ).fetchone()

    def company_external_ids_from_other_sources(
        self,
        company_slug: str,
        *,
        exclude_source_slug: str,
    ) -> set[str]:
        return {
            str(row["external_job_id"])
            for row in self.connection.execute(
                """
                SELECT j.external_job_id
                FROM jobs j
                JOIN companies c ON c.id = j.company_id
                JOIN crawl_sources cs ON cs.id = j.crawl_source_id
                WHERE c.slug = ?
                  AND cs.slug != ?
                  AND j.external_job_id IS NOT NULL
                """,
                (company_slug, exclude_source_slug),
            )
        }

    def create_crawled_job(self, source: dict[str, str | int], job: NormalizedJob) -> str:
        now = utc_now_iso()
        job_id = str(uuid4())
        snapshot = self._crawler_snapshot(job)
        job_source_id = self._ensure_crawl_job_source(
            str(source["company_id"]),
            str(source["source_slug"]),
            job.external_job_id,
            now,
        )
        self.connection.execute(
            """
            INSERT INTO jobs(
                id, company_id, source_id, crawl_source_id, external_job_id, canonical_url,
                title, location_raw, locations_json, recruitment_type, description_raw,
                responsibilities_json, requirements_json, status, content_hash, missing_count,
                first_seen_at, last_seen_at, last_changed_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', 'active', ?, 0, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                source["company_id"],
                job_source_id,
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
                now,
                now,
            ),
        )
        self._add_version(job_id, 1, job.content_hash, snapshot, job.observed_at)
        self._add_event(job_id, "created", "Job first observed", [], job.observed_at)
        return job_id

    def mark_seen(self, job_id: str, observed_at: str) -> None:
        self.connection.execute(
            """
            UPDATE jobs
            SET last_seen_at = ?, missing_count = 0, updated_at = ?
            WHERE id = ?
            """,
            (observed_at, utc_now_iso(), job_id),
        )

    def mark_changed(self, job_id: str, job: NormalizedJob) -> None:
        self._update_crawled_job(job_id, job, status="active")
        version_number = self.connection.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 FROM job_versions WHERE job_id = ?",
            (job_id,),
        ).fetchone()[0]
        self._add_version(
            job_id,
            int(version_number),
            job.content_hash,
            self._crawler_snapshot(job),
            job.observed_at,
        )
        self._add_event(job_id, "changed", "Job content changed", ["content"], job.observed_at)

    def reopen_job(self, job_id: str, job: NormalizedJob, *, changed: bool) -> None:
        self._update_crawled_job(job_id, job, status="active")
        if changed:
            version_number = self.connection.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 FROM job_versions WHERE job_id = ?",
                (job_id,),
            ).fetchone()[0]
            self._add_version(
                job_id,
                int(version_number),
                job.content_hash,
                self._crawler_snapshot(job),
                job.observed_at,
            )
        self._add_event(job_id, "reopened", "Job observed again", [], job.observed_at)

    def mark_absent(self, row: sqlite3.Row, *, threshold: int) -> str:
        missing_count = int(row["missing_count"]) + 1
        now = utc_now_iso()
        if missing_count >= threshold:
            self.connection.execute(
                """
                UPDATE jobs
                SET status = 'inactive', missing_count = ?, updated_at = ?
                WHERE id = ?
                """,
                (missing_count, now, row["id"]),
            )
            self._add_event(row["id"], "offline", "Job was absent for the threshold", [], now)
            return "offline"
        self.connection.execute(
            "UPDATE jobs SET missing_count = ?, updated_at = ? WHERE id = ?",
            (missing_count, now, row["id"]),
        )
        self._add_event(row["id"], "missing", "Job was not observed", [], now)
        return "missing"

    def active_crawled_jobs(self, crawl_source_id: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT * FROM jobs
            WHERE crawl_source_id = ? AND status = 'active'
            """,
            (crawl_source_id,),
        ).fetchall()

    def list_crawl_sources(self) -> list[dict]:
        return [
            {
                "slug": row["slug"],
                "name": row["name"],
                "missing_threshold": row["missing_threshold"],
                "enabled": bool(row["enabled"]),
            }
            for row in self.connection.execute(
                """
                SELECT slug, name, missing_threshold, enabled
                FROM crawl_sources
                ORDER BY slug ASC
                """
            )
        ]

    def list_recent_job_events(self, limit: int) -> list[dict]:
        return [
            {
                "job_id": row["job_id"],
                "company": row["company_name"],
                "title": row["title"],
                "event_type": row["event_type"],
                "summary": row["summary"],
                "occurred_at": row["occurred_at"],
            }
            for row in self.connection.execute(
                """
                SELECT e.job_id, c.name AS company_name, j.title, e.event_type,
                       e.summary, e.occurred_at
                FROM job_events e
                JOIN jobs j ON j.id = e.job_id
                JOIN companies c ON c.id = j.company_id
                ORDER BY e.occurred_at DESC, e.id DESC
                LIMIT ?
                """,
                (limit,),
            )
        ]

    def get_job_radar_digest_data(
        self,
        *,
        occurred_after: str,
        sample_limit: int,
    ) -> dict:
        job_counts = self.connection.execute(
            """
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(status = 'active'), 0) AS active,
                   COALESCE(SUM(status = 'inactive'), 0) AS inactive
            FROM jobs
            """
        ).fetchone()
        event_type_rows = self.connection.execute(
            """
            SELECT event_type, COUNT(*) AS count
            FROM job_events
            WHERE occurred_at >= ?
            GROUP BY event_type
            ORDER BY event_type
            """,
            (occurred_after,),
        ).fetchall()
        by_type = {
            str(row["event_type"]): int(row["count"])
            for row in event_type_rows
        }

        companies: dict[str, dict] = {}
        for row in self.connection.execute(
            """
            SELECT c.slug AS company_slug, c.name AS company_name,
                   e.event_type, COUNT(*) AS count
            FROM job_events e
            JOIN jobs j ON j.id = e.job_id
            JOIN companies c ON c.id = j.company_id
            WHERE e.occurred_at >= ?
            GROUP BY c.id, e.event_type
            ORDER BY c.slug, e.event_type
            """,
            (occurred_after,),
        ):
            company_slug = str(row["company_slug"])
            company = companies.setdefault(
                company_slug,
                {
                    "company_slug": company_slug,
                    "company_name": str(row["company_name"]),
                    "total": 0,
                },
            )
            count = int(row["count"])
            company[str(row["event_type"])] = count
            company["total"] += count

        samples = [
            {
                "job_id": str(row["job_id"]),
                "company_slug": str(row["company_slug"]),
                "company_name": str(row["company_name"]),
                "title": row["title"],
                "event_type": str(row["event_type"]),
                "summary": str(row["summary"]),
                "occurred_at": str(row["occurred_at"]),
                "source_url": str(row["source_url"]),
            }
            for row in self.connection.execute(
                """
                SELECT e.job_id, c.slug AS company_slug,
                       c.name AS company_name, j.title, e.event_type,
                       e.summary, e.occurred_at,
                       j.canonical_url AS source_url
                FROM job_events e
                JOIN jobs j ON j.id = e.job_id
                JOIN companies c ON c.id = j.company_id
                WHERE e.occurred_at >= ?
                ORDER BY e.occurred_at DESC, e.id DESC
                LIMIT ?
                """,
                (occurred_after, sample_limit),
            )
        ]

        source_items = [
            {
                "source_slug": str(row["source_slug"]),
                "source_name": str(row["source_name"]),
                "last_run_status": row["last_run_status"],
                "last_run_at": row["last_run_at"],
                "last_observed_count": row["last_observed_count"],
                "last_error": row["last_error"],
            }
            for row in self.connection.execute(
                """
                WITH ranked_runs AS (
                    SELECT cr.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY cr.source_id
                               ORDER BY cr.started_at DESC, cr.id DESC
                           ) AS run_rank
                    FROM crawl_runs cr
                )
                SELECT cs.slug AS source_slug, cs.name AS source_name,
                       rr.status AS last_run_status,
                       rr.started_at AS last_run_at,
                       rr.observed_count AS last_observed_count,
                       rr.error_summary AS last_error
                FROM crawl_sources cs
                LEFT JOIN ranked_runs rr
                  ON rr.source_id = cs.id AND rr.run_rank = 1
                WHERE cs.enabled = 1
                ORDER BY cs.slug
                """
            )
        ]
        healthy = sum(
            source["last_run_status"] == "succeeded"
            for source in source_items
        )
        failed = sum(
            source["last_run_status"] == "failed"
            for source in source_items
        )
        pending = sum(
            source["last_run_status"] is None
            for source in source_items
        )
        return {
            "jobs": {
                "total": int(job_counts["total"]),
                "active": int(job_counts["active"]),
                "inactive": int(job_counts["inactive"]),
            },
            "events": {
                "total": sum(by_type.values()),
                "by_type": by_type,
                "by_company": list(companies.values()),
                "samples": samples,
            },
            "sources": {
                "configured": len(source_items),
                "healthy": healthy,
                "failed": failed,
                "pending": pending,
                "items": [
                    source
                    for source in source_items
                    if source["last_run_status"] != "succeeded"
                ],
            },
        }

    def _update_crawled_job(
        self, job_id: str, job: NormalizedJob, *, status: str
    ) -> None:
        self.connection.execute(
            """
            UPDATE jobs
            SET canonical_url = ?, title = ?, location_raw = ?, locations_json = ?,
                recruitment_type = ?, description_raw = ?, content_hash = ?, status = ?,
                missing_count = 0, last_seen_at = ?, last_changed_at = ?, updated_at = ?
            WHERE id = ?
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
                utc_now_iso(),
                job_id,
            ),
        )

    def _ensure_crawl_job_source(
        self,
        company_id: str,
        source_slug: str,
        external_job_id: str,
        created_at: str,
    ) -> str:
        slug = f"{source_slug}:{external_job_id}"
        row = self.connection.execute(
            "SELECT id FROM job_sources WHERE company_id = ? AND slug = ?",
            (company_id, slug),
        ).fetchone()
        if row is not None:
            return row["id"]
        source_id = str(uuid4())
        self.connection.execute(
            """
            INSERT INTO job_sources(id, company_id, slug, source_type, base_url, created_at)
            VALUES (?, ?, ?, 'crawler', NULL, ?)
            """,
            (source_id, company_id, slug, created_at),
        )
        return source_id

    @staticmethod
    def _crawler_snapshot(job: NormalizedJob) -> dict:
        return {
            "external_job_id": job.external_job_id,
            "title": job.title,
            "description_raw": job.description_raw,
            "source_url": job.source_url,
            "locations": job.locations,
            "recruitment_type": job.recruitment_type,
        }

    def _add_version(
        self,
        job_id: str,
        version_number: int,
        content_hash: str,
        snapshot: dict,
        captured_at: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO job_versions(id, job_id, version_number, content_hash, snapshot_json, captured_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                job_id,
                version_number,
                content_hash,
                json.dumps(snapshot, ensure_ascii=False),
                captured_at,
            ),
        )

    def _add_event(
        self,
        job_id: str,
        event_type: str,
        summary: str,
        changed_fields: list[str],
        occurred_at: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO job_events(id, job_id, event_type, summary, changed_fields_json, occurred_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                job_id,
                event_type,
                summary,
                json.dumps(changed_fields),
                occurred_at,
            ),
        )

    @staticmethod
    def _job_row(row: sqlite3.Row) -> dict:
        return {
            "id": row["id"],
            "company": {"slug": row["company_slug"], "name": row["company_name"]},
            "title": row["title"],
            "location_raw": row["location_raw"],
            "locations": json.loads(row["locations_json"]),
            "recruitment_type": row["recruitment_type"],
            "status": row["status"],
            "description_raw": row["description_raw"],
            "responsibilities": json.loads(row["responsibilities_json"]),
            "requirements": json.loads(row["requirements_json"]),
            "source_url": row["canonical_url"],
            "first_seen_at": row["first_seen_at"],
            "last_seen_at": row["last_seen_at"],
            "last_changed_at": row["last_changed_at"],
            "tracking": (
                {
                    "is_favorite": bool(
                        row["tracking_is_favorite"] or 0
                    ),
                    "application_status": (
                        row["tracking_application_status"]
                        or "not_started"
                    ),
                    "version": int(row["tracking_version"] or 0),
                    "updated_at": row["tracking_updated_at"],
                }
                if "tracking_is_favorite" in row.keys()
                else {
                    "is_favorite": False,
                    "application_status": "not_started",
                    "version": 0,
                    "updated_at": None,
                }
            ),
        }
