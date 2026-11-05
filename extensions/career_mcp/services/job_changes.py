"""Observed catalog changes, independent of database import/first-seen dates.

A complete source observation establishes a baseline. Only consecutive successful
observations within 48 hours can establish an unseen ID as new. Recovery and
initial imports are backfills. These are observation dates, not publication dates.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Any


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def capture(connection: sqlite3.Connection, source_id: str) -> dict[str, dict[str, Any]]:
    return {row["id"]: dict(row) for row in connection.execute(
        "SELECT id,status,content_hash FROM jobs WHERE crawl_source_id=?", (source_id,))}


def record(connection: sqlite3.Connection, source_id: str, before: dict[str, dict[str, Any]],
           observed_at: str, *, origin: str) -> None:
    previous = connection.execute("SELECT observed_at FROM job_catalog_baselines WHERE source_id=?", (source_id,)).fetchone()
    current = instant(observed_at)
    if previous and current <= instant(previous[0]):
        return
    continuous = previous is not None and (current - instant(previous[0])).total_seconds() <= 48 * 3600
    for row in connection.execute("SELECT id,status,content_hash,last_seen_at,first_seen_at FROM jobs WHERE crawl_source_id=?", (source_id,)):
        old = before.get(row["id"])
        kind = None
        if old is None:
            # An old upstream record arriving late is a backfill even during an
            # otherwise continuous feed. First-seen is provenance here, never the
            # displayed new-event date or a substitute for publication time.
            inside_window = continuous and instant(previous[0]) < instant(row["first_seen_at"]) <= current
            kind = "new" if inside_window and row["status"] == "active" else "backfill"
        elif old["status"] == "inactive" and row["status"] == "active":
            kind = "reopened"
        elif old["content_hash"] != row["content_hash"]:
            kind = "updated"
        if kind:
            connection.execute("INSERT OR IGNORE INTO job_catalog_changes(job_id,source_id,kind,observed_at,window_start,origin) VALUES (?,?,?,?,?,?)",
                               (row["id"], source_id, kind, observed_at, previous[0] if previous else None, origin))
    connection.execute("INSERT INTO job_catalog_baselines(source_id,observed_at,origin) VALUES (?,?,?) ON CONFLICT(source_id) DO UPDATE SET observed_at=excluded.observed_at,origin=excluded.origin",
                       (source_id, observed_at, origin))


def enrich(connection: sqlite3.Connection, jobs: list[dict]) -> None:
    by_id = {job["id"]: job for job in jobs}
    ids = list(by_id)
    rows = []
    for offset in range(0, len(ids), 500):
        batch = ids[offset:offset + 500]
        rows.extend(connection.execute("SELECT job_id,kind,observed_at,window_start,origin FROM job_catalog_changes WHERE job_id IN (" + ",".join("?" for _ in batch) + ") ORDER BY julianday(observed_at),rowid", batch))
    for row in rows:
        job = by_id.get(row["job_id"])
        if job is None:
            continue
        field = {"new": "new_at", "updated": "updated_at", "reopened": "reopened_at", "backfill": "backfilled_at"}[row["kind"]]
        job[field] = row["observed_at"]
        job.update(change_kind=row["kind"], change_at=row["observed_at"],
                   change_evidence={"basis": "complete_source_comparison", "window_start": row["window_start"], "window_end": row["observed_at"], "origin": row["origin"]})


def digest(connection: sqlite3.Connection, *, since: str, until: str, limit: int) -> dict:
    """User-facing events must not reinterpret generic database-created audits."""
    args = (since, until)
    window = "julianday(e.observed_at)>=julianday(?) AND julianday(e.observed_at)<=julianday(?)"
    counts = {row["kind"]: row["count"] for row in connection.execute(
        "SELECT e.kind,COUNT(*) AS count FROM job_catalog_changes e WHERE " + window + " GROUP BY e.kind", args)}
    companies: dict[str, dict] = {}
    for row in connection.execute("SELECT c.slug,c.name,e.kind,COUNT(*) AS count FROM job_catalog_changes e JOIN jobs j ON j.id=e.job_id JOIN companies c ON c.id=j.company_id WHERE " + window + " GROUP BY c.id,e.kind ORDER BY c.slug,e.kind", args):
        company = companies.setdefault(row["slug"], {"company_slug": row["slug"], "company_name": row["name"], "total": 0})
        company[row["kind"]] = row["count"]
        company["total"] += row["count"]
    labels = {"new": "连续完整采集之间新增", "updated": "内容更新", "reopened": "重新开放", "backfill": "历史补录，不是当日新增"}
    samples = [{"job_id": row["job_id"], "company_slug": row["slug"], "company_name": row["name"], "title": row["title"], "event_type": row["kind"], "summary": labels[row["kind"]], "occurred_at": row["observed_at"], "source_url": row["canonical_url"]}
               for row in connection.execute("SELECT e.*,c.slug,c.name,j.title,j.canonical_url FROM job_catalog_changes e JOIN jobs j ON j.id=e.job_id JOIN companies c ON c.id=j.company_id WHERE " + window + " ORDER BY julianday(e.observed_at) DESC,e.rowid DESC LIMIT ?", (*args, limit))]
    return {"total": sum(counts.values()), "by_type": counts, "by_company": list(companies.values()), "samples": samples,
            "basis": "完整来源比较；首次入库审计不计为新增；初始监测基线之前的每日新增无法回溯"}
