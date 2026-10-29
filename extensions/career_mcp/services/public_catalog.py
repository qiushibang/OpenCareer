"""Download the public shared catalog into an isolated local Career database."""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import time
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from ..config import CareerConfig
from ..crawler.adapters import default_adapters, default_resumable_adapters
from ..crawler.normalize import normalize_snapshot
from ..database.migrations import connect
from ..database.repository import JobRepository
from ..domain.crawler import JobSnapshot, SourceDescriptor
from ..public_catalog_format import (MAX_EXPANDED_BYTES, MAX_JOBS, MAX_MANIFEST_BYTES,
                                    MAX_SOURCE_BYTES, SCHEMA, SNAPSHOT_PATH, public_descriptor,
                                    public_job, timestamp)

DEFAULT_FEED_URL = "https://app.opencareer.online/public/jobs/v1/"


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def download(url: str, max_bytes: int) -> bytes:
    request = Request(url, headers={"User-Agent": "OpenCareer-PublicCatalog/1", "Accept-Encoding": "identity"})
    with build_opener(_NoRedirect()).open(request, timeout=30) as response:
        size = response.headers.get("Content-Length")
        if size is not None and int(size) > max_bytes:
            raise ValueError("public feed response is too large")
        content = response.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError("public feed response is too large")
    return content


def _json(content: bytes) -> object:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    return json.loads(content, object_pairs_hook=unique)


def _save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


