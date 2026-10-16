"""PostgreSQL persistence for tenant-owned mock interviews."""

from __future__ import annotations

import json

from coworker.server.identity import Principal

_SESSION_UPDATE_FIELDS = {
    "conversation_id",
    "status",
    "phase",
    "started_at",
    "ended_at",
    "report_path",
    "transcript_path",
    "session_path",
    "report_sha256",
    "updated_at",
}


class PostgresInterviewRepository:
    def __init__(self, connection, principal: Principal) -> None:
        self.connection = connection
        self.principal = principal

    def create_session(self, record: dict) -> dict:
        if record.get("conversation_id") is not None:
            self.connection.execute(
                """
                INSERT INTO agent.conversations(id, user_id, metadata)
                VALUES (%s, %s, '{"agent":"career"}'::jsonb)
                ON CONFLICT (user_id, id) DO UPDATE
                SET metadata = CASE
                    WHEN agent.conversations.metadata ? 'agent'
                    THEN agent.conversations.metadata
                    ELSE agent.conversations.metadata || EXCLUDED.metadata
                END
                """,
                (
                    record["conversation_id"],
                    self.principal.user_id,
                ),
            )
        data = {
            key: value
            for key, value in record.items()
            if key
            not in {
                "id",
                "job_id",
                "resume_id",
                "conversation_id",
                "created_at",
                "updated_at",
            }
        }
        self.connection.execute(
            """
            INSERT INTO career.interview_sessions(
                id, user_id, job_id, resume_import_id,
                conversation_id, data, version, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, 1, %s, %s)
            """,
            (
                record["id"],
                self.principal.user_id,
                record["job_id"],
                record["resume_id"],
                record.get("conversation_id"),
                self._json(data),
                record["created_at"],
                record["updated_at"],
            ),
        )
        created = self.get_session(record["id"])
        if created is None:
            raise RuntimeError("interview session was not persisted")
        return created

    def get_session(self, session_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT id, job_id, resume_import_id, conversation_id,
                   data, version, created_at, updated_at
            FROM career.interview_sessions
            WHERE user_id = %s AND id = %s
            """,
            (self.principal.user_id, session_id),
        ).fetchone()
        return self._session(row) if row is not None else None

    def get_session_by_conversation_id(
        self,
        conversation_id: str,
    ) -> dict | None:
        row = self.connection.execute(
            """
            SELECT id, job_id, resume_import_id, conversation_id,
                   data, version, created_at, updated_at
            FROM career.interview_sessions
            WHERE user_id = %s AND conversation_id = %s
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (self.principal.user_id, conversation_id),
        ).fetchone()
        return self._session(row) if row is not None else None

    def get_active_session(
        self,
        job_id: str,
        resume_id: str,
    ) -> dict | None:
        row = self.connection.execute(
            """
            SELECT id, job_id, resume_import_id, conversation_id,
                   data, version, created_at, updated_at
            FROM career.interview_sessions
            WHERE user_id = %s
              AND job_id = %s
              AND resume_import_id = %s
              AND data->>'status' IN ('ready', 'in_progress')
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (self.principal.user_id, job_id, resume_id),
        ).fetchone()
        return self._session(row) if row is not None else None

    def update_session_if_version(
        self,
        session_id: str,
        expected_version: int,
        **changes: object,
    ) -> bool:
        if (
            not changes
            or any(key not in _SESSION_UPDATE_FIELDS for key in changes)
        ):
            raise ValueError("interview session update fields are invalid")
        assignments = ["version = version + 1"]
        params: list[object] = []
        conversation_marker = object()
        conversation_id = changes.pop(
            "conversation_id",
            conversation_marker,
        )
        updated_at = changes.pop("updated_at", None)
        if conversation_id is not conversation_marker:
            assignments.append("conversation_id = %s")
            params.append(conversation_id)
        if changes:
            assignments.append("data = data || %s::jsonb")
            params.append(self._json(changes))
        if updated_at is not None:
            assignments.append("updated_at = %s")
            params.append(updated_at)
        result = self.connection.execute(
            f"""
            UPDATE career.interview_sessions
            SET {", ".join(assignments)}
            WHERE user_id = %s AND id = %s AND version = %s
            """,
            (
                *params,
                self.principal.user_id,
                session_id,
                expected_version,
            ),
        )
        return result.rowcount == 1

    def insert_turn(self, record: dict) -> dict:
        data = {
            key: value
            for key, value in record.items()
            if key
            not in {
                "id",
                "session_id",
                "turn_index",
                "started_at",
            }
        }
        self.connection.execute(
            """
            INSERT INTO career.interview_turns(
                id, user_id, session_id, turn_index, data, created_at
            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            """,
            (
                record["id"],
                self.principal.user_id,
                record["session_id"],
                record["turn_index"],
                self._json(data),
                record["started_at"],
            ),
        )
        row = self.connection.execute(
            """
            SELECT id, session_id, turn_index, data, created_at
            FROM career.interview_turns
            WHERE user_id = %s AND id = %s
            """,
            (self.principal.user_id, record["id"]),
        ).fetchone()
        if row is None:
            raise RuntimeError("interview turn was not persisted")
        return self._turn(row)

    def current_turn(self, session_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT id, session_id, turn_index, data, created_at
            FROM career.interview_turns
            WHERE user_id = %s AND session_id = %s
            ORDER BY turn_index DESC
            LIMIT 1
            """,
            (self.principal.user_id, session_id),
        ).fetchone()
        return self._turn(row) if row is not None else None

    def list_turns(self, session_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT id, session_id, turn_index, data, created_at
            FROM career.interview_turns
            WHERE user_id = %s AND session_id = %s
            ORDER BY turn_index ASC
            """,
            (self.principal.user_id, session_id),
        ).fetchall()
        return [self._turn(row) for row in rows]

    def delete_unanswered_turn(self, turn_id: str) -> bool:
        result = self.connection.execute(
            """
            DELETE FROM career.interview_turns current
            WHERE current.user_id = %s
              AND current.id = %s
              AND current.data->'answer_text' = 'null'::jsonb
              AND NOT EXISTS (
                  SELECT 1
                  FROM career.interview_turns later
                  WHERE later.user_id = current.user_id
                    AND later.session_id = current.session_id
                    AND later.turn_index > current.turn_index
              )
            """,
            (self.principal.user_id, turn_id),
        )
        return result.rowcount == 1

    def answer_turn(
        self,
        turn_id: str,
        *,
        answer_text: str,
        answered_at: str,
    ) -> bool:
        result = self.connection.execute(
            """
            UPDATE career.interview_turns
            SET data = data || %s::jsonb
            WHERE user_id = %s
              AND id = %s
              AND data->'answer_text' = 'null'::jsonb
            """,
            (
                self._json(
                    {
                        "answer_text": answer_text,
                        "answered_at": answered_at,
                    }
                ),
                self.principal.user_id,
                turn_id,
            ),
        )
        return result.rowcount == 1

    def evaluate_turn(
        self,
        turn_id: str,
        *,
        evaluation: dict,
        next_action: str,
        next_reason: str,
        evaluated_at: str,
    ) -> bool:
        result = self.connection.execute(
            """
            UPDATE career.interview_turns
            SET data = data || %s::jsonb
            WHERE user_id = %s
              AND id = %s
              AND data->'answer_text' <> 'null'::jsonb
              AND data->'evaluation' = 'null'::jsonb
            """,
            (
                self._json(
                    {
                        "evaluation": evaluation,
                        "next_action": next_action,
                        "next_reason": next_reason,
                        "evaluated_at": evaluated_at,
                    }
                ),
                self.principal.user_id,
                turn_id,
            ),
        )
        return result.rowcount == 1

    @staticmethod
    def _session(row) -> dict:
        data = dict(row[4] or {})
        return {
            **data,
            "id": str(row[0]),
            "job_id": str(row[1]),
            "resume_id": str(row[2]),
            "conversation_id": row[3],
            "version": int(row[5]),
            "created_at": str(row[6]),
            "updated_at": str(row[7]),
        }

    @staticmethod
    def _turn(row) -> dict:
        data = dict(row[3] or {})
        return {
            **data,
            "id": str(row[0]),
            "session_id": str(row[1]),
            "turn_index": int(row[2]),
            "started_at": str(row[4]),
        }

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
