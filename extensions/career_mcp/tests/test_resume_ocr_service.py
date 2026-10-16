import threading
import time

import pytest

from extensions.career_mcp.domain.ocr import (
    OCR_PAGE_FAILED,
    OCR_RUNTIME_UNAVAILABLE,
    OcrLine,
)
from extensions.career_mcp.services.resume_ocr import (
    NativePdfPage,
    PdfiumPageRenderer,
    RenderedPage,
    ResumeOcrError,
    ResumeOcrService,
)


BOX = ((10.0, 10.0), (100.0, 10.0), (100.0, 30.0), (10.0, 30.0))
ENGINE_IDENTITY = {
    "name": "rapidocr-onnxruntime",
    "version": "3.9.2",
    "model_ids": ["det", "cls", "rec"],
    "model_sha256": ["a" * 64, "b" * 64, "c" * 64],
}


class FakeRenderer:
    def __init__(self):
        self.calls = []
        self.closed = []

    def render(self, raw_pdf, page_number, *, dpi):
        self.calls.append((raw_pdf, page_number, dpi))
        return RenderedPage(
            image={"page_number": page_number},
            width=100,
            height=200,
            close=lambda: self.closed.append(page_number),
        )


class FakeEngine:
    identity = ENGINE_IDENTITY

    def __init__(self, results=None):
        self.results = results or {}
        self.calls = []

    def recognize(self, image, *, page_number):
        self.calls.append((image, page_number))
        result = self.results.get(page_number, ())
        if isinstance(result, Exception):
            raise result
        return result


class EngineFactory:
    def __init__(self, engine=None, error=None):
        self.engine = engine
        self.error = error
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.engine


def _line(text, confidence=0.95):
    return OcrLine(text, confidence, BOX)


def test_native_only_pages_do_not_initialize_or_render_ocr():
    renderer = FakeRenderer()
    factory = EngineFactory(FakeEngine())
    service = ResumeOcrService(
        engine_factory=factory,
        renderer=renderer,
    )

    result = service.extract(
        (NativePdfPage(1, "N" * 80),),
        raw_pdf=b"%PDF-native",
    )

    assert result.text == "N" * 80
    assert result.extraction_method == "native"
    assert result.metadata["engine"] is None
    assert factory.calls == 0
    assert renderer.calls == []


def test_hybrid_pdf_renders_only_sparse_pages_and_releases_each_image():
    renderer = FakeRenderer()
    engine = FakeEngine({2: (_line("O" * 40),)})
    factory = EngineFactory(engine)
    service = ResumeOcrService(
        engine_factory=factory,
        renderer=renderer,
    )

    result = service.extract(
        (
            NativePdfPage(1, "N" * 80),
            NativePdfPage(2, "short"),
        ),
        raw_pdf=b"%PDF-hybrid",
    )

    assert result.text == f"{'N' * 80}\n\n{'O' * 40}"
    assert result.extraction_method == "hybrid"
    assert result.metadata["native_pages"] == [1]
    assert result.metadata["ocr_pages"] == [2]
    assert result.metadata["ocr_attempted_pages"] == [2]
    assert factory.calls == 1
    assert renderer.calls == [(b"%PDF-hybrid", 2, 200)]
    assert engine.calls == [({"page_number": 2}, 2)]
    assert renderer.closed == [2]


def test_more_than_ten_sparse_pages_fails_before_engine_initialization():
    renderer = FakeRenderer()
    factory = EngineFactory(FakeEngine())
    service = ResumeOcrService(
        engine_factory=factory,
        renderer=renderer,
    )

    with pytest.raises(ResumeOcrError) as error:
        service.extract(
            tuple(NativePdfPage(index, "") for index in range(1, 12)),
            raw_pdf=b"%PDF-eleven",
        )

    assert error.value.code == "OCR_PAGE_LIMIT"
    assert factory.calls == 0
    assert renderer.calls == []


def test_unavailable_runtime_degrades_when_native_text_is_still_sufficient():
    renderer = FakeRenderer()
    factory = EngineFactory(
        error=ResumeOcrError("OCR_UNAVAILABLE", "OCR runtime unavailable")
    )
    service = ResumeOcrService(
        engine_factory=factory,
        renderer=renderer,
    )

    result = service.extract(
        (
            NativePdfPage(1, "native fallback has enough text"),
            NativePdfPage(2, ""),
        ),
        raw_pdf=b"%PDF-fallback",
    )

    assert result.extraction_method == "native"
    assert result.metadata["review_required"] is True
    assert result.metadata["warning_codes"] == [OCR_RUNTIME_UNAVAILABLE]
    assert result.metadata["ocr_attempted_pages"] == [1, 2]
    assert renderer.calls == []


