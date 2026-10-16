"""Transactional service for job favorites and application progress."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from ..config import CareerConfig
from ..database.job_tracking_repository import JobTrackingRepository
from ..database.migrations import connect
from ..domain.job_tracking import (
    APPLIED_STATUSES,
    TrackingValidationError,
    normalize_tracking_patch,
)


class JobTrackingServiceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class JobTrackingService:
    def __init__(
        self,
        config: CareerConfig | None = None,
        *,
        clock=None,
        repository_session: Callable[..., object] | None = None,
    ) -> None:
        self.config = config or CareerConfig.from_env()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._injected_repository_session = repository_session

    def get(self, job_id: str) -> dict:
        normalized_id = self._job_id(job_id)
        with self._repository_session() as repository:
            if not repository.job_exists(normalized_id):
                raise JobTrackingServiceError(
                    "JOB_NOT_FOUND",
                    "job not found",
                )
            current = repository.get(normalized_id)
            result = current or self._default(normalized_id)
            return {
                **result,
                "events": repository.list_events(normalized_id),
            }

    def update(self, job_id: str, patch: object) -> dict:
        normalized_id = self._job_id(job_id)
        try:
            values = normalize_tracking_patch(patch)
        except TrackingValidationError as exc:
            raise JobTrackingServiceError(exc.code, str(exc)) from exc

        with self._repository_session(write=True) as repository:
            if not repository.job_exists(normalized_id):
                raise JobTrackingServiceError(
                    "JOB_NOT_FOUND",
                    "job not found",
                )
            current = repository.get(normalized_id)
            base = current or self._default(normalized_id)
            if values["expected_version"] != base["version"]:
                raise JobTrackingServiceError(
                    "VERSION_CONFLICT",
                    "tracking record changed",
                )

            favorite = values.get(
                "is_favorite",
                base["is_favorite"],
            )
            status = values.get(
                "application_status",
                base["application_status"],
            )
            note = values.get("note", base["note"])
            changed = (
                favorite != base["is_favorite"]
                or status != base["application_status"]
                or note != base["note"]
            )
            if not changed:
                return {
                    **base,
                    "events": repository.list_events(normalized_id),
                }

            now = self._iso(self._clock())
            tracking = {
                **base,
                "is_favorite": favorite,
                "favorited_at": (
                    (base["favorited_at"] or now)
                    if favorite
                    else None
                ),
                "application_status": status,
                "applied_at": (
                    base["applied_at"]
                    or (now if status in APPLIED_STATUSES else None)
                ),
                "note": note,
                "created_at": base["created_at"] or now,
                "updated_at": now,
            }
            if current is None:
                repository.insert(tracking)
            elif not repository.update_if_version(
                tracking,
                values["expected_version"],
            ):
                raise JobTrackingServiceError(
                    "VERSION_CONFLICT",
                    "tracking record changed",
                )
            if status != base["application_status"]:
                repository.add_status_event(
                    event_id=str(uuid4()),
                    job_id=normalized_id,
                    from_status=base["application_status"],
                    to_status=status,
                    occurred_at=now,
                )
            saved = repository.get(normalized_id)
            if saved is None:
                raise RuntimeError("tracking record was not persisted")
            result = {
                **saved,
                "events": repository.list_events(normalized_id),
            }
            return result

    @contextmanager
    def _repository_session(
        self,
        *,
        write: bool = False,
    ) -> Iterator[object]:
        if self._injected_repository_session is not None:
            with self._injected_repository_session(
                write=write
            ) as repository:
                yield repository
            return
        connection = connect(self.config.database_path)
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield JobTrackingRepository(connection)
            if write:
                connection.commit()
        except Exception:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _job_id(job_id: str) -> str:
        if not isinstance(job_id, str) or not job_id.strip():
            raise JobTrackingServiceError(
                "INVALID_INPUT",
                "job_id must be a non-empty string",
            )
        return job_id.strip()

    @staticmethod
    def _default(job_id: str) -> dict:
        return {
            "job_id": job_id,
            "is_favorite": False,
            "favorited_at": None,
            "application_status": "not_started",
            "applied_at": None,
            "note": None,
            "version": 0,
            "created_at": None,
            "updated_at": None,
        }

    @staticmethod
    def _iso(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return (
            value.astimezone(timezone.utc)
            .isoformat(timespec="seconds")
            .replace("+00:00", "Z")
        )
