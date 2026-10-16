// SKILLS-SPEC §4.6 GUI — the composer's "/" force-run popup: opens only for a leading
// slash, lists only the session's effective (enabled) menu, filters while typing, and the
// picked skill rides onSend as its own field — never as message text.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { Composer } from "./Composer";

const MENU = {
  skills: [
    { name: "weekly-report", description: "Monday status report", scope: "global", enabled: true },
    { name: "greet", description: "says hello", scope: "project", enabled: true },
    { name: "muted-one", description: "muted here", scope: "global", enabled: false },
  ],
};

function stubFetch() {
  const calls: { url: string; method: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, method: (init?.method || "GET").toUpperCase() });
      if (url.includes("/skills")) return { ok: true, json: async () => MENU } as Response;
      return { ok: true, json: async () => ({}) } as Response;
    }),
  );
  return calls;
}

const props = (extra: Partial<Parameters<typeof Composer>[0]> = {}) => ({
  mode: "interactive",
  model: "gpt-5.6-sol",
  running: false,
  connected: true,
  sessionId: "s1",
  onSend: vi.fn(),
  onInterrupt: vi.fn(),
  onModeChange: vi.fn(),
  onModelChange: vi.fn(),
  ...extra,
});

const box = () => screen.getByPlaceholderText(/向 Agent 提问/);

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("Composer / skills popup", () => {
  it("offers safe automatic approval instead of discussion or unrestricted access", () => {
    stubFetch();
    const p = props({ mode: "custom", workspace: "/tmp/career" });
    render(<Composer {...p} />);
    expect(screen.getByRole("button", { name: "权限模式" }).textContent).toContain("自动审批");
    fireEvent.click(screen.getByRole("button", { name: "权限模式" }));
    expect(screen.queryByText("仅讨论")).toBeNull();
    expect(screen.queryByText("完全访问")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /自动审批.*常规求职/ }));
    expect(p.onModeChange).toHaveBeenCalledWith("custom");
  });

  it("opens on a leading '/' and lists only enabled skills from the effective menu", async () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "/" } });
    await screen.findByTestId("skill-popup");
    expect(await screen.findByText("/weekly-report")).toBeTruthy();
    expect(screen.getByText("/greet")).toBeTruthy();
    expect(screen.queryByText("/muted-one")).toBeNull(); // muted → not offered
    expect(screen.queryByText("project")).toBeNull(); // scope 徽章已由 /name 标记取代
  });

  it("filters as you type", async () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "/" } });
    await screen.findByText("/weekly-report");
    fireEvent.change(box(), { target: { value: "/wee" } });
    expect(screen.getByText("/weekly-report")).toBeTruthy();
    expect(screen.queryByText("/greet")).toBeNull();
  });

  it("does NOT open for a mid-text slash", async () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "rate 5/10 please" } });
    expect(screen.queryByTestId("skill-popup")).toBeNull();
  });

  it("selecting keeps the input clean, pins the chip, and the send carries the skill field", async () => {
    stubFetch();
    const p = props();
    render(<Composer {...p} />);
    fireEvent.change(box(), { target: { value: "/gr" } });
    fireEvent.click(await screen.findByRole("option", { name: /greet/ }));
    // 输入区保持干净（技能只体现在上方上下文栏），光标回到输入区。
    expect((box() as HTMLTextAreaElement).value).toBe("");
    expect(screen.getByTestId("pinned-skill-chip").textContent).toContain("greet");
    fireEvent.change(box(), { target: { value: "say hi to the team" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    await waitFor(() => expect(p.onSend).toHaveBeenCalled());
    expect(p.onSend).toHaveBeenCalledWith("say hi to the team", [], "greet");
  });

  it("a skill-only send works and Enter inside the popup never sends the query text", async () => {
    stubFetch();
    const p = props();
    render(<Composer {...p} />);
    fireEvent.change(box(), { target: { value: "/wee" } });
    await screen.findByText("/weekly-report");
    fireEvent.keyDown(box(), { key: "Enter" }); // selects, does not send
    expect(p.onSend).not.toHaveBeenCalled();
    expect((box() as HTMLTextAreaElement).value).toBe("");
    expect(screen.getByTestId("pinned-skill-chip").textContent).toContain("weekly-report");
    fireEvent.keyDown(box(), { key: "Enter" }); // now sends, skill-only
    await waitFor(() => expect(p.onSend).toHaveBeenCalledWith("", [], "weekly-report"));
  });

  it("typing a leading slash unpins the skill and switches to slash invocation", async () => {
    stubFetch();
    const p = props();
    render(<Composer {...p} />);
    fireEvent.change(box(), { target: { value: "/gr" } });
    fireEvent.click(await screen.findByRole("option", { name: /greet/ }));
    expect(screen.getByTestId("pinned-skill-chip")).toBeTruthy();
    // 手敲 "/"：解除当前徽章，回到斜杠调用。
    fireEvent.change(box(), { target: { value: "/" } });
    expect(screen.queryByTestId("pinned-skill-chip")).toBeNull();
    fireEvent.change(box(), { target: { value: "hello plain" } });
    fireEvent.keyDown(box(), { key: "Enter" });
    await waitFor(() => expect(p.onSend).toHaveBeenCalledWith("hello plain", [], undefined));
  });

  it("Escape closes the popup and no popup ever opens without a sessionId", async () => {
    stubFetch();
    render(<Composer {...props()} />);
    fireEvent.change(box(), { target: { value: "/gr" } });
    await screen.findByTestId("skill-popup");
    fireEvent.keyDown(box(), { key: "Escape" });
    expect(screen.queryByTestId("skill-popup")).toBeNull();
    cleanup();
    stubFetch();
    render(<Composer {...props({ sessionId: undefined })} />);
    fireEvent.change(box(), { target: { value: "/" } });
    expect(screen.queryByTestId("skill-popup")).toBeNull();
  });
});

describe("Composer — the doorway prefill (SKILLS-SPEC §5.2)", () => {
  it("keeps an initial prefill when StrictMode repeats mount effects", async () => {
    stubFetch();
    render(
      <StrictMode>
        <Composer
          {...props({
            resetKey: "s2",
            prefill: {
              text: "Generate the application packet",
              nonce: 1,
            },
          })}
        />
      </StrictMode>,
    );

    await waitFor(() => {
      expect((box() as HTMLTextAreaElement).value).toBe(
        "Generate the application packet",
      );
    });
  });

  it("a prefill arriving together with a session switch survives the draft clear", async () => {
    stubFetch();
    const { rerender } = render(<Composer {...props({ resetKey: "s1" })} />);
    // The doorway does both in one render: new session (resetKey) + prefill. The clear
    // effect must run BEFORE the prefill effect or the prefill is wiped (regression).
    rerender(
      <Composer
        {...props({
          resetKey: "s2",
          prefill: { text: "Build a new skill for me: release procedure", nonce: 1 },
        })}
      />,
    );
    await waitFor(() => {
      expect((box() as HTMLTextAreaElement).value).toBe(
        "Build a new skill for me: release procedure",
      );
    });
  });
});

describe("Composer 技能按钮与挂载徽章", () => {
  it("collapses to one text line after the first character and uses a quiet book trigger", () => {
    stubFetch();
    vi.spyOn(window, "getComputedStyle").mockReturnValue({
      lineHeight: "22px",
    } as CSSStyleDeclaration);
    render(<Composer {...props()} />);

    const textarea = box() as HTMLTextAreaElement;
    const skillButton = screen.getByTestId("composer-skill-button");
    expect(textarea.style.height).toBe("40px");

    fireEvent.change(textarea, { target: { value: "我" } });

    expect(textarea.style.height).toBe("24px");
    expect(skillButton.classList.contains("chip")).toBe(false);
    expect(skillButton.querySelector('[data-icon="book"]')).toBeTruthy();
  });

  it("opens the menu, shows entries, pins a chip, and rides the skill on send", async () => {
    stubFetch();
    const onSend = vi.fn();
    render(<Composer {...props({ onSend })} />);

    fireEvent.click(screen.getByTestId("composer-skill-button"));
    const menu = await screen.findByTestId("skill-menu");
    expect(menu).toBeTruthy();
    expect(menu.classList.contains("border-b")).toBe(true);
    expect(
      Boolean(menu.compareDocumentPosition(box()) & Node.DOCUMENT_POSITION_FOLLOWING),
    ).toBe(true);
    // 未收录的技能回退原名/原描述。
    expect(await screen.findByTestId("skill-menu-weekly-report")).toBeTruthy();
    expect(screen.getByText("Monday status report")).toBeTruthy();
    // muted 技能不出现。
    expect(screen.queryByTestId("skill-menu-muted-one")).toBeNull();

    fireEvent.click(screen.getByTestId("skill-menu-weekly-report"));
    // 挂载技能出现在对话框上方独立一行；输入区保持干净（无 / 前缀文本）。
    const chip = await screen.findByTestId("pinned-skill-chip");
    const bar = screen.getByTestId("pinned-skill-bar");
    expect(chip.textContent).toContain("weekly-report");
    expect(bar.classList.contains("border-b")).toBe(true);
    expect(
      Boolean(bar.compareDocumentPosition(box()) & Node.DOCUMENT_POSITION_FOLLOWING),
    ).toBe(true);
    expect((box() as HTMLTextAreaElement).value).toBe("");

    // 正文照常输入，发送时技能作为独立字段随消息走。
    const textarea = box() as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "本周进展正常" } });
    fireEvent.click(screen.getByRole("button", { name: "发送" }));
    await waitFor(() => expect(onSend).toHaveBeenCalled());
    expect(onSend.mock.calls[0][0]).toBe("本周进展正常");
    expect(onSend.mock.calls[0][2]).toBe("weekly-report");
  });

  it("shows the Chinese title and description for career skills", async () => {
    stubFetch();
    const MENU_ZH = {
      skills: [
        { name: "mock-interview", description: "Run a mock interview", scope: "project", enabled: true },
      ],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("/skills")
          ? ({ ok: true, json: async () => MENU_ZH } as Response)
          : ({ ok: true, json: async () => ({}) } as Response)
      ),
    );
    render(<Composer {...props()} />);

    fireEvent.click(screen.getByTestId("composer-skill-button"));
    expect(await screen.findByTestId("skill-menu-mock-interview")).toBeTruthy();
    expect(screen.getByText("模拟面试")).toBeTruthy();
    expect(screen.getByText(/五轮自适应模拟面试/)).toBeTruthy();

    // 点选后徽章显示中文名称。
    fireEvent.click(screen.getByTestId("skill-menu-mock-interview"));
    const chip = await screen.findByTestId("pinned-skill-chip");
    expect(chip.textContent).toContain("模拟面试");
  });

  it("stays open on inside clicks and closes on outside pointerdown", async () => {
    stubFetch();
    render(<Composer {...props()} />);

    fireEvent.click(screen.getByTestId("composer-skill-button"));
    const menu = await screen.findByTestId("skill-menu");

    // 面板内部非技能行的点击不关闭（可继续浏览）。
    fireEvent.pointerDown(menu);
    fireEvent.click(menu);
    expect(screen.queryByTestId("skill-menu")).toBeTruthy();

    // 按钮以外、面板以外的任何位置点击 → 关闭。
    fireEvent.pointerDown(document.body);
    expect(screen.queryByTestId("skill-menu")).toBeNull();
  });

  it("Delete/Backspace on an empty pinned input unpins the skill", async () => {
    stubFetch();
    const onSend = vi.fn();
    render(<Composer {...props({ onSend })} />);

    fireEvent.click(screen.getByTestId("composer-skill-button"));
    fireEvent.click(await screen.findByTestId("skill-menu-greet"));
    expect(await screen.findByTestId("pinned-skill-chip")).toBeTruthy();

    const textarea = box() as HTMLTextAreaElement;
    expect(textarea.value).toBe("");
    fireEvent.keyDown(textarea, { key: "Backspace" });
    expect(screen.queryByTestId("pinned-skill-chip")).toBeNull();

    // 再挂载一次，Delete 键同样生效（事件在输入框上触发）。
    fireEvent.click(screen.getByTestId("composer-skill-button"));
    fireEvent.click(await screen.findByTestId("skill-menu-greet"));
    fireEvent.keyDown(box(), { key: "Delete" });
    expect(screen.queryByTestId("pinned-skill-chip")).toBeNull();
  });

  it("chip remove button unpins the skill and strips the prefix", async () => {
    stubFetch();
    const onSend = vi.fn();
    render(<Composer {...props({ onSend })} />);

    fireEvent.click(screen.getByTestId("composer-skill-button"));
    fireEvent.click(await screen.findByTestId("skill-menu-greet"));
    fireEvent.click(await screen.findByTestId("pinned-skill-remove"));

    expect(screen.queryByTestId("pinned-skill-chip")).toBeNull();
    expect((box() as HTMLTextAreaElement).value).toBe("");
  });
});
