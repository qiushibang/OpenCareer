"""Persistence boundary for user-owned job tracking state."""

from __future__ import annotations

import sqlite3

from .migrations import migrate


class JobTrackingRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        migrate(connection)

    def job_exists(self, job_id: str) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone() is not None

    def get(self, job_id: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM job_tracking WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return self._tracking_row(row) if row else None

    def list_events(self, job_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT id, from_status, to_status, occurred_at
            FROM job_application_events
            WHERE job_id = ?
            ORDER BY occurred_at DESC, rowid DESC
            """,
            (job_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def insert(self, tracking: dict) -> None:
        self.connection.execute(
            """
            INSERT INTO job_tracking(
                job_id, is_favorite, favorited_at, application_status,
                applied_at, note, version, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                tracking["job_id"],
                int(tracking["is_favorite"]),
                tracking["favorited_at"],
                tracking["application_status"],
                tracking["applied_at"],
                tracking["note"],
                tracking["created_at"],
                tracking["updated_at"],
            ),
        )

    def update_if_version(
        self,
        tracking: dict,
        expected_version: int,
    ) -> bool:
        cursor = self.connection.execute(
            """
            UPDATE job_tracking
            SET is_favorite = ?, favorited_at = ?,
                application_status = ?, applied_at = ?, note = ?,
                version = version + 1, updated_at = ?
            WHERE job_id = ? AND version = ?
            """,
            (
                int(tracking["is_favorite"]),
                tracking["favorited_at"],
                tracking["application_status"],
                tracking["applied_at"],
                tracking["note"],
                tracking["updated_at"],
                tracking["job_id"],
                expected_version,
            ),
        )
        return cursor.rowcount == 1

    def add_status_event(
        self,
        *,
        event_id: str,
        job_id: str,
        from_status: str,
        to_status: str,
        occurred_at: str,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO job_application_events(
                id, job_id, from_status, to_status, occurred_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                event_id,
                job_id,
                from_status,
                to_status,
                occurred_at,
            ),
        )

    @staticmethod
    def _tracking_row(row: sqlite3.Row) -> dict:
        return {
            "job_id": row["job_id"],
            "is_favorite": bool(row["is_favorite"]),
            "favorited_at": row["favorited_at"],
            "application_status": row["application_status"],
            "applied_at": row["applied_at"],
            "note": row["note"],
            "version": int(row["version"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
