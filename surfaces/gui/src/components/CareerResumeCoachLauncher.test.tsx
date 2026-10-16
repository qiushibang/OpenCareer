import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";

import { CareerResumeCoachLauncher } from "./CareerResumeCoachLauncher";

const api = vi.hoisted(() => ({
  getCareerResumes: vi.fn(),
}));

vi.mock("../api", () => api);

const job = {
  id: "job-1",
  company: { slug: "deepseek", name: "DeepSeek" },
  title: "大模型算法工程师",
  locations: ["北京"],
  location_raw: "北京",
  recruitment_type: "social",
  status: "active",
  description_raw: "完整 JD",
  responsibilities: ["训练大模型"],
  requirements: ["必须熟悉 Python", "有 RAG 项目经验优先"],
  source_url: "https://careers.deepseek.com/jobs/one",
  first_seen_at: "2026-08-05T00:00:00Z",
  last_seen_at: "2026-08-08T00:00:00Z",
  last_changed_at: "2026-08-07T00:00:00Z",
  versions: [],
  events: [],
  tracking: {
    is_favorite: false,
    application_status: "not_started" as const,
    version: 0,
    updated_at: null,
    events: [],
  },
};

const resumes = [
  {
    id: "resume-1",
    filename: "算法简历.txt",
    display_name: "算法简历",
    target_roles: ["大模型算法工程师"],
    source_kind: "text",
    status: "confirmed",
    confirmed_sections: ["basic", "project", "skill"],
    created_at: "2026-08-08T00:00:00Z",
    updated_at: "2026-08-09T00:00:00Z",
  },
  {
    id: "resume-2",
    filename: "通用简历.txt",
    display_name: "通用简历",
    target_roles: ["后端工程师"],
    source_kind: "text",
    status: "partially_confirmed",
    confirmed_sections: ["basic", "skill"],
    created_at: "2026-08-08T00:00:00Z",
    updated_at: "2026-08-09T00:00:00Z",
  },
  {
    id: "resume-unconfirmed",
    filename: "待确认简历.txt",
    display_name: "待确认简历",
    target_roles: [],
    source_kind: "text",
    status: "partially_confirmed",
    confirmed_sections: [],
    created_at: "2026-08-08T00:00:00Z",
    updated_at: "2026-08-09T00:00:00Z",
  },
];

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function arrange() {
  api.getCareerResumes.mockResolvedValue({ ok: true, resumes });
}

describe("CareerResumeCoachLauncher", () => {
  it("selects one confirmed resume and starts AI coaching", async () => {
    arrange();
    const onStartAnalysis = vi.fn();
    render(
      <CareerResumeCoachLauncher
        job={job}
        onStartAnalysis={onStartAnalysis}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "AI 分析与改简历" }),
    );
    fireEvent.click(await screen.findByLabelText("算法简历"));
    fireEvent.click(
      screen.getByRole("button", { name: "进入 Career Agent" }),
    );

    expect(onStartAnalysis).toHaveBeenCalledWith({
      jobId: "job-1",
      resumeId: "resume-1",
      companyName: "DeepSeek",
      position: "大模型算法工程师",
      jobSheet: expect.stringContaining("- 要求1：必须熟悉 Python"),
    });
    expect(screen.queryByText("岗位与简历证据匹配")).toBeNull();
    expect(screen.queryByText("生成申请准备包")).toBeNull();
    expect(screen.queryByText("生成定制简历建议")).toBeNull();
    expect(api.getCareerResumes).toHaveBeenCalledOnce();
  });

  it("keeps exactly one resume selected", async () => {
    arrange();
    render(
      <CareerResumeCoachLauncher
        job={job}
        onStartAnalysis={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "AI 分析与改简历" }),
    );
    fireEvent.click(await screen.findByLabelText("算法简历"));
    fireEvent.click(screen.getByLabelText("通用简历"));

    expect(
      (screen.getByLabelText("算法简历") as HTMLInputElement).checked,
    ).toBe(false);
    expect(
      (screen.getByLabelText("通用简历") as HTMLInputElement).checked,
    ).toBe(true);
    expect(screen.queryByLabelText("待确认简历")).toBeNull();
  });

  it("shows the empty state when no confirmed resume exists", async () => {
    api.getCareerResumes.mockResolvedValue({
      ok: true,
      resumes: [resumes[2]],
    });
    render(
      <CareerResumeCoachLauncher
        job={job}
        onStartAnalysis={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "AI 分析与改简历" }),
    );

    expect(
      await screen.findByText(
        "暂无已确认简历，请前往我的求职档案导入并确认简历。",
      ),
    ).toBeTruthy();
    expect(
      (
        screen.getByRole("button", {
          name: "进入 Career Agent",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
  });

  it("shows the API error without falling back to matching", async () => {
    api.getCareerResumes.mockResolvedValue({
      ok: false,
      error: { code: "RESUME_LIST_FAILED", message: "简历读取失败。" },
    });
    render(
      <CareerResumeCoachLauncher
        job={job}
        onStartAnalysis={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "AI 分析与改简历" }),
    );

    expect(await screen.findByText("简历读取失败。")).toBeTruthy();
    expect(api).toEqual({ getCareerResumes: expect.any(Function) });
  });

  it("clears the previous selection when reopening fails", async () => {
    api.getCareerResumes
      .mockResolvedValueOnce({ ok: true, resumes })
      .mockResolvedValueOnce({
        ok: false,
        error: { code: "RESUME_LIST_FAILED", message: "简历读取失败。" },
      });
    const onStartAnalysis = vi.fn();
    render(
      <CareerResumeCoachLauncher
        job={job}
        onStartAnalysis={onStartAnalysis}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "AI 分析与改简历" }),
    );
    fireEvent.click(await screen.findByLabelText("算法简历"));
    fireEvent.click(screen.getByRole("button", { name: "关闭" }));
    fireEvent.click(
      screen.getByRole("button", { name: "AI 分析与改简历" }),
    );

    expect(await screen.findByText("简历读取失败。")).toBeTruthy();
    expect(screen.queryByLabelText("算法简历")).toBeNull();
    expect(
      (
        screen.getByRole("button", {
          name: "进入 Career Agent",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    expect(onStartAnalysis).not.toHaveBeenCalled();
  });

  it("shows a connection error and uses a mobile-safe dialog", async () => {
    api.getCareerResumes.mockRejectedValue(new Error("offline"));
    render(
      <CareerResumeCoachLauncher
        job={job}
        onStartAnalysis={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: "AI 分析与改简历" }),
    );

    expect(await screen.findByText("无法连接简历服务。")).toBeTruthy();
    const dialog = screen.getByRole("dialog");
    expect(dialog.className).toContain("max-h-[calc(100dvh-2rem)]");
    expect(dialog.className).toContain("w-full");
    expect(dialog.className).toContain("max-w-md");
    expect(dialog.className).toContain("overflow-y-auto");
  });
});
