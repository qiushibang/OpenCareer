"""Pure normalization from an adapter snapshot to a crawler candidate."""

from __future__ import annotations

from hashlib import sha256

from ..domain.crawler import JobSnapshot, NormalizedJob
from ..domain.locations import split_job_locations


def normalize_snapshot(source_slug: str, snapshot: JobSnapshot) -> NormalizedJob:
    """Create a stable candidate identity and content hash."""
    title = snapshot.title.strip()
    description = snapshot.description_raw.strip()
    content_hash = sha256(f"{title}\n{description}".encode("utf-8")).hexdigest()
    location = snapshot.location_raw.strip() if snapshot.location_raw else None
    return NormalizedJob(
        identity=f"{source_slug}:{snapshot.external_job_id}",
        external_job_id=snapshot.external_job_id,
        title=title,
        description_raw=description,
        source_url=snapshot.source_url,
        observed_at=snapshot.observed_at,
        locations=split_job_locations([location] if location else []),
        recruitment_type=snapshot.recruitment_type,
        content_hash=content_hash,
    )
