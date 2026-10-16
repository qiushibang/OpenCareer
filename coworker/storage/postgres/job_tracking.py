"""PostgreSQL persistence for tenant-owned job tracking."""

from __future__ import annotations

import json
from uuid import uuid4

from coworker.server.identity import Principal


class PostgresJobTrackingRepository:
    def __init__(self, connection, principal: Principal) -> None:
        self.connection = connection
        self.principal = principal

    def job_exists(self, job_id: str) -> bool:
        return (
            self.connection.execute(
                "SELECT 1 FROM catalog.jobs WHERE id = %s",
                (job_id,),
            ).fetchone()
            is not None
        )

    def get(self, job_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT data, version, created_at, updated_at
            FROM career.job_tracking
            WHERE user_id = %s AND job_id = %s
            """,
            (self.principal.user_id, job_id),
        ).fetchone()
        if row is None:
            return None
        data = dict(row[0] or {})
        return {
            "job_id": job_id,
            "is_favorite": bool(data.get("is_favorite", False)),
            "favorited_at": data.get("favorited_at"),
            "application_status": data.get(
                "application_status",
                "not_started",
            ),
            "applied_at": data.get("applied_at"),
            "note": data.get("note"),
            "version": int(row[1]),
            "created_at": str(row[2]),
            "updated_at": str(row[3]),
        }

    def list_events(self, job_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT id, data, occurred_at
            FROM career.job_application_events
            WHERE user_id = %s AND job_id = %s
            ORDER BY occurred_at DESC, id DESC
            """,
            (self.principal.user_id, job_id),
        ).fetchall()
        return [
            {
                "id": str(row[0]),
                "from_status": (row[1] or {}).get("from_status"),
                "to_status": (row[1] or {}).get("to_status"),
                "occurred_at": str(row[2]),
            }
            for row in rows
        ]

    def insert(self, tracking: dict) -> None:
        self.connection.execute(
            """
            INSERT INTO career.job_tracking(
                user_id, job_id, data, version, created_at, updated_at
            ) VALUES (%s, %s, %s::jsonb, 1, %s, %s)
            """,
            (
                self.principal.user_id,
                tracking["job_id"],
                self._data(tracking),
                tracking["created_at"],
                tracking["updated_at"],
            ),
        )

    def update_if_version(
        self,
        tracking: dict,
        expected_version: int,
    ) -> bool:
        result = self.connection.execute(
            """
            UPDATE career.job_tracking
            SET data = %s::jsonb,
                version = version + 1,
                updated_at = %s
            WHERE user_id = %s
              AND job_id = %s
              AND version = %s
            """,
            (
                self._data(tracking),
                tracking["updated_at"],
                self.principal.user_id,
                tracking["job_id"],
                expected_version,
            ),
        )
        return result.rowcount == 1

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
            INSERT INTO career.job_application_events(
                id, user_id, job_id, data, occurred_at
            ) VALUES (%s, %s, %s, %s::jsonb, %s)
            """,
            (
                event_id or str(uuid4()),
                self.principal.user_id,
                job_id,
                json.dumps(
                    {
                        "from_status": from_status,
                        "to_status": to_status,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                occurred_at,
            ),
        )

    @staticmethod
    def _data(tracking: dict) -> str:
        return json.dumps(
            {
                "is_favorite": bool(tracking["is_favorite"]),
                "favorited_at": tracking["favorited_at"],
                "application_status": tracking["application_status"],
                "applied_at": tracking["applied_at"],
                "note": tracking["note"],
                "updated_at": tracking["updated_at"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
