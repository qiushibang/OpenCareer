from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path

import pytest

from extensions.career_mcp.config import CareerConfig
from extensions.career_mcp.database.migrations import connect
from extensions.career_mcp.services.resumes import (
    ResumeService,
    ResumeServiceError,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = Path(__file__).parent / "fixtures" / "ocr"
FIXTURE_CASES = (
    (
        "chinese-scanned.pdf",
        "d0d591172f20257568ffc8554d60a6671c3f70fcad2aa7040205641bd38a1e94",
        "ocr",
        False,
        [],
        {"total": 1, "ocr": [1]},
        [],
        [1],
        40,
    ),
    (
        "mixed-scanned.pdf",
        "9440104d32e0dc7bf5e69ef05ff12f486656bc3f40b6ce1b446e10f9786886c3",
        "ocr",
        False,
        [],
        {"total": 1, "ocr": [1]},
        [],
        [1],
        40,
    ),
    (
        "hybrid.pdf",
        "1a635857bc299ea4284b65b259e76e9e6857855a009c3ae3cb90628116ddb70e",
        "hybrid",
        False,
        [],
        {"total": 2, "ocr": [2]},
        [1],
        [2],
        180,
    ),
    (
        "low-quality-skewed.pdf",
        "bf3a7dea4e62411f9d83f93a30687072b565d0c917b9fc84e1be4dea8ed721ca",
        "ocr",
        True,
        ["OCR_SPARSE_TEXT"],
        {"total": 1, "ocr": [1]},
        [],
        [1],
        20,
    ),
)
FORBIDDEN_RESIDUE_SUFFIXES = {
    ".bmp",
    ".jpeg",
    ".jpg",
    ".npy",
    ".onnx",
    ".png",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot(roots: tuple[Path, ...]) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                snapshot[str(path.relative_to(ROOT))] = _sha256(path)
    return snapshot


@pytest.mark.ocr_acceptance
@pytest.mark.parametrize(
    (
        "fixture_name",
        "expected_sha256",
        "expected_method",
        "expected_review",
        "expected_warnings",
        "expected_pages",
        "expected_native_pages",
        "expected_attempted_pages",
        "minimum_characters",
    ),
    FIXTURE_CASES,
    ids=("chinese", "mixed", "hybrid", "low-quality"),
)
def test_resume_pdf_fixture_is_processed_offline_without_residue(
    fixture_name: str,
    expected_sha256: str,
    expected_method: str,
    expected_review: bool,
    expected_warnings: list[str],
    expected_pages: dict[str, object],
    expected_native_pages: list[int],
    expected_attempted_pages: list[int],
    minimum_characters: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = FIXTURES / fixture_name
    assert _sha256(fixture) == expected_sha256
    watched_roots = (ROOT / "artifacts", ROOT / ".local-state")
    workspace_before = _snapshot(watched_roots)

    def deny_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network disabled")

    monkeypatch.setattr(socket.socket, "connect", deny_network)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_network)
    monkeypatch.setattr(socket, "create_connection", deny_network)

    config = CareerConfig(data_dir=tmp_path / "career")
    private_root = tmp_path / "private"
    service = ResumeService(config, private_root=private_root)
    staged = service.stage_resume(
        filename=fixture.name,
        mime="application/pdf",
        raw_bytes=fixture.read_bytes(),
    )

    assert staged["extraction_method"] == expected_method
    assert staged["review_required"] is expected_review
    assert staged["warnings"] == expected_warnings
    assert staged["pages"] == expected_pages
    assert staged["characters"] >= minimum_characters

    imported = service.get_resume_import_text(staged["upload_token"])
    metadata = imported["extraction_metadata"]
    assert metadata["method"] == expected_method
    assert metadata["warning_codes"] == expected_warnings
    assert metadata["native_pages"] == expected_native_pages
    assert metadata["ocr_attempted_pages"] == expected_attempted_pages
    assert metadata["ocr_pages"] == expected_pages["ocr"]
    assert metadata["engine"]["name"] == "rapidocr-onnxruntime"
    serialized_metadata = json.dumps(
        metadata,
        ensure_ascii=False,
        sort_keys=True,
    )
    for forbidden in ("private_path", "model_path", "polygon", "page_image"):
        assert forbidden not in serialized_metadata

    with pytest.raises(ResumeServiceError) as profile_error:
        service.get_candidate_profile()
    assert profile_error.value.code == "PROFILE_NOT_FOUND"

    proposal = {
        "basic": {
            "name": "测试候选人",
            "phone": None,
            "email": None,
            "location": None,
            "summary": None,
        },
        "education": [],
        "experience": [],
        "project": [],
        "skill": [
            {"name": "Python", "level": None, "evidence": None}
        ],
        "missing_fields": [],
        "warnings": expected_warnings,
    }
    preview = service.preview_resume_import(
        staged["upload_token"],
        proposal,
    )
    service.confirm_resume_sections(
        preview["preview_token"],
        ["basic", "education", "experience", "project", "skill"],
        corrections={},
    )

    document = service.list_resume_documents()[0]
    original = private_root / "resumes" / f"{expected_sha256}.pdf"
    assert original.is_file()
    assert original.read_bytes() == fixture.read_bytes()
    files_after_stage = {
        path.relative_to(tmp_path)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert files_after_stage == {
        Path("career/career.sqlite3"),
        Path(f"private/resumes/{expected_sha256}.pdf"),
    }
    assert not any(
        path.suffix.lower() in FORBIDDEN_RESIDUE_SUFFIXES
        for path in files_after_stage
    )

    deleted = service.delete_resume_document(
        document["id"],
        confirm_name=document["display_name"],
    )
    assert deleted["original_removed"] is True
    assert not original.exists()

    connection = connect(config.database_path)
    try:
        row = connection.execute(
            """
            SELECT extracted_text, deleted_at
            FROM resume_imports
            WHERE id = ?
            """,
            (document["id"],),
        ).fetchone()
        source_references = connection.execute(
            """
            SELECT COUNT(*)
            FROM candidate_facts
            WHERE source_import_id = ?
            """,
            (document["id"],),
        ).fetchone()[0]
    finally:
        connection.close()
    assert row["extracted_text"] == ""
    assert row["deleted_at"] is not None
    assert source_references == 5
    assert {
        path.relative_to(tmp_path)
        for path in tmp_path.rglob("*")
        if path.is_file()
    } == {Path("career/career.sqlite3")}

    captured = capsys.readouterr()
    captured_output = captured.out + captured.err
    for private_text in ("测试候选人", "Test Candidate", "Python"):
        assert private_text not in captured_output
    assert _snapshot(watched_roots) == workspace_before
