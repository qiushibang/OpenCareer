"""PostgreSQL readers and repositories for private Career data."""

from __future__ import annotations

from coworker.server.identity import Principal


class PostgresResumeReader:
    def __init__(self, connection, principal: Principal) -> None:
        self.connection = connection
        self.principal = principal

    def get_interview_input(self, resume_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT data, updated_at
            FROM career.resume_imports
            WHERE user_id = %s
              AND id = %s
              AND COALESCE(data->>'status', 'confirmed') = 'confirmed'
            """,
            (self.principal.user_id, resume_id),
        ).fetchone()
        if row is None:
            return None
        data = dict(row[0] or {})
        sections = data.get("sections")
        if not isinstance(sections, dict):
            return None
        return {
            "id": resume_id,
            "display_name": data.get("display_name") or "未命名简历",
            "target_roles": list(data.get("target_roles") or []),
            "revision_at": data.get("revision_at") or str(row[1]),
            "sections": sections,
        }
