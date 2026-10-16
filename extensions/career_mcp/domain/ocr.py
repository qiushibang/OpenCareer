"""Pure values and selection rules for local resume OCR."""

from __future__ import annotations

import copy
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

MIN_OCR_LINE_CONFIDENCE = 0.50
LOW_OCR_CONFIDENCE = 0.85
MIN_OCR_PAGE_CHARS = 40

OCR_DID_NOT_IMPROVE = "OCR_DID_NOT_IMPROVE"
OCR_LOW_CONFIDENCE = "OCR_LOW_CONFIDENCE"
OCR_SPARSE_TEXT = "OCR_SPARSE_TEXT"
OCR_RUNTIME_UNAVAILABLE = "OCR_RUNTIME_UNAVAILABLE"
OCR_PAGE_FAILED = "OCR_PAGE_FAILED"

Polygon = tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    polygon: Polygon

    def __post_init__(self) -> None:
        if (
            not isinstance(self.confidence, (int, float))
            or not math.isfinite(self.confidence)
            or not 0 <= self.confidence <= 1
        ):
            raise ValueError("confidence must be between 0 and 1")
        if len(self.polygon) != 4 or any(
            len(point) != 2
            or any(
                not isinstance(coordinate, (int, float))
                or not math.isfinite(coordinate)
                for coordinate in point
            )
            for point in self.polygon
        ):
            raise ValueError("polygon must contain four finite points")


@dataclass(frozen=True)
class OcrPage:
    page_number: int
    text: str
    accepted_lines: tuple[OcrLine, ...]
    mean_confidence: float | None

    def __post_init__(self) -> None:
        _validate_page_number(self.page_number)
        if (
            self.mean_confidence is not None
            and (
                not math.isfinite(self.mean_confidence)
                or not 0 <= self.mean_confidence <= 1
            )
        ):
            raise ValueError("mean_confidence must be between 0 and 1")


@dataclass(frozen=True)
class PageSelection:
    page_number: int
    text: str
    method: Literal["native", "ocr"]
    ocr_attempted: bool
    mean_confidence: float | None
    ocr_characters: int
    warning_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _validate_page_number(self.page_number)
        if self.method not in {"native", "ocr"}:
            raise ValueError("method must be native or ocr")
        if self.ocr_characters < 0:
            raise ValueError("ocr_characters cannot be negative")
        if (
            self.mean_confidence is not None
            and (
                not math.isfinite(self.mean_confidence)
                or not 0 <= self.mean_confidence <= 1
            )
        ):
            raise ValueError("mean_confidence must be between 0 and 1")


