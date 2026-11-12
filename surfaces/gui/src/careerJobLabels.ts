import type { TagTone } from "./components/OcSelect";

const JOB_TYPE_LABELS: Record<string, string> = {
  experienced: "社会招聘",
  social: "社会招聘",
  campus: "校园招聘",
  internship: "实习",
};

// Each recruitment type keeps one colour everywhere (radar, chat cards, applications).
const JOB_TYPE_TONES: Record<string, TagTone> = {
  experienced: "orange",
  social: "orange",
  campus: "blue",
  internship: "purple",
};

export function careerJobTypeLabel(value: string | null): string {
  return (value && JOB_TYPE_LABELS[value]) || "类型未标注";
}

/** Null for unknown types: callers render nothing instead of a "类型未标注" placeholder. */
export function careerJobTypeTone(value: string | null | undefined): TagTone | null {
  return (value && JOB_TYPE_TONES[value]) || null;
}
