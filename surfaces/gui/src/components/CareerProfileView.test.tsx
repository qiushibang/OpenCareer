import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { CareerProfileView } from "./CareerProfileView";

const api = vi.hoisted(() => ({
  getCareerResumes: vi.fn(),
  getCareerResume: vi.fn(),
  getCareerResumeVersions: vi.fn(),
  getCareerResumeOriginal: vi.fn(),
  getCareerResumeOriginalContent: vi.fn(),
  updateCareerResume: vi.fn(),
  deleteCareerResume: vi.fn(),
  deleteCareerProfile: vi.fn(),
  downloadCareerResumeOriginal: vi.fn(),
}));

vi.mock("../api", () => api);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const resume = {
  id: "resume-1",
  filename: "通用简历.pdf",
  display_name: "通用简历",
  target_roles: ["AI 工程师"],
  source_kind: "pdf",
  status: "confirmed",
  confirmed_sections: ["basic", "education", "skill"],
  sections: {
    basic: {
      name: "Z*** S**",
      phone: "*******1234",
      email: "z***@example.com",
      birth_date: "2001.10.07",
      location: "北京",
      summary: "AI Engineer",
    },
    education: [
      {
        school: "北京航空航天大学",
        degree: "硕士",
        major: "工业工程",
        gpa: "3.83/4.00",
        ranking: "25%",
        start_date: "2021-09",
        end_date: "2025-06",
      },
    ],
    experience: [],
    project: [],
    skill: [{ name: "Python", level: "advanced" }],
  },
  created_at: "2026-08-06T08:00:00Z",
  updated_at: "2026-08-07T08:00:00Z",
};

