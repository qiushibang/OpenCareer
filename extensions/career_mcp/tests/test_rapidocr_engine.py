from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from extensions.career_mcp.domain.ocr import OcrLine
from extensions.career_mcp.ocr import rapidocr_engine
from extensions.career_mcp.ocr.rapidocr_engine import RapidOcrEngine
from extensions.career_mcp.services.resume_ocr import ResumeOcrError


MODEL_SPECS = (
    ("det", "det-model", "models/det.onnx", b"detection"),
    ("cls", "cls-model", "models/cls.onnx", b"classification"),
    ("rec", "rec-model", "models/rec.onnx", b"recognition"),
)


def _write_manifest(
    tmp_path: Path,
    *,
    roles: tuple[str, ...] = ("det", "cls", "rec"),
) -> tuple[Path, Path, dict[str, object]]:
    package_root = tmp_path / "rapidocr"
    models_root = package_root / "models"
    models_root.mkdir(parents=True)
    models = []
    for role, model_id, relative_path, content in MODEL_SPECS:
        model_path = package_root / relative_path
        model_path.write_bytes(content)
        models.append(
            {
                "role": role,
                "id": model_id,
                "package_relative_path": relative_path,
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "license": "Apache-2.0",
            }
        )
    for model, role in zip(models, roles, strict=True):
        model["role"] = role
    manifest: dict[str, object] = {
        "schema_version": 1,
        "engine": {
            "name": "rapidocr-onnxruntime",
            "version": "3.9.2",
        },
        "runtime": {"name": "onnxruntime", "version": "1.19.2"},
        "models": models,
    }
    manifest_path = tmp_path / "ocr-model-manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path, package_root, manifest


def _patch_resources(
    monkeypatch: pytest.MonkeyPatch,
    package_root: Path,
) -> None:
    monkeypatch.setattr(
        rapidocr_engine.resources,
        "files",
        lambda package: package_root,
    )
    monkeypatch.setattr(
        rapidocr_engine,
        "package_version",
        lambda package: {
            "rapidocr": "3.9.2",
            "onnxruntime": "1.19.2",
        }[package],
    )


def _install_fake_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    output: object,
    constructor_error: Exception | None = None,
    recognition_error: Exception | None = None,
) -> list[dict[str, Any]]:
    constructor_calls: list[dict[str, Any]] = []

    class FakeRapidOCR:
        def __init__(self, **kwargs: Any) -> None:
            constructor_calls.append(kwargs)
            if constructor_error is not None:
                raise constructor_error

        def __call__(self, image: object) -> object:
            if recognition_error is not None:
                raise recognition_error
            return output

    monkeypatch.setitem(
        sys.modules,
        "rapidocr",
        types.SimpleNamespace(RapidOCR=FakeRapidOCR),
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", types.SimpleNamespace())
    return constructor_calls


def _assert_unavailable(
    action: Any,
    *,
    secret_path: Path,
) -> None:
    with pytest.raises(ResumeOcrError) as error:
        action()
    assert error.value.code == "OCR_UNAVAILABLE"
    assert str(secret_path) not in str(error.value)


def test_adapter_module_import_is_lazy() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import extensions.career_mcp.ocr.rapidocr_engine; "
                "print('rapidocr' in sys.modules, "
                "'onnxruntime' in sys.modules)"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "False False"


def test_identity_and_output_use_verified_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, package_root, manifest = _write_manifest(tmp_path)
    _patch_resources(monkeypatch, package_root)
    output = types.SimpleNamespace(
        boxes=[[[1, 2], [8, 2], [8, 6], [1, 6]]],
        txts=("Python",),
        scores=(0.97,),
    )
    constructor_calls = _install_fake_runtime(
        monkeypatch,
        output=output,
    )
    engine = RapidOcrEngine(manifest_path=manifest_path)

    assert engine.identity == {
        "name": "rapidocr-onnxruntime",
        "version": "3.9.2",
        "model_ids": [
            model["id"] for model in manifest["models"]  # type: ignore[index]
        ],
        "model_sha256": [
            model["sha256"]  # type: ignore[index]
            for model in manifest["models"]  # type: ignore[index]
        ],
    }
    assert engine.recognize(object(), page_number=1) == (
        OcrLine(
            text="Python",
            confidence=0.97,
            polygon=((1.0, 2.0), (8.0, 2.0), (8.0, 6.0), (1.0, 6.0)),
        ),
    )
    assert len(constructor_calls) == 1
    params = constructor_calls[0]["params"]
    assert params["Global.max_side_len"] == 1600
    assert params["EngineConfig.onnxruntime.intra_op_num_threads"] == 1
    assert params["EngineConfig.onnxruntime.inter_op_num_threads"] == 1
    assert params["Det.model_path"] == str(
        (package_root / "models/det.onnx").resolve()
    )
    assert params["Cls.model_path"] == str(
        (package_root / "models/cls.onnx").resolve()
    )
    assert params["Rec.model_path"] == str(
        (package_root / "models/rec.onnx").resolve()
    )


def test_missing_model_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, package_root, _ = _write_manifest(tmp_path)
    (package_root / "models/rec.onnx").unlink()
    _patch_resources(monkeypatch, package_root)

    _assert_unavailable(
        lambda: RapidOcrEngine(manifest_path=manifest_path),
        secret_path=package_root,
    )


def test_changed_model_hash_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, package_root, _ = _write_manifest(tmp_path)
    (package_root / "models/rec.onnx").write_bytes(b"changed")
    _patch_resources(monkeypatch, package_root)

    _assert_unavailable(
        lambda: RapidOcrEngine(manifest_path=manifest_path),
        secret_path=package_root,
    )


def test_malformed_manifest_is_unavailable(tmp_path: Path) -> None:
    manifest_path = tmp_path / "ocr-model-manifest.json"
    manifest_path.write_text("{not-json", encoding="utf-8")

    _assert_unavailable(
        lambda: RapidOcrEngine(manifest_path=manifest_path),
        secret_path=tmp_path,
    )


def test_unexpected_model_role_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, package_root, _ = _write_manifest(
        tmp_path,
        roles=("det", "cls", "layout"),
    )
    _patch_resources(monkeypatch, package_root)

    _assert_unavailable(
        lambda: RapidOcrEngine(manifest_path=manifest_path),
        secret_path=package_root,
    )


def test_runtime_import_failure_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, package_root, _ = _write_manifest(tmp_path)
    _patch_resources(monkeypatch, package_root)
    monkeypatch.setitem(sys.modules, "rapidocr", None)

    engine = RapidOcrEngine(manifest_path=manifest_path)

    _assert_unavailable(
        lambda: engine.recognize(object(), page_number=1),
        secret_path=package_root,
    )


@pytest.mark.parametrize("failure_stage", ["constructor", "recognition"])
def test_adapter_exception_is_unavailable(
    failure_stage: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, package_root, _ = _write_manifest(tmp_path)
    _patch_resources(monkeypatch, package_root)
    _install_fake_runtime(
        monkeypatch,
        output=types.SimpleNamespace(boxes=None, txts=None, scores=None),
        constructor_error=(
            RuntimeError(str(package_root))
            if failure_stage == "constructor"
            else None
        ),
        recognition_error=(
            RuntimeError(str(package_root))
            if failure_stage == "recognition"
            else None
        ),
    )
    engine = RapidOcrEngine(manifest_path=manifest_path)

    _assert_unavailable(
        lambda: engine.recognize(object(), page_number=1),
        secret_path=package_root,
    )
