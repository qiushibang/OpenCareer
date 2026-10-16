from __future__ import annotations

import json
from pathlib import Path

from extensions.career_mcp.ocr.installation_verifier import main

FIXTURES = Path(__file__).parent / "fixtures" / "ocr"


def test_installation_verifier_recognizes_fixture_without_sensitive_output(
    capsys,
) -> None:
    exit_code = main(
        [
            "--fixture",
            str(FIXTURES / "chinese-scanned.pdf"),
            "--require-term",
            "Python",
            "--require-term",
            "技能",
        ]
    )

    output = capsys.readouterr()
    result = json.loads(output.out)
    assert exit_code == 0
    assert output.err == ""
    assert result["ok"] is True
    assert result["extraction_method"] == "ocr"
    assert result["pages"] == {"total": 1, "ocr": [1]}
    assert result["required_terms_matched"] == [True, True]
    assert result["engine"]["name"] == "rapidocr-onnxruntime"
    assert "测试候选人" not in output.out
    assert str(FIXTURES.resolve()) not in output.out
    assert "model_path" not in output.out


def test_installation_verifier_returns_safe_failure(
    tmp_path: Path,
    capsys,
) -> None:
    missing = tmp_path / "private-fixture.pdf"

    exit_code = main(["--fixture", str(missing)])

    output = capsys.readouterr()
    result = json.loads(output.out)
    assert exit_code == 1
    assert result == {
        "ok": False,
        "error": "OCR_INSTALLATION_VERIFICATION_FAILED",
    }
    assert str(tmp_path) not in output.out
