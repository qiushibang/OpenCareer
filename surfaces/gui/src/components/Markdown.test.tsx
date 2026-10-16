import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { Markdown, OPEN_ARTIFACT_EVENT } from "./Markdown";

afterEach(cleanup);

describe("Markdown image privacy", () => {
  it.runIf(import.meta.env.MODE === "alpha")("does not automatically load images in cloud replies", () => {
    const { container } = render(
      <Markdown text={'![预览](https://untrusted.example/collect?data=fictional)'} />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("图片未自动加载")).toBeTruthy();
    expect(container.innerHTML).not.toContain("untrusted.example");
  });

  it.runIf(import.meta.env.MODE !== "alpha")("keeps desktop reply images visible", () => {
    render(<Markdown text="![本地预览](https://example.com/preview.png)" />);
    expect(screen.getByRole("img", { name: "本地预览" }).getAttribute("src"))
      .toBe("https://example.com/preview.png");
  });

  it.runIf(import.meta.env.MODE === "alpha")("keeps cloud links available for manual opening", () => {
    render(<Markdown text="[岗位官网](https://example.com/job)" />);
    const link = screen.getByRole("link", { name: "岗位官网" });
    expect(link.getAttribute("href")).toBe("https://example.com/job");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noreferrer");
  });
});

// §34 (UX-016): [Title](artifact:path) renders as a chip that opens the artifact viewer via
// a window event; ordinary links keep the open-externally treatment.
describe("Markdown artifact links", () => {
  it("renders an artifact: link as a chip and dispatches the open event with the path", () => {
    const seen: string[] = [];
    const listener = (e: Event) => seen.push((e as CustomEvent).detail.path);
    window.addEventListener(OPEN_ARTIFACT_EVENT, listener);

    render(<Markdown text="Done — [Semiconductor dashboard](artifact:reports/semi.html)" />);
    const chip = screen.getByTestId("artifact-chip");
    expect(chip.textContent).toContain("Semiconductor dashboard");
    expect(chip.textContent).toContain("semi.html"); // filename shown under the title
    fireEvent.click(chip);
    expect(seen).toEqual(["reports/semi.html"]);

    window.removeEventListener(OPEN_ARTIFACT_EVENT, listener);
  });

  it("ordinary links stay external and never become chips", () => {
    const { container } = render(<Markdown text="see [the docs](https://example.com)" />);
    expect(screen.queryByTestId("artifact-chip")).toBeNull();
    const a = container.querySelector("a")!;
    expect(a.getAttribute("target")).toBe("_blank");
    expect(a.getAttribute("href")).toBe("https://example.com");
  });

  it("does not include trailing Chinese punctuation in a bare URL", () => {
    const url = "https://jobs.bytedance.com/campus/position/7676344137335966005/detail";
    const { container } = render(<Markdown text={`岗位来源：${url}）。以下是诊断。`} />);

    const a = container.querySelector("a")!;
    expect(a.getAttribute("href")).toBe(url);
    expect(a.textContent).toBe(url);
    expect(container.textContent).toBe(`岗位来源：${url}）。以下是诊断。`);
  });

  it("chip title falls back to the filename when the link text is empty", () => {
    vi.spyOn(window, "dispatchEvent");
    render(<Markdown text="[](artifact:out/report.pdf)" />);
    expect(screen.getByTestId("artifact-chip").textContent).toContain("report.pdf");
  });
});
