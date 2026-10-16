# Scanned PDF Resume OCR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add local, offline, page-level OCR fallback for scanned PDF resumes while preserving the existing private staging, Agent preview, and explicit five-section confirmation workflow.

**Architecture:** The existing PDF importer remains the only entry point. Pure OCR selection and quality logic lives in `domain/ocr.py`; `ResumeOcrService` renders only sparse PDF pages and invokes an injected engine; `RapidOcrEngine` is the sole production adapter and validates bundled model hashes before inference. Schema v9 stores deterministic provenance on the existing `resume_imports` row, and HTTP, MCP, Skill, and GUI expose only non-sensitive method and warning metadata.

**Tech Stack:** Python 3.12, SQLite, `pypdf`, `pypdfium2`, RapidOCR 3.9.2, ONNX Runtime 1.19.2, OpenCV 4.10.0.84, NumPy 1.26.4, FastAPI, FastMCP, React 18, TypeScript, Vitest, pytest, PyInstaller, Tauri

---

## Scope And Stop Conditions

This plan implements only scanned and hybrid PDF fallback. TXT and DOCX keep
their existing extraction path. PNG/JPEG input, cloud OCR, Provider vision,
automatic correction, layout reconstruction, and automatic fact confirmation
remain out of scope.

Gate 0 is a hard stop. Do not add RapidOCR or ONNX Runtime to production
dependencies and do not begin Tasks 2-11 unless all of these are proven:

1. Python 3.12 wheels exist for macOS arm64, macOS x86_64, and Windows x86_64.
2. A clean environment recognizes the committed Chinese and mixed Chinese/English fixtures.
3. A second recognition run succeeds with network access disabled.
4. Detection, classification/orientation, and recognition model files are local, identified,
   hashed, and redistributable.
5. PyInstaller includes runtime dynamic libraries and all fixed model files.

If any check fails, record the exact evidence in
`docs/ocr/2026-08-10-gate0-evidence.md` and stop. Do not silently substitute a
cloud service, system OCR, Tesseract, or a different engine.

## File Map

**Create**

- `config/ocr-model-manifest.json`: generated, version-controlled engine/model identity, size, hash, and license data.
- `packaging/generate_ocr_fixtures.py`: one-time generator for non-private scanned Gate 0 PDFs.
- `packaging/verify_ocr_runtime.py`: deterministic Gate 0 wheel, model, offline, and packaged-runtime checks.
- `.github/workflows/ocr-gate0.yml`: manual Python 3.12 macOS arm64/x64 and Windows x64 packaging spike.
- `docs/ocr/2026-08-10-gate0-evidence.md`: measured Gate 0 evidence and decision.
- `extensions/career_mcp/domain/ocr.py`: immutable OCR values and pure ordering, confidence, selection, quality, and provenance functions.
- `extensions/career_mcp/services/resume_ocr.py`: render limits, one-workflow concurrency, page orchestration, lazy engine factory, and stable errors.
- `extensions/career_mcp/ocr/__init__.py`: production OCR adapter package.
- `extensions/career_mcp/ocr/rapidocr_engine.py`: manifest-validated RapidOCR adapter with no network behavior.
- `extensions/career_mcp/tests/test_ocr_domain.py`: pure OCR behavior tests.
- `extensions/career_mcp/tests/test_resume_ocr_service.py`: fake renderer/engine, limits, fallback, and concurrency tests.
- `extensions/career_mcp/tests/test_rapidocr_engine.py`: manifest, hash, lazy import, and output adapter tests.
- `extensions/career_mcp/tests/fixtures/ocr/chinese-scanned.pdf`: synthetic non-private Chinese scanned resume.
- `extensions/career_mcp/tests/fixtures/ocr/mixed-scanned.pdf`: synthetic non-private Chinese/English scanned resume.
- `extensions/career_mcp/tests/fixtures/ocr/hybrid.pdf`: one native page plus one scanned page.
- `extensions/career_mcp/tests/fixtures/ocr/low-quality-skewed.pdf`: degraded synthetic page for review warning.
- `extensions/career_mcp/tests/test_ocr_offline_acceptance.py`: real local engine acceptance and no-artifact checks.
- `surfaces/gui/src/careerResumeImport.ts`: pure OCR prompt and user-message mapping.
- `surfaces/gui/src/careerResumeImport.test.ts`: privacy and Chinese-message regression tests.

**Modify**

- `pyproject.toml`: add exact production pins only after Gate 0 passes.
- `extensions/career_mcp/pyproject.toml`: mirror exact Career runtime pins.
- `packaging/openworker-server.spec`: collect RapidOCR, ONNX Runtime, OpenCV/Numpy dependencies, and model data.
- `packaging/build_dmg.sh`: verify the staged macOS sidecar can initialize OCR offline.
- `packaging/build_windows.ps1`: verify the staged Windows sidecar can initialize OCR offline.
- `extensions/career_mcp/domain/resume.py`: page-aware PDF extraction and `ExtractedResume` metadata fields.
- `extensions/career_mcp/services/resumes.py`: inject OCR service, persist provenance, and preserve write-after-validation behavior.
- `extensions/career_mcp/database/migrations.py`: schema v9 columns using transactional `execute()`.
- `extensions/career_mcp/database/resume_repository.py`: create/reuse mapping for extraction method and metadata.
- `extensions/career_mcp/tests/test_resume_parsing.py`: native, scanned, hybrid, encrypted, damaged, and page-limit contracts.
- `extensions/career_mcp/tests/test_resume_service.py`: persistence, idempotency, reimport, and no-partial-write contracts.
- `extensions/career_mcp/tests/test_resume_repository.py`: provenance serialization and reuse.
- `extensions/career_mcp/tests/test_migrations.py`: v8→v9 atomic migration and retry.
- `coworker/server/manager.py`: stable stage errors and response pass-through.
- `tests/test_server.py`: authenticated stage response and privacy.
- `extensions/career_mcp/server.py`: return provenance from the existing `get_resume_import_text` tool.
- `extensions/career_mcp/tests/test_resume_tools.py`: MCP provenance and privacy.
- `.coworker/skills/career-resume-import/SKILL.md`: “待确认识别结果” and low-quality review policy.
- `tests/test_skills.py`: Skill policy assertions.
- `surfaces/gui/src/api.ts`: typed extraction metadata in `StagedResume`.
- `surfaces/gui/src/components/Composer.tsx`: local-processing state, OCR notices, and metadata-only prompt.
- `surfaces/gui/src/components/Composer.resume.test.tsx`: native/OCR/review UI and prompt privacy.
- `docs/11_DEVELOPMENT_LOG.md`: Gate evidence, commands, counts, and adversarial findings.
- `docs/12_TONIGHT_PROGRESS.md`: OCR completion status and recruitment-source gate.

