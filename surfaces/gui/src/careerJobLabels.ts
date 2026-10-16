const JOB_TYPE_LABELS: Record<string, string> = {
  experienced: "社会招聘",
  social: "社会招聘",
  campus: "校园招聘",
  internship: "实习",
};

const JOB_TYPE_CLASSES: Record<string, string> = {
  experienced: "border-cyan-200 bg-cyan-50 text-cyan-700",
  social: "border-cyan-200 bg-cyan-50 text-cyan-700",
  campus: "border-blue-200 bg-blue-50 text-blue-700",
  internship: "border-purple-200 bg-purple-50 text-purple-700",
};

export function careerJobTypeLabel(value: string | null): string {
  return (value && JOB_TYPE_LABELS[value]) || "类型未标注";
}

export function careerJobTypeClass(value: string | null): string {
  return (
    (value && JOB_TYPE_CLASSES[value]) ||
    "border-line bg-paper text-muted"
  );
}
