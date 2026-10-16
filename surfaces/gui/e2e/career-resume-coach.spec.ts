import { expect } from "@playwright/test";
import { test } from "./fixtures";

const job = {
  id: "job-1",
  company: { slug: "deepseek", name: "DeepSeek" },
  title: "大模型算法工程师",
  locations: ["北京"],
  location_raw: "北京",
  recruitment_type: "social",
  status: "active",
  description_raw: "负责大模型训练与 RAG 系统建设。",
  responsibilities: ["训练大模型"],
  requirements: ["熟悉 Python", "具备 RAG 项目经验"],
  source_url: "https://careers.deepseek.com/jobs/one",
  first_seen_at: "2026-08-05T00:00:00Z",
  last_seen_at: "2026-08-08T00:00:00Z",
  last_changed_at: "2026-08-07T00:00:00Z",
  versions: [],
  events: [],
  tracking: {
    is_favorite: false,
    application_status: "not_started",
    version: 0,
    updated_at: null,
    events: [],
  },
};

const resume = {
  id: "resume-1",
  filename: "算法简历.txt",
  display_name: "算法简历",
  target_roles: ["大模型算法工程师"],
  source_kind: "text",
  status: "confirmed",
  confirmed_sections: ["basic", "project", "skill"],
  created_at: "2026-08-08T00:00:00Z",
  updated_at: "2026-08-09T00:00:00Z",
};

async function mockCareerApi(page: import("@playwright/test").Page) {
  await page.route("**/v1/career/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const json = (body: unknown) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(body),
      });

    if (url.pathname.endsWith("/v1/career/jobs/filters")) {
      return json({
        ok: true,
        filters: {
          favorite_count: 0,
          companies: [{ slug: "deepseek", name: "DeepSeek", count: 1 }],
          locations: [{ value: "北京", count: 1 }],
          recruitment_types: [{ value: "social", count: 1 }],
          statuses: [{ value: "active", count: 1 }],
        },
      });
    }
    if (url.pathname.endsWith("/v1/career/jobs/job-1")) {
      return json({ ok: true, job });
    }
    if (url.pathname.endsWith("/v1/career/jobs")) {
      return json({ ok: true, jobs: [job], total: 1 });
    }
    if (url.pathname.endsWith("/v1/career/resumes")) {
      return json({ ok: true, resumes: [resume] });
    }
    return json({});
  });
}

for (const viewport of [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 375, height: 812 },
]) {
  test(`AI resume coach launcher fits the ${viewport.name} viewport`, async ({
    page,
  }) => {
    const browserErrors: string[] = [];
    page.on("console", (message) => {
      if (message.type() === "error") browserErrors.push(message.text());
    });
    page.on("pageerror", (error) => browserErrors.push(error.message));
    await mockCareerApi(page);
    await page.setViewportSize({
      width: viewport.width,
      height: viewport.height,
    });
    await page.goto("/");
    await page.waitForLoadState("networkidle");

    if (viewport.name === "mobile") {
      await page
        .locator(".main-topbar")
        .getByRole("button", { name: "显示侧边栏" })
        .click();
      await expect(page.locator(".app")).toHaveClass(/mobile-nav-open/);
    }
    await page.getByRole("button", { name: "岗位雷达" }).click();

    const launch = page.getByRole("button", {
      name: "AI 分析与改简历",
    });
    await expect(launch).toBeVisible();
    await launch.click();

    const dialog = page.getByRole("dialog", {
      name: "选择用于分析的简历",
    });
    await expect(dialog).toBeVisible();
    await expect(page.getByLabel("算法简历")).toBeChecked();
    await expect(
      page.getByRole("button", { name: "进入 Career Agent" }),
    ).toBeEnabled();

    const box = await dialog.boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width);
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);

    await page.screenshot({
      path: `/tmp/opencareer-resume-coach-${viewport.name}.png`,
      fullPage: true,
    });

    await page
      .getByRole("button", { name: "进入 Career Agent" })
      .click();
    await expect(
      page.getByText("开始 AI 简历诊断", { exact: true }),
    ).toHaveCount(1);
    expect(browserErrors).toEqual([]);
  });
}
