import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import { CareerJobsView } from "./CareerJobsView";

// Filters use the custom listbox select: open the combobox, then pick an option.
function choose(name: string | RegExp, option: string | RegExp) {
  fireEvent.click(screen.getByRole("combobox", { name }));
  fireEvent.click(screen.getByRole("option", { name: option }));
}

const api = vi.hoisted(() => ({
  isLocal: () => false,
  getCareerJobs: vi.fn(),
  getCareerJob: vi.fn(),
  getCareerJobFilters: vi.fn(),
  getCareerResumes: vi.fn(),
  updateCareerJobTracking: vi.fn(),
}));

vi.mock("../api", () => api);
vi.mock("./LocalJobSyncBanner", () => ({
  LocalJobSyncBanner: ({ onUpdated }: { onUpdated: () => void }) => <button onClick={onUpdated}>模拟后台岗位更新</button>,
}));

const jobs = [
  {
    id: "job-1",
    company: { slug: "deepseek", name: "DeepSeek" },
    title: "大模型算法工程师",
    locations: ["北京"],
    location_raw: "北京",
    recruitment_type: "experienced",
    status: "active",
    description_raw: "完整 JD",
    responsibilities: ["训练大模型"],
    requirements: ["熟悉 Python"],
    source_url: "https://careers.deepseek.com/jobs/1",
    first_seen_at: "2026-08-05T00:00:00Z",
    last_seen_at: "2026-08-08T00:00:00Z",
    last_changed_at: "2026-08-07T00:00:00Z",
    tracking: {
      is_favorite: false,
      application_status: "not_started",
      version: 0,
      updated_at: null,
    },
  },
  {
    id: "job-2",
    company: { slug: "xiaomi", name: "小米" },
    title: "AI 平台研发工程师",
    locations: ["上海"],
    location_raw: "上海",
    recruitment_type: "campus",
    status: "active",
    description_raw: "第二份 JD",
    responsibilities: [],
    requirements: [],
    source_url: "manual://job-2",
    first_seen_at: "2026-08-04T00:00:00Z",
    last_seen_at: "2026-08-08T00:00:00Z",
    last_changed_at: "2026-08-06T00:00:00Z",
    tracking: {
      is_favorite: false,
      application_status: "not_started",
      version: 0,
      updated_at: null,
    },
  },
];

