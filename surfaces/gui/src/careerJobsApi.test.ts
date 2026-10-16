import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getCareerJob,
  getCareerJobFilters,
  getCareerJobs,
  updateCareerJobTracking,
} from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("career jobs API", () => {
  it("encodes non-empty filters and omits empty values", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      json: async () => ({ ok: true, jobs: [], total: 0 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await getCareerJobs({
      query: "大模型",
      companySlug: "deepseek",
      location: "",
      recruitmentType: undefined,
      status: "active",
      limit: 20,
      offset: 0,
    });

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("/v1/career/jobs?");
    expect(url).toContain("query=%E5%A4%A7%E6%A8%A1%E5%9E%8B");
    expect(url).toContain("company_slug=deepseek");
    expect(url).toContain("status=active");
    expect(url).toContain("limit=20");
    expect(url).toContain("offset=0");
    expect(url).not.toContain("location=");
    expect(url).not.toContain("recruitment_type=");
  });

  it("uses encoded detail and fixed filter paths", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await getCareerJob("job/one");
    await getCareerJobFilters();

    expect(String(fetchMock.mock.calls[0][0])).toContain(
      "/v1/career/jobs/job%2Fone",
    );
    expect(String(fetchMock.mock.calls[1][0])).toContain(
      "/v1/career/jobs/filters",
    );
  });

  it("encodes tracking filters and patches a versioned record", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      json: async () => ({ ok: true }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await getCareerJobs({
      favoriteOnly: true,
      applicationStatus: "interviewing",
    });
    await updateCareerJobTracking("job/one", {
      expected_version: 3,
      is_favorite: false,
    });

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("favorite_only=true");
    expect(url).toContain("application_status=interviewing");
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: "PATCH",
    });
    expect(fetchMock.mock.calls[1][1].body).toBe(
      JSON.stringify({
        expected_version: 3,
        is_favorite: false,
      }),
    );
  });
});
