"""Local configuration for the Career domain service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from coworker.secrets import state_dir


@dataclass(frozen=True)
class CareerConfig:
    data_dir: Path

    @classmethod
    def from_env(cls) -> "CareerConfig":
        value = os.environ.get("CAREER_DATA_DIR", "").strip()
        data_dir = Path(value).expanduser() if value else state_dir() / "career"
        return cls(data_dir=data_dir.resolve())

    @property
    def database_path(self) -> Path:
        return self.data_dir / "career.sqlite3"

    @property
    def private_resume_dir(self) -> Path:
        value = os.environ.get("CAREER_PRIVATE_DIR", "").strip()
        root = (
            Path(value).expanduser()
            if value
            else state_dir() / "career-private"
        )
        return root.resolve() / "resumes"

    @property
    def staged_resume_dir(self) -> Path:
        return self.private_resume_dir.parent / "staged"
