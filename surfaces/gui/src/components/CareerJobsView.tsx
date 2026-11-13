import { FormEvent, MouseEvent, useCallback, useEffect, useRef, useState } from "react";
import type { SubscriptionChatContext } from "../subscriptionChat";
import { applicationsRequest, type Application } from "../applications";

import {
  getCareerResumes,
  getCareerJob,
  getCareerJobFilters,
  getCareerJobs,
  updateCareerJobTracking,
  careerCatalogRequest, isLocal, type CatalogQuery, type CatalogResult,
  type CareerApplicationStatus,
  type CareerJobDetail,
  type CareerJobFilters,
  type CareerResumeSummary,
  type CareerJobSummary,
  type CareerJobTracking,
} from "../api";
import {
  careerJobTypeLabel,
  careerJobTypeTone,
} from "../careerJobLabels";
import type { ResumeCoachLaunchPayload } from "../careerResumeCoach";
import { CareerResumeCoachLauncher } from "./CareerResumeCoachLauncher";
import { Icon } from "./Icon";
import { supportsApplications } from "../applicationsSupport";
import { OcSelect, Tag } from "./OcSelect";
import { STATUS_TONE } from "../applications";
import { LocalJobSyncBanner } from "./LocalJobSyncBanner";
import { CatalogQueryForm, ConditionChips } from "./CatalogQueryForm";
import { JobSubscriptionsPanel } from "./JobSubscriptionsPanel";

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
  new: "新增岗位",
  updated: "内容更新",
  backfill: "历史补录",
  changed: "岗位变化",
  missing: "暂未发现",
  offline: "岗位下线",
  reopened: "重新开放",
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
const staleConfirmation = (job: {status: string; last_seen_at: string}) => job.status === "active" && Date.now() - Date.parse(job.last_seen_at) > 48 * 3600 * 1000;

const formatDate = (value: string) =>
  new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
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

