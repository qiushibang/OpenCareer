import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Composer } from "./Composer";

const props = (extra: Partial<Parameters<typeof Composer>[0]> = {}) => ({
  mode: "interactive",
  model: "ep-test",
  running: false,
  connected: true,
  sessionId: "career-session",
  personaId: "career",
  onSend: vi.fn(),
  onInterrupt: vi.fn(),
  onModeChange: vi.fn(),
  onModelChange: vi.fn(),
  ...extra,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Composer resume import", () => {
  it.each(["file", "text"])("asks for model setup before staging a %s resume", async (kind) => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const p = props({ modelReady: false, onConnectModel: vi.fn() });
    render(<Composer {...p} />);
    const box = screen.getByRole("textbox");
    fireEvent.change(box, { target: { value: "A fictional resume draft" } });
    if (kind === "file") {
      fireEvent.change(screen.getByTestId("resume-file-input"), {
        target: { files: [new File(["fixture"], "resume.pdf", { type: "application/pdf" })] },
      });
    } else {
      fireEvent.click(screen.getByRole("button", { name: "添加附件" }));
      fireEvent.click(screen.getByText("导入已粘贴的简历"));
    }
    await waitFor(() => expect(p.onConnectModel).toHaveBeenCalledOnce());
    expect(p.onSend).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
    expect((box as HTMLTextAreaElement).value).toBe("A fictional resume draft");
  });

  it("shows local reading state while the resume request is pending", async () => {
    let resolveRequest: ((value: unknown) => void) | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(
        () =>
          new Promise((resolve) => {
            resolveRequest = resolve;
          }),
      ),
    );
    render(<Composer {...props()} />);
    fireEvent.click(screen.getByRole("button", { name: "添加附件" }));
    fireEvent.click(screen.getByText("导入简历到求职档案（PDF/DOCX）"));
    const file = new File(["pdf-content"], "resume.pdf", {
      type: "application/pdf",
    });

    fireEvent.change(screen.getByTestId("resume-file-input"), {
      target: { files: [file] },
    });

    expect(
      await screen.findByText("正在本地读取简历…"),
    ).toBeTruthy();
    resolveRequest?.({
      ok: true,
      json: async () => ({
        ok: false,
        error: { code: "OCR_FAILED", message: "hidden details" },
      }),
    });
  });

  it("stages a DOCX and sends only the opaque upload token", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        ok: true,
        upload_token: "upload-secret-token",
        source_kind: "docx",
        filename: "resume.docx",
        sha256: "a".repeat(64),
        characters: 1234,
        expires_at: "2026-08-07T00:00:00Z",
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    const onSend = vi.fn();
    const p = props({ onSend });
    render(<Composer {...p} />);
    fireEvent.click(screen.getByRole("button", { name: "添加附件" }));
    fireEvent.click(screen.getByText("导入简历到求职档案（PDF/DOCX）"));
    const input = screen.getByTestId("resume-file-input");
    const file = new File(["private-binary-content"], "resume.docx", {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });

    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => expect(onSend).toHaveBeenCalled());
    const [prompt, attachments, skill, display] = onSend.mock.calls[0];
    expect(prompt).toContain("upload-secret-token");
    expect(prompt).toContain("resume.docx");
    expect(prompt).not.toContain("private-binary-content");
    expect(attachments).toEqual([]);
    expect(skill).toBe("career-resume-import");
    expect(display).toContain("resume.docx");
    expect(display).not.toContain("upload-secret-token");
  });

  it("stages pasted text without echoing it into the prepared prompt", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          ok: true,
          upload_token: "text-upload-token",
          source_kind: "text",
          filename: "pasted-resume.txt",
          sha256: "b".repeat(64),
          characters: 80,
          expires_at: "2026-08-07T00:00:00Z",
        }),
      })),
    );
    const onSend = vi.fn();
    const p = props({ onSend });
    render(<Composer {...p} />);
    const box = screen.getByPlaceholderText("告诉我你的求职目标，或直接导入简历…");
    const privateText = "Zhang San private resume content with enough characters for staging.";
    fireEvent.change(box, { target: { value: privateText } });
    fireEvent.click(screen.getByRole("button", { name: "添加附件" }));
    fireEvent.click(screen.getByText("导入已粘贴的简历"));

    await waitFor(() => expect(onSend).toHaveBeenCalled());
    expect(onSend.mock.calls[0][0]).toContain("text-upload-token");
    expect(onSend.mock.calls[0][0]).not.toContain(privateText);
  });

  it("does not show resume actions outside Career sessions", () => {
    render(<Composer {...props({ personaId: "cowork" })} />);
    fireEvent.click(screen.getByRole("button", { name: "添加附件" }));

    expect(screen.queryByText("导入简历到求职档案（PDF/DOCX）")).toBeNull();
    expect(screen.getByPlaceholderText(/向 Agent 提问/)).toBeTruthy();
  });

  it("opens the dedicated resume picker from an external Career action", () => {
    const click = vi.spyOn(HTMLInputElement.prototype, "click");
    const { rerender } = render(<Composer {...props({ resumeImportNonce: 0 })} />);

    rerender(<Composer {...props({ resumeImportNonce: 1 })} />);

    expect(click).toHaveBeenCalledOnce();
  });

  it.each([
    {
      extraction_method: "ocr",
      review_required: false,
      expected: "已使用本地 OCR，内容尚未确认",
    },
    {
      extraction_method: "hybrid",
      review_required: true,
      expected: "部分内容识别质量较低，请重点核对",
    },
  ])("shows OCR result notice: $expected", async (status) => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          ok: true,
          upload_token: "ocr-upload-token",
          source_kind: "pdf",
          filename: "resume.pdf",
          sha256: "c".repeat(64),
          characters: 128,
          expires_at: "2026-08-11T00:00:00Z",
          warnings: status.review_required ? ["OCR_LOW_CONFIDENCE"] : [],
          pages: { total: 2, ocr: [2] },
          ...status,
        }),
      })),
    );
    const onSend = vi.fn();
    render(<Composer {...props({ onSend })} />);
    fireEvent.click(screen.getByRole("button", { name: "添加附件" }));
    fireEvent.click(screen.getByText("导入简历到求职档案（PDF/DOCX）"));

    fireEvent.change(screen.getByTestId("resume-file-input"), {
      target: {
        files: [
          new File(["pdf-content"], "resume.pdf", {
            type: "application/pdf",
          }),
        ],
      },
    });

    expect(await screen.findByText(status.expected)).toBeTruthy();
    await waitFor(() => expect(onSend).toHaveBeenCalled());
    const prompt = onSend.mock.calls[0][0];
    expect(prompt).toContain(status.extraction_method);
    expect(prompt).not.toContain("pdf-content");
  });

  it("does not show an OCR notice for native extraction", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          ok: true,
          upload_token: "native-token",
          source_kind: "docx",
          filename: "resume.docx",
          extraction_method: "native",
          review_required: false,
          warnings: [],
          pages: { total: 1, ocr: [] },
        }),
      })),
    );
    const onSend = vi.fn();
    render(<Composer {...props({ onSend })} />);
    fireEvent.click(screen.getByRole("button", { name: "添加附件" }));
    fireEvent.click(screen.getByText("导入简历到求职档案（PDF/DOCX）"));
    fireEvent.change(screen.getByTestId("resume-file-input"), {
      target: {
        files: [
          new File(["docx"], "resume.docx", {
            type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          }),
        ],
      },
    });

    await waitFor(() => expect(onSend).toHaveBeenCalled());
    expect(
      screen.queryByText("已使用本地 OCR，内容尚未确认"),
    ).toBeNull();
  });

  it("shows a stable Chinese OCR error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: true,
        json: async () => ({
          ok: false,
          error: {
            code: "OCR_UNAVAILABLE",
            message: "/private/model/path",
          },
        }),
      })),
    );
    render(<Composer {...props()} />);
    fireEvent.click(screen.getByRole("button", { name: "添加附件" }));
    fireEvent.click(screen.getByText("导入简历到求职档案（PDF/DOCX）"));
    fireEvent.change(screen.getByTestId("resume-file-input"), {
      target: {
        files: [
          new File(["pdf"], "resume.pdf", {
            type: "application/pdf",
          }),
        ],
      },
    });

    expect(
      await screen.findByText("本地 OCR 暂不可用，请稍后重试"),
    ).toBeTruthy();
    expect(screen.queryByText("/private/model/path")).toBeNull();
  });
});