class PublicCatalogSync:
    def __init__(self, config: CareerConfig, *, base_url: str = DEFAULT_FEED_URL,
                 fetch: Callable[[str, int], bytes] = download,
                 descriptors: list[SourceDescriptor] | None = None) -> None:
        parsed = urlsplit(base_url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or not parsed.path.endswith("/")):
            raise ValueError("public feed needs a fixed HTTPS directory URL")
        self.config, self.base_url, self.fetch = config, base_url, fetch
        if descriptors is None:
            descriptors = [a.descriptor for a in [*default_adapters(), *default_resumable_adapters()]]
        self.descriptors = {d.source_slug: d for d in descriptors}
        self.cache_path = config.data_dir / "public-catalog-cache.json"

    def _manifest(self) -> dict:
        content = self.fetch(self.base_url + "manifest.json", MAX_MANIFEST_BYTES)
        manifest = _json(content)
        if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest["schema_version"] != SCHEMA:
            raise ValueError("unsupported public catalog manifest")
        timestamp(manifest.get("generated_at"))
        sources = manifest.get("sources")
        if not isinstance(sources, list) or not 1 <= len(sources) <= 200:
            raise ValueError("invalid public catalog sources")
        seen = set()
        new_descriptors = {}
        persisted_identities = self._persisted_identities()
        for source in sources:
            if not isinstance(source, dict):
                raise ValueError("invalid catalog source")
            descriptor = public_descriptor(source.get("descriptor"))
            slug = descriptor["source_slug"]
            if slug in seen:
                raise ValueError("duplicate public catalog source")
            seen.add(slug)
            path = source.get("path", "")
            checksum = source.get("sha256", "")
            if (not isinstance(path, str) or not SNAPSHOT_PATH.fullmatch(path)
                    or path != f"sources/{slug}/{checksum}.json.gz"):
                raise ValueError("invalid public catalog download path")
            if type(source.get("size")) is not int or not 0 < source["size"] <= MAX_SOURCE_BYTES:
                raise ValueError("invalid catalog download size")
            if type(source.get("job_count")) is not int or not 0 < source["job_count"] <= MAX_JOBS:
                raise ValueError("invalid catalog job count")
            if type(source.get("active_count")) is not int or not 0 <= source["active_count"] <= source["job_count"]:
                raise ValueError("invalid active catalog count")
            if not isinstance(source.get("latest_status"), str) or source["latest_status"] not in {"succeeded", "failed", "degraded", "running", "unknown"}:
                raise ValueError("invalid upstream catalog status")
            if source.get("last_success_at") is not None:
                timestamp(source["last_success_at"])
            expected = self.descriptors.get(slug)
            if expected is not None and (descriptor["company_slug"] != expected.company_slug
                                         or descriptor["scope_key"] != expected.scope_key):
                raise ValueError("public source identity changed")
            if slug in persisted_identities and persisted_identities[slug] != (descriptor["company_slug"], descriptor["scope_key"]):
                raise ValueError("persisted public source identity changed")
            if expected is None:
                # A shared feed distributes data, never downloadable adapter code.
                # New official sources do not require every client to upgrade.
                new_descriptors[slug] = SourceDescriptor(**descriptor)
        self.descriptors.update(new_descriptors)
        return manifest

    def _persisted_identities(self) -> dict[str, tuple[str, str]]:
        if not self.config.database_path.is_file():
            return {}
        connection = connect(self.config.database_path)
        try:
            return {row[0]: (row[1], row[2]) for row in connection.execute(
                "SELECT s.slug,c.slug,s.scope_key FROM crawl_sources s JOIN companies c ON c.id=s.company_id")}
        except sqlite3.OperationalError as exc:
            if "no such table" in str(exc):
                return {}
            raise
        finally:
            connection.close()

    def _rows(self, source: dict) -> list[dict]:
        content = self.fetch(self.base_url + source["path"], MAX_SOURCE_BYTES)
        if len(content) != source["size"] or hashlib.sha256(content).hexdigest() != source["sha256"]:
            raise ValueError("public catalog checksum does not match")
        with gzip.GzipFile(fileobj=BytesIO(content)) as zipped:
            expanded = zipped.read(MAX_EXPANDED_BYTES + 1)
        if len(expanded) > MAX_EXPANDED_BYTES:
            raise ValueError("public catalog expands beyond its limit")
        snapshot = _json(expanded)
        if (not isinstance(snapshot, dict) or type(snapshot.get("schema_version")) is not int or snapshot["schema_version"] != SCHEMA
                or snapshot.get("source_slug") != source["descriptor"]["source_slug"]):
            raise ValueError("public catalog source does not match")
        rows = snapshot.get("jobs")
        if not isinstance(rows, list) or len(rows) != source["job_count"]:
            raise ValueError("public catalog is incomplete")
        ids = set()
        for row in rows:
            public_job(row)
            if row["external_job_id"] in ids:
                raise ValueError("public catalog has duplicate job ids")
            ids.add(row["external_job_id"])
        if sum(row["status"] == "active" for row in rows) != source["active_count"]:
            raise ValueError("active catalog count does not match snapshot")
        return rows

    def _apply(self, descriptor: SourceDescriptor, rows: list[dict]) -> None:
        connection = connect(self.config.database_path)
        try:
            connection.execute("PRAGMA journal_mode=WAL")
            repository = JobRepository(connection)
            connection.commit()
            connection.execute("BEGIN IMMEDIATE")
            source = repository.ensure_crawl_source(descriptor)
            for row in rows:
                # SQLite range queries use UTC ISO strings. PostgreSQL may export
                # +08:00; preserving that spelling would shift daily event windows.
                row = {**row, **{key: datetime.fromisoformat(row[key].replace("Z", "+00:00"))
                                  .astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                                  for key in ("first_seen_at", "observed_at", "last_changed_at")}}
                snapshot = JobSnapshot(**{key: row[key] for key in ("external_job_id", "title", "description_raw",
                                         "source_url", "observed_at", "location_raw", "recruitment_type")})
                normalized = normalize_snapshot(descriptor.source_slug, snapshot)
                old = repository.find_crawled_job(str(source["crawl_source_id"]), snapshot.external_job_id)
                if old is None:
                    job_id = repository.create_crawled_job(source, normalized)
                    # A first download is not the official first discovery date.
                    connection.execute("UPDATE job_events SET occurred_at=? WHERE job_id=? AND event_type='created'",
                                       (row["first_seen_at"], job_id))
                else:
                    job_id = old["id"]
                    if old["status"] == "inactive" and row["status"] == "active":
                        repository.reopen_job(job_id, normalized, changed=old["content_hash"] != normalized.content_hash)
                    elif old["content_hash"] != normalized.content_hash:
                        repository.mark_changed(job_id, normalized)
                    else:
                        repository.mark_seen(job_id, normalized.observed_at)
                if row["status"] == "inactive" and (old is None or old["status"] != "inactive"):
                    repository._add_event(job_id, "offline", "Official catalog marked this job offline", [], row["last_changed_at"])
                connection.execute(
                    """UPDATE jobs SET status=?, first_seen_at=?, last_seen_at=?, last_changed_at=?,
                       location_raw=?, locations_json=?, responsibilities_json=?, requirements_json=? WHERE id=?""",
                    (row["status"], row["first_seen_at"], row["observed_at"], row["last_changed_at"], row["location_raw"],
                     json.dumps(row["locations"], ensure_ascii=False), json.dumps(row["responsibilities"], ensure_ascii=False),
                     json.dumps(row["requirements"], ensure_ascii=False), job_id),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _present(self, slug: str, expected_count: int) -> bool:
        connection = connect(self.config.database_path)
        try:
            row = connection.execute(
                """SELECT count(*) FROM jobs j JOIN crawl_sources s ON s.id=j.crawl_source_id
                   WHERE s.slug=?""", (slug,),
            ).fetchone()
            return row[0] >= expected_count
        except sqlite3.OperationalError:
            return False
        finally:
            connection.close()

    def run(self) -> dict:
        manifest = self._manifest()
        try:
            cache = json.loads(self.cache_path.read_text()) if self.config.database_path.exists() else {}
        except (OSError, ValueError):
            cache = {}
        # The source URL is part of cache identity: a self-hosted feed is independent.
        if not isinstance(cache, dict) or cache.get("base_url") != self.base_url or not isinstance(cache.get("sources"), dict):
            cache = {"base_url": self.base_url, "sources": {}}
        sources = [{"slug": s["descriptor"]["source_slug"], "name": s["descriptor"]["source_name"],
                    "status": "queued", "checked_at": 0, "last_success_at": s.get("last_success_at"),
                    "upstream_status": s.get("latest_status", "unknown")}
                   for s in manifest["sources"] if s["descriptor"]["source_slug"] in self.descriptors]
        if not sources:
            raise ValueError("public feed contains no supported official sources")
        result = {"ok": True, "mode": "shared", "state": "running", "sources": sources,
                  "completed": 0, "failed": 0, "unchanged": 0, "total_sources": len(sources),
                  "published_at": manifest["generated_at"], "updated_at": time.time()}
        path = self.config.data_dir / "local-job-sync.json"
        _save(path, result)
        entries = {s["descriptor"]["source_slug"]: s for s in manifest["sources"]}
        for progress in sources:
            slug = progress["slug"]
            source = entries[slug]
            progress["status"] = "running"
            _save(path, result)
            try:
                if cache.get("sources", {}).get(slug) == source["sha256"] and self._present(slug, source["job_count"]):
                    result["unchanged"] += 1
                else:
                    rows = self._rows(source)
                    self._apply(self.descriptors[slug], rows)
                    cache.setdefault("sources", {})[slug] = source["sha256"]
                    _save(self.cache_path, cache)
                progress["status"] = "succeeded"
                result["completed"] += 1
            except Exception:
                progress["status"] = "failed"
                result["failed"] += 1
            progress["checked_at"] = time.time()
            result["updated_at"] = time.time()
            _save(path, result)
        result["state"] = "partial" if result["failed"] else "completed"
        _save(path, result)
        return result
