import { describe, expect, it } from "vitest";
import app from "./App.tsx?raw";
import interviewBar from "./components/ConversationInterviewBar.tsx?raw";
import jobs from "./components/CareerJobsView.tsx?raw";
import profile from "./components/CareerProfileView.tsx?raw";
import resumeCoach from "./components/CareerResumeCoachLauncher.tsx?raw";

describe("Career-first interface theme", () => {
  it("never applies the desktop hover-peek class on mobile", () => {
    expect(app).toContain(
      "effectiveNavCollapsed && !isNarrow && navPeek",
    );
  });

  it("does not hard-code the retired blue Career palette", () => {
    for (const source of [
      interviewBar,
      jobs,
      profile,
      resumeCoach,
    ]) {
      expect(source).not.toMatch(
        /\b(?:bg|text|border)-(?:blue|slate)-\d+\b/,
      );
    }
  });
});