const detail = {
  ...jobs[0],
  versions: [
    {
      version_number: 2,
      content_hash: "hash",
      captured_at: "2026-08-07T00:00:00Z",
    },
  ],
  events: [
    {
      event_type: "changed",
      summary: "Job content changed",
      changed_fields: ["content"],
      occurred_at: "2026-08-07T00:00:00Z",
    },
  ],
  tracking: {
    ...jobs[0].tracking,
    events: [
      {
        id: "event-2",
        from_status: "preparing",
        to_status: "applied",
        occurred_at: "2026-08-09T02:00:00Z",
      },
      {
        id: "event-1",
        from_status: "not_started",
        to_status: "preparing",
        occurred_at: "2026-08-09T01:00:00Z",
      },
    ],
  },
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function arrange() {
  api.getCareerJobFilters.mockResolvedValue({
    ok: true,
    filters: {
      favorite_count: 1,
      companies: [
        { slug: "deepseek", name: "DeepSeek", count: 1 },
        { slug: "xiaomi", name: "小米", count: 1 },
      ],
      locations: [
        { value: "北京", count: 1 },
        { value: "上海", count: 1 },
      ],
      recruitment_types: [
        { value: "social", count: 1 },
        { value: "campus", count: 1 },
      ],
      statuses: [
        { value: "active", count: 2 },
        { value: "inactive", count: 0 },
      ],
    },
  });
  api.getCareerJobs.mockResolvedValue({
    ok: true,
    jobs,
    total: 21,
    limit: 20,
    offset: 0,
  });
  api.getCareerJob.mockResolvedValue({ ok: true, job: detail });
  api.getCareerResumes.mockResolvedValue({ ok: true, resumes: [] });
  api.updateCareerJobTracking.mockResolvedValue({
    ok: true,
    tracking: {
      ...detail.tracking,
      is_favorite: true,
      version: 1,
    },
  });
}

describe("CareerJobsView", () => {
  it("preserves the selected job and unsaved application note during background imports", async () => {
    arrange();
    render(<CareerJobsView />);
    await screen.findByLabelText("申请备注");
    fireEvent.change(screen.getByLabelText("申请备注"), { target: { value: "还未保存的申请备注" } });
    api.getCareerJobs.mockResolvedValue({ ok: true, jobs: [jobs[1]], total: 30 });
    fireEvent.click(screen.getByRole("button", { name: "模拟后台岗位更新" }));
    await waitFor(() => expect(screen.getByText("30 个岗位")).toBeTruthy());
    expect((screen.getByLabelText("申请备注") as HTMLTextAreaElement).value).toBe("还未保存的申请备注");
    expect(api.getCareerJob).toHaveBeenCalledTimes(1);
    expect(api.getCareerJob).toHaveBeenLastCalledWith("job-1");
  });
  it("opens one shared interview setup from list and detail entries", async () => {
    arrange();
    api.getCareerResumes.mockResolvedValue({
      ok: true,
      resumes: [
        {
          id: "resume-1",
          display_name: "算法简历",
          target_roles: ["大模型算法工程师"],
          source_kind: "text",
          status: "confirmed",
          confirmed_sections: ["basic", "project"],
          created_at: "2026-08-08T00:00:00Z",
          updated_at: "2026-08-09T00:00:00Z",
        },
      ],
    });

    render(<CareerJobsView onStartInterview={vi.fn()} />);

    await screen.findByRole("heading", { name: "JD" });
    expect(
      screen.getByRole("button", {
        name: "从岗位列表模拟面试：大模型算法工程师",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", {
        name: "从岗位列表模拟面试：AI 平台研发工程师",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", {
        name: "从岗位详情模拟面试：大模型算法工程师",
      }),
    ).toBeTruthy();

    fireEvent.click(
      screen.getByRole("button", {
        name: "从岗位列表模拟面试：AI 平台研发工程师",
      }),
    );

    expect(
      await screen.findByRole("dialog", { name: "模拟面试设置" }),
    ).toBeTruthy();
    expect(screen.getByText("AI 平台研发工程师")).toBeTruthy();
    fireEvent.click(screen.getByRole("combobox", { name: "面试时长" }));
    expect(
      screen.getAllByRole("option").map((option) => option.textContent),
    ).toEqual(["10 分钟 · 5 题", "15 分钟 · 5 题", "20 分钟 · 5 题"]);
    fireEvent.keyDown(screen.getByRole("listbox", { name: "面试时长" }), { key: "Escape" });
    expect(api.getCareerJob).not.toHaveBeenCalledWith("job-2");
  });

  it("launches an interview directly from one confirmed resume", async () => {
    arrange();
    api.getCareerResumes.mockResolvedValue({
      ok: true,
      resumes: [
        {
          id: "resume-1",
          display_name: "算法简历",
          target_roles: ["大模型算法工程师"],
          source_kind: "text",
          status: "confirmed",
          confirmed_sections: ["basic", "project"],
          created_at: "2026-08-08T00:00:00Z",
          updated_at: "2026-08-09T00:00:00Z",
        },
      ],
    });
    const onStartInterview = vi.fn();
    render(<CareerJobsView onStartInterview={onStartInterview} />);
    await screen.findByRole("heading", { name: "JD" });

    fireEvent.click(
      screen.getByRole("button", {
        name: "从岗位详情模拟面试：大模型算法工程师",
      }),
    );
    fireEvent.click(
      await screen.findByRole("button", {
        name: "开始模拟面试",
      }),
    );

    await waitFor(() =>
      expect(onStartInterview).toHaveBeenCalledWith({
        jobId: "job-1",
        resumeId: "resume-1",
        position: "大模型算法工程师",
        durationMinutes: 15,
        difficulty: "standard",
      }),
    );
  });

  it("keeps interview setup open when resume loading fails", async () => {
    arrange();
    api.getCareerResumes.mockRejectedValue(new Error("offline"));
    const onStartInterview = vi.fn();
    render(<CareerJobsView onStartInterview={onStartInterview} />);
    await screen.findByRole("heading", { name: "JD" });

    fireEvent.click(
      screen.getByRole("button", {
        name: "从岗位详情模拟面试：大模型算法工程师",
      }),
    );
    expect(
      await screen.findByText("无法连接本地简历服务。"),
    ).toBeTruthy();
    expect(
      screen.getByRole("dialog", { name: "模拟面试设置" }),
    ).toBeTruthy();
    expect(onStartInterview).not.toHaveBeenCalled();
  });

  it("recovers a throttled job list after the requested delay", async () => {
    arrange();
    api.getCareerJobs.mockRejectedValueOnce(Object.assign(new Error("请求较多，请稍后重试。"),{retryAfterMs:1000}));
    render(<CareerJobsView />);
    expect(await screen.findByRole("alert")).toHaveProperty("textContent",expect.stringContaining("自动重试"));
    await waitFor(()=>expect(screen.queryByRole("alert")).toBeNull(),{timeout:2500});
    expect(await screen.findByRole("heading",{name:"大模型算法工程师"})).toBeTruthy();
    expect(api.getCareerJobs).toHaveBeenCalledTimes(2);
  });

  it("loads active jobs and selects the first detail", async () => {
    arrange();

    const { container } = render(<CareerJobsView />);

    expect(await screen.findByText("大模型算法工程师")).toBeTruthy();
    expect(screen.queryByRole("combobox", {name:"岗位状态"})).toBeNull();
    expect(api.getCareerJobs).toHaveBeenCalledWith(
      expect.objectContaining({
        status: "active",
        limit: 20,
        offset: 0,
      }),
    );
    await waitFor(() =>
      expect(api.getCareerJob).toHaveBeenCalledWith("job-1"),
    );
    expect(
      await screen.findByRole("heading", { name: "JD" }),
    ).toBeTruthy();
    expect(screen.getByRole("link", { name: "查看官网" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "AI 分析与改简历" }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "匹配简历" }),
    ).toBeNull();
    expect(screen.getByText(/版本 2/)).toBeTruthy();
    expect(screen.queryByText("experienced")).toBeNull();
    expect(
      container.querySelector('[data-job-type="experienced"]')?.textContent,
    ).toBe("社会招聘");
  });

  it("applies filters, resets pagination, and switches details", async () => {
    arrange();

    render(<CareerJobsView />);
    await screen.findByText("大模型算法工程师");
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() =>
      expect(api.getCareerJobs).toHaveBeenLastCalledWith(
        expect.objectContaining({ offset: 20 }),
      ),
    );

    choose("公司", /^小米/);
    await waitFor(() =>
      expect(api.getCareerJobs).toHaveBeenLastCalledWith(
        expect.objectContaining({ companySlug: "xiaomi", offset: 0 }),
      ),
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: /^AI 平台研发工程师 小米/,
      }),
    );
    await waitFor(() =>
      expect(api.getCareerJob).toHaveBeenLastCalledWith("job-2"),
    );
  });

  it("renders only the original JD and hides non-http source links", async () => {
    arrange();
    api.getCareerJob.mockResolvedValueOnce({
      ok: true,
      job: { ...jobs[1], versions: [], events: [] },
    });

    render(<CareerJobsView />);
    await screen.findByText("大模型算法工程师");

    expect(screen.queryByRole("link", { name: "查看官网" })).toBeNull();
    expect(await screen.findByRole("heading", { name: "JD" })).toBeTruthy();
    expect(screen.getByText("第二份 JD")).toBeTruthy();
    expect(
      screen.queryByRole("heading", { name: "职位职责" }),
    ).toBeNull();
    expect(
      screen.queryByRole("heading", { name: "职位要求" }),
    ).toBeNull();
    expect(
      screen.queryByRole("heading", { name: "完整 JD" }),
    ).toBeNull();
  });

  it("switches between all jobs and the favorites box", async () => {
    arrange();
    render(<CareerJobsView />);
    await screen.findByText("大模型算法工程师");

    expect(
      screen
        .getByRole("button", { name: "全部岗位" })
        .getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      screen.getByRole("button", { name: "收藏箱（1）" }),
    ).toBeTruthy();
    expect(screen.queryByLabelText("仅看收藏")).toBeNull();

    fireEvent.click(
      screen.getByRole("button", { name: "收藏箱（1）" }),
    );
    choose(/^申请进度$/, "面试中");

    await waitFor(() =>
      expect(api.getCareerJobs).toHaveBeenLastCalledWith(
        expect.objectContaining({
          favoriteOnly: true,
          applicationStatus: "interviewing",
          offset: 0,
        }),
      ),
    );
  });

  it("retains inactive favorites and their notes after full catalog replacement", async () => {
    arrange();
    const archived = { ...jobs[0], id: "archived-favorite", title: "已下线的收藏岗位", status: "inactive",
      tracking: { ...detail.tracking, is_favorite: true, note: "保留原备注" } };
    api.getCareerJobs.mockImplementation(async (criteria: { favoriteOnly?: boolean; status?: string }) => {
      const visible = criteria.favoriteOnly ? (criteria.status === "" ? [archived] : []) : jobs;
      return { ok: true, jobs: visible, total: visible.length };
    });
    api.getCareerJob.mockImplementation(async (id: string) => ({ ok: true,
      job: id === archived.id ? { ...detail, ...archived } : detail }));
    render(<CareerJobsView />);
    await screen.findByRole("heading", { name: "JD" });
    fireEvent.click(screen.getByRole("button", { name: "收藏箱（1）" }));
    await screen.findByRole("heading", { name: archived.title });
    expect(await screen.findByDisplayValue("保留原备注")).toBeTruthy();
    expect(api.getCareerJobs).toHaveBeenLastCalledWith(expect.objectContaining({ favoriteOnly: true, status: "" }));
    fireEvent.click(screen.getByRole("button", { name: "全部岗位" }));
    await waitFor(() => expect(api.getCareerJobs).toHaveBeenLastCalledWith(
      expect.objectContaining({ favoriteOnly: false, status: "active" })));
    await waitFor(() => expect(screen.queryByRole("heading", { name: archived.title })).toBeNull());
  });

  it("uses responsive job filters and list-detail layout", async () => {
    arrange();
    render(<CareerJobsView />);
    await screen.findByRole("heading", { name: "JD" });

    // Two compact filter columns on phones; the search box spans the full row.
    expect(
      screen.getByTestId("job-filter-grid").className,
    ).toContain("grid-cols-2");
    expect(
      screen.getByTestId("job-radar-layout").className,
    ).toContain("grid-cols-1");
    expect(
      screen.getByTestId("job-detail-header").className,
    ).toContain("flex-col");
  });

  it("favorites without switching detail and rolls back on failure", async () => {
    arrange();
    api.updateCareerJobTracking.mockResolvedValueOnce({
      ok: false,
      error: {
        code: "PERSISTENCE_ERROR",
        message: "保存失败。",
      },
    });
    render(<CareerJobsView />);
    await screen.findByText("大模型算法工程师");
    await waitFor(() =>
      expect(api.getCareerJob).toHaveBeenCalledTimes(1),
    );

    fireEvent.click(
      screen.getByRole("button", {
        name: "收藏岗位：AI 平台研发工程师",
      }),
    );

    await waitFor(() =>
      expect(api.updateCareerJobTracking).toHaveBeenCalledWith(
        "job-2",
        {
          expected_version: 0,
          is_favorite: true,
        },
      ),
    );
    expect(api.getCareerJob).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("保存失败。")).toBeTruthy();
    expect(
      screen.getByRole("button", {
        name: "收藏岗位：AI 平台研发工程师",
      }),
    ).toBeTruthy();
  });

  it("saves application progress and renders a Chinese timeline", async () => {
    arrange();
    api.updateCareerJobTracking.mockResolvedValueOnce({
      ok: true,
      tracking: {
        ...detail.tracking,
        application_status: "applied",
        note: "已完成官网投递",
        version: 1,
      },
    });
    render(<CareerJobsView />);
    await screen.findByRole("heading", { name: "JD" });

    choose("我的申请进度", "已投递");
    fireEvent.change(screen.getByLabelText("申请备注"), {
      target: { value: "已完成官网投递" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "保存申请进度" }),
    );

    await waitFor(() =>
      expect(api.updateCareerJobTracking).toHaveBeenCalledWith(
        "job-1",
        {
          expected_version: 0,
          application_status: "applied",
          note: "已完成官网投递",
        },
      ),
    );
    const timeline = screen.getByTestId("application-timeline");
    expect(timeline.textContent).not.toContain("not_started");
    expect(timeline.textContent).not.toContain("preparing");
    expect(timeline.textContent).not.toContain("applied");
    expect(timeline.textContent?.indexOf("已投递")).toBeLessThan(
      timeline.textContent?.indexOf("准备材料") ?? 0,
    );
    expect(timeline.textContent).toContain("10:00");
    expect(timeline.textContent).toContain("09:00");
  });

  it("refreshes tracking after a version conflict", async () => {
    arrange();
    api.updateCareerJobTracking.mockResolvedValueOnce({
      ok: false,
      error: {
        code: "VERSION_CONFLICT",
        message: "记录已在其他入口更新。",
      },
    });
    api.getCareerJob
      .mockResolvedValueOnce({ ok: true, job: detail })
      .mockResolvedValueOnce({
        ok: true,
        job: {
          ...detail,
          tracking: {
            ...detail.tracking,
            application_status: "interviewing",
            version: 2,
          },
        },
      });
    render(<CareerJobsView />);
    await screen.findByRole("heading", { name: "JD" });

    fireEvent.click(
      screen.getByRole("button", { name: "保存申请进度" }),
    );

    expect(
      await screen.findByText(
        "记录已在其他入口更新，请确认最新内容后重试。",
      ),
    ).toBeTruthy();
    await waitFor(() =>
      expect(api.getCareerJob).toHaveBeenCalledTimes(2),
    );
    expect(
      screen.getByRole("combobox", { name: "我的申请进度" }).textContent,
    ).toBe("面试中");
  });

  it("refreshes the operated job after a favorite version conflict", async () => {
    arrange();
    api.updateCareerJobTracking.mockResolvedValueOnce({
      ok: false,
      error: {
        code: "VERSION_CONFLICT",
        message: "记录已在其他入口更新。",
      },
    });
    api.getCareerJob
      .mockReset()
      .mockResolvedValueOnce({ ok: true, job: detail })
      .mockResolvedValueOnce({
        ok: true,
        job: {
          ...jobs[1],
          versions: [],
          events: [],
          tracking: {
            ...jobs[1].tracking,
            is_favorite: true,
            version: 2,
            events: [],
          },
        },
      });
    render(<CareerJobsView />);
    await screen.findByRole("heading", { name: "JD" });

    fireEvent.click(
      screen.getByRole("button", {
        name: "收藏岗位：AI 平台研发工程师",
      }),
    );

    expect(
      await screen.findByText(
        "记录已在其他入口更新，请确认最新内容后重试。",
      ),
    ).toBeTruthy();
    await waitFor(() =>
      expect(api.getCareerJob).toHaveBeenLastCalledWith("job-2"),
    );
    expect(
      screen.getByRole("button", {
        name: "取消收藏：AI 平台研发工程师",
      }),
    ).toBeTruthy();
  });

  it("reloads favorite results and selects the next job after unfavorite", async () => {
    arrange();
    const favoriteJobs = jobs.map((job) => ({
      ...job,
      tracking: {
        ...job.tracking,
        is_favorite: true,
        version: 1,
      },
    }));
    const secondDetail = {
      ...detail,
      ...favoriteJobs[1],
      versions: [],
      events: [],
      tracking: {
        ...favoriteJobs[1].tracking,
        events: [],
      },
    };
    api.getCareerJobs
      .mockReset()
      .mockResolvedValueOnce({
        ok: true,
        jobs: favoriteJobs,
        total: 2,
        limit: 20,
        offset: 0,
      })
      .mockResolvedValueOnce({
        ok: true,
        jobs: favoriteJobs,
        total: 2,
        limit: 20,
        offset: 0,
      })
      .mockResolvedValueOnce({
        ok: true,
        jobs: [favoriteJobs[1]],
        total: 1,
        limit: 20,
        offset: 0,
      });
    api.getCareerJob.mockImplementation(async (jobId: string) => ({
      ok: true,
      job: jobId === "job-1"
        ? {
            ...detail,
            tracking: {
              ...detail.tracking,
              is_favorite: true,
              version: 1,
            },
          }
        : secondDetail,
    }));
    api.updateCareerJobTracking.mockResolvedValueOnce({
      ok: true,
      tracking: {
        ...favoriteJobs[0].tracking,
        is_favorite: false,
        version: 2,
      },
    });
    render(<CareerJobsView />);
    await screen.findByRole("button", {
      name: /^大模型算法工程师 DeepSeek/,
    });
    await waitFor(() =>
      expect(api.getCareerJob).toHaveBeenCalledWith("job-1"),
    );

    fireEvent.click(
      screen.getByRole("button", { name: "收藏箱（1）" }),
    );
    await waitFor(() =>
      expect(api.getCareerJobs).toHaveBeenCalledTimes(2),
    );
    fireEvent.click(
      screen.getAllByRole("button", {
        name: "取消收藏：大模型算法工程师",
      })[0],
    );

    await waitFor(() =>
      expect(api.getCareerJobs).toHaveBeenCalledTimes(3),
    );
    await waitFor(() =>
      expect(api.getCareerJob).toHaveBeenLastCalledWith("job-2"),
    );
    expect(
      screen.queryByRole("button", {
        name: /^大模型算法工程师 DeepSeek/,
      }),
    ).toBeNull();
    expect(
      screen.getByRole("button", {
        name: /^AI 平台研发工程师 小米/,
      }),
    ).toBeTruthy();
    expect(screen.getByText("1 个岗位")).toBeTruthy();
    expect(screen.getByText("1-1 / 1")).toBeTruthy();
  });

});
