"""Safety helpers for PostgreSQL integration-test databases."""

from urllib.parse import urlsplit


_NAMED_TEST_DATABASES = {
    "opencareer_gate",
    "opencareer_gate_fresh",
}


def validated_test_database_url(url: str) -> str:
    database_name = urlsplit(url).path.lstrip("/")
    is_isolated = (
        database_name in _NAMED_TEST_DATABASES
        or database_name.endswith("_test")
    )
    if not is_isolated:
        raise RuntimeError(
            "refusing PostgreSQL tests against database "
            f"{database_name or '<missing>'!r}"
        )
    return url


def cleanup_catalog_test_rows(database) -> int:
    with database.shared_transaction() as connection:
        rows = connection.execute(
            """
            SELECT j.id, js.id, c.id, js.source_type
            FROM catalog.jobs j
            JOIN catalog.job_sources js ON js.id = j.source_id
            JOIN catalog.companies c ON c.id = j.company_id
            WHERE c.slug IN ('api-company', 'flow-company')
               OR c.slug LIKE 'packet-company-%'
               OR c.slug LIKE 'tailored-company-%'
            """
        ).fetchall()
        if not rows:
            return 0
        invalid_source_types = {
            str(row[3])
            for row in rows
            if str(row[3]) not in {"test", "integration"}
        }
        if invalid_source_types:
            raise RuntimeError(
                "refusing to clean non-test Catalog sources: "
                + ", ".join(sorted(invalid_source_types))
            )
        job_ids = [str(row[0]) for row in rows]
        source_ids = sorted({str(row[1]) for row in rows})
        company_ids = sorted({str(row[2]) for row in rows})
        user_ids = [
            str(row[0])
            for row in connection.execute(
                "SELECT id FROM identity.users ORDER BY id"
            ).fetchall()
        ]
        for user_id in user_ids:
            connection.execute(
                "SELECT set_config('app.user_id', %s, true)",
                (user_id,),
            )
            packet_blob_ids = [
                row[0]
                for row in connection.execute(
                    """
                    SELECT blob_id
                    FROM career.application_packets
                    WHERE job_id = ANY(%s) AND blob_id IS NOT NULL
                    """,
                    (job_ids,),
                ).fetchall()
            ]
            export_blob_ids = [
                blob_id
                for row in connection.execute(
                    """
                    SELECT export.docx_blob_id, export.pdf_blob_id
                    FROM career.tailored_resume_exports AS export
                    JOIN career.tailored_resume_drafts AS draft
                      ON draft.user_id = export.user_id
                     AND draft.id = export.draft_id
                    WHERE draft.job_id = ANY(%s)
                    """,
                    (job_ids,),
                ).fetchall()
                for blob_id in row
            ]
            connection.execute(
                """
                DELETE FROM career.interview_turns
                WHERE session_id IN (
                    SELECT id
                    FROM career.interview_sessions
                    WHERE job_id = ANY(%s)
                )
                """,
                (job_ids,),
            )
            connection.execute(
                "DELETE FROM career.interview_sessions "
                "WHERE job_id = ANY(%s)",
                (job_ids,),
            )
            connection.execute(
                """
                DELETE FROM career.tailored_resume_exports
                WHERE draft_id IN (
                    SELECT id
                    FROM career.tailored_resume_drafts
                    WHERE job_id = ANY(%s)
                )
                """,
                (job_ids,),
            )
            for table in (
                "tailored_resume_drafts",
                "application_packets",
                "job_resume_matches",
                "job_application_events",
                "job_tracking",
            ):
                connection.execute(
                    f"DELETE FROM career.{table} "
                    "WHERE job_id = ANY(%s)",
                    (job_ids,),
                )
            blob_ids = [
                *packet_blob_ids,
                *export_blob_ids,
            ]
            if blob_ids:
                connection.execute(
                    "DELETE FROM blob.objects WHERE id = ANY(%s)",
                    (blob_ids,),
                )
        connection.execute(
            "DELETE FROM catalog.job_events WHERE job_id = ANY(%s)",
            (job_ids,),
        )
        connection.execute(
            "DELETE FROM catalog.job_versions WHERE job_id = ANY(%s)",
            (job_ids,),
        )
        connection.execute(
            "DELETE FROM catalog.jobs WHERE id = ANY(%s)",
            (job_ids,),
        )
        connection.execute(
            "DELETE FROM catalog.job_sources WHERE id = ANY(%s)",
            (source_ids,),
        )
        connection.execute(
            "DELETE FROM catalog.companies WHERE id = ANY(%s)",
            (company_ids,),
        )
        return len(job_ids)
