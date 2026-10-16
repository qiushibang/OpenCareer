import json
from contextlib import contextmanager

from coworker.memory import Scope
from coworker.server.identity import Principal
from coworker.storage.postgres.memory_store import PostgresMemoryStore
from coworker.storage.postgres.todos import PostgresTodoRepository
from coworker.tools.todo import TodoList, todo_tools


class _Rows:
    def __init__(self, rows: list[tuple] = ()) -> None:
        self.rows = list(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class _State:
    def __init__(self) -> None:
        self.next_memory_id = 1
        self.memories: dict[int, dict] = {}
        self.conversations: set[tuple[str, str]] = set()
        self.todos: dict[tuple[str, str], list[dict]] = {}


class _Connection:
    def __init__(self, state: _State, user_id: str) -> None:
        self.state = state
        self.user_id = user_id

    def execute(self, sql: str, params: tuple = ()) -> _Rows:
        compact = " ".join(sql.split())
        if compact.startswith("INSERT INTO identity.users"):
            return _Rows()
        if compact.startswith("INSERT INTO agent.conversations"):
            conversation_id, user_id = params
            self.state.conversations.add((user_id, conversation_id))
            return _Rows()
        if compact.startswith("INSERT INTO agent.memories"):
            user_id, scope, key, content, workspace, conversation_id = params
            item_id = self.state.next_memory_id
            self.state.next_memory_id += 1
            row = {
                "id": item_id,
                "user_id": user_id,
                "scope": scope,
                "key": key,
                "content": content,
                "workspace": workspace,
                "conversation_id": conversation_id,
                "created_at": "2026-08-18T00:00:00+00:00",
            }
            self.state.memories[item_id] = row
            return _Rows([self._memory_tuple(row)])
        if compact.startswith("SELECT id, scope, content"):
            rows = [
                row
                for row in self.state.memories.values()
                if row["user_id"] == params[0]
            ]
            if "AND id = %s" in compact:
                rows = [row for row in rows if row["id"] == params[1]]
            index = 1
            if "AND scope = %s" in compact:
                rows = [row for row in rows if row["scope"] == params[index]]
                index += 1
            if "AND workspace = %s" in compact:
                rows = [row for row in rows if row["workspace"] == params[index]]
                index += 1
            if "AND conversation_id = %s" in compact:
                rows = [
                    row
                    for row in rows
                    if row["conversation_id"] == params[index]
                ]
            return _Rows(
                [self._memory_tuple(row) for row in sorted(rows, key=lambda x: x["id"])]
            )
        if compact.startswith("UPDATE agent.memories"):
            content, user_id, item_id = params
            row = self.state.memories.get(item_id)
            if row is None or row["user_id"] != user_id:
                return _Rows()
            row["content"] = content
            return _Rows([self._memory_tuple(row)])
        if compact.startswith("DELETE FROM agent.memories"):
            user_id, item_id = params
            row = self.state.memories.get(item_id)
            if row is None or row["user_id"] != user_id:
                return _Rows()
            self.state.memories.pop(item_id)
            return _Rows([(item_id,)])
        if compact.startswith("SELECT data FROM agent.todos"):
            value = self.state.todos.get((params[0], params[1]))
            return _Rows([(value,)] if value is not None else [])
        if compact.startswith("INSERT INTO agent.todos"):
            user_id, conversation_id, data = params
            assert (user_id, conversation_id) in self.state.conversations
            if isinstance(data, str):
                data = json.loads(data)
            self.state.todos[(user_id, conversation_id)] = data
            return _Rows()
        raise AssertionError(f"unexpected SQL: {compact}")

    @staticmethod
    def _memory_tuple(row: dict) -> tuple:
        return (
            row["id"],
            row["scope"],
            row["content"],
            row["key"],
            row["workspace"],
            row["conversation_id"],
            row["created_at"],
        )


class _Database:
    def __init__(self) -> None:
        self.state = _State()

    @contextmanager
    def transaction(self, principal: Principal):
        yield _Connection(self.state, principal.user_id)


def test_postgres_memory_supports_scopes_updates_and_tenant_isolation() -> None:
    database = _Database()
    alice = PostgresMemoryStore(database, Principal("alice", "test"))
    bob = PostgresMemoryStore(database, Principal("bob", "test"))

    global_item = alice.add("Use concise answers", scope=Scope.GLOBAL)
    alice.add(
        "Project uses FastAPI",
        scope=Scope.WORKSPACE,
        workspace="/repo",
    )
    alice.add(
        "Interview in progress",
        scope=Scope.SESSION,
        session_id="conversation-1",
    )

    assert [item.content for item in alice.list(scope=Scope.GLOBAL)] == [
        "Use concise answers"
    ]
    assert [item.content for item in alice.list(workspace="/repo")] == [
        "Project uses FastAPI"
    ]
    assert bob.get(global_item.id) is None
    assert bob.list() == []

    updated = alice.update(global_item.id, "Prefer concise answers")
    assert updated is not None
    assert updated.content == "Prefer concise answers"
    assert alice.delete(global_item.id)
    assert alice.get(global_item.id) is None


def test_todo_write_replaces_and_restores_the_tenant_list() -> None:
    database = _Database()
    alice_repository = PostgresTodoRepository(
        database,
        Principal("alice", "test"),
    )
    bob_repository = PostgresTodoRepository(
        database,
        Principal("bob", "test"),
    )
    todo = TodoList(
        repository=alice_repository,
        session_id="conversation-1",
    )
    (tool,) = todo_tools(todo)

    result = tool(
        todos=[
            {"content": "Inspect schema", "status": "done"},
            {"content": "Migrate data", "status": "in_progress"},
        ]
    )

    restored = TodoList(
        repository=alice_repository,
        session_id="conversation-1",
    )
    isolated = TodoList(
        repository=bob_repository,
        session_id="conversation-1",
    )
    assert result["count"] == 2
    assert restored.items == result["todos"]
    assert isolated.items == []
