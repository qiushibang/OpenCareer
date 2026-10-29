"""Read-only PostgreSQL public catalog export; standalone on the existing server.

No application boot, migration, Redis, model client or private table is involved.
The host publisher receives counted JSON lines, never a database dump.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
import json
import os
import re
import sys

PUBLIC_ONLY = "j.visibility_user_id IS NULL AND j.crawl_source_id IS NOT NULL AND js.source_type = 'crawler'"
SOURCE_QUERY = f"""
SELECT cs.id, cs.slug, cs.name, c.slug, c.name, cs.scope_key, cs.adapter_type, cs.base_url,
       count(j.id),
       (SELECT max(r.completed_at) FROM catalog.crawl_runs r WHERE r.source_id=cs.id AND r.status='succeeded'),
       (SELECT r.status FROM catalog.crawl_runs r WHERE r.source_id=cs.id ORDER BY r.started_at DESC LIMIT 1)
FROM catalog.crawl_sources cs
JOIN catalog.companies c ON c.id=cs.company_id
JOIN catalog.jobs j ON j.crawl_source_id=cs.id
JOIN catalog.job_sources js ON js.id=j.source_id
WHERE {PUBLIC_ONLY} AND cs.slug=ANY(%s)
GROUP BY cs.id,c.id
ORDER BY cs.slug
"""
JOB_QUERY = f"""
SELECT j.external_job_id,j.title,j.description_raw,j.canonical_url,j.location_raw,j.locations,
       j.recruitment_type,j.status,j.first_seen_at,j.last_seen_at,j.last_changed_at,
       j.responsibilities,j.requirements
FROM catalog.jobs j JOIN catalog.job_sources js ON js.id=j.source_id
WHERE {PUBLIC_ONLY} AND j.crawl_source_id=%s
ORDER BY j.external_job_id
"""
JOB_FIELDS = ("external_job_id", "title", "description_raw", "source_url", "location_raw", "locations",
              "recruitment_type", "status", "first_seen_at", "observed_at", "last_changed_at",
              "responsibilities", "requirements")


def stream_public_catalog(connection, slugs: list[str]):
    """The caller must provide a read-only repeatable-read transaction."""
    if not slugs or any(not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,100}", slug) for slug in slugs):
        raise ValueError("only registered official source slugs are accepted")
    sources = connection.execute(SOURCE_QUERY, (slugs,)).fetchall()
    if not sources:
        raise ValueError("public catalog is empty; existing publication must remain")
    for index, row in enumerate(sources):
        descriptor = dict(zip(("source_slug", "source_name", "company_slug", "company_name", "scope_key", "adapter_type", "base_url"), row[1:8]))
        yield {"kind": "source", "descriptor": descriptor, "expected_count": row[8],
               "last_success_at": row[9], "latest_status": row[10] or "unknown"}
        # A named cursor bounds memory for large mainland job catalogs.
        with connection.cursor(name=f"public_job_export_{index}") as cursor:
            cursor.execute(JOB_QUERY, (row[0],))
            while True:
                rows = cursor.fetchmany(200)
                if not rows:
                    break
                for job in rows:
                    yield {"kind": "job", "job": dict(zip(JOB_FIELDS, job))}
        yield {"kind": "end_source"}
    yield {"kind": "end_feed"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Export only official public catalog fields as JSON lines")
    parser.add_argument("--slugs", required=True, help="Comma-separated registered source slugs")
    args = parser.parse_args()
    import psycopg
    def json_value(value):
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        raise TypeError("unexpected database type in public export")
    with psycopg.connect(os.environ["DATABASE_URL"], application_name="opencareer_public_catalog_export") as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        connection.execute("SET LOCAL statement_timeout='30s'")
        for record in stream_public_catalog(connection, args.slugs.split(",")):
            print(json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=json_value), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
