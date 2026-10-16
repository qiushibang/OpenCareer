"""Application service for manual JD import and job queries."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict

from ..config import CareerConfig
from ..database.migrations import connect
from ..database.repository import JobRepository
from ..domain.job_tracking import APPLICATION_STATUSES
from ..domain.manual_jd import clean_manual_jd, manual_content_hash, parse_manual_jd
from ..domain.models import JobSearchFilters
from .job_tracking import (
    JobTrackingService,
    JobTrackingServiceError,
)


def _preview_hash(preview: dict) -> str:
    payload = {
        "cleaned_text": preview["cleaned_text"],
        "source_url": preview["source_url"],
        "company_name": preview["company_name"],
        "title": preview["title"],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class JobService:
    def __init__(
        self,
        config: CareerConfig | None = None,
        *,
        repository_session: Callable[..., object] | None = None,
        tracking_service: JobTrackingService | None = None,
    ) -> None:
        self.config = config or CareerConfig.from_env()
        self._injected_repository_session = repository_session
        self._tracking_service = tracking_service or JobTrackingService(
            self.config
        )

    def preview_manual_jd(
        self,
        *,
        raw_text: str,
        source_url: str | None = None,
        company_name: str | None = None,
        title: str | None = None,
    ) -> dict:
        if not raw_text or not raw_text.strip():
            raise ValueError("raw_text must not be empty")
        cleaned = clean_manual_jd(raw_text)
        preview = parse_manual_jd(cleaned)
        values = asdict(preview)
        values["raw_text"] = raw_text.strip()
        values["source_url"] = source_url.strip() if source_url else None
        if company_name and company_name.strip():
            values["company_name"] = company_name.strip()
        if title and title.strip():
            values["title"] = title.strip()
        values["missing_fields"] = [
            field
            for field, value in (
                ("title", values["title"]),
                ("company_name", values["company_name"]),
                ("location", values["location_raw"]),
                ("recruitment_type", values["recruitment_type"]),
                ("responsibilities", values["responsibilities"]),
                ("requirements", values["requirements"]),
            )
            if not value
        ]
        return values

    def import_manual_jd(
        self,
        *,
        raw_text: str,
        source_url: str | None = None,
        company_name: str | None = None,
        title: str | None = None,
        preview_hash: str | None = None,
        confirmed: bool = False,
    ) -> dict:
        preview = self.preview_manual_jd(
            raw_text=raw_text,
            source_url=source_url,
            company_name=company_name,
            title=title,
        )
        current_preview_hash = _preview_hash(preview)
        if not confirmed:
            return {
                "confirmation_required": True,
                "preview": preview,
                "preview_hash": current_preview_hash,
            }
        if preview_hash != current_preview_hash:
            raise ValueError("manual JD preview changed; preview it again")
        if not preview["company_name"]:
            raise ValueError("company_name is required to confirm a manual JD")
        with self._repository_session(write=True) as repository:
            company_id, source_id = repository.ensure_manual_source(
                preview["company_name"]
            )
            content_hash = manual_content_hash(preview["cleaned_text"])
            existing = repository.find_by_source_and_hash(source_id, content_hash)
            if existing:
                return {"job_id": existing, "created": False, "duplicate": True}
            parsed = parse_manual_jd(preview["cleaned_text"])
            parsed = parsed.__class__(
                raw_text=preview["raw_text"],
                cleaned_text=preview["cleaned_text"],
                company_name=preview["company_name"],
                title=preview["title"],
                location_raw=preview["location_raw"],
                locations=preview["locations"],
                recruitment_type=preview["recruitment_type"],
                responsibilities=preview["responsibilities"],
                requirements=preview["requirements"],
                missing_fields=preview["missing_fields"],
            )
            canonical_url = preview["source_url"] or f"manual://{content_hash}"
            job_id = repository.create_manual_job(
                company_id=company_id,
                source_id=source_id,
                content_hash=content_hash,
                canonical_url=canonical_url,
                preview=parsed,
            )
            return {"job_id": job_id, "created": True, "duplicate": False}

    def get_job(self, job_id: str) -> dict:
        if not job_id.strip():
            raise ValueError("job_id must not be empty")
        with self._repository_session() as repository:
            detail = repository.get_job(job_id)
            if detail is None:
                raise LookupError("job not found")
            detail["tracking"] = self._tracking_service.get(job_id)
            return detail

    def search_jobs(self, **kwargs: object) -> dict:
        limit = int(kwargs.pop("limit", 20) or 20)
        offset = int(kwargs.pop("offset", 0) or 0)
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        favorite_only = kwargs.pop("favorite_only", False)
        application_status = kwargs.pop("application_status", None)
        if not isinstance(favorite_only, bool):
            raise ValueError("favorite_only must be a boolean")
        if (
            application_status is not None
            and application_status not in APPLICATION_STATUSES
        ):
            raise JobTrackingServiceError(
                "INVALID_STATUS",
                "unsupported application status",
            )
        filters = JobSearchFilters(
            limit=limit,
            offset=offset,
            favorite_only=favorite_only,
            application_status=application_status,
            **kwargs,
        )
        with self._repository_session() as repository:
            jobs, total = repository.search_jobs(filters)
            return {"jobs": jobs, "total": total, "limit": limit, "offset": offset}

    def get_job_filters(self) -> dict:
        with self._repository_session() as repository:
            return repository.get_job_filters()

    @contextmanager
    def _repository_session(self, *, write: bool = False) -> Iterator[object]:
        if self._injected_repository_session is not None:
            with self._injected_repository_session(
                write=write
            ) as repository:
                yield repository
            return
        connection = connect(self.config.database_path)
        try:
            repository = JobRepository(connection)
            if write:
                connection.execute("BEGIN")
            yield repository
            if write:
                connection.commit()
        except Exception:
            if write:
                connection.rollback()
            raise
        finally:
            connection.close()
