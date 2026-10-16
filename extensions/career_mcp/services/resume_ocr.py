"""Bounded page orchestration for local resume OCR."""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import Protocol

from ..domain.ocr import (
    OCR_PAGE_FAILED,
    OCR_RUNTIME_UNAVAILABLE,
    OcrLine,
    PageSelection,
    build_extraction_metadata,
    build_native_page,
    build_ocr_page,
    merge_page_text,
    select_page_text,
)

MIN_NATIVE_PAGE_CHARS = 80
MIN_RESUME_CHARS = 20
MAX_OCR_PAGES = 10
OCR_DPI = 200
MAX_RENDER_SIDE = 4096
MAX_RENDER_PIXELS = 16_000_000

_OCR_WORKFLOW_LOCK = threading.Lock()


class ResumeOcrError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class NativePdfPage:
    page_number: int
    text: str


@dataclass(frozen=True)
class RenderedPage:
    image: object
    width: int
    height: int
    close: Callable[[], None]


@dataclass(frozen=True)
class ResumeOcrResult:
    text: str
    extraction_method: str
    metadata: dict[str, object]


class OcrEngine(Protocol):
    @property
    def identity(self) -> dict[str, object]:
        raise NotImplementedError

    def recognize(
        self,
        image: object,
        *,
        page_number: int,
    ) -> Sequence[OcrLine]:
        raise NotImplementedError


class PdfPageRenderer(Protocol):
    def render(
        self,
        raw_pdf: bytes,
        page_number: int,
        *,
        dpi: int,
    ) -> RenderedPage:
        raise NotImplementedError


class PdfiumPageRenderer:
    def __init__(
        self,
        *,
        document_factory: Callable[[bytes], object] | None = None,
    ) -> None:
        self._document_factory = (
            document_factory or self._default_document_factory
        )

    def render(
        self,
        raw_pdf: bytes,
        page_number: int,
        *,
        dpi: int,
    ) -> RenderedPage:
        document = None
        page = None
        bitmap = None
        try:
            document = self._document_factory(raw_pdf)
            page = document[page_number - 1]
            width = float(page.get_width())
            height = float(page.get_height())
            if (
                dpi <= 0
                or not math.isfinite(width)
                or not math.isfinite(height)
                or width <= 0
                or height <= 0
            ):
                raise ValueError("invalid PDF page dimensions")
            scale = min(
                dpi / 72,
                MAX_RENDER_SIDE / width,
                MAX_RENDER_SIDE / height,
                math.sqrt(MAX_RENDER_PIXELS / (width * height)),
            )
            bitmap = page.render(scale=scale)
            image = bitmap.to_numpy()
            rendered_height, rendered_width = image.shape[:2]
            resources = (bitmap, page, document)
            closed = False

            def close() -> None:
                nonlocal closed
                if closed:
                    return
                closed = True
                for resource in resources:
                    try:
                        resource.close()
                    except Exception:
                        pass

            return RenderedPage(
                image=image,
                width=int(rendered_width),
                height=int(rendered_height),
                close=close,
            )
        except Exception as exc:
            for resource in (bitmap, page, document):
                if resource is None:
                    continue
                try:
                    resource.close()
                except Exception:
                    pass
            raise ResumeOcrError(
                "OCR_FAILED",
                "could not render PDF page for local OCR",
            ) from exc

    @staticmethod
    def _default_document_factory(raw_pdf: bytes) -> object:
        import pypdfium2 as pdfium

        return pdfium.PdfDocument(raw_pdf)


class ResumeOcrService:
    def __init__(
        self,
        *,
        engine_factory: Callable[[], OcrEngine],
        renderer: PdfPageRenderer,
    ) -> None:
        self._engine_factory = engine_factory
        self._renderer = renderer

    def extract(
        self,
        pages: Sequence[NativePdfPage],
        *,
        raw_pdf: bytes,
    ) -> ResumeOcrResult:
        native = {
            page.page_number: build_native_page(
                page.page_number,
                page.text,
            )
            for page in pages
        }
        sparse = [
            page
            for page in pages
            if len(native[page.page_number].text) < MIN_NATIVE_PAGE_CHARS
        ]
        if len(sparse) > MAX_OCR_PAGES:
            raise ResumeOcrError(
                "OCR_PAGE_LIMIT",
                "PDF requires OCR on more than 10 pages",
            )
        if not sparse:
            return self._result(
                tuple(native.values()),
                total_pages=len(pages),
                engine=None,
            )

        with _OCR_WORKFLOW_LOCK:
            try:
                engine = self._engine_factory()
            except ResumeOcrError as exc:
                if exc.code != "OCR_UNAVAILABLE":
                    raise
                return self._fallback(
                    pages,
                    native,
                    warning=OCR_RUNTIME_UNAVAILABLE,
                    failure_code="OCR_UNAVAILABLE",
                )
            except Exception as exc:
                raise ResumeOcrError(
                    "OCR_UNAVAILABLE",
                    "local OCR runtime is unavailable",
                ) from exc

            selections: list[PageSelection] = []
            page_failed = False
            sparse_numbers = {page.page_number for page in sparse}
            for page in pages:
                selection = native[page.page_number]
                if page.page_number not in sparse_numbers:
                    selections.append(selection)
                    continue
                rendered: RenderedPage | None = None
                try:
                    rendered = self._renderer.render(
                        raw_pdf,
                        page.page_number,
                        dpi=OCR_DPI,
                    )
                    lines = engine.recognize(
                        rendered.image,
                        page_number=page.page_number,
                    )
                    selection = select_page_text(
                        selection.text,
                        build_ocr_page(page.page_number, lines),
                    )
                except Exception:
                    page_failed = True
                    selection = replace(
                        selection,
                        ocr_attempted=True,
                        warning_codes=(OCR_PAGE_FAILED,),
                    )
                finally:
                    if rendered is not None:
                        rendered.close()
                selections.append(selection)

            return self._result(
                selections,
                total_pages=len(pages),
                engine=engine.identity,
                failure_code="OCR_FAILED" if page_failed else None,
            )

    def _fallback(
        self,
        pages: Sequence[NativePdfPage],
        native: dict[int, PageSelection],
        *,
        warning: str,
        failure_code: str,
    ) -> ResumeOcrResult:
        selections = [
            (
                replace(
                    native[page.page_number],
                    ocr_attempted=True,
                    warning_codes=(warning,),
                )
                if len(native[page.page_number].text)
                < MIN_NATIVE_PAGE_CHARS
                else native[page.page_number]
            )
            for page in pages
        ]
        return self._result(
            selections,
            total_pages=len(pages),
            engine=None,
            failure_code=failure_code,
        )

    @staticmethod
    def _result(
        selections: Sequence[PageSelection],
        *,
        total_pages: int,
        engine: dict[str, object] | None,
        failure_code: str | None = None,
    ) -> ResumeOcrResult:
        text = merge_page_text(selections)
        if len(text) < MIN_RESUME_CHARS:
            raise ResumeOcrError(
                failure_code or "NO_EXTRACTABLE_TEXT",
                (
                    "local OCR could not recover sufficient resume text"
                    if failure_code
                    else "resume contains too little extractable text"
                ),
            )
        metadata = build_extraction_metadata(
            selections,
            total_pages=total_pages,
            engine=engine,
        )
        return ResumeOcrResult(
            text=text,
            extraction_method=str(metadata["method"]),
            metadata=metadata,
        )
