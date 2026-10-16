import itertools
import math

import pytest

from extensions.career_mcp.domain.ocr import (
    OCR_DID_NOT_IMPROVE,
    OCR_LOW_CONFIDENCE,
    OCR_SPARSE_TEXT,
    OcrLine,
    OcrPage,
    build_extraction_metadata,
    build_native_page,
    build_ocr_page,
    merge_page_text,
    order_lines,
    select_page_text,
)


BOX_1 = ((10.0, 10.0), (70.0, 10.0), (70.0, 30.0), (10.0, 30.0))
BOX_2 = ((10.0, 60.0), (90.0, 60.0), (90.0, 80.0), (10.0, 80.0))
BOX_3 = ((10.0, 110.0), (90.0, 110.0), (90.0, 130.0), (10.0, 130.0))
ENGINE = {
    "name": "rapidocr-onnxruntime",
    "version": "3.9.2",
    "model_ids": [
        "PP-OCRv6_det_small",
        "ch_ppocr_mobile_v2.0_cls_mobile",
        "PP-OCRv6_rec_small",
    ],
    "model_sha256": ["a" * 64, "b" * 64, "c" * 64],
}


@pytest.mark.parametrize("confidence", [-0.01, 1.01, math.nan])
def test_ocr_line_rejects_invalid_confidence(confidence):
    with pytest.raises(ValueError, match="confidence"):
        OcrLine("Python", confidence, BOX_1)


@pytest.mark.parametrize(
    "polygon",
    [
        BOX_1[:3],
        ((math.inf, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
    ],
)
def test_ocr_line_rejects_invalid_polygon(polygon):
    with pytest.raises(ValueError, match="polygon"):
        OcrLine("Python", 0.9, polygon)


def test_ocr_page_rejects_invalid_page_or_mean_confidence():
    with pytest.raises(ValueError, match="page_number"):
        OcrPage(0, "Python", (), 0.9)
    with pytest.raises(ValueError, match="mean_confidence"):
        OcrPage(1, "Python", (), 1.1)


def test_order_lines_is_stable_across_input_permutations():
    lines = (
        OcrLine(
            "right",
            0.90,
            ((150.0, 10.0), (210.0, 10.0), (210.0, 30.0), (150.0, 30.0)),
        ),
        OcrLine("next", 0.80, BOX_2),
        OcrLine(
            "left",
            0.95,
            ((10.0, 12.0), (70.0, 12.0), (70.0, 32.0), (10.0, 32.0)),
        ),
    )

    for permutation in itertools.permutations(lines):
        assert [line.text for line in order_lines(permutation)] == [
            "left",
            "right",
            "next",
        ]


def test_build_ocr_page_filters_noise_and_weights_confidence_by_characters():
    page = build_ocr_page(
        2,
        (
            OcrLine("noise", 0.49, BOX_1),
            OcrLine("Python", 0.90, BOX_2),
            OcrLine("人工智能", 0.80, BOX_3),
        ),
    )

    assert page.text == "Python\n人工智能"
    assert [line.text for line in page.accepted_lines] == ["Python", "人工智能"]
    assert page.mean_confidence == pytest.approx(
        (6 * 0.90 + 4 * 0.80) / 10
    )


def test_select_page_text_uses_ocr_only_when_it_is_strictly_more_complete():
    ocr_page = build_ocr_page(
        1,
        (OcrLine("Python Engineer", 0.95, BOX_1),),
    )

    selected = select_page_text("Python", ocr_page)
    tied = select_page_text("Python Engineer", ocr_page)

    assert selected.method == "ocr"
    assert selected.text == "Python Engineer"
    assert selected.warning_codes == (OCR_SPARSE_TEXT,)
    assert tied.method == "native"
    assert tied.text == "Python Engineer"
    assert tied.mean_confidence is None
    assert tied.warning_codes == (OCR_DID_NOT_IMPROVE,)


def test_select_page_text_marks_low_confidence_selected_ocr_for_review():
    ocr_page = build_ocr_page(
        1,
        (OcrLine("A" * 40, 0.84, BOX_1),),
    )

    selected = select_page_text("short", ocr_page)

    assert selected.method == "ocr"
    assert selected.warning_codes == (OCR_LOW_CONFIDENCE,)


def test_merge_and_metadata_preserve_page_order_and_hybrid_provenance():
    page_1 = build_native_page(1, "Native page")
    page_2 = select_page_text(
        "",
        build_ocr_page(
            2,
            (OcrLine("B" * 40, 0.80, BOX_1),),
        ),
    )
    page_3 = select_page_text(
        "",
        build_ocr_page(
            3,
            (OcrLine("C" * 60, 0.90, BOX_1),),
        ),
    )

    merged = merge_page_text((page_3, page_1, page_2))
    metadata = build_extraction_metadata(
        (page_3, page_1, page_2),
        total_pages=3,
        engine=ENGINE,
    )

    assert merged == f"Native page\n\n{'B' * 40}\n\n{'C' * 60}"
    assert metadata == {
        "version": 1,
        "method": "hybrid",
        "total_pages": 3,
        "native_pages": [1],
        "ocr_pages": [2, 3],
        "ocr_attempted_pages": [2, 3],
        "mean_confidence": pytest.approx(
            (40 * 0.80 + 60 * 0.90) / 100
        ),
        "quality": "review",
        "review_required": True,
        "warning_codes": [OCR_LOW_CONFIDENCE],
        "engine": ENGINE,
    }


def test_native_metadata_does_not_claim_an_ocr_engine():
    page = build_native_page(1, "Native resume text")

    metadata = build_extraction_metadata(
        (page,),
        total_pages=1,
        engine=ENGINE,
    )

    assert metadata["method"] == "native"
    assert metadata["quality"] == "native"
    assert metadata["review_required"] is False
    assert metadata["engine"] is None


@pytest.mark.parametrize(
    "pages,total_pages,message",
    [
        ((build_native_page(1, "one"),), 2, "cover"),
        (
            (
                build_native_page(1, "one"),
                build_native_page(1, "duplicate"),
            ),
            2,
            "unique",
        ),
    ],
)
def test_metadata_rejects_incomplete_or_duplicate_page_sets(
    pages,
    total_pages,
    message,
):
    with pytest.raises(ValueError, match=message):
        build_extraction_metadata(
            pages,
            total_pages=total_pages,
            engine=None,
        )
