"""Bounded crawler batches backed by persistent staging cycles."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Iterator

from ..config import CareerConfig
from ..crawler.normalize import normalize_snapshot
from ..database.migrations import connect
from ..database.repository import JobRepository
from ..domain.crawler import JobSnapshot, SourceDescriptor
from ..domain.manual_jd import utc_now_iso
from .crawler import CrawlerService


class _ReplayAdapter:
    def __init__(
        self,
        descriptor: SourceDescriptor,
        snapshots: list[JobSnapshot],
    ) -> None:
        self.descriptor = descriptor
        self.source_slug = descriptor.source_slug
        self._snapshots = snapshots

    def fetch_jobs(self) -> list[JobSnapshot]:
        return list(self._snapshots)


class ResumableCrawlerService:
    tail_limit = 40
    tail_batch_size = 5
    def __init__(
        self,
        config: CareerConfig | None = None,
        *,
        max_pages_per_batch: int = 5,
        repository_session=None,
    ) -> None:
        if not 1 <= max_pages_per_batch <= 100:
            raise ValueError(
                "max_pages_per_batch must be between 1 and 100"
            )
        self.config = config or CareerConfig.from_env()
        self.max_pages_per_batch = max_pages_per_batch
        self._injected_repository_session = repository_session

    def run_batch(self, adapter, *, continuation_only: bool = False) -> dict:
        tail_verification: dict[str, int] | None = None
        with self._repository_session() as repository:
            source = repository.ensure_crawl_source(adapter.descriptor)
            if not repository.acquire_source_lock(adapter.source_slug):
                return {
                    "source_slug": adapter.source_slug,
                    "status": "locked",
                    "has_more": True,
                    "processed_pages": 0,
                }
            running = getattr(repository, "get_running_crawl_cycle", lambda _: None)(str(source["crawl_source_id"]))
            if running is None and callable(getattr(adapter, "verify_stale_jobs", None)):
                running = self._resume_recent_tail(repository, str(source["crawl_source_id"]))
            # Between daily refreshes, resume checkpoints without starting a new
            # cycle for sources which have already finished.
            if continuation_only and running is None:
                return {"source_slug": adapter.source_slug, "status": "idle", "has_more": False,
                        "processed_pages": 0}
            cycle = running or repository.get_or_create_crawl_cycle(
                str(source["crawl_source_id"]), adapter.initial_shards(),
            )
            processed_pages = 0
            for shard in repository.list_cycle_shards(cycle["id"]):
                if shard["status"] == "complete":
                    continue
                while processed_pages < self.max_pages_per_batch:
                    remaining = (
                        self.max_pages_per_batch - processed_pages
                    )
                    fetch_pages = getattr(
                        adapter,
                        "fetch_pages",
                        None,
                    )
                    pages = (
                        fetch_pages(
                            shard["filters"],
                            int(shard["next_offset"]),
                            remaining,
                        )
                        if callable(fetch_pages)
                        else [
                            adapter.fetch_page(
                                shard["filters"],
                                int(shard["next_offset"]),
                            )
                        ]
                    )
                    if not pages:
                        raise ValueError(
                            "resumable adapter returned no pages"
                        )
                    for page in pages:
                        if page.total >= 10_000:
                            repository.complete_cycle(
                                cycle["id"],
                                status="degraded",
                                error_summary=(
                                    "ByteDance shard remains at the "
                                    "10,000-job public API cap"
                                ),
                            )
                            return {
                                "source_slug": adapter.source_slug,
                                "cycle_id": cycle["id"],
                                "status": "degraded",
                                "has_more": False,
                                "processed_pages": (
                                    processed_pages + 1
                                ),
                                "observed_unique": len(
                                    repository.list_cycle_jobs(
                                        cycle["id"]
                                    )
                                ),
                                "transitions": {},
                                "error_summary": (
                                    "ByteDance shard remains at the "
                                    "10,000-job public API cap"
                                ),
                            }
                        previous_total = shard.get(
                            "expected_count"
                        )
                        if (
                            previous_total is not None
                            and int(previous_total) != page.total
                            and int(cycle["pass_number"]) >= 2
                        ):
                            pass_number = int(cycle["pass_number"])
                            if pass_number < 3:
                                next_pass = pass_number + 1
                                repository.advance_cycle_pass(
                                    cycle["id"],
                                    next_pass,
                                    reset_expected_counts=True,
                                )
                                return {
                                    "source_slug": adapter.source_slug,
                                    "cycle_id": cycle["id"],
                                    "status": "running",
                                    "has_more": True,
                                    "processed_pages": (
                                        processed_pages + 1
                                    ),
                                    "observed_unique": len(
                                        repository.list_cycle_jobs(
                                            cycle["id"]
                                        )
                                    ),
                                    "pass_number": next_pass,
                                    "transitions": {},
                                }
                        for snapshot in page.jobs:
                            normalized = normalize_snapshot(
                                adapter.source_slug,
                                snapshot,
                            )
                            try:
                                repository.stage_cycle_job(
                                    cycle["id"],
                                    external_job_id=(
                                        snapshot.external_job_id
                                    ),
                                    snapshot=asdict(snapshot),
                                    content_hash=(
                                        normalized.content_hash
                                    ),
                                    pass_number=int(
                                        cycle["pass_number"]
                                    ),
                                    observed_at=(
                                        snapshot.observed_at
                                    ),
                                )
                            except ValueError as exc:
                                repository.complete_cycle(
                                    cycle["id"],
                                    status="degraded",
                                    error_summary=str(exc),
                                )
                                return {
                                    "source_slug": (
                                        adapter.source_slug
                                    ),
                                    "cycle_id": cycle["id"],
                                    "status": "degraded",
                                    "has_more": False,
                                    "processed_pages": (
                                        processed_pages + 1
                                    ),
                                    "observed_unique": len(
                                        repository.list_cycle_jobs(
                                            cycle["id"]
                                        )
                                    ),
                                    "transitions": {},
                                    "error_summary": str(exc),
                                }
                        processed_pages += 1
                        shard_status = (
                            "complete"
                            if page.complete
                            else "running"
                        )
                        repository.checkpoint_cycle_shard(
                            cycle["id"],
                            shard["shard_key"],
                            expected_count=page.total,
                            next_offset=page.next_offset,
                            status=shard_status,
                            last_page_fingerprint=(
                                page.fingerprint
                            ),
                        )
                        shard["expected_count"] = page.total
                        shard["next_offset"] = page.next_offset
                        shard["status"] = shard_status
                        if page.complete:
                            break
                    if shard["status"] == "complete":
                        break
                # Commit a finished category before opening another browser for
                # the next one. Its network failure must not roll back this
                # category's already verified pages.
                if processed_pages:
                    break
            shards = repository.list_cycle_shards(cycle["id"])
            cycle_jobs = repository.list_cycle_jobs(cycle["id"])
            observed_unique = len(cycle_jobs)
            pass_number = int(cycle["pass_number"])
            if not shards or any(
                shard["status"] != "complete" for shard in shards
            ):
                return {
                    "source_slug": adapter.source_slug,
                    "cycle_id": cycle["id"],
                    "status": "running",
                    "processed_pages": processed_pages,
                    "observed_unique": observed_unique,
                    "has_more": True,
                    "pass_number": pass_number,
                }
            converged = all(
                int(row["last_pass"]) == pass_number
                for row in cycle_jobs
            )
            if pass_number == 1:
                repository.advance_cycle_pass(
                    cycle["id"],
                    2,
                )
                return {
                    "source_slug": adapter.source_slug,
                    "cycle_id": cycle["id"],
                    "status": "running",
                    "processed_pages": processed_pages,
                    "observed_unique": observed_unique,
                    "has_more": True,
                    "pass_number": 2,
                }
            if not converged:
                if pass_number >= 3:
                    stale_rows = [
                        row
                        for row in cycle_jobs
                        if int(row["last_pass"]) < pass_number
                    ]
                    verifier = getattr(
                        adapter,
                        "verify_stale_jobs",
                        None,
                    )
                    if (
                        not stale_rows
                        or len(stale_rows) > self.tail_limit
                        or not callable(verifier)
                    ):
                        error_summary = (
                            "ByteDance listing did not converge after "
                            "three passes"
                        )
                        repository.complete_cycle(
                            cycle["id"],
                            status="degraded",
                            error_summary=error_summary,
                        )
                        return {
                            "source_slug": adapter.source_slug,
                            "cycle_id": cycle["id"],
                            "status": "degraded",
                            "processed_pages": processed_pages,
                            "observed_unique": observed_unique,
                            "has_more": False,
                            "pass_number": pass_number,
                            "transitions": {},
                            "error_summary": error_summary,
                        }
                    stale_snapshots = [
                        JobSnapshot(**row["snapshot"])
                        for row in stale_rows[:self.tail_batch_size]
                    ]
                    # Transport failures retain the running checkpoint for the
                    # normal retry loop. Unknown or inconsistent results below
                    # still fail closed and can never publish a catalog.
                    detail_statuses = verifier(stale_snapshots)
                    stale_ids = {
                        snapshot.external_job_id
                        for snapshot in stale_snapshots
                    }
                    if (
                        set(detail_statuses) != stale_ids
                        or any(
                            status not in {"active", "offline"}
                            for status in detail_statuses.values()
                        )
                    ):
                        error_summary = (
                            "ByteDance stale detail verification "
                            "returned unknown results"
                        )
                        repository.complete_cycle(
                            cycle["id"],
                            status="degraded",
                            error_summary=error_summary,
                        )
                        return {
                            "source_slug": adapter.source_slug,
                            "cycle_id": cycle["id"],
                            "status": "degraded",
                            "processed_pages": processed_pages,
                            "observed_unique": observed_unique,
                            "has_more": False,
                            "pass_number": pass_number,
                            "transitions": {},
                            "error_summary": error_summary,
                        }
                    tail_verification = (
                        repository.reconcile_cycle_tail(
                            cycle["id"],
                            active_ids={
                                job_id
                                for job_id, status
                                in detail_statuses.items()
                                if status == "active"
                            },
                            offline_ids={
                                job_id
                                for job_id, status
                                in detail_statuses.items()
                                if status == "offline"
                            },
                            pass_number=pass_number,
                            observed_at=utc_now_iso(),
                        )
                    )
                    cycle_jobs = repository.list_cycle_jobs(
                        cycle["id"]
                    )
                    observed_unique = len(cycle_jobs)
                    if not all(
                        int(row["last_pass"]) == pass_number
                        for row in cycle_jobs
                    ):
                        return {"source_slug": adapter.source_slug, "cycle_id": cycle["id"],
                                "status": "running", "processed_pages": processed_pages,
                                "observed_unique": observed_unique, "has_more": True,
                                "pass_number": pass_number, "tail_verification": tail_verification,
                                "tail_verification_scope": "batch",
                                "tail_remaining": sum(int(row["last_pass"]) < pass_number for row in cycle_jobs)}
                    converged = True
                next_pass = pass_number + 1
                if not converged:
                    repository.advance_cycle_pass(
                        cycle["id"],
                        next_pass,
                    )
                    return {
                        "source_slug": adapter.source_slug,
                        "cycle_id": cycle["id"],
                        "status": "running",
                        "processed_pages": processed_pages,
                        "observed_unique": observed_unique,
                        "has_more": True,
                        "pass_number": next_pass,
                    }
            snapshots = [
                JobSnapshot(**row["snapshot"])
                for row in cycle_jobs
            ]

        with self._repository_session() as repository:
            replay = _ReplayAdapter(
                adapter.descriptor,
                snapshots,
            )
            result = CrawlerService(
                self.config,
            ).commit_complete_snapshot(
                repository,
                replay,
                snapshots,
                cycle_id=cycle["id"],
            )
        return {
            "source_slug": adapter.source_slug,
            "cycle_id": cycle["id"],
            "status": (
                "committed"
                if result.status == "succeeded"
                else "failed"
            ),
            "processed_pages": processed_pages,
            "observed_unique": len(snapshots),
            "has_more": False,
            "transitions": result.transitions,
            "error_summary": result.error_summary,
            **(
                {"tail_verification": tail_verification, "tail_verification_scope": "batch", "tail_remaining": 0}
                if tail_verification is not None
                else {}
            ),
        }

    def _resume_recent_tail(self, repository, source_id: str) -> dict | None:
        """Re-evaluate only a recent cycle stopped by the old tail budget.

        This reopens staging, never commits it. Every remaining row must still
        pass official detail verification. Old or otherwise invalid cycles are
        excluded so archived observations cannot become a fresh publication.
        """
        getter = getattr(repository, "get_latest_crawl_cycle", None)
        if not callable(getter):
            return None
        cycle = getter(source_id)
        if (not cycle or cycle["status"] != "degraded" or int(cycle["pass_number"]) != 3
                or cycle["error_summary"] != "ByteDance listing did not converge after three passes"):
            return None
        shards = repository.list_cycle_shards(cycle["id"])
        rows = repository.list_cycle_jobs(cycle["id"])
        stale = [row for row in rows if int(row["last_pass"]) < 3]
        verified = [row for row in rows if int(row["last_pass"]) == 3]
        if not shards or any(row["status"] != "complete" for row in shards) or not verified or not 1 <= len(stale) <= self.tail_limit:
            return None
        cutoff = datetime.fromisoformat(utc_now_iso().replace("Z", "+00:00")) - timedelta(hours=24)
        try:
            for row in verified:
                stamp = datetime.fromisoformat(row["snapshot"]["observed_at"].replace("Z", "+00:00"))
                if stamp.tzinfo is None or not cutoff <= stamp <= cutoff + timedelta(hours=24):
                    return None
        except (KeyError, TypeError, ValueError):
            return None
        if not repository.resume_bounded_tail(cycle["id"]):
            return None
        return repository.get_running_crawl_cycle(source_id)

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
