"""Tenant-scoped PostgreSQL automation tasks and run history."""

from __future__ import annotations

import json
from typing import Optional

from coworker.automation.models import ScheduledTask, TaskRun
from coworker.automation.store import compute_next_run
from coworker.server.identity import Principal


class PostgresAutomationStore:
    def __init__(self, database, principal: Principal) -> None:
        self._database = database
        self._principal = principal

    def save(self, task: ScheduledTask) -> ScheduledTask:
        from coworker.automation.store import _epoch_now

        task.updated_at = _epoch_now()
        task.next_run = compute_next_run(task) if task.enabled else None
        with self._database.transaction(self._principal) as connection:
            self._ensure_user(connection)
            connection.execute(
                """
                INSERT INTO agent.automations(
                    id, user_id, enabled, next_run, data
                ) VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (user_id, id)
                DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    next_run = EXCLUDED.next_run,
                    data = EXCLUDED.data,
                    updated_at = now()
                """,
                (
                    task.id,
                    self._principal.user_id,
                    task.enabled,
                    task.next_run,
                    json.dumps(task.to_dict(), ensure_ascii=False),
                ),
            )
        return task

    def get(self, task_id: str) -> Optional[ScheduledTask]:
        with self._database.transaction(self._principal) as connection:
            row = connection.execute(
                """
                SELECT data
                FROM agent.automations
                WHERE user_id = %s AND id = %s
                """,
                (self._principal.user_id, task_id),
            ).fetchone()
        return _task(row[0]) if row is not None else None

    def list(self) -> list[ScheduledTask]:
        with self._database.transaction(self._principal) as connection:
            rows = connection.execute(
                """
                SELECT data
                FROM agent.automations
                WHERE user_id = %s
                ORDER BY next_run IS NULL, next_run
                """,
                (self._principal.user_id,),
            ).fetchall()
        return [_task(row[0]) for row in rows]

    def delete(self, task_id: str) -> bool:
        with self._database.transaction(self._principal) as connection:
            connection.execute(
                """
                DELETE FROM agent.automation_runs
                WHERE user_id = %s AND automation_id = %s
                """,
                (self._principal.user_id, task_id),
            )
            row = connection.execute(
                """
                DELETE FROM agent.automations
                WHERE user_id = %s AND id = %s
                RETURNING id
                """,
                (self._principal.user_id, task_id),
            ).fetchone()
        return row is not None

    def due(self, *, now: Optional[float] = None) -> list[ScheduledTask]:
        if now is None:
            from coworker.automation.store import _epoch_now

            now = _epoch_now()
        with self._database.transaction(self._principal) as connection:
            rows = connection.execute(
                """
                SELECT data
                FROM agent.automations
                WHERE user_id = %s
                  AND enabled = TRUE
                  AND next_run IS NOT NULL
                  AND next_run <= %s
                ORDER BY next_run
                """,
                (self._principal.user_id, now),
            ).fetchall()
        return [_task(row[0]) for row in rows]

    def add_run(self, run: TaskRun) -> TaskRun:
        with self._database.transaction(self._principal) as connection:
            connection.execute(
                """
                INSERT INTO agent.automation_runs(
                    id, user_id, automation_id, data
                ) VALUES (%s, %s, %s, %s::jsonb)
                ON CONFLICT (user_id, id)
                DO UPDATE SET data = EXCLUDED.data
                """,
                (
                    run.run_id,
                    self._principal.user_id,
                    run.task_id,
                    json.dumps(run.to_dict(), ensure_ascii=False),
                ),
            )
        return run

    def find_run(self, run_id: str) -> Optional[TaskRun]:
        with self._database.transaction(self._principal) as connection:
            row = connection.execute(
                """
                SELECT data
                FROM agent.automation_runs
                WHERE user_id = %s AND id = %s
                """,
                (self._principal.user_id, run_id),
            ).fetchone()
        return _run(row[0]) if row is not None else None

    def task_for_run_session(
        self,
        session_id: str,
    ) -> Optional[ScheduledTask]:
        if not session_id.startswith("__run__"):
            return None
        run = self.find_run(session_id[len("__run__") :])
        return self.get(run.task_id) if run is not None else None

    def runs(self, task_id: str, *, limit: int = 50) -> list[TaskRun]:
        with self._database.transaction(self._principal) as connection:
            rows = connection.execute(
                """
                SELECT data
                FROM agent.automation_runs
                WHERE user_id = %s AND automation_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (self._principal.user_id, task_id, limit),
            ).fetchall()
        return [_run(row[0]) for row in rows]

    def close(self) -> None:
        return None

    def _ensure_user(self, connection) -> None:
        connection.execute(
            """
            INSERT INTO identity.users(id)
            VALUES (%s)
            ON CONFLICT (id) DO NOTHING
            """,
            (self._principal.user_id,),
        )


def _json_object(value) -> dict:
    if isinstance(value, str):
        value = json.loads(value)
    return dict(value) if isinstance(value, dict) else {}


def _task(value) -> ScheduledTask:
    return ScheduledTask.from_dict(_json_object(value))


def _run(value) -> TaskRun:
    return TaskRun.from_dict(_json_object(value))
