import { FormEvent, MouseEvent, useCallback, useEffect, useRef, useState } from "react";

import {
  getCareerResumes,
  getCareerJob,
  getCareerJobFilters,
  getCareerJobs,
  updateCareerJobTracking,
  type CareerApplicationStatus,
  type CareerJobDetail,
  type CareerJobFilters,
  type CareerResumeSummary,
  type CareerJobSummary,
  type CareerJobTracking,
} from "../api";
import {
  careerJobTypeClass,
  careerJobTypeLabel,
} from "../careerJobLabels";
import type { ResumeCoachLaunchPayload } from "../careerResumeCoach";
import { CareerResumeCoachLauncher } from "./CareerResumeCoachLauncher";
import { LocalJobSyncBanner } from "./LocalJobSyncBanner";

const PAGE_SIZE = 20;

export interface InterviewLaunchPayload {
  jobId: string;
  resumeId: string;
  position: string;
  durationMinutes: 10 | 15 | 20;
  difficulty: "simple" | "standard" | "deep";
}

const STATUS_NAMES: Record<string, string> = {
  active: "在招中",
  inactive: "已下线",
};

const EVENT_NAMES: Record<string, string> = {
  created: "首次发现",
  changed: "岗位变化",
  missing: "暂未发现",
  offline: "岗位下线",
  reopened: "重新上线",
};

const APPLICATION_STATUS_NAMES: Record<CareerApplicationStatus, string> = {
  not_started: "未开始",
  preparing: "准备材料",
  applied: "已投递",
  assessment: "笔试/测评",
  interviewing: "面试中",
  offer: "已获 Offer",
  accepted: "已接受 Offer",
  rejected: "未通过",
  withdrawn: "已撤回",
};

const APPLICATION_STATUSES = Object.keys(
  APPLICATION_STATUS_NAMES,
) as CareerApplicationStatus[];

const displayStatus = (value: string) => STATUS_NAMES[value] || value;

const formatDate = (value: string) =>
  new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));

const formatDateTime = (value: string) =>
  new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "Asia/Shanghai",
  }).format(new Date(value));

const jobScopeClass = (active: boolean) =>
  "min-w-[112px] rounded-md px-3 py-1.5 text-[12.5px] font-medium " +
  "transition-colors " +
  (active
    ? "bg-accent text-white"
    : "text-muted hover:bg-panel hover:text-ink");

