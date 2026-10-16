from coworker.server.manager import SessionManager
from coworker.sessions import SessionRecord


class _ConversationRepository:
    pass


class _ExistingConversationRepository:
    def __init__(self, record: SessionRecord) -> None:
        self.record = record

    def load(self, session_id: str) -> SessionRecord | None:
        return self.record if session_id == self.record.session_id else None

    def touch_workspace(self, workspace: str) -> None:
        pass


def test_session_manager_accepts_an_injected_conversation_repository(
    tmp_path,
) -> None:
    repository = _ConversationRepository()

    manager = SessionManager(
        data_dir=tmp_path,
        session_store=repository,
    )

    assert manager.session_store is repository


def test_existing_conversation_without_workspace_adopts_requested_workspace(
    tmp_path,
) -> None:
    requested = tmp_path / "requested"
    requested.mkdir()
    record = SessionRecord(
        session_id="conversation-1",
        workspace="",
        model="aiden:deepseek-v4-flash",
        mode="interactive",
        agent="career",
    )
    manager = SessionManager(
        data_dir=tmp_path / "data",
        session_store=_ExistingConversationRepository(record),
    )

    assert manager.engine_workspace(
        record.session_id,
        workspace=str(requested),
        agent="career",
    ) == str(requested.resolve())
    engine = manager.get_engine(
        record.session_id,
        workspace=str(requested),
        agent="career",
    )

    assert engine is not None
    assert engine.executor.cwd == str(requested.resolve())


def test_existing_conversation_keeps_its_persisted_workspace(tmp_path) -> None:
    persisted = tmp_path / "persisted"
    persisted.mkdir()
    requested = tmp_path / "requested"
    requested.mkdir()
    record = SessionRecord(
        session_id="conversation-1",
        workspace=str(persisted),
        model="aiden:deepseek-v4-flash",
        mode="interactive",
        agent="career",
    )
    manager = SessionManager(
        data_dir=tmp_path / "data",
        session_store=_ExistingConversationRepository(record),
    )

    engine = manager.get_engine(
        record.session_id,
        workspace=str(requested),
        agent="career",
    )

    assert engine is not None
    assert engine.executor.cwd == str(persisted.resolve())


def test_session_manager_wires_session_skill_state(
    tmp_path,
    monkeypatch,
) -> None:
    class State:
        def __init__(self) -> None:
            self.hashes: dict[str, str] = {}

        def loaded_hash(self, name: str) -> str | None:
            return self.hashes.get(name)

        def mark_loaded(
            self,
            name: str,
            *,
            version: str | None,
            content_sha256: str,
        ) -> None:
            self.hashes[name] = content_sha256

    states: dict[str, State] = {}
    monkeypatch.setenv("COWORKER_STATE_DIR", str(tmp_path / "state"))
    manager = SessionManager(
        data_dir=tmp_path / "data",
        session_skill_state_factory=lambda session_id: states.setdefault(
            session_id,
            State(),
        ),
    )
    skill_dir = manager.skill_store.global_dir / "interview"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: interview\ndescription: Interview\n---\n\nDo it.",
        encoding="utf-8",
    )

    engine = manager.get_engine("conversation-1", agent="chat")
    first = engine.registry.execute("load_skill", {"name": "interview"})
    second = engine.registry.execute("load_skill", {"name": "interview"})

    assert first["instructions"] == "Do it."
    assert second["already_loaded"] is True
    assert set(states) == {"conversation-1"}


def test_session_manager_wires_context_manifest_recorder(tmp_path) -> None:
    recorder = object()
    requested: list[str] = []

    manager = SessionManager(
        data_dir=tmp_path,
        context_manifest_recorder_factory=lambda session_id: (
            requested.append(session_id) or recorder
        ),
    )

    engine = manager.get_engine("conversation-1", agent="chat")

    assert engine.context_manifest_recorder is recorder
    assert requested == ["conversation-1"]


def test_session_manager_keeps_the_runtime_coordinator(tmp_path) -> None:
    coordinator = object()

    manager = SessionManager(
        data_dir=tmp_path,
        runtime_coordinator=coordinator,
    )

    assert manager.runtime_coordinator is coordinator


def test_session_manager_wires_durable_memory_and_todos(tmp_path) -> None:
    class MemoryStore:
        def list(self, **kwargs) -> list:
            return []

    memory_store = MemoryStore()

    class TodoRepository:
        def load(self, session_id: str) -> list[dict]:
            assert session_id == "conversation-1"
            return [{"content": "Persist me", "status": "in_progress"}]

        def replace(self, session_id: str, items: list[dict]) -> None:
            raise AssertionError("replace is not expected during engine build")

    todo_repository = TodoRepository()
    manager = SessionManager(
        data_dir=tmp_path,
        memory_store=memory_store,
        todo_repository=todo_repository,
    )

    engine = manager.get_engine("conversation-1", agent="chat")

    assert manager.memory_store is memory_store
    assert engine.todo.items == [
        {"content": "Persist me", "status": "in_progress"}
    ]


def test_session_manager_accepts_a_durable_inbox_repository(tmp_path) -> None:
    inbox = object()

    manager = SessionManager(
        data_dir=tmp_path,
        inbox_repository=inbox,
    )

    assert manager.inbox is inbox


def test_session_manager_accepts_a_durable_automation_store(tmp_path) -> None:
    automation_store = object()

    manager = SessionManager(
        data_dir=tmp_path,
        automation_store=automation_store,
    )

    assert manager.task_store is automation_store