def order_lines(lines: Sequence[OcrLine]) -> tuple[OcrLine, ...]:
    if not lines:
        return ()
    heights = sorted(
        max(point[1] for point in line.polygon)
        - min(point[1] for point in line.polygon)
        for line in lines
    )
    tolerance = heights[len(heights) // 2] * 0.5
    positioned = sorted(
        lines,
        key=lambda line: (
            min(point[1] for point in line.polygon),
            min(point[0] for point in line.polygon),
            line.text,
        ),
    )
    groups: list[list[OcrLine]] = []
    group_tops: list[float] = []
    for line in positioned:
        top = min(point[1] for point in line.polygon)
        if not groups or abs(top - group_tops[-1]) > tolerance:
            groups.append([line])
            group_tops.append(top)
        else:
            groups[-1].append(line)
    return tuple(
        line
        for group in groups
        for line in sorted(
            group,
            key=lambda item: (
                min(point[0] for point in item.polygon),
                item.text,
            ),
        )
    )


def build_ocr_page(
    page_number: int,
    lines: Sequence[OcrLine],
) -> OcrPage:
    accepted = tuple(
        line
        for line in order_lines(lines)
        if line.confidence >= MIN_OCR_LINE_CONFIDENCE
        and _normalize_text(line.text)
    )
    text = _normalize_text("\n".join(line.text for line in accepted))
    weights = [
        (len(_normalize_text(line.text)), line.confidence)
        for line in accepted
    ]
    characters = sum(length for length, _ in weights)
    mean_confidence = (
        sum(length * confidence for length, confidence in weights)
        / characters
        if characters
        else None
    )
    return OcrPage(
        page_number=page_number,
        text=text,
        accepted_lines=accepted,
        mean_confidence=mean_confidence,
    )


def build_native_page(page_number: int, text: str) -> PageSelection:
    return PageSelection(
        page_number=page_number,
        text=_normalize_text(text),
        method="native",
        ocr_attempted=False,
        mean_confidence=None,
        ocr_characters=0,
        warning_codes=(),
    )


def select_page_text(
    native_text: str,
    ocr_page: OcrPage,
) -> PageSelection:
    native = _normalize_text(native_text)
    if len(ocr_page.text) <= len(native):
        return PageSelection(
            page_number=ocr_page.page_number,
            text=native,
            method="native",
            ocr_attempted=True,
            mean_confidence=None,
            ocr_characters=0,
            warning_codes=(OCR_DID_NOT_IMPROVE,),
        )

    warnings: list[str] = []
    if (
        ocr_page.mean_confidence is not None
        and ocr_page.mean_confidence < LOW_OCR_CONFIDENCE
    ):
        warnings.append(OCR_LOW_CONFIDENCE)
    if len(ocr_page.text) < MIN_OCR_PAGE_CHARS:
        warnings.append(OCR_SPARSE_TEXT)
    return PageSelection(
        page_number=ocr_page.page_number,
        text=ocr_page.text,
        method="ocr",
        ocr_attempted=True,
        mean_confidence=ocr_page.mean_confidence,
        ocr_characters=len(ocr_page.text),
        warning_codes=tuple(warnings),
    )


def merge_page_text(selections: Sequence[PageSelection]) -> str:
    ordered = _ordered_unique_pages(selections)
    return "\n\n".join(page.text for page in ordered if page.text)


def build_extraction_metadata(
    selections: Sequence[PageSelection],
    *,
    total_pages: int,
    engine: dict[str, object] | None,
) -> dict[str, object]:
    if total_pages < 1:
        raise ValueError("total_pages must be positive")
    ordered = _ordered_unique_pages(selections)
    if [page.page_number for page in ordered] != list(
        range(1, total_pages + 1)
    ):
        raise ValueError("page selections must cover every PDF page")

    native_pages = [
        page.page_number for page in ordered if page.method == "native"
    ]
    ocr_pages = [
        page.page_number for page in ordered if page.method == "ocr"
    ]
    attempted_pages = [
        page.page_number for page in ordered if page.ocr_attempted
    ]
    weighted_confidence = [
        (page.mean_confidence, page.ocr_characters)
        for page in ordered
        if page.method == "ocr" and page.mean_confidence is not None
    ]
    confidence_characters = sum(
        characters for _, characters in weighted_confidence
    )
    mean_confidence = (
        sum(
            confidence * characters
            for confidence, characters in weighted_confidence
        )
        / confidence_characters
        if confidence_characters
        else None
    )
    warning_codes = sorted(
        {
            warning
            for page in ordered
            for warning in page.warning_codes
        }
    )
    if ocr_pages and engine is None:
        raise ValueError("engine is required when OCR text is selected")
    method = (
        "hybrid"
        if native_pages and ocr_pages
        else "ocr"
        if ocr_pages
        else "native"
    )
    review_required = bool(warning_codes)
    return {
        "version": 1,
        "method": method,
        "total_pages": total_pages,
        "native_pages": native_pages,
        "ocr_pages": ocr_pages,
        "ocr_attempted_pages": attempted_pages,
        "mean_confidence": mean_confidence,
        "quality": (
            "review"
            if review_required
            else "good"
            if ocr_pages
            else "native"
        ),
        "review_required": review_required,
        "warning_codes": warning_codes,
        "engine": copy.deepcopy(engine) if ocr_pages else None,
    }


def _ordered_unique_pages(
    selections: Sequence[PageSelection],
) -> tuple[PageSelection, ...]:
    page_numbers = [page.page_number for page in selections]
    if len(page_numbers) != len(set(page_numbers)):
        raise ValueError("page selections must use unique page numbers")
    return tuple(sorted(selections, key=lambda page: page.page_number))


def _validate_page_number(page_number: int) -> None:
    if not isinstance(page_number, int) or isinstance(page_number, bool):
        raise ValueError("page_number must be an integer")
    if page_number < 1:
        raise ValueError("page_number must be positive")


def _normalize_text(text: str) -> str:
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [
        re.sub(r"[^\S\n]+", " ", line).strip()
        for line in normalized.split("\n")
    ]
    return "\n".join(line for line in lines if line)
