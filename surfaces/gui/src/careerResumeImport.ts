export type ResumeExtractionMethod = "native" | "ocr" | "hybrid";

export interface CareerResumeImportPromptInput {
  uploadToken: string;
  filename: string;
  sourceKind: "text" | "pdf" | "docx";
  extractionMethod: ResumeExtractionMethod;
  warningCodes: string[];
}

export function careerResumeImportDisplay(filename: string): string {
  return `已暂存简历：${filename}，等待五个分区预览。`;
}

export function careerResumeImportPrompt(
  input: CareerResumeImportPromptInput,
): string {
  const warnings = input.warningCodes.length
    ? input.warningCodes.join(",")
    : "none";
  return (
    "A private resume was staged locally. Load the career-resume-import " +
    `skill and import it. Upload token: ${input.uploadToken}. ` +
    `Filename: ${input.filename}. Format: ${input.sourceKind}. ` +
    `Extraction method: ${input.extractionMethod}. Warning codes: ${warnings}. ` +
    "Start with get_resume_import_text, then preview the five sections. " +
    "Do not confirm any section until I explicitly approve it."
  );
}

export function careerResumeImportNotice(input: {
  extractionMethod?: ResumeExtractionMethod;
  reviewRequired?: boolean;
}): string | null {
  if (input.reviewRequired) {
    return "部分内容识别质量较低，请重点核对";
  }
  if (
    input.extractionMethod === "ocr" ||
    input.extractionMethod === "hybrid"
  ) {
    return "已使用本地 OCR，内容尚未确认";
  }
  return null;
}

const OCR_ERRORS: Record<string, string> = {
  OCR_UNAVAILABLE: "本地 OCR 暂不可用，请稍后重试",
  OCR_PAGE_LIMIT: "需要识别的扫描页超过 10 页限制",
  OCR_FAILED: "本地 OCR 未能读取这份简历",
  NO_EXTRACTABLE_TEXT: "未读取到足够的简历文字",
};

export function careerResumeImportError(code?: string): string {
  return OCR_ERRORS[code || ""] || "无法暂存简历";
}
