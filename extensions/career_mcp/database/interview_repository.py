"""SQLite persistence for versioned mock interview sessions."""

from __future__ import annotations

import json
import sqlite3

from .migrations import migrate

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


class InterviewRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        migrate(connection)

    def create_session(self, record: dict) -> dict:
        self.connection.execute(
            """
            INSERT INTO interview_sessions(
                id, job_id, resume_import_id, legacy_snapshot_id,
                conversation_id, company, position, difficulty,
                duration_minutes, question_budget, blueprint_json,
                status, phase, version, started_at, ended_at,
                report_path, transcript_path, session_path,
                report_sha256, created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1,
                ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                record["id"],
                record["job_id"],
                record["resume_id"],
                record.get("legacy_snapshot_id"),
                record.get("conversation_id"),
                record.get("company"),
                record["position"],
                record["difficulty"],
                record["duration_minutes"],
                record["question_budget"],
                self._json(record["blueprint"]),
                record["status"],
                record["phase"],
                record.get("started_at"),
                record.get("ended_at"),
                record.get("report_path"),
                record.get("transcript_path"),
                record.get("session_path"),
                record.get("report_sha256"),
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
            "SELECT * FROM interview_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        return self._session(row) if row else None

    def get_session_by_conversation_id(
        self,
        conversation_id: str,
    ) -> dict | None:
        row = self.connection.execute(
            """
            SELECT *
            FROM interview_sessions
            WHERE conversation_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (conversation_id,),
        ).fetchone()
        return self._session(row) if row else None

    def get_active_session(
        self,
        job_id: str,
        resume_id: str,
    ) -> dict | None:
        row = self.connection.execute(
            """
            SELECT *
            FROM interview_sessions
            WHERE job_id = ?
              AND resume_import_id = ?
              AND status IN ('ready', 'in_progress')
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (job_id, resume_id),
        ).fetchone()
        return self._session(row) if row else None

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
        assignments = [f"{key} = ?" for key in changes]
        assignments.append("version = version + 1")
        values = [changes[key] for key in changes]
        cursor = self.connection.execute(
            f"""
            UPDATE interview_sessions
            SET {", ".join(assignments)}
            WHERE id = ? AND version = ?
            """,
            (*values, session_id, expected_version),
        )
        return cursor.rowcount == 1

    def insert_turn(self, record: dict) -> dict:
        self.connection.execute(
            """
            INSERT INTO interview_turns(
                id, session_id, turn_index, question_text,
                question_refs_json, answer_text, evaluation_json,
                next_action, next_reason, question_topic,
                probe_target, probe_dimension, depth_level,
                started_at, answered_at, evaluated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                record["id"],
                record["session_id"],
                record["turn_index"],
                record["question_text"],
                self._json(record["question_refs"]),
                record.get("answer_text"),
                (
                    self._json(record["evaluation"])
                    if record.get("evaluation") is not None
                    else None
                ),
                record.get("next_action"),
                record.get("next_reason"),
                record.get("question_topic"),
                record.get("probe_target"),
                record.get("probe_dimension"),
                record.get("depth_level"),
                record["started_at"],
                record.get("answered_at"),
                record.get("evaluated_at"),
            ),
        )
        row = self.connection.execute(
            "SELECT * FROM interview_turns WHERE id = ?",
            (record["id"],),
        ).fetchone()
        if row is None:
            raise RuntimeError("interview turn was not persisted")
        return self._turn(row)

    def current_turn(self, session_id: str) -> dict | None:
        row = self.connection.execute(
            """
            SELECT *
            FROM interview_turns
            WHERE session_id = ?
            ORDER BY turn_index DESC
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        return self._turn(row) if row else None

    def list_turns(self, session_id: str) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT *
            FROM interview_turns
            WHERE session_id = ?
            ORDER BY turn_index ASC
            """,
            (session_id,),
        ).fetchall()
        return [self._turn(row) for row in rows]

    def delete_unanswered_turn(self, turn_id: str) -> bool:
        cursor = self.connection.execute(
            """
            DELETE FROM interview_turns
            WHERE id = ?
              AND answer_text IS NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM interview_turns later
                  WHERE later.session_id = interview_turns.session_id
                    AND later.turn_index > interview_turns.turn_index
              )
            """,
            (turn_id,),
        )
        return cursor.rowcount == 1

    def answer_turn(
        self,
        turn_id: str,
        *,
        answer_text: str,
        answered_at: str,
    ) -> bool:
        cursor = self.connection.execute(
            """
            UPDATE interview_turns
            SET answer_text = ?, answered_at = ?
            WHERE id = ? AND answer_text IS NULL
            """,
            (answer_text, answered_at, turn_id),
        )
        return cursor.rowcount == 1

    def evaluate_turn(
        self,
        turn_id: str,
        *,
        evaluation: dict,
        next_action: str,
        next_reason: str,
        evaluated_at: str,
    ) -> bool:
        cursor = self.connection.execute(
            """
            UPDATE interview_turns
            SET evaluation_json = ?, next_action = ?,
                next_reason = ?, evaluated_at = ?
            WHERE id = ?
              AND answer_text IS NOT NULL
              AND evaluation_json IS NULL
            """,
            (
                self._json(evaluation),
                next_action,
                next_reason,
                evaluated_at,
                turn_id,
            ),
        )
        return cursor.rowcount == 1

    @staticmethod
    def _session(row: sqlite3.Row) -> dict:
        return {
            "id": str(row["id"]),
            "job_id": str(row["job_id"]),
            "resume_id": str(row["resume_import_id"]),
            "conversation_id": row["conversation_id"],
            "company": row["company"],
            "position": str(row["position"]),
            "difficulty": str(row["difficulty"]),
            "duration_minutes": int(row["duration_minutes"]),
            "question_budget": int(row["question_budget"]),
            "blueprint": json.loads(row["blueprint_json"]),
            "status": str(row["status"]),
            "phase": str(row["phase"]),
            "version": int(row["version"]),
            "started_at": row["started_at"],
            "ended_at": row["ended_at"],
            "report_path": row["report_path"],
            "transcript_path": row["transcript_path"],
            "session_path": row["session_path"],
            "report_sha256": row["report_sha256"],
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }

    @staticmethod
    def _turn(row: sqlite3.Row) -> dict:
        return {
            "id": str(row["id"]),
            "session_id": str(row["session_id"]),
            "turn_index": int(row["turn_index"]),
            "question_text": str(row["question_text"]),
            "question_refs": json.loads(row["question_refs_json"]),
            "answer_text": row["answer_text"],
            "evaluation": (
                json.loads(row["evaluation_json"])
                if row["evaluation_json"] is not None
                else None
            ),
            "next_action": row["next_action"],
            "next_reason": row["next_reason"],
            "question_topic": row["question_topic"],
            "probe_target": row["probe_target"],
            "probe_dimension": row["probe_dimension"],
            "depth_level": (
                int(row["depth_level"])
                if row["depth_level"] is not None
                else None
            ),
            "started_at": str(row["started_at"]),
            "answered_at": row["answered_at"],
            "evaluated_at": row["evaluated_at"],
        }

    @staticmethod
    def _json(value: object) -> str:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
