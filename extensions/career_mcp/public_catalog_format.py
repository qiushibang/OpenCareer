"""Versioned public-job format and streaming publisher (standard library only).

This file can also run by itself on the export host. It never opens a database.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit

SCHEMA = 1
MAX_MANIFEST_BYTES = 1_000_000
MAX_SOURCE_BYTES = 32_000_000
MAX_EXPANDED_BYTES = 128_000_000
MAX_JOBS = 200_000
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,100}\Z")
SNAPSHOT_PATH = re.compile(r"sources/[a-z0-9][a-z0-9-]{0,100}/[0-9a-f]{64}\.json\.gz\Z")
DESCRIPTOR_FIELDS = {"source_slug", "source_name", "company_slug", "company_name", "scope_key", "adapter_type", "base_url"}
JOB_FIELDS = {"external_job_id", "title", "description_raw", "source_url", "location_raw", "locations",
              "recruitment_type", "status", "first_seen_at", "observed_at", "last_changed_at",
              "responsibilities", "requirements"}


def timestamp(value: object) -> str:
    if not isinstance(value, str) or len(value) > 50:
        raise ValueError("invalid catalog timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("catalog timestamp needs a timezone")
    return value


def public_job(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != JOB_FIELDS:
        raise ValueError("unexpected or private fields in public job")
    for field, limit in (("external_job_id", 300), ("title", 2000), ("description_raw", 200_000), ("source_url", 4096)):
        text = value[field]
        if not isinstance(text, str) or not text.strip() or len(text) > limit or "\x00" in text:
            raise ValueError("invalid public job text")
    url = urlsplit(value["source_url"])
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("invalid official job URL")
    if value["status"] not in {"active", "inactive"}:
        raise ValueError("invalid public job state")
    for field in ("first_seen_at", "observed_at", "last_changed_at"):
        timestamp(value[field])
    for field in ("location_raw", "recruitment_type"):
        if value[field] is not None and (not isinstance(value[field], str) or len(value[field]) > 2000):
            raise ValueError("invalid public job metadata")
    for field in ("locations", "responsibilities", "requirements"):
        items = value[field]
        if not isinstance(items, list) or len(items) > 500 or any(not isinstance(x, str) or len(x) > 100_000 for x in items):
            raise ValueError("invalid public job list")
    return value


def public_descriptor(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != DESCRIPTOR_FIELDS:
        raise ValueError("invalid public source descriptor")
    for key in DESCRIPTOR_FIELDS - {"base_url"}:
        if not isinstance(value[key], str) or not value[key] or len(value[key]) > 500:
            raise ValueError("invalid public source descriptor")
    if not SLUG.fullmatch(value["source_slug"]) or not SLUG.fullmatch(value["company_slug"]):
        raise ValueError("invalid source slug")
    if value["base_url"] is not None and (not isinstance(value["base_url"], str) or not value["base_url"].startswith("https://")):
        raise ValueError("invalid source URL")
    return value


def encoded(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def publish_stream(records, output: Path) -> dict:
    """Publish only after an entire, counted export ends successfully.

    Producers send source/job/end_source records then an end_feed sentinel. Large
    descriptions stream straight into gzip instead of accumulating in host RAM.
    """
    output.mkdir(parents=True, exist_ok=True)
    sources, slugs = [], set()
    current = None
    zipped = raw = None
    temporary = None
    finished = False
    try:
        for record in records:
            if finished or not isinstance(record, dict):
                raise ValueError("invalid catalog stream")
            kind = record.get("kind")
            if kind == "source" and current is None:
                descriptor = public_descriptor(record.get("descriptor"))
                slug = descriptor["source_slug"]
                if slug in slugs or len(slugs) >= 200:
                    raise ValueError("duplicate or excessive sources")
                slugs.add(slug)
                count = record.get("expected_count")
                if type(count) is not int or not 1 <= count <= MAX_JOBS:
                    raise ValueError("invalid source count")
                success_at = record.get("last_success_at")
                if success_at is not None:
                    timestamp(success_at)
                latest = record.get("latest_status", "unknown")
                if latest not in {"succeeded", "failed", "degraded", "running", "unknown"}:
                    latest = "unknown"
                folder = output / "sources" / slug
                folder.mkdir(parents=True, exist_ok=True)
                fd, name = tempfile.mkstemp(prefix=".publishing-", dir=folder)
                os.fchmod(fd, 0o644)
                temporary = Path(name)
                raw = os.fdopen(fd, "wb")
                zipped = gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0)
                zipped.write(b'{"schema_version":1,"source_slug":' + encoded(slug) + b',"jobs":[')
                current = {"descriptor": descriptor, "expected": count, "count": 0, "active": 0,
                           "ids": set(), "expanded": 0, "latest_status": latest, "last_success_at": success_at}
            elif kind == "job" and current is not None:
                item = public_job(record.get("job"))
                if item["external_job_id"] in current["ids"]:
                    raise ValueError("duplicate public job id")
                current["ids"].add(item["external_job_id"])
                content = encoded(item)
                current["expanded"] += len(content) + 1
                if current["expanded"] > MAX_EXPANDED_BYTES or current["count"] >= current["expected"]:
                    raise ValueError("source export exceeded its bounds")
                if current["count"]:
                    zipped.write(b",")
                zipped.write(content)
                current["count"] += 1
                current["active"] += item["status"] == "active"
            elif kind == "end_source" and current is not None:
                if current["count"] != current["expected"]:
                    raise ValueError("incomplete public source export")
                zipped.write(b"]}")
                zipped.close()
                zipped = None
                raw.close()
                raw = None
                size = temporary.stat().st_size
                if size > MAX_SOURCE_BYTES:
                    raise ValueError("compressed source is too large")
                digest = hashlib.sha256()
                with temporary.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(65536), b""):
                        digest.update(chunk)
                checksum = digest.hexdigest()
                relative = f"sources/{current['descriptor']['source_slug']}/{checksum}.json.gz"
                temporary.replace(output / relative)
                temporary = None
                sources.append({"descriptor": current["descriptor"], "path": relative,
                                "sha256": checksum, "size": size, "job_count": current["count"],
                                "active_count": current["active"], "last_success_at": current["last_success_at"],
                                "latest_status": current["latest_status"]})
                current = None
            elif kind == "end_feed" and current is None and sources:
                finished = True
            else:
                raise ValueError("incomplete or out-of-order catalog stream")
        if not finished or current is not None:
            raise ValueError("catalog export was interrupted")
        manifest = {"schema_version": SCHEMA, "generated_at": datetime.now(timezone.utc).isoformat(),
                    "revision": hashlib.sha256(encoded(sources)).hexdigest(), "sources": sources,
                    "job_count": sum(s["job_count"] for s in sources),
                    "active_count": sum(s["active_count"] for s in sources)}
        content = encoded(manifest)
        if len(content) > MAX_MANIFEST_BYTES:
            raise ValueError("catalog manifest is too large")
        fd, name = tempfile.mkstemp(prefix=".manifest-", dir=output)
        os.fchmod(fd, 0o644)
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
        Path(name).replace(output / "manifest.json")
        return manifest
    finally:
        if zipped is not None:
            zipped.close()
        if raw is not None:
            raw.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publish a counted, public-only job export from standard input")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = publish_stream((json.loads(line) for line in sys.stdin if line.strip()), args.output)
    print(json.dumps({k: result[k] for k in ("revision", "job_count", "active_count")}), flush=True)
