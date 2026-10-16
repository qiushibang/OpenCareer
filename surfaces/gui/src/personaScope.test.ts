import { describe, expect, it } from "vitest";

import {
  personaDisplayName,
  personaDisplayTagline,
  sortPersonasForNewSession,
} from "./personaScope";

describe("persona display policy", () => {
  it.each([
    ["career", "Career Agent", "职业 Agent"],
    ["cowork", "OpenWorker", "通用 Agent"],
    ["code", "Code", "编程 Agent"],
    ["ops", "Ops Coworker", "运维 Agent"],
    ["chat", "Chat", "聊天 Agent"],
  ])("shows %s with a Chinese product name", (id, name, expected) => {
    expect(personaDisplayName(name, id)).toBe(expected);
  });

  it("puts Career first and preserves unknown persona order", () => {
    const sorted = sortPersonasForNewSession([
      { id: "custom-b" },
      { id: "cowork" },
      { id: "career" },
      { id: "custom-a" },
      { id: "code" },
    ]);

    expect(sorted.map((persona) => persona.id)).toEqual([
      "career",
      "cowork",
      "code",
      "custom-b",
      "custom-a",
    ]);
  });

  it("localizes core persona taglines but preserves custom persona copy", () => {
    expect(personaDisplayTagline("Discover jobs, analyze JDs", "career")).toBe(
      "发现岗位、分析 JD、准备申请",
    );
    expect(personaDisplayTagline("custom copy", "custom")).toBe("custom copy");
  });
});
