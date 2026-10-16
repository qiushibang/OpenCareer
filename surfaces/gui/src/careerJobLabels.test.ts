import { describe, expect, it } from "vitest";

import { careerJobTypeLabel } from "./careerJobLabels";

describe("careerJobTypeLabel", () => {
  it("maps persisted recruitment types to Chinese labels", () => {
    expect(careerJobTypeLabel("experienced")).toBe("社会招聘");
    expect(careerJobTypeLabel("social")).toBe("社会招聘");
    expect(careerJobTypeLabel("campus")).toBe("校园招聘");
    expect(careerJobTypeLabel("internship")).toBe("实习");
  });

  it("does not expose unknown internal values", () => {
    expect(careerJobTypeLabel(null)).toBe("类型未标注");
    expect(careerJobTypeLabel("unexpected")).toBe("类型未标注");
  });
});
