from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "deploy" / "entrypoint.sh"


def _skill(root: Path, name: str, body: str) -> None:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(body, encoding="utf-8")


def test_entrypoint_syncs_managed_skills_without_deleting_custom_skills(
    tmp_path: Path,
) -> None:
    state = tmp_path / "state"
    skills = state / "skills"
    bundled = tmp_path / "bundled"
    state.mkdir()
    (state / "mcp.json").write_text("{}", encoding="utf-8")
    _skill(skills, "career-tailored-resume", "retired")
    _skill(skills, "career-application-packet", "retired")
    _skill(skills, "mock-interview", "old")
    _skill(skills, "custom-user-skill", "keep")
    _skill(bundled, "mock-interview", "new")
    _skill(bundled, "career-resume-coach", "coach")

    environment = {
        **os.environ,
        "COWORKER_STATE_DIR": str(state),
        "CAREER_DATA_DIR": str(tmp_path / "career"),
        "CAREER_PRIVATE_DIR": str(tmp_path / "private"),
        "OPENCAR_ALPHA_WORKSPACE": str(tmp_path / "workspace"),
        "OPENCAR_BUNDLED_SKILLS_DIR": str(bundled),
        "OPENCAR_SEED_DEMO": "0",
    }
    subprocess.run(
        ["sh", str(ENTRYPOINT), "true"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert not (skills / "career-tailored-resume").exists()
    assert not (skills / "career-application-packet").exists()
    assert (skills / "mock-interview" / "SKILL.md").read_text() == "new"
    assert (skills / "career-resume-coach" / "SKILL.md").read_text() == "coach"
    assert (skills / "custom-user-skill" / "SKILL.md").read_text() == "keep"

    for path in bundled.iterdir():
        if path.name == "career-resume-coach":
            continue
        for child in path.iterdir():
            child.unlink()
        path.rmdir()
    subprocess.run(
        ["sh", str(ENTRYPOINT), "true"],
        check=True,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert not (skills / "mock-interview").exists()
    assert (skills / "career-resume-coach").is_dir()
    assert (skills / "custom-user-skill").is_dir()
