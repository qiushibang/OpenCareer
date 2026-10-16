import json
from contextlib import contextmanager
from datetime import datetime, timezone

from coworker.automation import Schedule, ScheduledTask, TaskRun
from coworker.server.identity import Principal
from coworker.storage.postgres.automation_store import (
    PostgresAutomationStore,
)


class _Rows:
    def __init__(self, rows: list[tuple] = ()) -> None:
        self.rows = list(rows)
        self.rowcount = len(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _State:
    def __init__(self) -> None:
        self.tasks: dict[tuple[str, str], dict] = {}
        self.runs: dict[tuple[str, str], dict] = {}


class _Connection:
    def __init__(self, state: _State, user_id: str) -> None:
        self.state = state
        self.user_id = user_id

    def execute(self, sql: str, params: tuple = ()) -> _Rows:
        compact = " ".join(sql.split())
        if compact.startswith("INSERT INTO identity.users"):
            return _Rows()
        if compact.startswith("INSERT INTO agent.automations"):
            task_id, user_id, enabled, next_run, data = params
            self.state.tasks[(user_id, task_id)] = {
                "enabled": enabled,
                "next_run": next_run,
                "data": json.loads(data),
            }
            return _Rows()
        if compact.startswith("SELECT data FROM agent.automations"):
            rows = [
                value
                for (user_id, _), value in self.state.tasks.items()
                if user_id == params[0]
            ]
            if "AND id = %s" in compact:
                value = self.state.tasks.get((params[0], params[1]))
                rows = [value] if value is not None else []
            if "enabled = TRUE" in compact:
                now = params[1]
                rows = [
                    value
                    for value in rows
                    if value["enabled"]
                    and value["next_run"] is not None
                    and value["next_run"] <= now
                ]
            rows.sort(
                key=lambda value: (
                    value["next_run"] is None,
                    value["next_run"] or 0,
                )
            )
            return _Rows([(value["data"],) for value in rows])
        if compact.startswith("DELETE FROM agent.automation_runs"):
            user_id, task_id = params
            for key, value in list(self.state.runs.items()):
                if key[0] == user_id and value["task_id"] == task_id:
                    self.state.runs.pop(key)
            return _Rows()
        if compact.startswith("DELETE FROM agent.automations"):
            user_id, task_id = params
            existed = self.state.tasks.pop((user_id, task_id), None)
            return _Rows([(task_id,)] if existed is not None else [])
        if compact.startswith("INSERT INTO agent.automation_runs"):
            run_id, user_id, task_id, data = params
            self.state.runs[(user_id, run_id)] = {
                "task_id": task_id,
                "data": json.loads(data),
            }
            return _Rows()
        if compact.startswith("SELECT data FROM agent.automation_runs"):
            rows = [
                value
                for (user_id, _), value in self.state.runs.items()
                if user_id == params[0]
            ]
            if "AND id = %s" in compact:
                value = self.state.runs.get((params[0], params[1]))
                rows = [value] if value is not None else []
            if "AND automation_id = %s" in compact:
                rows = [
                    value
                    for value in rows
                    if value["task_id"] == params[1]
                ][: params[2]]
            return _Rows([(value["data"],) for value in rows])
        raise AssertionError(f"unexpected SQL: {compact}")


class _Database:
    def __init__(self) -> None:
        self.state = _State()

    @contextmanager
    def transaction(self, principal: Principal):
        yield _Connection(self.state, principal.user_id)


def test_postgres_automation_store_persists_due_tasks_and_runs() -> None:
    database = _Database()
    alice = PostgresAutomationStore(database, Principal("alice", "test"))
    fire_at = datetime(2030, 1, 1, tzinfo=timezone.utc)
    task = ScheduledTask(
        title="Daily radar",
        instructions="Refresh jobs",
        schedule=Schedule(kind="once", fire_at=fire_at.isoformat()),
        workspace="/repo",
    )

    alice.save(task)

    assert alice.get(task.id) == task
    assert alice.list() == [task]
    assert alice.due(now=fire_at.timestamp() - 1) == []
    assert alice.due(now=fire_at.timestamp() + 1) == [task]

    run = alice.add_run(TaskRun(task_id=task.id))
    assert alice.find_run(run.run_id) == run
    assert alice.task_for_run_session(run.session_id) == task
    assert alice.runs(task.id) == [run]

    assert alice.delete(task.id)
    assert alice.get(task.id) is None
    assert alice.find_run(run.run_id) is None


def test_postgres_automation_store_is_tenant_scoped() -> None:
    database = _Database()
    alice = PostgresAutomationStore(database, Principal("alice", "test"))
    bob = PostgresAutomationStore(database, Principal("bob", "test"))
    task = ScheduledTask(
        title="Private",
        instructions="Do private work",
        schedule=Schedule(kind="cron", cron="0 4 * * *"),
        workspace="/repo",
    )

    alice.save(task)

    assert bob.get(task.id) is None
    assert bob.list() == []
