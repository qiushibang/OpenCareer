"""Verify the fixed local OCR runtime without exposing recognized text."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import socket
import time
from contextlib import ExitStack
from importlib.metadata import metadata, version
from importlib.util import find_spec
from pathlib import Path
from typing import Callable, Sequence
from unittest.mock import patch

try:
    import resource
except ImportError:  # pragma: no cover - exercised by the Windows gate
    resource = None

ENGINE_VERSION = "3.9.2"
RUNTIME_VERSION = "1.19.2"
MODEL_LICENSE = "Apache-2.0"
MODEL_FILES = (
    ("det", "PP-OCRv6_det_small", "PP-OCRv6_det_small.onnx"),
    (
        "cls",
        "ch_ppocr_mobile_v2.0_cls_mobile",
        "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
    ),
    ("rec", "PP-OCRv6_rec_small", "PP-OCRv6_rec_small.onnx"),
)


def _rapidocr_root() -> Path:
    spec = find_spec("rapidocr")
    locations = tuple(spec.submodule_search_locations or ()) if spec else ()
    if len(locations) != 1:
        raise RuntimeError("RapidOCR package is unavailable")
    return Path(locations[0]).resolve()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_models() -> list[dict[str, object]]:
    """Return fixed package model identities without absolute paths."""
    package_root = _rapidocr_root()
    models_root = (package_root / "models").resolve()
    models: list[dict[str, object]] = []
    for role, model_id, filename in MODEL_FILES:
        path = (models_root / filename).resolve()
        try:
            relative = path.relative_to(package_root)
        except ValueError as exc:
            raise RuntimeError("OCR model is outside the package") from exc
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("OCR model is unavailable")
        size = path.stat().st_size
        if size <= 0:
            raise RuntimeError("OCR model is empty")
        models.append(
            {
                "role": role,
                "id": model_id,
                "package_relative_path": relative.as_posix(),
                "bytes": size,
                "sha256": _sha256(path),
                "license": MODEL_LICENSE,
            }
        )
    return models


def _manifest() -> dict[str, object]:
    if version("rapidocr") != ENGINE_VERSION:
        raise RuntimeError("RapidOCR version does not match the gate")
    if version("onnxruntime") != RUNTIME_VERSION:
        raise RuntimeError("ONNX Runtime version does not match the gate")
    if metadata("rapidocr").get("License-Expression") != "Apache-2.0":
        raise RuntimeError("RapidOCR license metadata is unexpected")
    return {
        "schema_version": 1,
        "engine": {
            "name": "rapidocr-onnxruntime",
            "version": ENGINE_VERSION,
        },
        "runtime": {
            "name": "onnxruntime",
            "version": RUNTIME_VERSION,
        },
        "models": discover_models(),
    }


def _model_paths() -> dict[str, str]:
    package_root = _rapidocr_root()
    return {
        role: str((package_root / "models" / filename).resolve())
        for role, _, filename in MODEL_FILES
    }


def verify_fixture(
    path: Path,
    required_terms: tuple[str, ...],
) -> dict[str, object]:
    """Run OCR and report only non-sensitive gate measurements."""
    import pypdfium2 as pdfium
    from rapidocr import RapidOCR

    models = _model_paths()
    started = time.perf_counter()
    engine = RapidOCR(
        params={
            "Global.log_level": "error",
            "Global.use_det": True,
            "Global.use_cls": True,
            "Global.use_rec": True,
            "Global.max_side_len": 1600,
            "EngineConfig.onnxruntime.intra_op_num_threads": 1,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
            "Det.model_path": models["det"],
            "Cls.model_path": models["cls"],
            "Rec.model_path": models["rec"],
        }
    )
    recognized: list[str] = []
    initial_document = pdfium.PdfDocument(path)
    page_count = len(initial_document)
    initial_document.close()
    for index in range(page_count):
        document = pdfium.PdfDocument(path)
        try:
            page = document[index]
            bitmap = page.render(scale=200 / 72)
            image = bitmap.to_numpy()
            try:
                result = engine(image)
                recognized.extend(result.txts or ())
            finally:
                if "result" in locals():
                    del result
                del image
                bitmap.close()
                page.close()
                gc.collect()
        finally:
            document.close()
    text = "\n".join(recognized)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    max_rss = None
    if resource is not None:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        max_rss = int(usage.ru_maxrss)
    return {
        "engine_version": version("rapidocr"),
        "runtime_version": version("onnxruntime"),
        "page_count": page_count,
        "required_terms_matched": [
            term.casefold() in text.casefold() for term in required_terms
        ],
        "duration_ms": elapsed_ms,
        "max_rss": max_rss,
        "model_sha256": [
            model["sha256"] for model in discover_models()
        ],
    }


def assert_no_network(action: Callable[[], object]) -> object:
    """Run an action while rejecting Python socket network access."""

    def denied(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network disabled")

    with ExitStack() as stack:
        stack.enter_context(patch.object(socket.socket, "connect", denied))
        stack.enter_context(patch.object(socket.socket, "connect_ex", denied))
        stack.enter_context(patch("socket.create_connection", denied))
        return action()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--require-term", action="append", default=[])
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        manifest = _manifest()
        if args.manifest_out:
            args.manifest_out.parent.mkdir(parents=True, exist_ok=True)
            args.manifest_out.write_text(
                json.dumps(
                    manifest,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
        result: dict[str, object] = {"manifest": manifest}
        if args.fixture:
            action = lambda: verify_fixture(
                args.fixture,
                tuple(args.require_term),
            )
            verification = assert_no_network(action) if args.offline else action()
            result["verification"] = verification
            if not all(verification["required_terms_matched"]):
                raise RuntimeError("required OCR fixture terms were not recognized")
        if args.json:
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "message": "OCR gate verification failed",
                },
                sort_keys=True,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
