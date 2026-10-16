import { describe, expect, it } from "vitest";
import { DEFAULT_PERSONA_ID } from "./personaDefaults";

describe("default persona", () => {
  it("starts first-run users in Career", () => {
    expect(DEFAULT_PERSONA_ID).toBe("career");
  });
});