## Shared Contracts

Use these constants exactly:

```python
MIN_NATIVE_PAGE_CHARS = 80
MIN_OCR_LINE_CONFIDENCE = 0.50
LOW_OCR_CONFIDENCE = 0.85
MIN_OCR_PAGE_CHARS = 40
MIN_RESUME_CHARS = 20
MAX_RESUME_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 20
MAX_OCR_PAGES = 10
OCR_DPI = 200
MAX_RENDER_SIDE = 4096
MAX_RENDER_PIXELS = 16_000_000
```

Stable OCR errors:

```text
OCR_UNAVAILABLE
OCR_PAGE_LIMIT
OCR_FAILED
NO_EXTRACTABLE_TEXT
FILE_TOO_LARGE
PDF_PAGE_LIMIT
INVALID_INPUT
PERSISTENCE_ERROR
```

Public stage response:

```json
{
  "ok": true,
  "upload_token": "opaque-token",
  "source_kind": "pdf",
  "filename": "resume.pdf",
  "sha256": "64-lowercase-hex",
  "characters": 428,
  "expires_at": "2026-08-11T08:00:00Z",
  "extraction_method": "hybrid",
  "review_required": true,
  "warnings": ["OCR_LOW_CONFIDENCE"],
  "pages": {"total": 2, "ocr": [2]}
}
```

Persisted metadata v1:

```python
{
    "version": 1,
    "method": "hybrid",
    "total_pages": 2,
    "native_pages": [1],
    "ocr_pages": [2],
    "ocr_attempted_pages": [2],
    "mean_confidence": 0.82,
    "quality": "review",
    "review_required": True,
    "warning_codes": ["OCR_LOW_CONFIDENCE"],
    "engine": {
        "name": "rapidocr-onnxruntime",
        "version": "3.9.2",
        "model_ids": ["det", "cls", "rec"],
        "model_sha256": manifest_engine["model_sha256"],
    },
}
```

`manifest_engine` is loaded from the generated manifest. Runtime code and
tests must use those exact generated values rather than invented hashes.

### Task 1: Gate 0 Dependency, Model, License, Offline, And Packaging Spike

**Files:**

- Create: `packaging/verify_ocr_runtime.py`
- Create: `packaging/generate_ocr_fixtures.py`
- Create: `config/ocr-model-manifest.json`
- Create: `docs/ocr/2026-08-10-gate0-evidence.md`
- Create: `.github/workflows/ocr-gate0.yml`
- Create: `extensions/career_mcp/tests/fixtures/ocr/chinese-scanned.pdf`
- Create: `extensions/career_mcp/tests/fixtures/ocr/mixed-scanned.pdf`

- [ ] **Step 1: Prove all three Python 3.12 wheel sets are downloadable**

Run:

```bash
rm -rf /tmp/opencareer-ocr-wheels
mkdir -p /tmp/opencareer-ocr-wheels/macos-arm64
mkdir -p /tmp/opencareer-ocr-wheels/macos-x64
mkdir -p /tmp/opencareer-ocr-wheels/windows-x64
.venv/bin/python -m pip download --only-binary=:all: --no-deps \
  --python-version 312 --platform macosx_12_0_arm64 \
  --dest /tmp/opencareer-ocr-wheels/macos-arm64 \
  rapidocr==3.9.2 onnxruntime==1.19.2 \
  opencv-python==4.10.0.84 numpy==1.26.4
.venv/bin/python -m pip download --only-binary=:all: --no-deps \
  --python-version 312 --platform macosx_12_0_x86_64 \
  --dest /tmp/opencareer-ocr-wheels/macos-x64 \
  rapidocr==3.9.2 onnxruntime==1.19.2 \
  opencv-python==4.10.0.84 numpy==1.26.4
.venv/bin/python -m pip download --only-binary=:all: --no-deps \
  --python-version 312 --platform win_amd64 \
  --dest /tmp/opencareer-ocr-wheels/windows-x64 \
  rapidocr==3.9.2 onnxruntime==1.19.2 \
  opencv-python==4.10.0.84 numpy==1.26.4
```

Expected: each directory contains wheels for both requested packages. If
RapidOCR is distributed as a universal wheel, the same wheel filename may
appear in all three directories.

- [ ] **Step 2: Create an isolated candidate environment and capture the full lock**

Run:

```bash
rm -rf /tmp/opencareer-ocr-venv
python3.12 -m venv /tmp/opencareer-ocr-venv
/tmp/opencareer-ocr-venv/bin/python -m pip install --upgrade pip
/tmp/opencareer-ocr-venv/bin/pip install \
  rapidocr==3.9.2 onnxruntime==1.19.2 \
  opencv-python==4.10.0.84 numpy==1.26.4 \
  "pypdfium2>=4,<5" "pypdf>=5" pillow
/tmp/opencareer-ocr-venv/bin/pip freeze \
  > /tmp/opencareer-ocr-freeze.txt
```

Expected: clean install succeeds without source builds.

- [ ] **Step 3: Generate non-private scanned fixtures**

Create `packaging/generate_ocr_fixtures.py`:

```python
import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "extensions/career_mcp/tests/fixtures/ocr"
FONT = Path("/System/Library/Fonts/Hiragino Sans GB.ttc")

FIXTURES = {
    "chinese-scanned.pdf": (
        "测试候选人\n项目经历\n使用 Python 构建本地检索服务\n"
        "技能：Python、SQL、人工智能"
    ),
    "mixed-scanned.pdf": (
        "测试候选人 Test Candidate\nAI Engineer\n"
        "项目 Project: Local Agent\n技能 Skills: Python SQL"
    ),
}


def main() -> None:
    if not FONT.is_file():
        raise SystemExit("Hiragino Sans GB fixture font is unavailable")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(FONT), 38)
    for filename, text in FIXTURES.items():
        image = Image.new("RGB", (1654, 2339), "white")
        draw = ImageDraw.Draw(image)
        draw.multiline_text(
            (120, 140),
            text,
            fill="black",
            font=font,
            spacing=28,
        )
        generated = io.BytesIO()
        image.save(generated, "PDF", resolution=200.0)
        image.close()
        reader = PdfReader(io.BytesIO(generated.getvalue()))
        writer = PdfWriter()
        writer.add_page(reader.pages[0])
        writer.add_metadata(
            {
                "/CreationDate": "D:20260810000000Z",
                "/Producer": "OpenCareer OCR fixture generator",
            }
        )
        with (OUTPUT / filename).open("wb") as handle:
            writer.write(handle)


if __name__ == "__main__":
    main()
```

Run:

```bash
/tmp/opencareer-ocr-venv/bin/python packaging/generate_ocr_fixtures.py
shasum -a 256 extensions/career_mcp/tests/fixtures/ocr/*.pdf
```

