"""Generate synthetic scanned PDFs used by the local OCR gate."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "extensions/career_mcp/tests/fixtures/ocr"
FONT_CANDIDATES = (
    Path("/System/Library/Fonts/Hiragino Sans GB.ttc"),
    Path("/System/Library/Fonts/STHeiti Medium.ttc"),
)
FIXTURES = {
    "chinese-scanned.pdf": (
        "测试候选人\n"
        "项目经历\n"
        "使用 Python 构建本地检索服务\n"
        "技能：Python、SQL、人工智能"
    ),
    "mixed-scanned.pdf": (
        "测试候选人 Test Candidate\n"
        "AI Engineer\n"
        "项目 Project: Local Agent\n"
        "技能 Skills: Python SQL"
    ),
}
HYBRID_NATIVE_TEXT = (
    "Synthetic Candidate builds local Python retrieval agents, evaluates "
    "quality, and documents reliable deployment workflows for product teams."
)
HYBRID_SCANNED_TEXT = (
    "测试候选人 Test Candidate\n"
    "扫描页项目经历 Scanned Project Experience\n"
    "使用 Python 和 SQL 构建本地 Agent"
)
LOW_QUALITY_TEXT = "测试候选人\nPython 项目经历\nSQL 技能"


def _font_path() -> Path:
    for candidate in FONT_CANDIDATES:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("a supported local Chinese fixture font is required")


def _scanned_page(
    text: str,
    font: ImageFont.FreeTypeFont,
    *,
    skew_degrees: float = 0,
    fill: str = "black",
) -> object:
    image = Image.new("RGB", (1654, 2339), "white")
    draw = ImageDraw.Draw(image)
    draw.multiline_text(
        (120, 140),
        text,
        fill=fill,
        font=font,
        spacing=28,
    )
    if skew_degrees:
        skewed = image.rotate(
            skew_degrees,
            resample=Image.Resampling.BICUBIC,
            fillcolor="white",
        )
        image.close()
        image = skewed
    generated = io.BytesIO()
    image.save(generated, "PDF", resolution=200.0)
    image.close()
    return PdfReader(io.BytesIO(generated.getvalue())).pages[0]


def _native_page(writer: PdfWriter, text: str) -> object:
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    font_ref = writer._add_object(font)
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject(
                {NameObject("/F1"): font_ref}
            )
        }
    )
    content = DecodedStreamObject()
    content.set_data(
        f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode("ascii")
    )
    page[NameObject("/Contents")] = writer._add_object(content)
    return page


def _write(filename: str, writer: PdfWriter) -> None:
    writer.add_metadata(
        {
            "/CreationDate": "D:20260810000000Z",
            "/Producer": "OpenCareer OCR fixture generator",
        }
    )
    with (OUTPUT / filename).open("wb") as handle:
        writer.write(handle)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(_font_path()), 38)
    for filename, text in FIXTURES.items():
        writer = PdfWriter()
        writer.add_page(_scanned_page(text, font))
        _write(filename, writer)

    hybrid = PdfWriter()
    _native_page(hybrid, HYBRID_NATIVE_TEXT)
    hybrid.add_page(_scanned_page(HYBRID_SCANNED_TEXT, font))
    _write("hybrid.pdf", hybrid)

    low_quality = PdfWriter()
    low_quality.add_page(
        _scanned_page(
            LOW_QUALITY_TEXT,
            font,
            skew_degrees=4,
            fill="#777777",
        )
    )
    _write("low-quality-skewed.pdf", low_quality)


if __name__ == "__main__":
    main()