export function CareerJobsView({
  onStartResumeCoach,
  onStartInterview,
}: {
  onStartResumeCoach?: (payload: ResumeCoachLaunchPayload) => void;
  onStartInterview?: (payload: InterviewLaunchPayload) => void;
} = {}) {
  const [filters, setFilters] = useState<CareerJobFilters | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [companySlug, setCompanySlug] = useState("");
  const [location, setLocation] = useState("");
  const [recruitmentType, setRecruitmentType] = useState("");
  const [status, setStatus] = useState("active");
  const [favoriteOnly, setFavoriteOnly] = useState(false);
  const [applicationStatus, setApplicationStatus] = useState<
    CareerApplicationStatus | ""
  >("");
  const [offset, setOffset] = useState(0);
  const [listRevision, setListRevision] = useState(0);
  const [catalogRevision, setCatalogRevision] = useState(0);
  const refreshCatalog = useCallback(() => setCatalogRevision(value => value + 1), []);
  const previousList = useRef({ criteria: "", catalogRevision: 0 });
  const [jobs, setJobs] = useState<CareerJobSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState<CareerJobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [trackingPending, setTrackingPending] = useState(false);
  const [trackingError, setTrackingError] = useState("");
  const [draftStatus, setDraftStatus] =
    useState<CareerApplicationStatus>("not_started");
  const [draftNote, setDraftNote] = useState("");
  const [interviewJob, setInterviewJob] =
    useState<CareerJobSummary | null>(null);
  const [interviewResumes, setInterviewResumes] = useState<
    CareerResumeSummary[]
  >([]);
  const [interviewResumeId, setInterviewResumeId] = useState("");
  const [interviewSetupLoading, setInterviewSetupLoading] =
    useState(false);
  const [interviewSetupError, setInterviewSetupError] = useState("");
  const [interviewDuration, setInterviewDuration] =
    useState<10 | 15 | 20>(15);
  const [interviewDifficulty, setInterviewDifficulty] = useState<
    "simple" | "standard" | "deep"
  >("standard");

  useEffect(() => {
    getCareerJobFilters()
      .then((result) => {
        if (result.ok && result.filters) setFilters(result.filters);
      })
      .catch(() => undefined);
  }, [listRevision, catalogRevision]);

  useEffect(() => {
    let current = true;
    const criteria = JSON.stringify([query, companySlug, location, recruitmentType,
      status, favoriteOnly, applicationStatus, offset]);
    const preserveSelection = previousList.current.criteria === criteria
      && previousList.current.catalogRevision !== catalogRevision;
    previousList.current = { criteria, catalogRevision };
    setLoading(true);
    setError("");
    getCareerJobs({
      query,
      companySlug,
      location,
      recruitmentType,
      status,
      favoriteOnly,
      applicationStatus: applicationStatus || undefined,
      limit: PAGE_SIZE,
      offset,
    })
      .then((result) => {
        if (!current) return;
        if (!result.ok) {
          setError(result.error?.message || "无法读取岗位列表。");
          setJobs([]);
          setTotal(0);
          return;
        }
        const nextJobs = result.jobs || [];
        setJobs(nextJobs);
        setTotal(result.total || 0);
        setSelectedId((value) =>
          (preserveSelection && value) || nextJobs.some((job) => job.id === value)
            ? value
            : nextJobs[0]?.id || "",
        );
      })
      .catch(() => {
        if (current) setError("无法连接本地岗位服务。");
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [
    query,
    companySlug,
    location,
    recruitmentType,
    status,
    favoriteOnly,
    applicationStatus,
    offset,
    listRevision,
    catalogRevision,
  ]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    let current = true;
    setDetailLoading(true);
    setDetailError("");
    setTrackingError("");
    getCareerJob(selectedId)
      .then((result) => {
        if (!current) return;
        if (result.ok && result.job) setDetail(result.job);
        else {
          setDetail(null);
          setDetailError(result.error?.message || "无法读取岗位详情。");
        }
      })
      .catch(() => {
        if (current) {
          setDetail(null);
          setDetailError("无法连接本地岗位服务。");
        }
      })
      .finally(() => {
        if (current) setDetailLoading(false);
      });
    return () => {
      current = false;
    };
  }, [selectedId]);

  useEffect(() => {
    if (!detail) return;
    setDraftStatus(detail.tracking.application_status);
    setDraftNote(detail.tracking.note || "");
  }, [detail?.id, detail?.tracking.version]);

  const resetOffset = (change: () => void) => {
    change();
    setOffset(0);
  };

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    resetOffset(() => setQuery(queryInput.trim()));
  };

  const applyTracking = (
    jobId: string,
    tracking: CareerJobTracking,
  ) => {
    setJobs((current) =>
      current.map((job) =>
        job.id === jobId ? { ...job, tracking } : job,
      ),
    );
    setDetail((current) =>
      current?.id === jobId ? { ...current, tracking } : current,
    );
  };

  const toggleFavorite = async (
    event: MouseEvent<HTMLButtonElement>,
    job: CareerJobSummary,
  ) => {
    event.stopPropagation();
    if (trackingPending) return;
    const previous = job.tracking;
    const target = !previous.is_favorite;
    setTrackingPending(true);
    setTrackingError("");
    applyTracking(job.id, { ...previous, is_favorite: target });
    try {
      const result = await updateCareerJobTracking(job.id, {
        expected_version: previous.version,
        is_favorite: target,
      });
      if (!result.ok || !result.tracking) {
        applyTracking(job.id, previous);
        if (result.error?.code === "VERSION_CONFLICT") {
          setTrackingError(
            "记录已在其他入口更新，请确认最新内容后重试。",
          );
          const refreshed = await getCareerJob(job.id);
          if (refreshed.ok && refreshed.job) {
            applyTracking(job.id, refreshed.job.tracking);
          }
        } else {
          setTrackingError(
            result.error?.message || "收藏状态保存失败。",
          );
        }
        return;
      }
      applyTracking(job.id, result.tracking);
      setFilters((current) =>
        current
          ? {
              ...current,
              favorite_count: Math.max(
                0,
                current.favorite_count + (target ? 1 : -1),
              ),
            }
          : current,
      );
      if (favoriteOnly && !target) {
        const nextTotal = Math.max(0, total - 1);
        if (offset > 0 && offset >= nextTotal) {
          setOffset(Math.max(0, offset - PAGE_SIZE));
        } else {
          setListRevision((value) => value + 1);
        }
      }
    } catch {
      applyTracking(job.id, previous);
      setTrackingError("无法连接本地岗位服务。");
    } finally {
      setTrackingPending(false);
    }
  };

  const saveTracking = async () => {
    if (!detail || trackingPending) return;
    setTrackingPending(true);
    setTrackingError("");
    try {
      const result = await updateCareerJobTracking(detail.id, {
        expected_version: detail.tracking.version,
        application_status: draftStatus,
        note: draftNote,
      });
      if (result.ok && result.tracking) {
        applyTracking(detail.id, result.tracking);
      } else if (result.error?.code === "VERSION_CONFLICT") {
        setTrackingError(
          "记录已在其他入口更新，请确认最新内容后重试。",
        );
        const refreshed = await getCareerJob(detail.id);
        if (refreshed.ok && refreshed.job) {
          setDetail(refreshed.job);
        }
      } else {
        setTrackingError(
          result.error?.message || "申请进度保存失败。",
        );
      }
    } catch {
      setTrackingError("无法连接本地岗位服务。");
    } finally {
      setTrackingPending(false);
    }
  };

  const openInterviewSetup = async (job: CareerJobSummary) => {
    setInterviewJob(job);
    setInterviewSetupLoading(true);
    setInterviewSetupError("");
    setInterviewResumes([]);
    setInterviewResumeId("");
    try {
      const resumeResponse = await getCareerResumes();
      if (!resumeResponse.ok) {
        setInterviewSetupError(
          resumeResponse.error?.message || "无法读取简历库。",
        );
        return;
      }
      const confirmed = (resumeResponse.resumes || []).filter(
        (resume) => resume.status === "confirmed",
      );
      setInterviewResumes(confirmed);
      setInterviewResumeId(confirmed[0]?.id || "");
      if (!confirmed.length) {
        setInterviewSetupError(
          "没有可用于面试的已确认简历，请先导入并确认简历。",
        );
      }
    } catch {
      setInterviewSetupError("无法连接本地简历服务。");
    } finally {
      setInterviewSetupLoading(false);
    }
  };

  const startInterviewFromSetup = async () => {
    if (
      !interviewJob ||
      !interviewResumeId ||
      !onStartInterview ||
      interviewSetupLoading
    ) {
      return;
    }
    onStartInterview({
      jobId: interviewJob.id,
      resumeId: interviewResumeId,
      position: interviewJob.title || "未命名岗位",
      durationMinutes: interviewDuration,
      difficulty: interviewDifficulty,
    });
    setInterviewJob(null);
  };

  const rangeStart = total ? offset + 1 : 0;
  const rangeEnd = Math.min(offset + PAGE_SIZE, total);

  return (
    <main className="flex-1 min-w-0 bg-paper overflow-hidden flex flex-col">
      <header className="shrink-0 bg-panel border-b border-line px-3 py-3 sm:px-6 sm:py-4">
        <div className="flex flex-wrap items-end justify-between gap-3 mb-3">
          <div>
            <h1 className="text-xl font-semibold">发现岗位</h1>
            <p className="text-[12.5px] text-muted mt-1">
              浏览已入库的官方招聘岗位，选择岗位后在右侧查看完整 JD。
            </p>
          </div>
          <div className="text-[12px] text-muted">{total.toLocaleString()} 个岗位</div>
        </div>
        <LocalJobSyncBanner onUpdated={refreshCatalog} />
        <div
          aria-label="岗位范围"
          className="mb-3 inline-flex w-fit rounded-lg border border-line bg-paper p-1"
          role="group"
        >
          <button
            aria-pressed={!favoriteOnly}
            className={jobScopeClass(!favoriteOnly)}
            onClick={() =>
              resetOffset(() => setFavoriteOnly(false))
            }
            type="button"
          >
            全部岗位
          </button>
          <button
            aria-pressed={favoriteOnly}
            className={jobScopeClass(favoriteOnly)}
            onClick={() =>
              resetOffset(() => setFavoriteOnly(true))
            }
            type="button"
          >
            收藏箱（{filters?.favorite_count || 0}）
          </button>
        </div>
        <div
          className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-[minmax(220px,1.6fr)_repeat(4,minmax(120px,1fr))]"
          data-testid="job-filter-grid"
        >
          <form onSubmit={submitSearch} className="flex gap-1.5">
            <input
              aria-label="搜索岗位"
              className="min-w-0 flex-1 rounded-lg border border-line bg-paper px-3 py-2 text-[12.5px]"
              placeholder="搜索职位、技能或 JD"
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
            />
            <button className="rounded-lg bg-accent text-white px-3 text-[12px]" type="submit">
              搜索
            </button>
          </form>
          <select
            aria-label="公司"
            className="rounded-lg border border-line bg-paper px-2.5 py-2 text-[12px]"
            value={companySlug}
            onChange={(event) =>
              resetOffset(() => setCompanySlug(event.target.value))
            }
          >
            <option value="">全部公司</option>
            {(filters?.companies || []).map((item) => (
              <option key={item.slug} value={item.slug}>
                {item.name}（{item.count}）
              </option>
            ))}
          </select>
          <select
            aria-label="城市"
            className="rounded-lg border border-line bg-paper px-2.5 py-2 text-[12px]"
            value={location}
            onChange={(event) =>
              resetOffset(() => setLocation(event.target.value))
            }
          >
            <option value="">全部城市</option>
            {(filters?.locations || []).map((item) => (
              <option key={item.value} value={item.value}>
                {item.value}（{item.count}）
              </option>
            ))}
          </select>
          <select
            aria-label="招聘类型"
            className="rounded-lg border border-line bg-paper px-2.5 py-2 text-[12px]"
            value={recruitmentType}
            onChange={(event) =>
              resetOffset(() => setRecruitmentType(event.target.value))
            }
          >
            <option value="">全部类型</option>
            {(filters?.recruitment_types || []).map((item) => (
              <option key={item.value} value={item.value}>
                {careerJobTypeLabel(item.value)}（{item.count}）
              </option>
            ))}
          </select>
          <select
            aria-label="岗位状态"
            className="rounded-lg border border-line bg-paper px-2.5 py-2 text-[12px]"
            value={status}
            onChange={(event) =>
              resetOffset(() => setStatus(event.target.value))
            }
          >
            <option value="">全部状态</option>
            {(filters?.statuses || []).map((item) => (
              <option key={item.value} value={item.value}>
                {displayStatus(item.value)}（{item.count}）
              </option>
            ))}
          </select>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <select
            aria-label="申请进度"
            className="w-full rounded-lg border border-line bg-paper px-2.5 py-2 text-[12px] sm:w-auto"
            value={applicationStatus}
            onChange={(event) =>
              resetOffset(() =>
                setApplicationStatus(
                  event.target.value as
                    | CareerApplicationStatus
                    | "",
                ),
              )
            }
          >
            <option value="">全部申请进度</option>
            {APPLICATION_STATUSES.map((value) => (
              <option key={value} value={value}>
                {APPLICATION_STATUS_NAMES[value]}
              </option>
            ))}
          </select>
          {trackingError && (
            <span className="text-[12px] text-red-700">
              {trackingError}
            </span>
          )}
        </div>
      </header>

      <div
        className="flex-1 min-h-0 overflow-y-auto grid grid-cols-1 lg:overflow-hidden lg:grid-cols-[minmax(300px,38%)_1fr]"
        data-testid="job-radar-layout"
      >
        <section className="min-h-[420px] border-r border-line bg-paper flex flex-col lg:min-h-0">
          <div className="flex-1 overflow-y-auto p-3 space-y-2">
            {loading && (
              <div className="text-center text-muted py-16">正在加载岗位…</div>
            )}
            {!loading && error && (
              <div className="rounded-lg bg-red-50 text-red-700 p-3 text-sm">
                {error}
              </div>
            )}
            {!loading && !error && jobs.length === 0 && (
              <div className="text-center text-muted py-16">
                没有符合当前条件的岗位
              </div>
            )}
            {jobs.map((job) => (
              <div key={job.id} className="relative">
                <button
                  className={
                    "w-full text-left rounded-xl border p-3 pb-12 pr-11 transition-colors " +
                    (selectedId === job.id
                      ? "border-accent bg-panel"
                      : "border-line bg-panel hover:border-faint")
                  }
                  onClick={() => setSelectedId(job.id)}
                >
                  <div className="font-medium text-[13.5px]">
                    {job.title || "未命名岗位"}
                  </div>
                  <div className="text-[12px] text-muted mt-1.5">
                    {job.company.name} ·{" "}
                    {job.locations.join("、") || "地点未标注"}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-faint mt-2">
                    <span
                      className={
                        "rounded-full border px-2 py-0.5 " +
                        careerJobTypeClass(job.recruitment_type)
                      }
                      data-job-type={
                        job.recruitment_type || "unknown"
                      }
                    >
                      {careerJobTypeLabel(job.recruitment_type)}
                    </span>
                    <span className="rounded-full bg-green-50 text-green-700 px-2 py-0.5">
                      {displayStatus(job.status)}
                    </span>
                    {job.tracking.application_status !==
                      "not_started" && (
                      <span className="rounded-full bg-accentSoft text-accent px-2 py-0.5">
                        {
                          APPLICATION_STATUS_NAMES[
                            job.tracking.application_status
                          ]
                        }
                      </span>
                    )}
                    <span>
                      最近确认 {formatDate(job.last_seen_at)}
                    </span>
                  </div>
                </button>
                <button
                  aria-label={`${
                    job.tracking.is_favorite
                      ? "取消收藏"
                      : "收藏岗位"
                  }：${job.title || "未命名岗位"}`}
                  className="absolute right-3 top-3 rounded-md px-2 py-1 text-[16px] text-accent disabled:opacity-40"
                  disabled={trackingPending}
                  onClick={(event) => toggleFavorite(event, job)}
                >
                  {job.tracking.is_favorite ? "★" : "☆"}
                </button>
                {onStartInterview && (
                  <button
                    aria-label={`从岗位列表模拟面试：${
                      job.title || "未命名岗位"
                    }`}
                    className="absolute bottom-3 right-3 rounded-lg border border-accent px-3 py-1.5 text-[12px] text-accent"
                    disabled={interviewSetupLoading}
                    onClick={(event) => {
                      event.stopPropagation();
                      void openInterviewSetup(job);
                    }}
                  >
                    模拟面试
                  </button>
                )}
              </div>
            ))}
          </div>
          <footer className="border-t border-line px-3 py-2.5 flex items-center justify-between">
            <span className="text-[11.5px] text-muted">
              {rangeStart}-{rangeEnd} / {total}
            </span>
            <div className="flex gap-2">
              <button
                className="px-3 py-1.5 rounded-lg border border-line text-[12px] disabled:opacity-40"
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                上一页
              </button>
              <button
                className="px-3 py-1.5 rounded-lg border border-line text-[12px] disabled:opacity-40"
                disabled={offset + PAGE_SIZE >= total}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                下一页
              </button>
            </div>
          </footer>
        </section>

        <section className="min-h-[420px] overflow-y-auto bg-panel lg:min-h-0">
          {detailLoading && (
            <div className="text-center text-muted py-20">正在加载岗位详情…</div>
          )}
          {!detailLoading && detailError && (
            <div className="m-5 rounded-lg bg-red-50 text-red-700 p-3 text-sm">
              {detailError}
            </div>
          )}
          {!detailLoading && !detailError && !detail && (
            <div className="text-center text-muted py-20">请选择一个岗位</div>
          )}
          {!detailLoading && detail && (
            <article className="max-w-4xl mx-auto p-4 space-y-6 sm:p-6">
              <header
                className="flex flex-col items-start justify-between gap-4 lg:flex-row lg:gap-5"
                data-testid="job-detail-header"
              >
                <div>
                  <h2 className="text-xl font-semibold">
                    {detail.title || "未命名岗位"}
                  </h2>
                  <div className="text-[13px] text-muted mt-2">
                    {detail.company.name} ·{" "}
                    {detail.locations.join("、") || "地点未标注"}
                  </div>
                  <div className="flex items-center gap-2 mt-3 text-[11px]">
                    <span
                      className={
                        "rounded-full border px-2 py-0.5 " +
                        careerJobTypeClass(detail.recruitment_type)
                      }
                      data-job-type-detail={detail.recruitment_type || "unknown"}
                    >
                      {careerJobTypeLabel(detail.recruitment_type)}
                    </span>
                    <span className="rounded-full bg-green-50 text-green-700 px-2 py-0.5">
                      {displayStatus(detail.status)}
                    </span>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 lg:shrink-0">
                  {onStartInterview && (
                    <button
                      aria-label={`从岗位详情模拟面试：${
                        detail.title || "未命名岗位"
                      }`}
                      className="rounded-lg bg-accent px-3.5 py-2 text-[12.5px] text-white"
                      disabled={interviewSetupLoading}
                      onClick={() => void openInterviewSetup(detail)}
                    >
                      模拟面试
                    </button>
                  )}
                  <button
                    aria-label={`${
                      detail.tracking.is_favorite
                        ? "取消收藏"
                        : "收藏岗位"
                    }：${detail.title || "未命名岗位"}`}
                    className="rounded-lg border border-line px-3.5 py-2 text-[12.5px] text-accent disabled:opacity-40"
                    disabled={trackingPending}
                    onClick={(event) =>
                      toggleFavorite(event, detail)
                    }
                  >
                    {detail.tracking.is_favorite
                      ? "已收藏"
                      : "收藏"}
                  </button>
                  <CareerResumeCoachLauncher
                    job={detail}
                    onStartAnalysis={(payload) =>
                      onStartResumeCoach?.(payload)
                    }
                  />
                  {/^https?:\/\//.test(detail.source_url) && (
                    <a
                      className="rounded-lg bg-accent text-white px-3.5 py-2 text-[12.5px]"
                      href={detail.source_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      查看官网
                    </a>
                  )}
                </div>
              </header>

              <div className="grid grid-cols-1 gap-3 text-[11.5px] text-muted sm:grid-cols-3">
                <div className="rounded-lg bg-paper p-3">
                  首次发现
                  <div className="text-ink mt-1">{formatDate(detail.first_seen_at)}</div>
                </div>
                <div className="rounded-lg bg-paper p-3">
                  最近确认
                  <div className="text-ink mt-1">{formatDate(detail.last_seen_at)}</div>
                </div>
                <div className="rounded-lg bg-paper p-3">
                  最近变化
                  <div className="text-ink mt-1">{formatDate(detail.last_changed_at)}</div>
                </div>
              </div>

              <section className="rounded-xl bg-paper p-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold">
                    我的申请进度
                  </h3>
                  <span className="text-[11.5px] text-muted">
                    {detail.tracking.updated_at
                      ? `最近更新 ${formatDate(
                          detail.tracking.updated_at,
                        )}`
                      : "尚未记录"}
                  </span>
                </div>
                <div className="grid grid-cols-[180px_1fr] gap-3">
                  <label className="space-y-1 text-[12px] text-muted">
                    <span>申请进度</span>
                    <select
                      aria-label="我的申请进度"
                      className="w-full rounded-lg border border-line bg-panel px-2.5 py-2 text-[12.5px] text-ink"
                      value={draftStatus}
                      onChange={(event) =>
                        setDraftStatus(
                          event.target
                            .value as CareerApplicationStatus,
                        )
                      }
                    >
                      {APPLICATION_STATUSES.map((value) => (
                        <option key={value} value={value}>
                          {APPLICATION_STATUS_NAMES[value]}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="space-y-1 text-[12px] text-muted">
                    <span>申请备注</span>
                    <textarea
                      aria-label="申请备注"
                      className="w-full min-h-20 resize-y rounded-lg border border-line bg-panel px-3 py-2 text-[12.5px] text-ink"
                      maxLength={2000}
                      value={draftNote}
                      onChange={(event) =>
                        setDraftNote(event.target.value)
                      }
                    />
                  </label>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-[11.5px] text-muted">
                    {draftNote.length} / 2000
                  </span>
                  <button
                    className="rounded-lg bg-accent px-3.5 py-2 text-[12.5px] text-white disabled:opacity-40"
                    disabled={trackingPending}
                    onClick={saveTracking}
                  >
                    {trackingPending
                      ? "正在保存…"
                      : "保存申请进度"}
                  </button>
                </div>
                {detail.tracking.applied_at && (
                  <div className="text-[11.5px] text-muted">
                    首次投递{" "}
                    {formatDate(detail.tracking.applied_at)}
                  </div>
                )}
                <div
                  className="space-y-2"
                  data-testid="application-timeline"
                >
                  {(detail.tracking.events || []).map((event) => (
                    <div
                      key={event.id}
                      className="rounded-lg border border-line px-3 py-2 text-[12px]"
                    >
                      <span className="font-medium">
                        {
                          APPLICATION_STATUS_NAMES[
                            event.to_status
                          ]
                        }
                      </span>
                      <span className="text-muted">
                        {" "}
                        · {formatDateTime(event.occurred_at)}
                      </span>
                    </div>
                  ))}
                  {!detail.tracking.events?.length && (
                    <div className="text-[12px] text-muted">
                      暂无申请进度记录
                    </div>
                  )}
                </div>
              </section>

              <section>
                <h3 className="text-sm font-semibold mb-2">JD</h3>
                <div className="rounded-xl bg-paper p-4 whitespace-pre-wrap text-[13px] leading-6">
                  {detail.description_raw}
                </div>
              </section>

              <section>
                <h3 className="text-sm font-semibold mb-2">版本记录</h3>
                <div className="space-y-2">
                  {(detail.versions || []).map((version) => (
                    <div
                      key={version.version_number}
                      className="rounded-lg bg-paper px-3 py-2 text-[12px]"
                    >
                      版本 {version.version_number} ·{" "}
                      {formatDate(version.captured_at)}
                    </div>
                  ))}
                  {!detail.versions?.length && (
                    <div className="text-[12px] text-muted">暂无版本记录</div>
                  )}
                </div>
              </section>

              <section>
                <h3 className="text-sm font-semibold mb-2">变化记录</h3>
                <div className="space-y-2">
                  {(detail.events || []).map((event, index) => (
                    <div
                      key={`${event.occurred_at}-${index}`}
                      className="rounded-lg bg-paper px-3 py-2 text-[12px]"
                    >
                      <span className="font-medium">
                        {EVENT_NAMES[event.event_type] || event.event_type}
                      </span>
                      <span className="text-muted">
                        {" "}· {formatDate(event.occurred_at)} · {event.summary}
                      </span>
                    </div>
                  ))}
                  {!detail.events?.length && (
                    <div className="text-[12px] text-muted">暂无变化记录</div>
                  )}
                </div>
              </section>
            </article>
          )}
        </section>
      </div>
      {interviewJob && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-5">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="career-interview-setup-title"
            className="w-full max-w-lg rounded-xl border border-line bg-panel p-5 shadow-xl"
          >
            <header>
              <h2
                id="career-interview-setup-title"
                className="font-semibold"
              >
                模拟面试设置
              </h2>
              <p className="mt-1 text-[12px] text-muted">
                {interviewJob.title || "未命名岗位"} ·{" "}
                {interviewJob.company.name}
              </p>
            </header>
            <div className="mt-4 grid gap-3">
              <label className="text-xs text-muted">
                面试简历
                <select
                  aria-label="面试简历"
                  className="mt-1 block w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink"
                  disabled={interviewSetupLoading}
                  value={interviewResumeId}
                  onChange={(event) =>
                    setInterviewResumeId(event.target.value)
                  }
                >
                  {!interviewResumes.length && (
                    <option value="">暂无已确认简历</option>
                  )}
                  {interviewResumes.map((resume) => (
                    <option key={resume.id} value={resume.id}>
                      {resume.display_name}
                    </option>
                  ))}
                </select>
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs text-muted">
                  面试时长
                  <select
                    aria-label="面试时长"
                    className="mt-1 block w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink"
                    value={interviewDuration}
                    onChange={(event) =>
                      setInterviewDuration(
                        Number(event.target.value) as 10 | 15 | 20,
                      )
                    }
                  >
                    <option value={10}>10 分钟 · 5 题</option>
                    <option value={15}>15 分钟 · 5 题</option>
                    <option value={20}>20 分钟 · 5 题</option>
                  </select>
                </label>
                <label className="text-xs text-muted">
                  面试难度
                  <select
                    aria-label="面试难度"
                    className="mt-1 block w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink"
                    value={interviewDifficulty}
                    onChange={(event) =>
                      setInterviewDifficulty(
                        event.target.value as
                          | "simple"
                          | "standard"
                          | "deep",
                      )
                    }
                  >
                    <option value="simple">简单</option>
                    <option value="standard">标准</option>
                    <option value="deep">深入</option>
                  </select>
                </label>
              </div>
              {interviewSetupLoading && (
                <p className="text-sm text-muted">正在读取面试资料…</p>
              )}
              {interviewSetupError && (
                <p role="alert" className="text-sm text-red-700">
                  {interviewSetupError}
                </p>
              )}
            </div>
            <footer className="mt-5 flex justify-end gap-2">
              <button
                className="rounded-lg border border-line px-4 py-2 text-sm"
                onClick={() => setInterviewJob(null)}
              >
                取消
              </button>
              <button
                className="rounded-lg bg-accent px-4 py-2 text-sm text-white disabled:opacity-40"
                disabled={
                  interviewSetupLoading || !interviewResumeId
                }
                onClick={() => void startInterviewFromSetup()}
              >
                {interviewSetupLoading
                  ? "正在准备面试…"
                  : "开始模拟面试"}
              </button>
            </footer>
          </section>
        </div>
      )}
    </main>
  );
}