Expected: exactly two PDFs, both contain image content and no extractable PDF
text. Generate twice with a two-second delay and require identical SHA-256
before recording both hashes in Gate 0 evidence.

- [ ] **Step 4: Add a verifier that emits model identity without OCR text**

Create `packaging/verify_ocr_runtime.py` with this interface:

```python
def discover_models() -> list[dict[str, object]]:
    """Return exactly det/cls/rec model id, package-relative path, bytes, sha256, license."""


def verify_fixture(path: Path, required_terms: tuple[str, ...]) -> dict[str, object]:
    """Run local OCR and return engine version, matched terms, duration_ms, and model hashes."""


def assert_no_network(action: Callable[[], object]) -> object:
    """Replace socket connect/create_connection and fail on any attempted network access."""


def main(argv: Sequence[str] | None = None) -> int:
    """Support --manifest-out, --fixture, --require-term, --offline, and --json."""
```

The script must:

```python
with patch("socket.socket.connect", side_effect=AssertionError("network disabled")), \
     patch("socket.create_connection", side_effect=AssertionError("network disabled")):
    result = verify_fixture(fixture, required_terms)
```

It must never print recognized text, absolute model paths, names, email
addresses, or phone numbers. JSON output may contain only versions, model IDs,
hashes, sizes, matched boolean terms, duration, and process RSS.

- [ ] **Step 5: Generate and inspect the model manifest**

Run:

```bash
/tmp/opencareer-ocr-venv/bin/python packaging/verify_ocr_runtime.py \
  --manifest-out config/ocr-model-manifest.json \
  --json
python -m json.tool config/ocr-model-manifest.json
```

Validate the generated manifest with:

```python
import json
import re
from pathlib import Path

manifest = json.loads(Path("config/ocr-model-manifest.json").read_text())
assert manifest["schema_version"] == 1
assert manifest["engine"] == {
    "name": "rapidocr-onnxruntime",
    "version": "3.9.2",
}
assert manifest["runtime"] == {
    "name": "onnxruntime",
    "version": "1.19.2",
}
assert [model["role"] for model in manifest["models"]] == [
    "det",
    "cls",
    "rec",
]
assert all(int(model["bytes"]) > 0 for model in manifest["models"])
assert all(
    re.fullmatch(r"[0-9a-f]{64}", str(model["sha256"]))
    for model in manifest["models"]
)
assert all(
    not Path(str(model["package_relative_path"])).is_absolute()
    for model in manifest["models"]
)
assert all(str(model["license"]).strip() for model in manifest["models"])
```

Paths, IDs, hashes, byte sizes, and license IDs must be generated from
installed package evidence.

- [ ] **Step 6: Run connected and disconnected fixture recognition**

Run:

```bash
/tmp/opencareer-ocr-venv/bin/python packaging/verify_ocr_runtime.py \
  --fixture extensions/career_mcp/tests/fixtures/ocr/chinese-scanned.pdf \
  --require-term 项目 --require-term Python --json
/tmp/opencareer-ocr-venv/bin/python packaging/verify_ocr_runtime.py \
  --offline \
  --fixture extensions/career_mcp/tests/fixtures/ocr/mixed-scanned.pdf \
  --require-term Python --require-term 技能 --json
```

Expected: exit 0, all required terms matched, no network attempt, and no OCR
text in stdout/stderr.

- [ ] **Step 7: Verify package licenses and record measured evidence**

Run:

```bash
/tmp/opencareer-ocr-venv/bin/pip show rapidocr onnxruntime opencv-python numpy
du -sh /tmp/opencareer-ocr-venv
/usr/bin/time -l /tmp/opencareer-ocr-venv/bin/python \
  packaging/verify_ocr_runtime.py --offline \
  --fixture extensions/career_mcp/tests/fixtures/ocr/chinese-scanned.pdf \
  --require-term Python --json
```

Write exact command results, package license sources, installed-size delta,
first-load RSS, one-page duration, and three-page duration to
`docs/ocr/2026-08-10-gate0-evidence.md`. The final line must be exactly one of:

```text
Gate 0 decision: PASS
Gate 0 decision: FAIL
```

- [ ] **Step 8: Run a clean cross-platform PyInstaller matrix**

Create a manually dispatched workflow with:

```yaml
name: OCR Gate 0
on:
  workflow_dispatch:
jobs:
  verify:
    strategy:
      fail-fast: false
      matrix:
        include:
          - os: macos-14
            python: "3.12"
            smoke: dist/verify_ocr_runtime/verify_ocr_runtime
          - os: macos-13
            python: "3.12"
            smoke: dist/verify_ocr_runtime/verify_ocr_runtime
          - os: windows-2025
            python: "3.12"
            smoke: dist/verify_ocr_runtime/verify_ocr_runtime.exe
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: python -m pip install pyinstaller rapidocr==3.9.2 onnxruntime==1.19.2 opencv-python==4.10.0.84 numpy==1.26.4 "pypdfium2>=4,<5"
      - run: python packaging/verify_ocr_runtime.py --offline --fixture extensions/career_mcp/tests/fixtures/ocr/mixed-scanned.pdf --require-term Python --require-term 技能 --json
      - run: pyinstaller --clean --noconfirm --onedir --collect-data rapidocr packaging/verify_ocr_runtime.py
      - shell: bash
        run: ${{ matrix.smoke }} --offline --fixture extensions/career_mcp/tests/fixtures/ocr/mixed-scanned.pdf --require-term Python --require-term 技能 --json
```

Expected: all three jobs recognize offline from the frozen onedir bundle.
Record run URL, runner architecture, wheel filenames, durations, and artifact
sizes in the Gate 0 evidence.

- [ ] **Step 9: Commit Gate 0 evidence only when it passes**

```bash
git add packaging/generate_ocr_fixtures.py \
  packaging/verify_ocr_runtime.py config/ocr-model-manifest.json \
  .github/workflows/ocr-gate0.yml \
  docs/ocr/2026-08-10-gate0-evidence.md \
  extensions/career_mcp/tests/fixtures/ocr/chinese-scanned.pdf \
  extensions/career_mcp/tests/fixtures/ocr/mixed-scanned.pdf
git commit -m "chore(ocr): verify offline runtime and model supply chain"
```

### Task 2: Pure OCR Domain Values, Ordering, Selection, And Quality

**Files:**

- Create: `extensions/career_mcp/domain/ocr.py`
- Create: `extensions/career_mcp/tests/test_ocr_domain.py`

- [x] **Step 1: Write RED tests for stable polygon ordering**

Add tests using:

