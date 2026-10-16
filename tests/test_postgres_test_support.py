import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deploy.test_database import validated_test_database_url


def test_rejects_production_database_name() -> None:
    with pytest.raises(RuntimeError, match="refusing PostgreSQL tests"):
        validated_test_database_url(
            "postgresql://user:secret@localhost/opencareer_prod"
        )


@pytest.mark.parametrize(
    "database_name",
    ["opencareer_gate", "opencareer_gate_fresh", "feature_test"],
)
def test_accepts_isolated_database_names(database_name: str) -> None:
    url = f"postgresql://user:secret@localhost/{database_name}"

    assert validated_test_database_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "postgresql://user:secret@localhost/postgres",
        "postgresql://user:secret@localhost/",
    ],
)
def test_rejects_missing_or_unsafe_database_names(url: str) -> None:
    with pytest.raises(RuntimeError, match="refusing PostgreSQL tests"):
        validated_test_database_url(url)


@pytest.mark.parametrize(
    "relative_path",
    [
        "tests/test_postgres_integration.py",
    ],
)
def test_catalog_writing_suites_use_guard_and_teardown(
    relative_path: str,
) -> None:
    source = (
        Path(__file__).resolve().parents[1] / relative_path
    ).read_text(encoding="utf-8")

    assert "validated_test_database_url(" in source
    assert "cleanup_catalog_test_rows(database)" in source