describe("CareerProfileView", () => {
  it("stacks the resume library and detail on mobile", async () => {
    api.getCareerResumes.mockResolvedValue({ ok: true, resumes: [resume] });
    api.getCareerResume.mockResolvedValue({ ok: true, resume });

    render(<CareerProfileView onImportResume={vi.fn()} />);

    await screen.findByText("北京航空航天大学");
    expect(screen.getByTestId("career-profile-layout").className).toContain(
      "grid-cols-1",
    );
    expect(screen.getByTestId("career-profile-layout").className).toContain(
      "lg:grid-cols-[240px_minmax(0,1fr)]",
    );
  });

  it("shows an import action when no profile exists", async () => {
    api.getCareerResumes.mockResolvedValue({ ok: true, resumes: [] });
    const onImportResume = vi.fn();

    render(<CareerProfileView onImportResume={onImportResume} />);

    expect(await screen.findByText("尚未建立求职档案")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "导入简历" }));
    expect(onImportResume).toHaveBeenCalledOnce();
  });

  it("switches independent resumes and renders the selected resume tabs", async () => {
    api.getCareerResumes.mockResolvedValue({
      ok: true,
      resumes: [
        resume,
        {
          ...resume,
          id: "resume-2",
          filename: "产品经理简历.docx",
          display_name: "产品经理简历",
          source_kind: "docx",
        },
      ],
    });
    api.getCareerResume.mockImplementation(async (resumeId: string) => ({
      ok: true,
      resume:
        resumeId === "resume-1"
          ? resume
          : {
              ...resume,
              id: "resume-2",
              filename: "产品经理简历.docx",
              display_name: "产品经理简历",
              source_kind: "docx",
              sections: {
                ...resume.sections,
                basic: {
                  ...resume.sections.basic,
                  summary: "产品经理定制版",
                },
              },
            },
    }));
    api.getCareerResumeVersions.mockResolvedValue({
      ok: true,
      versions: [
        {
          version: 2,
          confirmed_sections: ["basic", "skill"],
          filename: "resume.pdf",
          source_kind: "pdf",
          created_at: "2026-08-07T08:00:00Z",
        },
      ],
    });
    api.getCareerResumeOriginal.mockResolvedValue({
      ok: true,
      original: {
        filename: "产品经理简历.docx",
        source_kind: "pdf",
        size: 1024,
        preview_kind: "pdf",
      },
    });
    api.getCareerResumeOriginalContent.mockResolvedValue(
      "blob:resume-preview",
    );

    render(<CareerProfileView onImportResume={vi.fn()} />);

    expect(await screen.findByText("北京航空航天大学")).toBeTruthy();
    expect(screen.getByText("*******1234")).toBeTruthy();
    expect(screen.getByText("出生日期")).toBeTruthy();
    expect(screen.getByText("学历")).toBeTruthy();
    expect(screen.getByText("结束时间")).toBeTruthy();
    expect(screen.getByText("GPA")).toBeTruthy();
    expect(screen.getByText("排名")).toBeTruthy();
    expect(screen.queryByText("birth_date")).toBeNull();
    expect(screen.queryByText("end_date")).toBeNull();

    fireEvent.click(
      screen.getByRole("button", { name: /产品经理简历 DOCX/ }),
    );
    expect(await screen.findByText("产品经理定制版")).toBeTruthy();
    expect(api.getCareerResume).toHaveBeenLastCalledWith(
      "resume-2",
      false,
    );

    fireEvent.click(screen.getByRole("button", { name: "原始简历" }));
    expect(
      (await screen.findByTitle("原始简历预览")).getAttribute("src"),
    ).toBe("blob:resume-preview");
    expect(api.getCareerResumeOriginalContent).toHaveBeenCalledWith(
      "resume-2",
    );

    fireEvent.click(screen.getByRole("button", { name: "版本记录" }));
    expect(await screen.findByText("版本 2")).toBeTruthy();
    expect(screen.getByText(/确认章节：基本信息、技能/)).toBeTruthy();
  });

  it("loads clear sensitive fields only after explicit click", async () => {
    api.getCareerResumes.mockResolvedValue({
      ok: true,
      resumes: [resume],
    });
    api.getCareerResume
      .mockResolvedValueOnce({ ok: true, resume })
      .mockResolvedValueOnce({
        ok: true,
        resume: {
          ...resume,
          sections: {
            ...resume.sections,
            basic: {
              ...resume.sections.basic,
              phone: "13800001234",
              email: "zhang@example.com",
            },
          },
        },
      });

    render(<CareerProfileView onImportResume={vi.fn()} />);
    await screen.findByText("*******1234");
    fireEvent.click(screen.getByRole("button", { name: "显示敏感信息" }));

    await waitFor(() => expect(screen.getByText("13800001234")).toBeTruthy());
    expect(api.getCareerResume).toHaveBeenLastCalledWith("resume-1", true);
  });

  it("edits the selected resume name and target roles", async () => {
    api.getCareerResumes.mockResolvedValue({
      ok: true,
      resumes: [resume],
    });
    api.getCareerResume.mockResolvedValue({ ok: true, resume });
    api.updateCareerResume.mockResolvedValue({
      ok: true,
      resume: {
        ...resume,
        display_name: "AI 产品经理简历",
        target_roles: ["AI 产品经理", "Agent 产品经理"],
      },
    });

    render(<CareerProfileView onImportResume={vi.fn()} />);
    await screen.findByText("北京航空航天大学");
    fireEvent.click(screen.getByRole("button", { name: "编辑信息" }));
    fireEvent.change(screen.getByLabelText("简历名称"), {
      target: { value: "AI 产品经理简历" },
    });
    fireEvent.change(screen.getByLabelText("目标岗位"), {
      target: { value: "AI 产品经理, Agent 产品经理" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));

    await waitFor(() =>
      expect(api.updateCareerResume).toHaveBeenCalledWith("resume-1", {
        displayName: "AI 产品经理简历",
        targetRoles: ["AI 产品经理", "Agent 产品经理"],
      }),
    );
    expect(await screen.findAllByText("AI 产品经理简历")).toHaveLength(2);
    expect(screen.getAllByText("AI 产品经理")).toHaveLength(2);
    expect(screen.getAllByText("Agent 产品经理")).toHaveLength(2);
  });

  it("deletes one resume by exact name and selects the adjacent resume", async () => {
    const secondResume = {
      ...resume,
      id: "resume-2",
      filename: "产品经理简历.docx",
      display_name: "产品经理简历",
      source_kind: "docx",
      sections: {
        ...resume.sections,
        basic: {
          ...resume.sections.basic,
          summary: "产品经理定制版",
        },
      },
    };
    api.getCareerResumes.mockResolvedValue({
      ok: true,
      resumes: [resume, secondResume],
    });
    api.getCareerResume.mockImplementation(async (resumeId: string) => ({
      ok: true,
      resume: resumeId === "resume-1" ? resume : secondResume,
    }));
    api.deleteCareerResume.mockResolvedValue({
      ok: true,
      deleted: { resume_id: "resume-1", original_removed: true },
    });

    render(<CareerProfileView onImportResume={vi.fn()} />);
    await screen.findByText("北京航空航天大学");
    fireEvent.click(screen.getByRole("button", { name: "删除此简历" }));
    expect(screen.getByText(/已确认进入共享求职档案的事实会保留/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("输入简历名称"), {
      target: { value: "通用简历" },
    });
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    await waitFor(() =>
      expect(api.deleteCareerResume).toHaveBeenCalledWith(
        "resume-1",
        "通用简历",
      ),
    );
    expect(await screen.findByText("产品经理定制版")).toBeTruthy();
    expect(api.getCareerResume).toHaveBeenLastCalledWith("resume-2", false);
    expect(
      screen.queryByRole("button", { name: /通用简历 PDF/ }),
    ).toBeNull();
  });
});
