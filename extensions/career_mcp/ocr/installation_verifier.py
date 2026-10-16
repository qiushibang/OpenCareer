"""Offline self-check for the packaged local OCR runtime."""

from __future__ import annotations

import argparse
import json
import socket
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from ..domain.resume import extract_resume_text
from ..services.resume_ocr import PdfiumPageRenderer, ResumeOcrService
from .rapidocr_engine import RapidOcrEngine


def _without_network(action: Callable[[], object]) -> object:
    def denied(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network disabled")

    with ExitStack() as stack:
        stack.enter_context(patch.object(socket.socket, "connect", denied))
        stack.enter_context(patch.object(socket.socket, "connect_ex", denied))
        stack.enter_context(patch("socket.create_connection", denied))
        return action()


def verify_installation(
    fixture: Path,
    *,
    required_terms: tuple[str, ...],
) -> dict[str, object]:
    raw_pdf = fixture.read_bytes()
    ocr_service = ResumeOcrService(
        engine_factory=RapidOcrEngine,
        renderer=PdfiumPageRenderer(),
    )
    extracted = _without_network(
        lambda: extract_resume_text(
            filename=fixture.name,
            mime="application/pdf",
            raw_bytes=raw_pdf,
            ocr_service=ocr_service,
        )
    )
    text = extracted.text  # type: ignore[union-attr]
    metadata = extracted.extraction_metadata  # type: ignore[union-attr]
    matches = [
        term.casefold() in text.casefold() for term in required_terms
    ]
    engine = metadata.get("engine")
    if not isinstance(engine, dict) or not all(matches):
        raise RuntimeError("packaged OCR verification failed")
    return {
        "ok": True,
        "extraction_method": extracted.extraction_method,  # type: ignore[union-attr]
        "pages": {
            "total": metadata["total_pages"],
            "ocr": metadata["ocr_pages"],
        },
        "required_terms_matched": matches,
        "engine": engine,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--require-term", action="append", default=[])
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        result = verify_installation(
            args.fixture,
            required_terms=tuple(args.require_term),
        )
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except Exception:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "OCR_INSTALLATION_VERIFICATION_FAILED",
                },
                sort_keys=True,
            )
        )
        return 1