```python
lines = [
    OcrLine("right", 0.90, ((150, 10), (210, 10), (210, 30), (150, 30))),
    OcrLine("next", 0.80, ((10, 60), (70, 60), (70, 80), (10, 80))),
    OcrLine("left", 0.95, ((10, 12), (70, 12), (70, 32), (10, 32))),
]
assert [line.text for line in order_lines(lines)] == ["left", "right", "next"]
```

Also assert identical output for every permutation of `lines`.

- [x] **Step 2: Run the domain test and verify RED**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_ocr_domain.py -q
```

Expected: collection fails because `extensions.career_mcp.domain.ocr` does not exist.

- [x] **Step 3: Implement immutable values and deterministic ordering**

Create:

```python
@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    polygon: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class OcrPage:
    page_number: int
    text: str
    accepted_lines: tuple[OcrLine, ...]
    mean_confidence: float | None


@dataclass(frozen=True)
class PageSelection:
    page_number: int
    text: str
    method: Literal["native", "ocr"]
    ocr_attempted: bool
    mean_confidence: float | None
    ocr_characters: int
    warning_codes: tuple[str, ...]


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
```

Use median line height to form a deterministic vertical tolerance, then sort
line groups by top coordinate and members by left coordinate. Validate finite
coordinates, four polygon points, confidence in `[0, 1]`, and one-based page
numbers.

- [x] **Step 4: Add RED tests for filtering and character-weighted confidence**

Use:

```python
page = build_ocr_page(
    2,
    (
        OcrLine("noise", 0.49, BOX_1),
        OcrLine("Python", 0.90, BOX_2),
        OcrLine("人工智能", 0.80, BOX_3),
    ),
)
assert page.text == "Python\n人工智能"
assert page.mean_confidence == pytest.approx((6 * 0.90 + 4 * 0.80) / 10)
```

- [x] **Step 5: Implement filtering, page selection, and quality**

Expose:

```python
def build_ocr_page(page_number: int, lines: Sequence[OcrLine]) -> OcrPage:
    accepted = tuple(
        line
        for line in order_lines(lines)
        if line.confidence >= MIN_OCR_LINE_CONFIDENCE
        and normalize_resume_text(line.text)
    )
    text = normalize_resume_text("\n".join(line.text for line in accepted))
    denominator = sum(len(normalize_resume_text(line.text)) for line in accepted)
    mean = (
        sum(
            len(normalize_resume_text(line.text)) * line.confidence
            for line in accepted
        )
        / denominator
        if denominator
        else None
    )
    return OcrPage(page_number, text, accepted, mean)


def select_page_text(native_text: str, ocr_page: OcrPage) -> PageSelection:
    native = normalize_resume_text(native_text)
    use_ocr = len(ocr_page.text) > len(native)
    warning_codes: list[str] = []
    if not use_ocr:
        warning_codes.append(OCR_DID_NOT_IMPROVE)
    if use_ocr and len(ocr_page.text) < MIN_OCR_PAGE_CHARS:
        warning_codes.append(OCR_SPARSE_TEXT)
    if (
        use_ocr
        and ocr_page.mean_confidence is not None
        and ocr_page.mean_confidence < LOW_OCR_CONFIDENCE
    ):
        warning_codes.append(OCR_LOW_CONFIDENCE)
    return PageSelection(
        page_number=ocr_page.page_number,
        text=ocr_page.text if use_ocr else native,
        method="ocr" if use_ocr else "native",
        ocr_attempted=True,
        mean_confidence=ocr_page.mean_confidence if use_ocr else None,
        ocr_characters=len(ocr_page.text) if use_ocr else 0,
        warning_codes=tuple(sorted(warning_codes)),
    )


def quality_warnings(
    selections: Sequence[PageSelection],
) -> list[str]:
    return sorted(
        {
            warning
            for item in selections
            for warning in item.warning_codes
        }
    )


