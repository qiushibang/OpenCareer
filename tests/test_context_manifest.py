import asyncio

from coworker.context_manifest import (
    ModelContextRecorder,
    build_context_manifest,
)
from coworker.engine import TurnEngine
from coworker.permissions import PermissionEngine
from coworker.providers import (
    AssistantTurn,
    ModelCapabilities,
    ProviderClient,
)
from coworker.providers.base import TokenUsage
from coworker.tools import ToolRegistry


def test_context_manifest_records_auditable_refs_without_prompt_content() -> None:
    messages = [
        {
            "role": "system",
            "content": "API key sk-secret-value",
        },
        {
            "role": "user",
            "content": "resume body and token=private-token",
        },
    ]

    manifest = build_context_manifest(
        conversation_id="conversation-1",
        turn_id="turn-1",
        messages=messages,
        canonical_start=1,
        canonical_end=8,
        compaction_id="compaction-2",
        memory_ids=("memory-1",),
        skill_hashes={"mock-interview": "a" * 64},
        career_refs=("job:job-1", "resume:resume-1"),
        model="deepseek:model",
        estimated_tokens=1200,
    )
    payload = manifest.as_dict()
    serialized = str(payload)

    assert payload == {
        "conversation_id": "conversation-1",
        "turn_id": "turn-1",
        "canonical_range": {"start": 1, "end": 8},
        "compaction_id": "compaction-2",
        "memory_ids": ["memory-1"],
        "skill_hashes": {"mock-interview": "a" * 64},
        "career_refs": ["job:job-1", "resume:resume-1"],
        "model": "deepseek:model",
        "estimated_tokens": 1200,
        "actual_usage": None,
        "content_hash": manifest.content_hash,
    }
    assert len(manifest.content_hash) == 64
    assert "sk-secret-value" not in serialized
    assert "private-token" not in serialized
    assert "resume body" not in serialized


def test_context_manifest_actual_usage_is_a_separate_update() -> None:
    manifest = build_context_manifest(
        conversation_id="conversation-1",
        turn_id="turn-1",
        messages=[{"role": "user", "content": "hello"}],
        canonical_start=0,
        canonical_end=0,
        model="deepseek:model",
        estimated_tokens=12,
    )

    updated = manifest.with_actual_usage(
        {
            "input": 10,
            "output": 4,
            "cache_read": 2,
            "cache_write": 0,
        }
    )

    assert manifest.actual_usage is None
    assert updated.actual_usage == {
        "input": 10,
        "output": 4,
        "cache_read": 2,
        "cache_write": 0,
    }
    assert updated.content_hash == manifest.content_hash


def test_engine_records_manifest_before_model_call_and_updates_usage(
    tmp_path,
) -> None:
    events: list[tuple[str, object]] = []

    class Provider(ProviderClient):
        def complete(self, *, model, messages, tools=None, **settings):
            events.append(("provider", messages))
            return AssistantTurn(
                text="done",
                usage=TokenUsage(input=10, output=3, cache_read=2),
            )

        def capabilities(self, model):
            return ModelCapabilities()

    class Recorder:
        def begin(self, **context) -> str:
            events.append(("begin", context))
            return "manifest-1"

        def complete(self, manifest_id: str, usage: dict[str, int]) -> None:
            events.append(("complete", (manifest_id, usage)))

    engine = TurnEngine(
        provider=Provider(),
        registry=ToolRegistry(),
        permissions=PermissionEngine(workspace_root=tmp_path),
        model="deepseek:model",
        messages=[{"role": "system", "content": "system"}],
    )
    engine.context_manifest_recorder = Recorder()

    async def run() -> None:
        async for _ in engine.run("hello"):
            pass

    asyncio.run(run())

    assert [event[0] for event in events] == [
        "begin",
        "provider",
        "complete",
    ]
    begin = events[0][1]
    assert begin["model"] == "deepseek:model"
    assert begin["canonical_start"] == 0
    assert begin["canonical_end"] == 1
    assert begin["estimated_tokens"] > 0
    assert events[2][1] == (
        "manifest-1",
        {
            "input": 10,
            "output": 3,
            "cache_read": 2,
            "cache_write": 0,
        },
    )


def test_model_context_recorder_samples_current_reference_ids() -> None:
    class Repository:
        def __init__(self) -> None:
            self.created = None
            self.updated = None

        def create(self, manifest) -> str:
            self.created = manifest
            return "manifest-1"

        def update_actual_usage(self, manifest_id, usage) -> bool:
            self.updated = (manifest_id, usage)
            return True

    repository = Repository()
    recorder = ModelContextRecorder(
        repository,
        conversation_id="conversation-1",
        memory_ids=lambda: ("memory-1",),
        skill_hashes=lambda: {"interview": "a" * 64},
        career_refs=lambda: ("job:job-1",),
    )

    manifest_id = recorder.begin(
        messages=[{"role": "user", "content": "hello"}],
        model="deepseek:model",
        canonical_start=0,
        canonical_end=0,
        compaction_id=None,
        estimated_tokens=10,
    )
    recorder.complete(
        manifest_id,
        {"input": 8, "output": 2, "cache_read": 0, "cache_write": 0},
    )

    assert repository.created.memory_ids == ("memory-1",)
    assert repository.created.skill_hashes == {"interview": "a" * 64}
    assert repository.created.career_refs == ("job:job-1",)
    assert repository.updated[0] == "manifest-1"
