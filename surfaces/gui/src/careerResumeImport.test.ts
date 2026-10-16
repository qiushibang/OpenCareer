import { describe, expect, it } from "vitest";
import {
  careerResumeImportError,
  careerResumeImportDisplay,
  careerResumeImportNotice,
  careerResumeImportPrompt,
} from "./careerResumeImport";

describe("career resume import metadata", () => {
  it("builds a token-free visible message", () => {
    const display = careerResumeImportDisplay("resume.pdf");
    expect(display).toContain("resume.pdf");
    expect(display).not.toMatch(/token|opaque|upload/i);
  });

  it("builds a metadata-only prompt for hybrid OCR", () => {
    const prompt = careerResumeImportPrompt({
      uploadToken: "opaque-token",
      filename: "resume.pdf",
      sourceKind: "pdf",
      extractionMethod: "hybrid",
      warningCodes: ["OCR_LOW_CONFIDENCE"],
    });

    expect(prompt).toContain("opaque-token");
    expect(prompt).toContain("resume.pdf");
    expect(prompt).toContain("pdf");
    expect(prompt).toContain("hybrid");
    expect(prompt).toContain("OCR_LOW_CONFIDENCE");
    expect(prompt).not.toMatch(/138\d{8}|@|private_path|model_path|识别全文/);
  });

  it("maps native, OCR, and review status to Chinese notices", () => {
    expect(
      careerResumeImportNotice({
        extractionMethod: "native",
        reviewRequired: false,
      }),
    ).toBeNull();
    expect(
      careerResumeImportNotice({
        extractionMethod: "ocr",
        reviewRequired: false,
      }),
    ).toBe("已使用本地 OCR，内容尚未确认");
    expect(
      careerResumeImportNotice({
        extractionMethod: "hybrid",
        reviewRequired: true,
      }),
    ).toBe("部分内容识别质量较低，请重点核对");
  });

  it("maps stable OCR errors without exposing backend details", () => {
    expect(careerResumeImportError("OCR_UNAVAILABLE")).toBe(
      "本地 OCR 暂不可用，请稍后重试",
    );
    expect(careerResumeImportError("OCR_PAGE_LIMIT")).toBe(
      "需要识别的扫描页超过 10 页限制",
    );
    expect(careerResumeImportError("OCR_FAILED")).toBe(
      "本地 OCR 未能读取这份简历",
    );
    expect(careerResumeImportError("NO_EXTRACTABLE_TEXT")).toBe(
      "未读取到足够的简历文字",
    );
  });
});