export function CareerJobsView({
  onStartResumeCoach,
  onStartInterview,
  onOpenApplication,
  onConfigureSubscription,
}: {
  onStartResumeCoach?: (payload: ResumeCoachLaunchPayload) => void;
  onStartInterview?: (payload: InterviewLaunchPayload) => void;
  onOpenApplication?: (id: string) => void;
  onConfigureSubscription?: (context: SubscriptionChatContext) => void;
} = {}) {
  const [filters, setFilters] = useState<CareerJobFilters | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [companySlug, setCompanySlug] = useState("");
  const [location, setLocation] = useState("");
  const [recruitmentType, setRecruitmentType] = useState("");
  const [favoriteOnly, setFavoriteOnly] = useState(false);
  // The current catalog is active-only; private favorites retain retired jobs.
  const status = favoriteOnly ? "" : "active";
  const [applicationStatus, setApplicationStatus] = useState<
    CareerApplicationStatus | ""
  >("");
  const [offset, setOffset] = useState(0);
  const [listRevision, setListRevision] = useState(0);
  const [catalogRevision, setCatalogRevision] = useState(0);
  const [advanced, setAdvanced] = useState<CatalogQuery | null>(null);
  const [advancedResult, setAdvancedResult] = useState<CatalogResult | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showSubscriptions, setShowSubscriptions] = useState(false);
  const standalone = typeof isLocal === "function" && isLocal();
  // Personal applications also exist on the hosted build; filters/subscriptions stay local-only.
  const canTrack = standalone || supportsApplications();
  const [subscriptionDraft,setSubscriptionDraft]=useState<{title?:string;send_time?:string;subscription_id?:string;channel_ids?:string[]}>();
  useEffect(() => {
    const read = () => {
      try {
        const stored = sessionStorage.getItem("opencareer-catalog-query");
        if (stored) { setAdvanced(JSON.parse(stored)); setOffset(0); sessionStorage.removeItem("opencareer-catalog-query"); }
        const subscription=sessionStorage.getItem("opencareer-subscription-query");
        if(subscription){setSubscriptionDraft(JSON.parse(subscription));setShowSubscriptions(true);sessionStorage.removeItem("opencareer-subscription-query");}
      } catch { /* Invalid browser state is ignored; no query is executed. */ }
    };
    read(); window.addEventListener("opencareer:catalog-open", read);
    return () => window.removeEventListener("opencareer:catalog-open", read);
  }, []);
  const refreshCatalog = useCallback(() => setCatalogRevision(value => value + 1), []);
  const previousList = useRef({ criteria: "", catalogRevision: 0 });
  const rateLimitRetries = useRef(0);
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
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    const criteria = JSON.stringify([query, companySlug, location, recruitmentType,
      status, favoriteOnly, applicationStatus, offset, advanced]);
    if (previousList.current.criteria !== criteria) rateLimitRetries.current = 0;
    const preserveSelection = previousList.current.criteria === criteria
      && previousList.current.catalogRevision !== catalogRevision;
    previousList.current = { criteria, catalogRevision };
    setLoading(true);
    setError("");
    const pending = advanced ? careerCatalogRequest<CatalogResult>("catalog/search", {...advanced, limit: PAGE_SIZE, offset}).then(r => {
      if (current) setAdvancedResult(r);
      return {ok: true, jobs:r.jobs, total:r.total ?? r.evaluated_matches, error:undefined};
    }) : getCareerJobs({
      query,
      companySlug,
      location,
      recruitmentType,
      status,
      favoriteOnly,
      applicationStatus: applicationStatus || undefined,
      limit: PAGE_SIZE,
      offset,
    });
    pending.then((result) => {
        if (!current) return;
        if (!result.ok) {
          setError(result.error?.message || "无法读取岗位列表。");
          setJobs([]);
          setTotal(0);
          return;
        }
        const nextJobs = result.jobs || [];
        rateLimitRetries.current = 0;
        setJobs(nextJobs);
        setTotal(result.total || 0);
        setSelectedId((value) =>
          (preserveSelection && value) || nextJobs.some((job) => job.id === value)
            ? value
            : nextJobs[0]?.id || "",
        );
      })
      .catch((failure) => {
        if (!current) return;
        const message = failure instanceof Error ? failure.message : "无法连接本地岗位服务。";
        const delay = Number(failure?.retryAfterMs);
        // Retry only responses that supply a retry delay, respect Retry-After, and
        // stop after two attempts. Query changes/unmount cancel stale retries.
        if (Number.isFinite(delay) && delay > 0 && rateLimitRetries.current < 2) {
          const wait = Math.min(60000, Math.max(1000, delay));
          rateLimitRetries.current += 1;
          setError(`${message}将在 ${Math.ceil(wait / 1000)} 秒后自动重试。`);
          retryTimer = setTimeout(() => setListRevision(value => value + 1), wait);
        } else setError(message);
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
      clearTimeout(retryTimer);
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
    advanced,
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

  const [notice, setNotice] = useState<{ text: string; applicationId?: string } | null>(null);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 6000);
    return () => clearTimeout(timer);
  }, [notice]);
  const openOrAddApplication = async (job: CareerJobDetail, tracked: boolean) => {
    if (!onOpenApplication) return;
    if (draftNote !== (job.tracking.note || "") || draftStatus !== job.tracking.application_status) {
      setTrackingError("请先保存下面的原进度草稿，再打开求职进度。");
      return;
    }
    setTrackingPending(true);
    setTrackingError("");
    try {
      const application = await applicationsRequest<Application>("", { job_id: job.id });
      if (tracked) { onOpenApplication(application.id); return; }
      const fresh = await getCareerJob(job.id).catch(() => null);
      if (fresh?.ok && fresh.job) applyTracking(job.id, fresh.job.tracking);
      setNotice({ text: `已将「${job.title || "未命名岗位"}」加入求职进度`, applicationId: application.id });
    } catch (e) {
      setTrackingError((e as Error).message);
    } finally {
      setTrackingPending(false);
    }
  };
  // Skeleton while a different job is loading, or before the first page has picked one.
  const detailSkeleton = (detailLoading && detail?.id !== selectedId) || (!detail && loading && !jobs.length);
  const rangeStart = total ? offset + 1 : 0;
  const rangeEnd = Math.min(offset + PAGE_SIZE, total);

  return (
    <main className="oc-page oc-jobs flex-1 min-w-0 bg-paper overflow-hidden flex flex-col">
      <header className="shrink-0 bg-panel border-b border-line">
        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 mb-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1>发现岗位</h1>
              {loading && !jobs.length ? <span className="oc-skeleton h-[22px] w-[72px] rounded-full" aria-hidden="true" /> : <span className="oc-chip tabular-nums">{total.toLocaleString()} 个岗位</span>}
            </div>
            {/* 产品说明移至代码：浏览已入库的官方招聘岗位，选择岗位后在右侧查看完整 JD。 */}
          </div>
          <div className="radar-toolbar flex flex-wrap items-center">
            <LocalJobSyncBanner onUpdated={refreshCatalog} showStatus={false} />
            {standalone && <>
              <button type="button" className={"oc-btn oc-btn-sm " + (showAdvanced || advanced ? "oc-btn-accent" : "")} aria-expanded={showAdvanced} onClick={() => setShowAdvanced(v => !v)}><Icon name="filter" size={14}/>组合筛选</button>
              <button type="button" className="oc-btn oc-btn-sm" onClick={() => {setSubscriptionDraft(undefined);setShowSubscriptions(true);}}><Icon name="bell" size={14}/>岗位订阅</button>
            </>}
          </div>
        </div>
        {standalone && advanced && <div className="oc-alert is-info mb-3 items-center"><Icon name="filter" size={14} className="shrink-0 text-accent"/><div className="flex-1 min-w-0"><ConditionChips inline condition={advanced.condition || {all: []}} today={advanced.today} semanticQuery={advanced.semantic_query} /></div><button type="button" className="oc-btn oc-btn-ghost oc-btn-sm" onClick={() => {setAdvanced(null);setAdvancedResult(null);setOffset(0);}}>清除组合条件</button></div>}
        {showAdvanced && <div className="mb-3"><CatalogQueryForm onSubmit={criteria => {setAdvanced(criteria);setOffset(0);setShowAdvanced(false);}} /></div>}
        {advancedResult?.semantic.partial && <p role="status" className="oc-alert is-warn mb-3">仅评估了 {advancedResult.semantic.evaluated} 个候选，当前数量不是全库总数。{advancedResult.semantic.next_offset !== null && <button className="text-accent ml-2 font-medium" onClick={() => {setAdvanced(p => ({...p,semantic_offset:advancedResult.semantic.next_offset!}));setOffset(0);}}>评估下一批候选</button>}</p>}
        {/* The catalog keeps full diagnostics for tools. In Radar, surface coverage only when it affects a date filter or an empty result. */}
        {advanced && advancedResult && (advanced.today || /"new_at"/.test(JSON.stringify(advanced.condition)) || advancedResult.total === 0) &&
          advancedResult.warnings.some(w => /监测初始基线|公共目录有|尚未完成本轮同步/.test(w) &&
            (!w.startsWith("监测初始基线") || advanced.today || /"new_at"/.test(JSON.stringify(advanced.condition)))) &&
          <p className="text-xs text-warnInk mb-2">岗位监测记录可能不完整，请以官网为准。</p>}
        <fieldset className={advanced ? "hidden" : "contents"} disabled={!!advanced}>
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <div
            aria-label="岗位范围"
            className="oc-seg"
            role="group"
          >
            <button
              aria-pressed={!favoriteOnly}
              onClick={() =>
                resetOffset(() => setFavoriteOnly(false))
              }
              type="button"
            >
              全部岗位
            </button>
            <button
              aria-pressed={favoriteOnly}
              onClick={() =>
                resetOffset(() => setFavoriteOnly(true))
              }
              type="button"
            >
              收藏箱（{filters?.favorite_count || 0}）
            </button>
          </div>
          {trackingError && (
            <span className="text-[12px] text-danger">
              {trackingError}
            </span>
          )}
        </div>
        <div
          className="radar-filters grid grid-cols-2 gap-2 lg:grid-cols-4 xl:grid-cols-[minmax(240px,1.8fr)_repeat(4,minmax(112px,1fr))]"
          data-testid="job-filter-grid"
        >
          <form onSubmit={submitSearch} className="oc-search col-span-2 lg:col-span-4 xl:col-span-1">
            <Icon name="search" size={15} />
            <input
              aria-label="搜索岗位"
              className="oc-field pr-16"
              placeholder="搜索职位、技能或 JD"
              value={queryInput}
              onChange={(event) => setQueryInput(event.target.value)}
            />
            <button className="absolute right-1 oc-btn oc-btn-primary oc-btn-sm" type="submit">
              搜索
            </button>
          </form>
          <OcSelect
            ariaLabel="公司"
            value={companySlug}
            searchable
            onChange={(value) => resetOffset(() => setCompanySlug(value))}
            options={[{ value: "", label: "全部公司" }, ...(filters?.companies || []).map((item) => ({ value: item.slug, label: item.name, count: item.count }))]}
          />
          <OcSelect
            ariaLabel="城市"
            value={location}
            searchable
            onChange={(value) => resetOffset(() => setLocation(value))}
            options={[{ value: "", label: "全部城市" }, ...(filters?.locations || []).map((item) => ({ value: item.value, label: item.value, count: item.count }))]}
          />
          <OcSelect
            ariaLabel="招聘类型"
            value={recruitmentType}
            onChange={(value) => resetOffset(() => setRecruitmentType(value))}
            options={[{ value: "", label: "全部类型" }, ...(filters?.recruitment_types || []).map((item) => ({ value: item.value, label: careerJobTypeLabel(item.value), count: item.count, tone: careerJobTypeTone(item.value) || undefined }))]}
          />
          <OcSelect
            ariaLabel="申请进度"
            value={applicationStatus}
            onChange={(value) => resetOffset(() => setApplicationStatus(value as CareerApplicationStatus | ""))}
            options={[{ value: "", label: "全部申请进度" }, ...APPLICATION_STATUSES.map((value) => ({ value, label: APPLICATION_STATUS_NAMES[value], tone: STATUS_TONE[value] }))]}
          />
        </div>
        </fieldset>
      </header>
      {showSubscriptions && <JobSubscriptionsPanel key={JSON.stringify(subscriptionDraft)} initialDraft={subscriptionDraft} condition={advanced?.condition || {all: [
        ...(companySlug ? [{field:"company",op:"in",values:[companySlug]}] : []),
        ...(location ? [{field:"locations",op:"in",values:[location]}] : []),
        ...(query ? [{field:"text",op:"contains",values:[query]}] : []),
        ...(recruitmentType ? [{field:"recruitment_type",op:"in",values:[recruitmentType]}] : []),
      ]}} today={advanced?.today} includeInactive={advanced?.include_inactive ?? false} semanticQuery={advanced?.semantic_query} onConfigureInChat={onConfigureSubscription ? prompt => {setShowSubscriptions(false);onConfigureSubscription(prompt);} : undefined} onClose={() => setShowSubscriptions(false)} />}

      <div
        className="flex-1 min-h-0 overflow-y-auto grid grid-cols-1 lg:overflow-hidden lg:grid-cols-[minmax(300px,38%)_1fr]"
        data-testid="job-radar-layout"
      >
        <section className="radar-list min-h-[420px] border-r border-line flex flex-col lg:min-h-0">
          {/* Refreshing an existing page keeps the old cards visible under a thin progress bar;
              only the very first load shows skeleton cards. */}
          <div className={"radar-progress" + (loading && jobs.length ? " is-active" : "")} aria-hidden="true" />
          <div className={"flex-1 overflow-y-auto p-3 space-y-2 transition-opacity " + (loading && jobs.length ? "opacity-60 pointer-events-none" : "")} aria-busy={loading}>
            {loading && !jobs.length && (
              <div role="status" aria-label="正在加载岗位…" className="space-y-2">
                {[0, 1, 2, 3, 4, 5].map((index) => (
                  <div key={index} className="oc-skeleton-card" aria-hidden="true" style={{ animationDelay: `${index * 60}ms` }}>
                    <div className="oc-skeleton h-[15px]" style={{ width: `${[62, 48, 70, 55, 66, 44][index]}%` }} />
                    <div className="oc-skeleton h-3" style={{ width: `${[38, 30, 42, 34, 28, 40][index]}%` }} />
                    <div className="oc-skeleton h-[20px] w-14 rounded-md" />
                  </div>
                ))}
              </div>
            )}
            {!loading && error && (
              <div role="alert" className="oc-alert">
                <span className="flex-1">{error}</span><button type="button" className="shrink-0 font-medium underline underline-offset-2" onClick={() => {rateLimitRetries.current=0;setListRevision(value=>value+1);}}>重新加载</button>
              </div>
            )}
            {!loading && !error && jobs.length === 0 && (
              <div className="oc-empty">
                <div className="oc-empty-icon"><Icon name="search" size={20} /></div>
                <strong>没有符合当前条件的岗位</strong>
                <p>试试放宽城市、公司或关键词条件。</p>
              </div>
            )}
            {jobs.map((job) => (
              <div key={job.id} className="radar-item relative">
                <button
                  className="radar-card"
                  aria-current={selectedId === job.id ? "true" : undefined}
                  onClick={() => setSelectedId(job.id)}
                >
                  <div className="radar-card-title">
                    {job.title || "未命名岗位"}
                  </div>
                  <div className="radar-card-sub">
                    {job.company.name} ·{" "}
                    {job.locations.join("、") || "地点未标注"}
                  </div>
                  {/* Verification state and confirmation date live in the detail pane;
                      the card only carries what helps choose (type, my progress). */}
                  {(careerJobTypeTone(job.recruitment_type) || job.tracking.application_status !== "not_started" || job.status !== "active") && (
                    <div className="radar-card-meta">
                      {careerJobTypeTone(job.recruitment_type) && (
                        <Tag tone={careerJobTypeTone(job.recruitment_type)!}>
                          <span data-job-type={job.recruitment_type}>{careerJobTypeLabel(job.recruitment_type)}</span>
                        </Tag>
                      )}
                      {job.status !== "active" && <Tag tone="gray">{displayStatus(job.status)}</Tag>}
                      {job.tracking.application_status !== "not_started" && (
                        <Tag tone={STATUS_TONE[job.tracking.application_status] || "gray"}>
                          {APPLICATION_STATUS_NAMES[job.tracking.application_status]}
                        </Tag>
                      )}
                    </div>
                  )}
                </button>
                <button
                  aria-label={`${
                    job.tracking.is_favorite
                      ? "取消收藏"
                      : "收藏岗位"
                  }：${job.title || "未命名岗位"}`}
                  aria-pressed={job.tracking.is_favorite}
                  className="radar-fav disabled:opacity-40"
                  disabled={trackingPending}
                  onClick={(event) => toggleFavorite(event, job)}
                >
                  <Icon name={job.tracking.is_favorite ? "starFilled" : "star"} size={17} />
                </button>
                {onStartInterview && (
                  <button
                    aria-label={`从岗位列表模拟面试：${
                      job.title || "未命名岗位"
                    }`}
                    className="radar-card-action oc-btn oc-btn-accent oc-btn-sm"
                    disabled={interviewSetupLoading}
                    onClick={(event) => {
                      event.stopPropagation();
                      void openInterviewSetup(job);
                    }}
                  >
                    <Icon name="mic" size={13} />
                    模拟面试
                  </button>
                )}
              </div>
            ))}
          </div>
          <footer className="radar-pager">
            <span>
              {loading && !jobs.length ? "正在加载…" : `${rangeStart}-${rangeEnd} / ${total}`}
            </span>
            <div className="flex gap-1.5">
              <button
                className="oc-btn oc-btn-sm"
                disabled={offset === 0 || loading}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                上一页
              </button>
              <button
                className="oc-btn oc-btn-sm"
                disabled={offset + PAGE_SIZE >= total || loading}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                下一页
              </button>
            </div>
          </footer>
        </section>

        <section className="min-h-[420px] overflow-y-auto bg-panel lg:min-h-0">
          {detailSkeleton && (
            <div role="status" aria-label="正在加载岗位详情…" className="max-w-4xl mx-auto p-4 space-y-5 sm:p-7">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 space-y-2.5"><div className="oc-skeleton h-6 w-3/5" /><div className="oc-skeleton h-3.5 w-1/3" /><div className="flex gap-1.5"><div className="oc-skeleton h-[22px] w-16 rounded-md" /><div className="oc-skeleton h-[22px] w-12 rounded-md" /></div></div>
                <div className="hidden sm:flex gap-2"><div className="oc-skeleton h-9 w-20 rounded-[10px]" /><div className="oc-skeleton h-9 w-24 rounded-[10px]" /></div>
              </div>
              <div className="oc-skeleton h-[68px] w-full rounded-[14px]" />
              <div className="oc-skeleton h-[72px] w-full rounded-[14px]" />
              <div className="space-y-2.5 pt-2">{[92, 84, 96, 70, 88, 60, 80].map((width, index) => <div key={index} className="oc-skeleton h-3" style={{ width: `${width}%` }} />)}</div>
            </div>
          )}
          {!detailLoading && detailError && (
            <div className="m-5 oc-alert">
              {detailError}
            </div>
          )}
          {!detailLoading && !loading && !detailError && !detail && (
            <div className="oc-empty h-full">
              <div className="oc-empty-icon"><Icon name="briefcase" size={20} /></div>
              <strong>请选择一个岗位</strong>
              <p>在左侧列表中选择岗位，查看完整 JD、变化记录与申请进度。</p>
            </div>
          )}
          {detail && !detailSkeleton && (
            <article key={detail.id} className="radar-detail-enter max-w-4xl mx-auto p-4 space-y-7 sm:p-7">
              <header
                className="flex flex-col items-start justify-between gap-4 lg:flex-row lg:gap-5"
                data-testid="job-detail-header"
              >
                <div className="min-w-0">
                  <h2>
                    {detail.title || "未命名岗位"}
                  </h2>
                  <div className="text-[13px] text-muted mt-1.5">
                    {detail.company.name} ·{" "}
                    {detail.locations.join("、") || "地点未标注"}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5 mt-3">
                    {careerJobTypeTone(detail.recruitment_type) && (
                      <Tag tone={careerJobTypeTone(detail.recruitment_type)!}>
                        <span data-job-type-detail={detail.recruitment_type}>{careerJobTypeLabel(detail.recruitment_type)}</span>
                      </Tag>
                    )}
                    <span className={"oc-chip " + (staleConfirmation(detail) ? "is-warn" : detail.status === "active" ? "is-ok" : "")} title={staleConfirmation(detail) ? "超过 48 小时未在官网再次确认，请以官网为准" : undefined}>
                      <span className="oc-dot" />{staleConfirmation(detail) ? "待核验" : displayStatus(detail.status)}
                    </span>
                    {detail.tracking.application_status !== "not_started" && (
                      <Tag tone={STATUS_TONE[detail.tracking.application_status] || "gray"}>{APPLICATION_STATUS_NAMES[detail.tracking.application_status]}</Tag>
                    )}
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 lg:shrink-0">
                  {onStartInterview && (
                    <button
                      aria-label={`从岗位详情模拟面试：${
                        detail.title || "未命名岗位"
                      }`}
                      className="oc-btn"
                      disabled={interviewSetupLoading}
                      onClick={() => void openInterviewSetup(detail)}
                    >
                      <Icon name="mic" size={14} />
                      模拟面试
                    </button>
                  )}
                  <button
                    aria-label={`${
                      detail.tracking.is_favorite
                        ? "取消收藏"
                        : "收藏岗位"
                    }：${detail.title || "未命名岗位"}`}
                    aria-pressed={detail.tracking.is_favorite}
                    className={"oc-btn " + (detail.tracking.is_favorite ? "oc-btn-accent" : "")}
                    disabled={trackingPending}
                    onClick={(event) =>
                      toggleFavorite(event, detail)
                    }
                  >
                    <Icon name={detail.tracking.is_favorite ? "starFilled" : "star"} size={14} />
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
                      className="oc-btn oc-btn-primary"
                      href={detail.source_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      查看官网
                      <Icon name="external" size={14} />
                    </a>
                  )}
                </div>
              </header>

              <div className="radar-metadata grid grid-cols-2 gap-3 text-[11.5px] text-muted sm:grid-cols-3">
                <div>
                  最近确认
                  <div className="text-ink text-[13px] font-medium mt-1">{formatDate(detail.last_seen_at)}</div>
                </div>
                <div>
                  最近变化
                  <div className="text-ink text-[13px] font-medium mt-1">{formatDate(detail.last_changed_at)}</div>
                </div>
                <div className="hidden sm:block">
                  来源
                  <div className="text-ink text-[13px] font-medium mt-1 truncate">{detail.company.name} 官网</div>
                </div>
              </div>

              <section className="rounded-[14px] border border-line bg-[color-mix(in_srgb,var(--paper)_55%,var(--panel))] p-4 space-y-3">
                {canTrack && onOpenApplication && (() => {
                  // Adding is a quick bookmark: stay on the radar and offer a link. Only an
                  // already-tracked job navigates, because then the user wants the record.
                  const tracked = detail.tracking.application_status !== "not_started";
                  return <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-3 min-w-0">
                      <span className={"w-9 h-9 shrink-0 grid place-items-center rounded-[10px] " + (tracked ? "bg-okSoft text-ok" : "bg-accentSoft text-accent")}><Icon name={tracked ? "check" : "table"} size={17}/></span>
                      <div className="min-w-0">
                        <h3 className="text-sm font-semibold">{tracked ? "已在求职进度中" : "求职进度"}</h3>
                        <p className="text-xs text-muted mt-0.5">{tracked ? `${APPLICATION_STATUS_NAMES[detail.tracking.application_status]} · 在工作台管理面试、面经和导出` : "加入后可记录投递、面试与面经；加入不代表已投递"}</p>
                      </div>
                    </div>
                    <button className={"oc-btn oc-btn-sm " + (tracked ? "" : "oc-btn-primary")} disabled={trackingPending} onClick={() => void openOrAddApplication(detail, tracked)}>
                      {tracked ? <>在求职进度中查看<Icon name="arrowRight" size={13}/></> : <><Icon name="plus" size={14}/>加入求职进度</>}
                    </button>
                  </div>;
                })()}
                <details open={!canTrack}>
                <summary className="inline-flex items-center gap-1 text-xs text-muted cursor-pointer mb-3 hover:text-ink"><Icon name="chevronRight" size={12} className="transition-transform" />原申请进度与备注（快速编辑）</summary>
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
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-[180px_1fr]">
                  <label className="space-y-1 text-[12px] text-muted">
                    <span>申请进度</span>
                    <OcSelect
                      ariaLabel="我的申请进度"
                      value={draftStatus}
                      onChange={(value) => setDraftStatus(value as CareerApplicationStatus)}
                      options={APPLICATION_STATUSES.map((value) => ({ value, label: APPLICATION_STATUS_NAMES[value], tone: STATUS_TONE[value] }))}
                    />
                  </label>
                  <label className="space-y-1 text-[12px] text-muted">
                    <span>申请备注</span>
                    <textarea
                      aria-label="申请备注"
                      className="oc-field min-h-20 resize-y"
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
                    className="oc-btn oc-btn-primary oc-btn-sm"
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
                  className="radar-timeline"
                  data-testid="application-timeline"
                >
                  {(detail.tracking.events || []).map((event) => (
                    <div
                      key={event.id}
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
                </details>
                {canTrack && trackingError && <p role="alert" className="text-xs text-danger">{trackingError}</p>}
              </section>

              <section>
                <h3 className="oc-section-title">JD</h3>
                <div className="radar-jd">
                  {detail.description_raw}
                </div>
              </section>

              <div className="grid grid-cols-1 gap-7 md:grid-cols-2">
              <section>
                <h3 className="oc-section-title">版本记录</h3>
                <div className="radar-timeline">
                  {(detail.versions || []).map((version) => (
                    <div
                      key={version.version_number}
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
                <h3 className="oc-section-title">变化记录</h3>
                <div className="radar-timeline">
                  {(detail.catalog_events || detail.events || []).filter(event => event.event_type !== "created").map((event, index) => (
                    <div
                      key={`${event.occurred_at}-${index}`}
                    >
                      <span className="font-medium">
                        {EVENT_NAMES[event.event_type] || event.event_type}
                      </span>
                      <span className="text-muted">
                        {" "}· {formatDate(event.occurred_at)} · {event.summary}
                      </span>
                    </div>
                  ))}
                  {!(detail.catalog_events || detail.events)?.some(event => event.event_type !== "created") && (
                    <div className="text-[12px] text-muted">暂无变化记录</div>
                  )}
                </div>
              </section>
              </div>
            </article>
          )}
        </section>
      </div>
      {interviewJob && (
        <div className="oc-dialog-backdrop">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="career-interview-setup-title"
            className="oc-dialog max-w-lg"
          >
            <header>
              <h2
                id="career-interview-setup-title"
              >
                模拟面试设置
              </h2>
              <p>
                {interviewJob.title || "未命名岗位"} ·{" "}
                {interviewJob.company.name}
              </p>
            </header>
            <div className="mt-5 grid gap-4">
              <div className="oc-field-label">
                <span>面试简历</span>
                <OcSelect
                  ariaLabel="面试简历"
                  disabled={interviewSetupLoading}
                  value={interviewResumeId}
                  placeholder="暂无已确认简历"
                  onChange={setInterviewResumeId}
                  options={interviewResumes.map((resume) => ({ value: resume.id, label: resume.display_name }))}
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="oc-field-label">
                  <span>面试时长</span>
                  <OcSelect
                    ariaLabel="面试时长"
                    value={String(interviewDuration)}
                    onChange={(value) => setInterviewDuration(Number(value) as 10 | 15 | 20)}
                    options={[10, 15, 20].map((minutes) => ({ value: String(minutes), label: `${minutes} 分钟 · 5 题` }))}
                  />
                </div>
                <div className="oc-field-label">
                  <span>面试难度</span>
                  <OcSelect
                    ariaLabel="面试难度"
                    value={interviewDifficulty}
                    onChange={(value) => setInterviewDifficulty(value as "simple" | "standard" | "deep")}
                    options={[{ value: "simple", label: "简单", hint: "基础问题，热身练习" }, { value: "standard", label: "标准", hint: "接近真实面试" }, { value: "deep", label: "深入", hint: "追问细节与原理" }]}
                  />
                </div>
              </div>
              {interviewSetupLoading && (
                <p className="text-sm text-muted">正在读取面试资料…</p>
              )}
              {interviewSetupError && (
                <p role="alert" className="oc-alert">
                  {interviewSetupError}
                </p>
              )}
            </div>
            <footer>
              <button
                className="oc-btn"
                onClick={() => setInterviewJob(null)}
              >
                取消
              </button>
              <button
                className="oc-btn oc-btn-primary"
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
      {notice && (
        <div role="status" className="oc-toast">
          <Icon name="check" size={15} className="text-ok shrink-0" />
          <span className="min-w-0 truncate">{notice.text}</span>
          {notice.applicationId && onOpenApplication && (
            <button type="button" className="oc-toast-action" onClick={() => { const id = notice.applicationId!; setNotice(null); onOpenApplication(id); }}>去查看</button>
          )}
          <button type="button" className="oc-toast-close" aria-label="关闭提示" onClick={() => setNotice(null)}><Icon name="x" size={14} /></button>
        </div>
      )}
    </main>
  );
}