def test_unavailable_runtime_fails_when_native_text_is_insufficient():
    service = ResumeOcrService(
        engine_factory=EngineFactory(
            error=ResumeOcrError(
                "OCR_UNAVAILABLE",
                "OCR runtime unavailable",
            )
        ),
        renderer=FakeRenderer(),
    )

    with pytest.raises(ResumeOcrError) as error:
        service.extract(
            (NativePdfPage(1, "short"),),
            raw_pdf=b"%PDF-empty",
        )

    assert error.value.code == "OCR_UNAVAILABLE"


def test_page_failure_degrades_with_warning_and_closes_rendered_page():
    renderer = FakeRenderer()
    engine = FakeEngine({2: RuntimeError("private engine detail")})
    service = ResumeOcrService(
        engine_factory=EngineFactory(engine),
        renderer=renderer,
    )

    result = service.extract(
        (
            NativePdfPage(1, "N" * 80),
            NativePdfPage(2, ""),
        ),
        raw_pdf=b"%PDF-page-failure",
    )

    assert result.metadata["warning_codes"] == [OCR_PAGE_FAILED]
    assert result.metadata["review_required"] is True
    assert renderer.closed == [2]
    assert "private engine detail" not in str(result)


def test_page_failure_returns_stable_error_when_no_safe_fallback_exists():
    service = ResumeOcrService(
        engine_factory=EngineFactory(
            FakeEngine({1: RuntimeError("private engine detail")})
        ),
        renderer=FakeRenderer(),
    )

    with pytest.raises(ResumeOcrError) as error:
        service.extract(
            (NativePdfPage(1, "short"),),
            raw_pdf=b"%PDF-page-failure",
        )

    assert error.value.code == "OCR_FAILED"
    assert "private engine detail" not in str(error.value)


def test_successful_ocr_with_too_little_final_text_is_rejected():
    service = ResumeOcrService(
        engine_factory=EngineFactory(
            FakeEngine({1: (_line("tiny"),)})
        ),
        renderer=FakeRenderer(),
    )

    with pytest.raises(ResumeOcrError) as error:
        service.extract(
            (NativePdfPage(1, ""),),
            raw_pdf=b"%PDF-too-short",
        )

    assert error.value.code == "NO_EXTRACTABLE_TEXT"


def test_sparse_workflows_never_run_engine_inference_concurrently():
    active = 0
    maximum_active = 0
    state_lock = threading.Lock()

    class SlowEngine(FakeEngine):
        def recognize(self, image, *, page_number):
            nonlocal active, maximum_active
            with state_lock:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.05)
            with state_lock:
                active -= 1
            return (_line("recognized resume text has enough characters"),)

    service = ResumeOcrService(
        engine_factory=EngineFactory(SlowEngine()),
        renderer=FakeRenderer(),
    )
    results = []

    def run():
        results.append(
            service.extract(
                (NativePdfPage(1, ""),),
                raw_pdf=b"%PDF-concurrent",
            )
        )

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(results) == 2
    assert maximum_active == 1


class FakeArray:
    def __init__(self, height, width):
        self.shape = (height, width, 3)


class FakeBitmap:
    def __init__(self, height, width):
        self.height = height
        self.width = width
        self.closed = 0

    def to_numpy(self):
        return FakeArray(self.height, self.width)

    def close(self):
        self.closed += 1


class FakePdfPage:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.render_scales = []
        self.bitmap = None
        self.closed = 0

    def get_width(self):
        return self.width

    def get_height(self):
        return self.height

    def render(self, *, scale):
        self.render_scales.append(scale)
        self.bitmap = FakeBitmap(
            max(1, round(self.height * scale)),
            max(1, round(self.width * scale)),
        )
        return self.bitmap

    def close(self):
        self.closed += 1


class FakePdfDocument:
    def __init__(self, page):
        self.page = page
        self.indices = []
        self.closed = 0

    def __getitem__(self, index):
        self.indices.append(index)
        return self.page

    def close(self):
        self.closed += 1


def test_pdfium_renderer_uses_200_dpi_and_releases_all_resources_once():
    page = FakePdfPage(612, 792)
    document = FakePdfDocument(page)
    renderer = PdfiumPageRenderer(
        document_factory=lambda raw: document,
    )

    rendered = renderer.render(
        b"%PDF-render",
        1,
        dpi=200,
    )
    rendered.close()
    rendered.close()

    assert document.indices == [0]
    assert page.render_scales == [pytest.approx(200 / 72)]
    assert rendered.width == 1700
    assert rendered.height == 2200
    assert page.bitmap.closed == 1
    assert page.closed == 1
    assert document.closed == 1


def test_pdfium_renderer_scales_huge_pages_within_side_and_pixel_limits():
    page = FakePdfPage(10_000, 10_000)
    document = FakePdfDocument(page)
    renderer = PdfiumPageRenderer(
        document_factory=lambda raw: document,
    )

    rendered = renderer.render(
        b"%PDF-huge",
        1,
        dpi=200,
    )

    assert rendered.width <= 4096
    assert rendered.height <= 4096
    assert rendered.width * rendered.height <= 16_000_000
    rendered.close()