def build_extraction_metadata(
    selections: Sequence[PageSelection],
    *,
    total_pages: int,
    engine: dict[str, object] | None,
) -> dict[str, object]:
    native_pages = sorted(
        item.page_number for item in selections if item.method == "native"
    )
    ocr_pages = sorted(
        item.page_number for item in selections if item.method == "ocr"
    )
    attempted = sorted(
        item.page_number for item in selections if item.ocr_attempted
    )
    weighted_confidence = [
        (item.mean_confidence, item.ocr_characters)
        for item in selections
        if item.method == "ocr" and item.mean_confidence is not None
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
    warnings = quality_warnings(selections)
    method = (
        "hybrid"
        if native_pages and ocr_pages
        else "ocr"
        if ocr_pages
        else "native"
    )
    return {
        "version": 1,
        "method": method,
        "total_pages": total_pages,
        "native_pages": native_pages,
        "ocr_pages": ocr_pages,
        "ocr_attempted_pages": attempted,
        "mean_confidence": mean_confidence,
        "quality": "review" if warnings else ("good" if ocr_pages else "native"),
        "review_required": bool(warnings),
        "warning_codes": warnings,
        "engine": engine if ocr_pages else None,
    }
```

Selection uses normalized character count and chooses OCR only when it is
strictly longer. Warnings are closed-world constants:

```python
OCR_LOW_CONFIDENCE = "OCR_LOW_CONFIDENCE"
OCR_SPARSE_TEXT = "OCR_SPARSE_TEXT"
OCR_DID_NOT_IMPROVE = "OCR_DID_NOT_IMPROVE"
OCR_RUNTIME_UNAVAILABLE = "OCR_RUNTIME_UNAVAILABLE"
OCR_PAGE_FAILED = "OCR_PAGE_FAILED"
```

- [x] **Step 6: Run pure tests**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_ocr_domain.py -q
```

Expected: all tests pass.

- [x] **Step 7: Commit**

```bash
git add extensions/career_mcp/domain/ocr.py \
  extensions/career_mcp/tests/test_ocr_domain.py
git commit -m "feat(ocr): add deterministic page selection domain"
```

### Task 3: Render Limits And Injectable OCR Orchestration

**Files:**

- Create: `extensions/career_mcp/services/resume_ocr.py`
- Create: `extensions/career_mcp/tests/test_resume_ocr_service.py`

- [x] **Step 1: Write RED tests with fake renderer and fake engine**

The tests must prove:

```python
result = service.extract(
    (
        NativePdfPage(1, "A" * 80),
        NativePdfPage(2, "short"),
    ),
    raw_pdf=b"%PDF-fixture",
)
assert renderer.calls == [2]
assert engine.calls == [2]
assert result.metadata["native_pages"] == [1]
assert result.metadata["ocr_pages"] == [2]
```

Add separate cases for no OCR initialization on all-native input, 11 sparse
pages returning `OCR_PAGE_LIMIT`, OCR unavailable with sufficient native
fallback, OCR unavailable without 20 final characters, one failed page,
oversized render dimensions, and two concurrent calls never entering engine
inference simultaneously.

- [x] **Step 2: Run and verify RED**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_resume_ocr_service.py -q
```

Expected: collection fails because `resume_ocr.py` does not exist.

- [x] **Step 3: Implement protocols and result values**

Create:

```python
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


@dataclass(frozen=True)
class ResumeOcrResult:
    text: str
    extraction_method: str
    metadata: dict[str, object]
```

`ResumeOcrError` carries only stable `code` and safe message.

- [x] **Step 4: Implement bounded rendering**

The production renderer uses `pypdfium2.PdfDocument(raw_pdf)`, renders only
the requested zero-based index, calculates the scale for 200 DPI, and reduces
scale until both dimensions are `<=4096` and total pixels are `<=16_000_000`.
It returns an in-memory BGR/RGB array accepted by RapidOCR and never writes a
temporary image.

- [x] **Step 5: Implement one-workflow concurrency and fallback**

Use one module-level `threading.Lock` around the full sparse-page workflow.
Do not lock native-only extraction. Instantiate renderer and engine lazily
only after the sparse-page count is known and within 10 pages.

Map:

```python
engine factory/model/hash failure -> OCR_UNAVAILABLE
render/inference failure with final native chars < 20 -> OCR_FAILED
render/inference failure with final native chars >= 20 -> warning + review
more than 10 sparse pages -> OCR_PAGE_LIMIT
final merged text < 20 -> NO_EXTRACTABLE_TEXT
```

- [x] **Step 6: Run service tests**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_ocr_domain.py \
  extensions/career_mcp/tests/test_resume_ocr_service.py -q
```

Expected: all tests pass and no fixture image appears under `tmp_path`.

- [x] **Step 7: Commit**

```bash
git add extensions/career_mcp/services/resume_ocr.py \
  extensions/career_mcp/tests/test_resume_ocr_service.py
git commit -m "feat(ocr): add bounded local page orchestration"
```

### Task 4: Manifest-Validated RapidOCR Production Adapter

**Files:**

- Create: `extensions/career_mcp/ocr/__init__.py`
- Create: `extensions/career_mcp/ocr/rapidocr_engine.py`
- Create: `extensions/career_mcp/tests/test_rapidocr_engine.py`
- Modify: `pyproject.toml`
- Modify: `extensions/career_mcp/pyproject.toml`

- [x] **Step 1: Write RED adapter tests**

Tests must inject fake RapidOCR results and assert:

```python
expected_ids = [model["id"] for model in manifest["models"]]
expected_hashes = [model["sha256"] for model in manifest["models"]]
assert engine.identity == {
    "name": "rapidocr-onnxruntime",
    "version": "3.9.2",
    "model_ids": expected_ids,
    "model_sha256": expected_hashes,
}
assert engine.recognize(image, page_number=1)[0] == OcrLine(
    text="Python",
    confidence=0.97,
    polygon=((1.0, 2.0), (8.0, 2.0), (8.0, 6.0), (1.0, 6.0)),
)
```

Also assert missing model, changed model hash, malformed manifest, unexpected
model role, adapter exception, and import failure all raise
`ResumeOcrError("OCR_UNAVAILABLE", safe_message)` without absolute paths.

- [x] **Step 2: Run and verify RED**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_rapidocr_engine.py -q
```

Expected: collection fails because the adapter does not exist.

- [x] **Step 3: Implement manifest loading and hash verification**

Resolve the manifest from the repository/package resource, resolve every
model using `importlib.resources`, and compare file byte length and SHA-256
before constructing RapidOCR. Reject symlinks that resolve outside the
installed package root.

- [x] **Step 4: Implement lazy RapidOCR construction**

Import RapidOCR and ONNX Runtime inside the factory, pass the three verified
model paths explicitly, disable any download/update behavior exposed by the
selected API, and normalize engine output into `OcrLine`. Do not expose raw
engine objects or model paths.

- [x] **Step 5: Add exact production dependencies after Gate 0 PASS**

Add the Gate 0 accepted exact pins to both project files:

```toml
"rapidocr==3.9.2",
"onnxruntime==1.19.2",
"opencv-python==4.10.0.84",
"numpy==1.26.4",
```

If Gate 0 selected different exact versions, use those measured versions in
both files and update the plan’s `Tech Stack` line in the same commit.

- [x] **Step 6: Run adapter and existing parsing tests**

Run:

```bash
.venv/bin/pip install -e .
.venv/bin/pytest \
  extensions/career_mcp/tests/test_rapidocr_engine.py \
  extensions/career_mcp/tests/test_resume_parsing.py -q
```

Expected: adapter tests pass; existing resume parsing remains green.

- [x] **Step 7: Commit**

```bash
git add pyproject.toml extensions/career_mcp/pyproject.toml \
  extensions/career_mcp/ocr \
  extensions/career_mcp/tests/test_rapidocr_engine.py
git commit -m "feat(ocr): add fixed offline RapidOCR adapter"
```

### Task 5: Page-Aware Resume Extraction

**Files:**

- Modify: `extensions/career_mcp/domain/resume.py`
- Modify: `extensions/career_mcp/tests/test_resume_parsing.py`

- [x] **Step 1: Write RED native/scanned/hybrid extraction tests**

Inject a fake `ResumeOcrService` and assert:

```python
native = extract_resume_text(
    filename="native.pdf",
    mime="application/pdf",
    raw_bytes=native_pdf,
    ocr_service=fake,
)
assert fake.calls == []
assert native.extraction_method == "native"
assert native.extraction_metadata["engine"] is None

hybrid = extract_resume_text(
    filename="hybrid.pdf",
    mime="application/pdf",
    raw_bytes=hybrid_pdf,
    ocr_service=fake,
)
assert fake.sparse_pages == [2]
assert hybrid.extraction_method == "hybrid"
assert hybrid.extraction_metadata["ocr_pages"] == [2]
```

Keep existing TXT/DOCX equivalence tests and assert their method is `native`.

- [x] **Step 2: Add RED safety cases**

Assert encrypted PDF, malformed PDF, 21-page PDF, 11 sparse-page PDF,
oversized bytes, and final text below 20 characters return the exact shared
error codes. Assert no error string contains extracted text.

- [x] **Step 3: Run and verify RED**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_resume_parsing.py -q
```

Expected: failures because `ExtractedResume` lacks extraction fields and the
extractor does not accept `ocr_service`.

- [x] **Step 4: Extend `ExtractedResume` and PDF parsing**

Use:

```python
@dataclass(frozen=True)
class ExtractedResume:
    filename: str
    source_kind: str
    text: str
    raw_bytes: bytes
    extraction_method: str
    extraction_metadata: dict[str, object]
```

`_extract_pdf_pages()` returns immutable one-based pages after checking
encryption and the 20-page bound. `extract_resume_text()` invokes OCR only for
PDF. TXT/DOCX return native metadata with `engine=None`, empty OCR arrays, and
one logical page.

- [x] **Step 5: Run parsing and OCR tests**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_resume_parsing.py \
  extensions/career_mcp/tests/test_ocr_domain.py \
  extensions/career_mcp/tests/test_resume_ocr_service.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add extensions/career_mcp/domain/resume.py \
  extensions/career_mcp/tests/test_resume_parsing.py
git commit -m "feat(ocr): add page-aware PDF resume extraction"
```

### Task 6: Schema v9 And Provenance Repository

**Files:**

- Modify: `extensions/career_mcp/database/migrations.py`
- Modify: `extensions/career_mcp/database/resume_repository.py`
- Modify: `extensions/career_mcp/tests/test_migrations.py`
- Modify: `extensions/career_mcp/tests/test_resume_repository.py`

- [ ] **Step 1: Write schema v9 RED tests**

Assert:

```python
assert schema_version(connection) == 9
columns = {
    row["name"]: row
    for row in connection.execute("PRAGMA table_info(resume_imports)")
}
assert columns["extraction_method"]["notnull"] == 1
assert columns["extraction_metadata_json"]["notnull"] == 1
assert row["extraction_method"] == "native"
assert json.loads(row["extraction_metadata_json"])["version"] == 1
```

Build a real v8 database row before migration. Add failure/retry coverage with
a connection proxy whose second v9 `ALTER TABLE` raises
`sqlite3.OperationalError`; prove user version remains 8 and the first column
is rolled back, then disable the fault and prove retry reaches 9.

- [ ] **Step 2: Run and verify RED**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_migrations.py \
  extensions/career_mcp/tests/test_resume_repository.py -q
```

Expected: schema assertions fail at version 8.

- [ ] **Step 3: Implement v9 with transactional `execute()`**

Set `SCHEMA_VERSION = 9`. Use individual `connection.execute()` statements:

```sql
ALTER TABLE resume_imports
ADD COLUMN extraction_method TEXT NOT NULL DEFAULT 'native'
CHECK(extraction_method IN ('native', 'ocr', 'hybrid'));

ALTER TABLE resume_imports
ADD COLUMN extraction_metadata_json TEXT NOT NULL DEFAULT '{}';
```

Backfill every existing row with valid metadata v1. Do not use
`executescript()` in the v9 block. Because historical rows do not retain
page-level extraction provenance, use the explicit compatible legacy value:

```python
{
    "version": 1,
    "method": "native",
    "total_pages": 1,
    "native_pages": [1],
    "ocr_pages": [],
    "ocr_attempted_pages": [],
    "mean_confidence": None,
    "quality": "native",
    "review_required": False,
    "warning_codes": ["LEGACY_PROVENANCE"],
    "engine": None,
}
```

- [ ] **Step 4: Extend create/reuse persistence**

`create_or_reuse_import()` accepts:

```python
extraction_method: str
extraction_metadata: dict[str, object]
```

Every active, expired, and soft-deleted reuse path refreshes extracted text,
method, metadata, filename, and token as applicable while preserving the
stable import ID. Row mapping parses JSON and never returns raw JSON text.

- [ ] **Step 5: Run migration and repository tests**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_migrations.py \
  extensions/career_mcp/tests/test_resume_repository.py -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add extensions/career_mcp/database/migrations.py \
  extensions/career_mcp/database/resume_repository.py \
  extensions/career_mcp/tests/test_migrations.py \
  extensions/career_mcp/tests/test_resume_repository.py
git commit -m "feat(ocr): persist resume extraction provenance"
```

### Task 7: Transactional Resume Service Integration

**Files:**

- Modify: `extensions/career_mcp/services/resumes.py`
- Modify: `extensions/career_mcp/tests/test_resume_service.py`

- [ ] **Step 1: Write RED success and degradation tests**

Construct `ResumeService(config, private_root=private_root,
ocr_service=fake)` and assert exact public
responses for native, OCR, hybrid, low-confidence, runtime-unavailable with
sufficient native text, and OCR failure without sufficient text.

- [ ] **Step 2: Write RED no-partial-write tests**

For extraction failure, model hash failure, repository failure, and private
file rename failure, assert:

```python
assert not list((private_root / "resumes").glob("*"))
assert connection.execute("SELECT COUNT(*) FROM resume_imports").fetchone()[0] == 0
```

For a database failure after publishing a new original, require compensation
to remove that new file. Never delete a pre-existing deduplicated original.

- [ ] **Step 3: Run and verify RED**

Run:

```bash
.venv/bin/pytest extensions/career_mcp/tests/test_resume_service.py -q
```

Expected: constructor injection and provenance assertions fail.

- [ ] **Step 4: Inject OCR lazily and persist metadata**

Add:

```python
def __init__(
    self,
    config: CareerConfig | None = None,
    *,
    private_root: Path | None = None,
    clock: Callable[[], datetime] | None = None,
    ocr_service: ResumeOcrService | None = None,
    ocr_service_factory: Callable[[], ResumeOcrService] | None = None,
) -> None:
```

Only PDF sparse-page extraction calls the factory. Pass method and metadata to
the repository and return only:

```python
"extraction_method"
"review_required"
"warnings"
"pages": {"total": int, "ocr": list[int]}
```

- [ ] **Step 5: Make file/database publication compensating**

Extract and validate fully before creating a directory or database row. Write
new originals with owner-only mode to a same-directory temporary file, flush,
`fsync`, and `os.replace`. If the database transaction fails and this call
created the target, remove it. Convert all filesystem/SQLite failures to
`PERSISTENCE_ERROR` without paths or OCR text.

- [ ] **Step 6: Return provenance to the existing MCP read path**

`get_resume_import_text()` returns text plus:

```python
"extraction_method"
"extraction_metadata"
"review_required"
"warnings"
```

It does not return private path, page images, polygons, or model paths.

- [ ] **Step 7: Run service regression**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_resume_service.py \
  extensions/career_mcp/tests/test_resume_repository.py \
  extensions/career_mcp/tests/test_resume_parsing.py -q
```

Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add extensions/career_mcp/services/resumes.py \
  extensions/career_mcp/tests/test_resume_service.py
git commit -m "feat(ocr): integrate private resume staging"
```

### Task 8: HTTP, MCP, And Skill Contracts

**Files:**

- Modify: `coworker/server/manager.py`
- Modify: `tests/test_server.py`
- Modify: `extensions/career_mcp/server.py`
- Modify: `extensions/career_mcp/tests/test_resume_tools.py`
- Modify: `.coworker/skills/career-resume-import/SKILL.md`
- Modify: `tests/test_skills.py`

- [ ] **Step 1: Write HTTP RED tests**

Add cases for non-object JSON, bad base64, each stable OCR error, and a hybrid
success. Assert the response contains method/warnings/page numbers but not:

```python
for forbidden in (
    "text", "private_path", "polygon", "model_path",
    "13800001234", "candidate@example.com",
):
    assert forbidden not in json.dumps(body)
```

- [ ] **Step 2: Write MCP and Skill RED tests**

Assert `get_resume_import_text` returns extraction metadata without paths or
images. Assert Skill text contains:

```text
待确认识别结果
姓名
联系方式
数字
日期
公司
学校
```

and still requires `preview_resume_import` followed by explicit per-section
confirmation.

- [ ] **Step 3: Run and verify RED**

Run:

```bash
.venv/bin/pytest \
  tests/test_server.py \
  extensions/career_mcp/tests/test_resume_tools.py \
  tests/test_skills.py -q
```

Expected: OCR response and Skill policy assertions fail.

- [ ] **Step 4: Implement stable HTTP and MCP pass-through**

Keep `POST /v1/career/resumes/stage`; do not add an OCR endpoint. Ensure
`stage_resume_upload()` rejects non-dict body before field access and maps
`ResumeServiceError` unchanged. Generic failures return only
`PERSISTENCE_ERROR`.

- [ ] **Step 5: Update the Skill**

Add exact policy:

```text
When extraction_method is ocr or hybrid, call the text a “待确认识别结果”.
Never describe OCR confidence as accuracy or verification.
When review_required is true, explicitly ask the user to check names,
contact details, numbers, dates, companies, and schools.
Never skip preview_resume_import or confirm any section without the user's
explicit approval of that named section.
```

- [ ] **Step 6: Run contract tests**

Run:

```bash
.venv/bin/pytest \
  tests/test_server.py \
  extensions/career_mcp/tests/test_resume_tools.py \
  tests/test_skills.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add coworker/server/manager.py tests/test_server.py \
  extensions/career_mcp/server.py \
  extensions/career_mcp/tests/test_resume_tools.py \
  .coworker/skills/career-resume-import/SKILL.md tests/test_skills.py
git commit -m "feat(ocr): expose safe resume extraction status"
```

### Task 9: GUI Local OCR Feedback And Privacy-Safe Prompt

**Files:**

- Create: `surfaces/gui/src/careerResumeImport.ts`
- Create: `surfaces/gui/src/careerResumeImport.test.ts`
- Modify: `surfaces/gui/src/api.ts`
- Modify: `surfaces/gui/src/components/Composer.tsx`
- Modify: `surfaces/gui/src/components/Composer.resume.test.tsx`

- [ ] **Step 1: Write pure prompt RED tests**

Assert:

```typescript
const prompt = careerResumeImportPrompt({
  uploadToken: "opaque-token",
  filename: "resume.pdf",
  sourceKind: "pdf",
  extractionMethod: "hybrid",
  warningCodes: ["OCR_LOW_CONFIDENCE"],
});
expect(prompt).toContain("opaque-token");
expect(prompt).toContain("hybrid");
expect(prompt).toContain("OCR_LOW_CONFIDENCE");
expect(prompt).not.toMatch(/138\d{8}|@|private_path|model_path|识别全文/);
```

- [ ] **Step 2: Write Composer RED tests**

Cover:

1. During upload: `正在本地读取简历…`.
2. Native success: no OCR notice.
3. OCR success: `已使用本地 OCR，内容尚未确认`.
4. Review success: `部分内容识别质量较低，请重点核对`.
5. OCR error: stable Chinese message and no unhandled promise rejection.
6. Prompt includes only token, filename, format, method, and warning codes.

- [ ] **Step 3: Run and verify RED**

Run:

```bash
cd surfaces/gui
npm test -- --run src/careerResumeImport.test.ts \
  src/components/Composer.resume.test.tsx
```

Expected: missing module/type failures and absent notices.

- [ ] **Step 4: Add typed response and pure mapping**

Extend `StagedResume`:

```typescript
extraction_method?: "native" | "ocr" | "hybrid";
review_required?: boolean;
warnings?: string[];
pages?: { total: number; ocr: number[] };
```

`careerResumeImportPrompt()` accepts no text, hashes, private paths, model
paths, confidence, or page images.

- [ ] **Step 5: Implement Composer feedback**

Set a temporary notice before the request, replace it with the relevant OCR
notice on success, and preserve existing native behavior. Continue sending
the existing `career-resume-import` Skill and no attachments.

- [ ] **Step 6: Run GUI focused tests**

Run:

```bash
cd surfaces/gui
npm test -- --run src/careerResumeImport.test.ts \
  src/components/Composer.resume.test.tsx
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add surfaces/gui/src/api.ts \
  surfaces/gui/src/careerResumeImport.ts \
  surfaces/gui/src/careerResumeImport.test.ts \
  surfaces/gui/src/components/Composer.tsx \
  surfaces/gui/src/components/Composer.resume.test.tsx
git commit -m "feat(gui): show local OCR review status"
```

### Task 10: Real Offline Fixtures And End-To-End Acceptance

**Files:**

- Create: `extensions/career_mcp/tests/fixtures/ocr/hybrid.pdf`
- Create: `extensions/career_mcp/tests/fixtures/ocr/low-quality-skewed.pdf`
- Create: `extensions/career_mcp/tests/test_ocr_offline_acceptance.py`

- [x] **Step 1: Add four synthetic, non-private fixtures**

Fixtures contain only invented names and facts. Record their SHA-256 in the
acceptance test. The hybrid fixture has exactly two pages: page 1 has at least
80 native characters and page 2 has no text layer.

- [x] **Step 2: Write real-engine acceptance tests**

Mark with `@pytest.mark.ocr_acceptance` and patch socket networking to fail.
Test:

```python
assert chinese["extraction_method"] == "ocr"
assert mixed["extraction_method"] == "ocr"
assert hybrid["extraction_method"] == "hybrid"
assert hybrid["pages"]["ocr"] == [2]
assert low_quality["review_required"] is True
```

Stage each fixture, call the real `get_resume_import_text`, preview all five
sections with a deterministic synthetic proposal, explicitly confirm them,
and verify Career Vault facts exist only after confirmation.

- [x] **Step 3: Assert no image/debug/network residue**

Snapshot files under `tmp_path`, repository root `artifacts`, and
`.local-state` before and after. The only new private file may be the original
PDF. Reject `.png`, `.jpg`, `.jpeg`, `.bmp`, `.npy`, `.onnx` copies, OCR text
logs, and debug visualizations.

- [x] **Step 4: Run offline acceptance**

Run:

```bash
.venv/bin/pytest \
  extensions/career_mcp/tests/test_ocr_offline_acceptance.py \
  -m ocr_acceptance -q
```

Expected: four fixtures pass with every socket attempt blocked.

- [x] **Step 5: Verify deletion semantics**

Delete each acceptance resume through the existing exact-name confirmation
path. Assert private originals are removed, extracted text is cleared, and
confirmed fact source references follow the existing soft-delete invariant.

- [ ] **Step 6: Commit**

```bash
git add extensions/career_mcp/tests/fixtures/ocr/hybrid.pdf \
  extensions/career_mcp/tests/fixtures/ocr/low-quality-skewed.pdf \
  extensions/career_mcp/tests/test_ocr_offline_acceptance.py
git commit -m "test(ocr): add offline scanned resume acceptance"
```

### Task 11: PyInstaller, macOS, And Windows Packaging Gate

**Files:**

- Modify: `packaging/openworker-server.spec`
- Modify: `packaging/build_dmg.sh`
- Modify: `packaging/build_windows.ps1`
- Modify: `packaging/verify_ocr_runtime.py`

- [x] **Step 1: Write packaged-runtime verifier mode**

Add:

```text
--verify-installation
--fixture PATH
--offline
```

The mode imports the production adapter, validates manifest hashes, performs
one recognition, and exits non-zero on missing runtime libraries, models,
hash mismatch, download attempt, or missing required term.

- [x] **Step 2: Update PyInstaller collection**

Collect the accepted Gate 0 packages and package data. Remove `"PIL"` from
`excludes` only if the accepted RapidOCR dependency graph imports Pillow.
Explicitly include `config/ocr-model-manifest.json` and verify all three ONNX
model files are present once in the staged tree.

- [x] **Step 3: Add macOS staged-sidecar smoke**

After staging and before signing, run the bundled server executable in a
dedicated verifier mode or invoke a bundled verifier entry point against the
Chinese fixture with networking blocked. Fail the build if model hashes or
required terms fail.

- [ ] **Step 4: Add Windows staged-sidecar smoke**

Mirror the same check after `Copy-Item` and before `tauri build`. Use no shell
download and fail on any missing DLL or model.

- [x] **Step 5: Build and inspect macOS arm64**

Run:

```bash
OCW_SKIP_NOTARIZE=1 packaging/build_dmg.sh
find surfaces/gui/src-tauri/binaries/sidecar -type f \
  \( -name '*.onnx' -o -name 'ocr-model-manifest.json' \) -print
```

Expected: build succeeds; exactly the manifest’s three model hashes are
present; the staged verifier passes offline.

- [ ] **Step 6: Run Windows x64 CI/build**

Run on the Windows x64 builder:

```powershell
.\packaging\build_windows.ps1
```

Expected: PyInstaller, staged OCR smoke, Tauri build, NSIS, and MSI succeed.
Attach the build log and artifact hashes to Gate 0 evidence.

- [ ] **Step 7: Commit**

```bash
git add packaging/openworker-server.spec packaging/build_dmg.sh \
  packaging/build_windows.ps1 packaging/verify_ocr_runtime.py \
  docs/ocr/2026-08-10-gate0-evidence.md
git commit -m "build(ocr): bundle and verify offline runtime"
```

### Task 12: Full Regression, Browser Acceptance, Adversarial Review, And Closeout

**Files:**

- Modify: `docs/11_DEVELOPMENT_LOG.md`
- Modify: `docs/12_TONIGHT_PROGRESS.md`

- [ ] **Step 1: Run the full backend suite**

Run:

```bash
.venv/bin/pytest -q
```

Expected: all backend tests pass.

- [ ] **Step 2: Run the full GUI suite and production build**

Run:

```bash
cd surfaces/gui
npm test -- --run
npm run build
```

Expected: all GUI tests pass and Vite production build succeeds.

- [ ] **Step 3: Verify schema and database integrity**

Run against a disposable migrated database:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from tempfile import TemporaryDirectory
from extensions.career_mcp.database.migrations import connect, migrate, schema_version

with TemporaryDirectory() as directory:
    connection = connect(Path(directory) / "career.sqlite3")
    migrate(connection)
    print("schema", schema_version(connection))
    print("foreign_keys", connection.execute("PRAGMA foreign_key_check").fetchall())
    connection.close()
PY
```

Expected:

```text
schema 9
foreign_keys []
```

- [ ] **Step 4: Perform authenticated real-browser acceptance**

Restart Server first, then Vite so the GUI reads the current sidecar token.
Upload the hybrid and low-quality fixtures through the visible Career resume
import action. Verify Chinese status text, generated prompt fields, Agent
preview, and explicit confirmation. Capture network, console, page error, and
request failure counts; each must be zero except expected successful local
requests.

- [ ] **Step 5: Run adversarial privacy and resource review**

Search runtime logs, database JSON, HTTP bodies, prompt text, artifacts, and
temporary directories for fixture phone/email strings, absolute model paths,
OCR page images, and raw engine responses. Test:

1. Model hash tampering.
2. Missing model.
3. Network disabled.
4. 11 sparse pages.
5. 21 total pages.
6. Huge PDF media box.
7. Concurrent OCR imports.
8. OCR error containing a fake private path.
9. Low-confidence text attempting to bypass preview.
10. Reimport after an engine metadata change.

Every failure must be stable, bounded, private, and leave no partial staged
row or image.

- [ ] **Step 6: Record authoritative evidence**

Append exact files changed, commands, test counts, fixture hashes, schema
version, browser results, packaging results, adversarial findings, and any
remaining risk to `docs/11_DEVELOPMENT_LOG.md`. Mark OCR complete in
`docs/12_TONIGHT_PROGRESS.md` only if Gates 0-E all pass.

- [ ] **Step 7: Commit closeout**

```bash
git add docs/11_DEVELOPMENT_LOG.md docs/12_TONIGHT_PROGRESS.md
git commit -m "docs: close scanned resume OCR gate"
```

## Completion Audit

OCR is complete only when current evidence proves every item:

- Gate 0 PASS with exact wheel, model, hash, license, offline, and packaging evidence.
- Native PDFs never initialize OCR.
- Hybrid PDFs OCR only sparse pages and preserve one-based page order.
- OCR never makes a network request or writes page images.
- Resource bounds and stable errors hold under adversarial inputs.
- Schema v9 migration is atomic, retryable, and backfills valid metadata.
- Reimport refreshes provenance without changing the stable import ID.
- HTTP and prompts expose no OCR text, private path, model path, or confidence.
- MCP labels OCR output as pending confirmation.
- No OCR result reaches Career Vault without existing five-section user confirmation.
- macOS arm64 and Windows x64 packaged sidecars initialize and recognize offline.
- Full backend, GUI, production build, browser acceptance, and database integrity pass.

Do not start recruitment-source expansion until every item above is backed by
current test, runtime, database, and package evidence.
