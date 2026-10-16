"""Fixed, offline RapidOCR adapter for scanned resume pages."""

from __future__ import annotations

import hashlib
import json
from importlib import resources
from importlib.metadata import version as package_version
from pathlib import Path, PurePosixPath
from typing import Any

from ..domain.ocr import OcrLine
from ..services.resume_ocr import ResumeOcrError

ENGINE_NAME = "rapidocr-onnxruntime"
ENGINE_VERSION = "3.9.2"
RUNTIME_NAME = "onnxruntime"
RUNTIME_VERSION = "1.19.2"
MODEL_ROLES = ("det", "cls", "rec")
MODEL_LICENSE = "Apache-2.0"


class RapidOcrEngine:
    def __init__(self, *, manifest_path: Path | None = None) -> None:
        try:
            manifest = _load_manifest(manifest_path)
            models = _validate_manifest(manifest)
            _validate_installed_versions()
            model_paths = _verify_models(models)
        except ResumeOcrError:
            raise
        except Exception as exc:
            raise _unavailable("local OCR configuration is unavailable") from exc

        self._identity = {
            "name": ENGINE_NAME,
            "version": ENGINE_VERSION,
            "model_ids": [model["id"] for model in models],
            "model_sha256": [model["sha256"] for model in models],
        }
        self._model_paths = model_paths
        self._engine: object | None = None

    @property
    def identity(self) -> dict[str, object]:
        return {
            "name": self._identity["name"],
            "version": self._identity["version"],
            "model_ids": list(self._identity["model_ids"]),
            "model_sha256": list(self._identity["model_sha256"]),
        }

    def recognize(
        self,
        image: object,
        *,
        page_number: int,
    ) -> tuple[OcrLine, ...]:
        del page_number
        try:
            engine = self._get_engine()
            output = engine(image)  # type: ignore[operator]
            return _normalize_output(output)
        except ResumeOcrError:
            raise
        except Exception as exc:
            raise _unavailable("local OCR inference is unavailable") from exc

    def _get_engine(self) -> object:
        if self._engine is not None:
            return self._engine
        try:
            import onnxruntime  # noqa: F401
            from rapidocr import RapidOCR

            self._engine = RapidOCR(
                params={
                    "Global.log_level": "error",
                    "Global.use_det": True,
                    "Global.use_cls": True,
                    "Global.use_rec": True,
                    "Global.max_side_len": 1600,
                    "EngineConfig.onnxruntime.intra_op_num_threads": 1,
                    "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                    "Det.model_path": str(self._model_paths["det"]),
                    "Cls.model_path": str(self._model_paths["cls"]),
                    "Rec.model_path": str(self._model_paths["rec"]),
                }
            )
            return self._engine
        except Exception as exc:
            raise _unavailable("local OCR runtime is unavailable") from exc


def _load_manifest(manifest_path: Path | None) -> dict[str, object]:
    try:
        if manifest_path is not None:
            raw = manifest_path.read_text(encoding="utf-8")
        else:
            repository_path = (
                Path(__file__).resolve().parents[3]
                / "config"
                / "ocr-model-manifest.json"
            )
            if repository_path.is_file():
                raw = repository_path.read_text(encoding="utf-8")
            else:
                packaged = resources.files("extensions.career_mcp").joinpath(
                    "ocr-model-manifest.json"
                )
                raw = packaged.read_text(encoding="utf-8")
        manifest = json.loads(raw)
    except Exception as exc:
        raise _unavailable("local OCR manifest is invalid") from exc
    if not isinstance(manifest, dict):
        raise _unavailable("local OCR manifest is invalid")
    return manifest


def _validate_manifest(
    manifest: dict[str, object],
) -> tuple[dict[str, object], ...]:
    engine = manifest.get("engine")
    runtime = manifest.get("runtime")
    raw_models = manifest.get("models")
    if (
        manifest.get("schema_version") != 1
        or engine
        != {
            "name": ENGINE_NAME,
            "version": ENGINE_VERSION,
        }
        or runtime
        != {
            "name": RUNTIME_NAME,
            "version": RUNTIME_VERSION,
        }
        or not isinstance(raw_models, list)
        or len(raw_models) != len(MODEL_ROLES)
    ):
        raise _unavailable("local OCR manifest is invalid")

    models: list[dict[str, object]] = []
    for expected_role, raw_model in zip(
        MODEL_ROLES,
        raw_models,
        strict=True,
    ):
        if not isinstance(raw_model, dict):
            raise _unavailable("local OCR manifest is invalid")
        role = raw_model.get("role")
        model_id = raw_model.get("id")
        relative_path = raw_model.get("package_relative_path")
        size = raw_model.get("bytes")
        sha256 = raw_model.get("sha256")
        license_name = raw_model.get("license")
        path = (
            PurePosixPath(relative_path)
            if isinstance(relative_path, str)
            else None
        )
        if (
            role != expected_role
            or not isinstance(model_id, str)
            or not model_id
            or path is None
            or path.is_absolute()
            or ".." in path.parts
            or not isinstance(size, int)
            or isinstance(size, bool)
            or size <= 0
            or not isinstance(sha256, str)
            or len(sha256) != 64
            or any(character not in "0123456789abcdef" for character in sha256)
            or license_name != MODEL_LICENSE
        ):
            raise _unavailable("local OCR manifest is invalid")
        models.append(
            {
                "role": role,
                "id": model_id,
                "package_relative_path": path.as_posix(),
                "bytes": size,
                "sha256": sha256,
            }
        )
    return tuple(models)


def _validate_installed_versions() -> None:
    if (
        package_version("rapidocr") != ENGINE_VERSION
        or package_version("onnxruntime") != RUNTIME_VERSION
    ):
        raise _unavailable("local OCR runtime version is unavailable")


def _verify_models(
    models: tuple[dict[str, object], ...],
) -> dict[str, Path]:
    try:
        package_root = Path(str(resources.files("rapidocr"))).resolve(
            strict=True
        )
        if not package_root.is_dir():
            raise ValueError("package root is not a directory")
        verified: dict[str, Path] = {}
        for model in models:
            relative_path = PurePosixPath(
                str(model["package_relative_path"])
            )
            candidate = package_root.joinpath(*relative_path.parts)
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(package_root)
            if not resolved.is_file():
                raise ValueError("model is not a file")
            if (
                resolved.stat().st_size != model["bytes"]
                or _sha256(resolved) != model["sha256"]
            ):
                raise ValueError("model identity does not match")
            verified[str(model["role"])] = resolved
        return verified
    except Exception as exc:
        raise _unavailable("local OCR model verification failed") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize_output(output: object) -> tuple[OcrLine, ...]:
    boxes = getattr(output, "boxes", None)
    texts = getattr(output, "txts", None)
    scores = getattr(output, "scores", None)
    if boxes is None and texts is None and scores is None:
        return ()
    if boxes is None or texts is None or scores is None:
        raise _unavailable("local OCR output is invalid")
    if not (len(boxes) == len(texts) == len(scores)):
        raise _unavailable("local OCR output is invalid")

    lines: list[OcrLine] = []
    for box, text, score in zip(boxes, texts, scores, strict=True):
        polygon = tuple(
            tuple(float(coordinate) for coordinate in point)
            for point in box
        )
        lines.append(
            OcrLine(
                text=str(text),
                confidence=float(score),
                polygon=polygon,
            )
        )
    return tuple(lines)


def _unavailable(message: str) -> ResumeOcrError:
    return ResumeOcrError("OCR_UNAVAILABLE", message)
