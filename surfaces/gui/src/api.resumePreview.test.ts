import { afterEach, expect, it, vi } from "vitest";
import { getCareerResumeOriginalContent } from "./api";

afterEach(() => vi.unstubAllGlobals());

it("returns HTML without allocating a blob URL and retains launch authentication", async () => {
  vi.stubGlobal("__COWORKER_API_TOKEN__", "fixture-launch-token");
  const request = vi.fn(async (_url: string, init?: RequestInit) => {
    expect(new Headers(init?.headers).get("X-OpenWorker-Token")).toBe("fixture-launch-token");
    return new Response("<article>Fictional resume</article>");
  });
  vi.stubGlobal("fetch", request);
  await expect(getCareerResumeOriginalContent("resume-1", "html"))
    .resolves.toBe("<article>Fictional resume</article>");
  expect(request.mock.calls[0][0]).toContain("/resumes/resume-1/original/content");
});

it("preserves blob URL previews for PDF content", async () => {
  const createObjectURL = vi.fn(() => "blob:pdf-preview");
  class TestURL extends URL { static createObjectURL = createObjectURL; }
  vi.stubGlobal("URL", TestURL);
  vi.stubGlobal("fetch", vi.fn(async () => new Response("%PDF-1.7", {
    headers: { "Content-Type": "application/pdf" },
  })));
  await expect(getCareerResumeOriginalContent("resume-1")).resolves.toBe("blob:pdf-preview");
  expect(createObjectURL).toHaveBeenCalledOnce();
});

it("does not return a server error body as a preview", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response("private error detail", { status: 409 })));
  await expect(getCareerResumeOriginalContent("resume-1", "html"))
    .rejects.toThrow("无法读取原始简历");
});
