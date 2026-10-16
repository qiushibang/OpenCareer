"""Transactional orchestration for offline crawler adapters."""

from __future__ import annotations

import json
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Iterator

from ..config import CareerConfig
from ..crawler.adapters import AdapterRegistry, JobAdapter
from ..crawler.normalize import normalize_snapshot
from ..database.migrations import connect, schema_version
from ..database.repository import JobRepository
from ..domain.crawler import CrawlBatchResult, CrawlResult


class CrawlerService:
    def __init__(
        self,
        config: CareerConfig | None = None,
        *,
        adapters: Iterable[JobAdapter] = (),
        clock: Callable[[], datetime] | None = None,
        repository_session: Callable[[], object] | None = None,
    ) -> None:
        self.config = config or CareerConfig.from_env()
        self.adapters = AdapterRegistry(adapters)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._injected_repository_session = repository_session

    def crawl_registered_source(self, source_slug: str, *, dry_run: bool = False) -> CrawlResult:
        return self.crawl(self.adapters.get(source_slug), dry_run=dry_run)

    def crawl_all_sources(
        self,
        *,
        dry_run: bool = True,
        cursor: str | None = None,
        batch_size: int = 1,
    ) -> CrawlBatchResult:
        if not 1 <= batch_size <= 100:
            raise ValueError("batch_size must be between 1 and 100")
        source_slugs = self.adapters.source_slugs()
        start = 0
        if cursor is not None:
            try:
                start = source_slugs.index(cursor) + 1
            except ValueError as exc:
                raise ValueError("cursor is not a registered source") from exc
        selected = source_slugs[start : start + batch_size]
        results = [
            self.crawl_registered_source(source_slug, dry_run=dry_run)
            for source_slug in selected
        ]
        transitions: Counter[str] = Counter()
        for result in results:
            transitions.update(result.transitions)
        failed = sum(result.status == "failed" for result in results)
        has_more = start + len(selected) < len(source_slugs)
        return CrawlBatchResult(
            results=results,
            transitions=dict(transitions),
            completed=len(results) - failed,
            failed=failed,
            total_sources=len(source_slugs),
            has_more=has_more,
            next_cursor=selected[-1] if has_more and selected else None,
        )

    def validate_source_overlap(self, adapter: JobAdapter) -> None:
        snapshots = adapter.fetch_jobs()
        candidate_ids = [snapshot.external_job_id for snapshot in snapshots]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("candidate source returned duplicate external job ids")
        if not self.config.database_path.is_file():
            return
        with self._repository_session() as repository:
            existing_ids = repository.company_external_ids_from_other_sources(
                adapter.descriptor.company_slug,
                exclude_source_slug=adapter.descriptor.source_slug,
            )
        overlap = sorted(set(candidate_ids) & existing_ids)
        if overlap:
            preview = ", ".join(overlap[:10])
            raise ValueError(
                f"candidate source overlaps existing company jobs: {preview}"
            )

    def crawl(self, adapter: JobAdapter, *, dry_run: bool = False) -> CrawlResult:
        if dry_run:
            return self._dry_run(adapter)
        with self._repository_session() as repository:
            source = repository.ensure_crawl_source(adapter.descriptor)
        try:
            snapshots = adapter.fetch_jobs()
        except Exception as exc:
            with self._repository_session() as repository:
                run_id = repository.start_crawl_run(str(source["crawl_source_id"]))
                repository.complete_crawl_run(
                    run_id,
                    status="failed",
                    observed_count=0,
                    error_summary=str(exc),
                )
            return CrawlResult(
                adapter.source_slug,
                run_id,
                "failed",
                {},
                error_summary=str(exc),
            )

        with self._repository_session() as repository:
            return self._commit_snapshots(
                repository,
                adapter,
                snapshots,
                source=source,
            )

    def commit_complete_snapshot(
        self,
        repository,
        adapter: JobAdapter,
        snapshots: list,
        *,
        cycle_id: str,
    ) -> CrawlResult:
        source = repository.ensure_crawl_source(adapter.descriptor)
        result = self._commit_snapshots(
            repository,
            adapter,
            snapshots,
            source=source,
        )
        repository.complete_cycle(
            cycle_id,
            status=(
                "committed"
                if result.status == "succeeded"
                else "failed"
            ),
            error_summary=result.error_summary,
        )
        return result

    def _commit_snapshots(
        self,
        repository,
        adapter: JobAdapter,
        snapshots: list,
        *,
        source: dict,
    ) -> CrawlResult:
        normalized = self._normalize(adapter, snapshots)
        acquire_lock = getattr(
            repository,
            "acquire_source_lock",
            None,
        )
        if callable(acquire_lock) and not acquire_lock(
            adapter.source_slug
        ):
            return CrawlResult(
                adapter.source_slug,
                "locked",
                "failed",
                {},
                error_summary="crawl source is already running",
            )
        run_id = repository.start_crawl_run(
            str(source["crawl_source_id"])
        )
        store_raw_snapshot = getattr(
            repository,
            "store_raw_snapshot",
            None,
        )
        if callable(store_raw_snapshot):
            payload = json.dumps(
                {
                    "descriptor": asdict(adapter.descriptor),
                    "snapshots": [
                        asdict(snapshot) for snapshot in snapshots
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            store_raw_snapshot(
                str(source["crawl_source_id"]),
                run_id,
                url=adapter.descriptor.base_url or "",
                payload=payload,
                fetched_at=self._clock(),
            )
        transitions: Counter[str] = Counter()
        observed_ids = {
            job.external_job_id for job in normalized
        }
        for job in normalized:
            stored = repository.find_crawled_job(
                str(source["crawl_source_id"]),
                job.external_job_id,
            )
            if stored is None:
                repository.create_crawled_job(source, job)
                transitions["created"] += 1
            elif stored["status"] == "inactive":
                repository.reopen_job(
                    stored["id"],
                    job,
                    changed=(
                        stored["content_hash"]
                        != job.content_hash
                    ),
                )
                transitions["reopened"] += 1
            elif stored["content_hash"] == job.content_hash:
                repository.mark_seen(
                    stored["id"],
                    job.observed_at,
                )
                transitions["unchanged"] += 1
            else:
                repository.mark_changed(stored["id"], job)
                transitions["changed"] += 1

        for stored in repository.active_crawled_jobs(
            str(source["crawl_source_id"])
        ):
            if stored["external_job_id"] not in observed_ids:
                transitions[
                    repository.mark_absent(
                        stored,
                        threshold=int(
                            source["missing_threshold"]
                        ),
                    )
                ] += 1

        repository.complete_crawl_run(
            run_id,
            status="succeeded",
            observed_count=len(normalized),
        )
        return CrawlResult(
            adapter.source_slug,
            run_id,
            "succeeded",
            dict(transitions),
        )

    def list_sources(self) -> dict:
        with self._repository_session() as repository:
            persisted = {
                source["slug"]: source
                for source in repository.list_crawl_sources()
            }
            sources = []
            for source_slug in self.adapters.source_slugs():
                descriptor = self.adapters.get(source_slug).descriptor
                source = persisted.pop(source_slug, None)
                sources.append(
                    source
                    or {
                        "slug": source_slug,
                        "name": descriptor.source_name,
                        "missing_threshold": None,
                        "enabled": True,
                    }
                )
                sources[-1]["configured"] = True
            for source in persisted.values():
                source["configured"] = False
                sources.append(source)
            return {"sources": sorted(sources, key=lambda source: source["slug"])}

    def list_recent_job_events(self, *, limit: int = 20) -> dict:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        with self._repository_session() as repository:
            return {
                "events": repository.list_recent_job_events(limit),
                "limit": limit,
            }

    def get_job_radar_digest(
        self,
        *,
        hours: int = 24,
        sample_limit: int = 20,
    ) -> dict:
        if not 1 <= hours <= 168:
            raise ValueError("hours must be between 1 and 168")
        if not 1 <= sample_limit <= 100:
            raise ValueError("sample_limit must be between 1 and 100")
        ended_at = self._clock()
        if ended_at.tzinfo is None or ended_at.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        ended_at = ended_at.astimezone(timezone.utc)
        started_at = ended_at - timedelta(hours=hours)
        started_at_iso = self._format_utc(started_at)

        with self._repository_session() as repository:
            digest = repository.get_job_radar_digest_data(
                occurred_after=started_at_iso,
                sample_limit=sample_limit,
            )
            persisted_source_slugs = {
                source["slug"]
                for source in repository.list_crawl_sources()
            }

        exceptions = {
            source["source_slug"]: source
            for source in digest["sources"]["items"]
        }
        source_items = []
        healthy = 0
        failed = 0
        pending = 0
        for source_slug in self.adapters.source_slugs():
            source = exceptions.get(source_slug)
            if source is not None:
                source_items.append(source)
                if source["last_run_status"] == "failed":
                    failed += 1
                else:
                    pending += 1
            elif source_slug in persisted_source_slugs:
                healthy += 1
            else:
                descriptor = self.adapters.get(source_slug).descriptor
                source_items.append(
                    {
                        "source_slug": source_slug,
                        "source_name": descriptor.source_name,
                        "last_run_status": None,
                        "last_run_at": None,
                        "last_observed_count": None,
                        "last_error": None,
                    }
                )
                pending += 1
        digest["sources"] = {
            "configured": len(self.adapters.source_slugs()),
            "healthy": healthy,
            "failed": failed,
            "pending": pending,
            "items": source_items,
        }
        return {
            "window": {
                "started_at": started_at_iso,
                "ended_at": self._format_utc(ended_at),
                "hours": hours,
            },
            **digest,
        }

    @staticmethod
    def _format_utc(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace(
            "+00:00",
            "Z",
        )

    def _dry_run(self, adapter: JobAdapter) -> CrawlResult:
        try:
            snapshots = adapter.fetch_jobs()
        except Exception as exc:
            return CrawlResult(
                adapter.source_slug,
                "dry-run",
                "failed",
                {},
                error_summary=str(exc),
            )
        normalized = self._normalize(adapter, snapshots)
        external_ids = [job.external_job_id for job in normalized]
        if (
            self._injected_repository_session is None
            and not self.config.database_path.is_file()
        ):
            return CrawlResult(
                adapter.source_slug,
                "dry-run",
                "dry_run",
                {"created": len(normalized)} if normalized else {},
            )
        with self._repository_session() as repository:
            connection = getattr(repository, "connection", None)
            if connection is not None and schema_version(connection) < 2:
                raise RuntimeError("database schema must be migrated before dry run")
            source = repository.find_crawl_source(adapter.source_slug)
            if source is None:
                return CrawlResult(
                    adapter.source_slug,
                    "dry-run",
                    "dry_run",
                    {"created": len(normalized)} if normalized else {},
                )
            transitions: Counter[str] = Counter()
            observed_ids = set(external_ids)
            for job in normalized:
                stored = repository.find_crawled_job(source["id"], job.external_job_id)
                if stored is None:
                    transitions["created"] += 1
                elif stored["status"] == "inactive":
                    transitions["reopened"] += 1
                elif stored["content_hash"] == job.content_hash:
                    transitions["unchanged"] += 1
                else:
                    transitions["changed"] += 1
            for stored in repository.active_crawled_jobs(source["id"]):
                if stored["external_job_id"] not in observed_ids:
                    next_missing = int(stored["missing_count"]) + 1
                    transition = (
                        "offline"
                        if next_missing >= int(source["missing_threshold"])
                        else "missing"
                    )
                    transitions[transition] += 1
            return CrawlResult(adapter.source_slug, "dry-run", "dry_run", dict(transitions))

    @contextmanager
    def _repository_session(self) -> Iterator[object]:
        if self._injected_repository_session is not None:
            with self._injected_repository_session() as repository:
                yield repository
            return
        connection = connect(self.config.database_path)
        try:
            yield JobRepository(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _normalize(adapter: JobAdapter, snapshots: list) -> list:
        normalized = [
            normalize_snapshot(adapter.source_slug, snapshot) for snapshot in snapshots
        ]
        external_ids = [job.external_job_id for job in normalized]
        if len(external_ids) != len(set(external_ids)):
            raise ValueError("adapter returned duplicate external_job_id values")
        return normalized
