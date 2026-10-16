from pathlib import Path

from coworker.skills import SkillLoader, skill_tools


class _State:
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


def _write_skill(root: Path, body: str) -> None:
    folder = root / "interview"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        "---\n"
        "name: interview\n"
        "description: Run an interview\n"
        "---\n\n"
        f"{body}\n",
        encoding="utf-8",
    )


def test_unchanged_session_skill_hash_skips_reloading_instructions(
    tmp_path,
) -> None:
    _write_skill(tmp_path, "version one")
    loader = SkillLoader([tmp_path])
    state = _State()
    tool = skill_tools(loader, state=state)[0]

    first = tool("interview")
    second = tool("interview")

    assert first["instructions"] == "version one"
    assert len(first["content_sha256"]) == 64
    assert second == {
        "name": "interview",
        "already_loaded": True,
        "content_sha256": first["content_sha256"],
    }


def test_changed_session_skill_hash_reloads_instructions(tmp_path) -> None:
    _write_skill(tmp_path, "version one")
    loader = SkillLoader([tmp_path])
    state = _State()
    tool = skill_tools(loader, state=state)[0]
    first = tool("interview")

    _write_skill(tmp_path, "version two")
    loader.rescan()
    changed = tool("interview")

    assert changed["instructions"] == "version two"
    assert changed["content_sha256"] != first["content_sha256"]
