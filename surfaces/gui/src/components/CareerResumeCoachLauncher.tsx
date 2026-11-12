import { useState } from "react";

import {
  getCareerResumes,
  type CareerJobDetail,
  type CareerResumeSummary,
} from "../api";
import { buildCareerJobSheet, type ResumeCoachLaunchPayload } from "../careerResumeCoach";
import { Icon } from "./Icon";

export function CareerResumeCoachLauncher({
  job,
  onStartAnalysis,
}: {
  job: CareerJobDetail;
  onStartAnalysis: (payload: ResumeCoachLaunchPayload) => void;
}) {
  const [open, setOpen] = useState(false);
  const [resumes, setResumes] = useState<CareerResumeSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const openLauncher = async () => {
    setOpen(true);
    setLoading(true);
    setError("");
    setResumes([]);
    setSelectedId("");
    try {
      const response = await getCareerResumes();
      if (!response.ok) {
        setError(response.error?.message || "无法读取简历库。");
        return;
      }
      const confirmed = (response.resumes || []).filter(
        (resume) => resume.confirmed_sections.length > 0,
      );
      setResumes(confirmed);
      setSelectedId(confirmed.length === 1 ? confirmed[0].id : "");
    } catch {
      setError("无法连接简历服务。");
    } finally {
      setLoading(false);
    }
  };

  const submit = () => {
    if (!selectedId) return;
    onStartAnalysis({
      jobId: job.id,
      resumeId: selectedId,
      companyName: job.company.name || "未知公司",
      position: job.title || "未命名岗位",
      jobSheet: buildCareerJobSheet({
        title: job.title,
        companyName: job.company.name,
        locationRaw: job.location_raw,
        recruitmentType: job.recruitment_type,
        sourceUrl: job.source_url,
        jobId: job.id,
        descriptionRaw: job.description_raw,
        responsibilities: job.responsibilities,
        requirements: job.requirements,
      }),
    });
    setOpen(false);
  };

  return (
    <>
      <button
        className="oc-btn oc-btn-accent shrink-0"
        onClick={() => void openLauncher()}
      >
        <Icon name="sparkle" size={13} />
        AI 分析与改简历
      </button>

      {open && (
        <div className="oc-dialog-backdrop">
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="career-resume-coach-title"
            className="oc-dialog max-h-[calc(100dvh-2rem)] w-full max-w-md overflow-y-auto"
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h2
                  id="career-resume-coach-title"
                  className="text-[17px] font-semibold tracking-[-0.02em]"
                >
                  选择用于分析的简历
                </h2>
                <p className="mt-1 break-words text-[12px] text-muted">
                  {job.company.name} · {job.title || "未命名岗位"}
                </p>
              </div>
              <button
                className="oc-btn oc-btn-ghost oc-btn-sm shrink-0"
                onClick={() => setOpen(false)}
              >
                关闭
              </button>
            </div>

            {error && (
              <div className="mt-4 oc-alert">
                {error}
              </div>
            )}

            {loading ? (
              <div role="status" className="py-10 text-center text-sm text-muted">
                正在读取简历…
              </div>
            ) : resumes.length === 0 ? (
              <p className="mt-4 rounded-lg bg-paper p-4 text-sm text-muted">{/* 产品说明移至代码：暂无已确认简历，请前往我的求职档案导入并确认简历。 */}请先导入并确认简历。</p>
            ) : (
              <div className="mt-4 space-y-2">
                {resumes.map((resume) => (
                  <label
                    key={resume.id}
                    className="flex min-w-0 cursor-pointer items-center gap-3 rounded-[10px] border border-line bg-panel p-3 hover:border-lineStrong has-[:checked]:border-accentLine has-[:checked]:bg-accentSoft/40"
                  >
                    <input
                      type="radio"
                      name="career-resume-coach"
                      aria-label={resume.display_name}
                      checked={selectedId === resume.id}
                      onChange={() => setSelectedId(resume.id)}
                    />
                    <span className="min-w-0 break-words text-sm">
                      {resume.display_name}
                    </span>
                  </label>
                ))}
              </div>
            )}

            <div className="mt-5 flex justify-end">
              <button
                className="oc-btn oc-btn-primary"
                disabled={!selectedId || loading}
                onClick={submit}
              >
                进入 Career Agent
              </button>
            </div>
          </section>
        </div>
      )}
    </>
  );
}
