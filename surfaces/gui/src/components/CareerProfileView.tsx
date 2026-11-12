import { useEffect, useState } from "react";

import {
  deleteCareerResume,
  deleteCareerProfile,
  downloadCareerResumeOriginal,
  getCareerResume,
  getCareerResumeOriginal,
  getCareerResumeOriginalContent,
  getCareerResumes,
  getCareerResumeVersions,
  updateCareerResume,
  type CareerOriginal,
  type CareerProfileVersion,
  type CareerResumeDocument,
  type CareerResumeSummary,
} from "../api";
import { careerProfileFieldLabel } from "../careerProfileFields";
import { Icon } from "./Icon";

type Tab = "profile" | "original" | "versions";

const SECTION_NAMES: Record<string, string> = {
  basic: "基本信息",
  education: "教育经历",
  experience: "工作经历",
  project: "项目经历",
  skill: "技能",
};

const formatDate = (value: string) =>
  new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));

function FactValue({ value, section }: { value: unknown; section?: string }) {
  if (value == null || value === "") {
    return <span className="text-faint">未填写</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="text-faint">暂无内容</span>;
    }
    return (
      <div className="space-y-2">
        {value.map((item, index) => (
          <div key={index} className="rounded-lg bg-paper px-3 py-2.5">
            <FactValue value={item} section={section} />
          </div>
        ))}
      </div>
    );
  }
  if (typeof value === "object") {
    return (
      <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-1.5 text-[12.5px]">
        {Object.entries(value as Record<string, unknown>).map(
          ([key, entry]) => (
            <div key={key} className="contents">
              <dt className="text-muted">{careerProfileFieldLabel(key, section)}</dt>
              <dd className="min-w-0 break-words">
                <FactValue value={entry} section={section} />
              </dd>
            </div>
          ),
        )}
      </dl>
    );
  }
  return <>{String(value)}</>;
}

export function CareerProfileView({
  onImportResume,
}: {
  onImportResume: () => void;
}) {
  const [tab, setTab] = useState<Tab>("profile");
  const [resumes, setResumes] = useState<CareerResumeSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [resume, setResume] = useState<CareerResumeDocument | null>(null);
  const [versions, setVersions] = useState<CareerProfileVersion[]>([]);
  const [original, setOriginal] = useState<CareerOriginal | null>(null);
  const [previewUrl, setPreviewUrl] = useState("");
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState("");
  const [previewAttempt, setPreviewAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState("");
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteText, setDeleteText] = useState("");
  const [editOpen, setEditOpen] = useState(false);
  const [editName, setEditName] = useState("");
  const [editRoles, setEditRoles] = useState("");
  const [resumeDeleteOpen, setResumeDeleteOpen] = useState(false);
  const [resumeDeleteText, setResumeDeleteText] = useState("");

  useEffect(() => {
    let current = true;
    getCareerResumes()
      .then((result) => {
        if (!current) return;
        if (!result.ok) {
          setError(result.error?.message || "无法读取简历库。");
          return;
        }
        const items = result.resumes || [];
        setResumes(items);
        setSelectedId(items[0]?.id || "");
      })
      .catch(() => {
        if (current) setError("无法连接本地求职档案服务。");
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, []);

  const loadResume = async (includeSensitive = false) => {
    if (!selectedId) return;
    setDetailLoading(true);
    setError("");
    try {
      const result = await getCareerResume(selectedId, includeSensitive);
      if (result.ok && result.resume) setResume(result.resume);
      else setError(result.error?.message || "无法读取这份简历。");
    } catch {
      setError("无法连接本地求职档案服务。");
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedId) {
      setResume(null);
      return;
    }
    setTab("profile");
    setVersions([]);
    setOriginal(null);
    setPreviewUrl("");
    setPreviewHtml(null);
    setPreviewError("");
    void loadResume();
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    if (tab === "versions" && versions.length === 0) {
      getCareerResumeVersions(selectedId)
        .then((result) => setVersions(result.versions || []))
        .catch(() => setError("无法读取版本记录。"));
    }
  }, [tab, selectedId, versions.length]);

  useEffect(() => {
    if (tab !== "original" || !selectedId) return;
    let current = true;
    setOriginal(null);
    setPreviewUrl("");
    setPreviewHtml(null);
    setPreviewError("");
    const loadOriginal = async () => {
      try {
        const result = await getCareerResumeOriginal(selectedId);
        if (!current) return;
        if (!result.ok || !result.original) throw new Error("Preview unavailable");
        setOriginal(result.original);
        if (result.original.preview_kind === "html") {
          // Embedded browsers can block blob navigation. Keep escaped DOCX HTML
          // in a sandboxed srcDoc frame, never in the application's DOM.
          const html = await getCareerResumeOriginalContent(selectedId, "html");
          if (current) setPreviewHtml(html);
          return;
        }
        const url = await getCareerResumeOriginalContent(selectedId);
        if (current) setPreviewUrl(url);
        else if (typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(url);
      } catch {
        if (current) setPreviewError("无法预览原始简历。");
      }
    };
    void loadOriginal();
    return () => { current = false; };
  }, [tab, selectedId, previewAttempt]);

  useEffect(
    () => () => {
      if (previewUrl && typeof URL.revokeObjectURL === "function") {
        URL.revokeObjectURL(previewUrl);
      }
    },
    [previewUrl],
  );

  const removeProfile = async () => {
    if (deleteText !== "删除我的求职档案") return;
    const result = await deleteCareerProfile("DELETE MY CAREER PROFILE");
    if (!result.ok) {
      setError(result.error?.message || "删除求职档案失败。");
      return;
    }
    setDeleteOpen(false);
    setDeleteText("");
    setResume(null);
    setResumes([]);
    setSelectedId("");
  };

  const openEdit = () => {
    if (!resume) return;
    setEditName(resume.display_name);
    setEditRoles(resume.target_roles.join(", "));
    setEditOpen(true);
  };

  const saveResumeMetadata = async () => {
    if (!resume) return;
    const targetRoles = editRoles
      .split(/[,，\n]/)
      .map((role) => role.trim())
      .filter(Boolean);
    try {
      const result = await updateCareerResume(resume.id, {
        displayName: editName,
        targetRoles,
      });
      if (!result.ok || !result.resume) {
        setError(result.error?.message || "保存简历信息失败。");
        return;
      }
      setResume(result.resume);
      setResumes((items) =>
        items.map((item) =>
          item.id === result.resume?.id ? result.resume : item,
        ),
      );
      setEditOpen(false);
      setError("");
    } catch {
      setError("无法连接本地求职档案服务。");
    }
  };

  const removeResume = async () => {
    if (!resume || resumeDeleteText !== resume.display_name) return;
    try {
      const result = await deleteCareerResume(
        resume.id,
        resumeDeleteText,
      );
      if (!result.ok) {
        setError(result.error?.message || "删除简历失败。");
        return;
      }
      const currentIndex = resumes.findIndex(
        (item) => item.id === resume.id,
      );
      const remaining = resumes.filter((item) => item.id !== resume.id);
      const adjacent = remaining[Math.min(currentIndex, remaining.length - 1)];
      setResumes(remaining);
      setResume(null);
      setSelectedId(adjacent?.id || "");
      setResumeDeleteOpen(false);
      setResumeDeleteText("");
      setError("");
    } catch {
      setError("无法连接本地求职档案服务。");
    }
  };

  if (loading) {
    return (
      <main role="status" className="oc-page oc-profile flex-1 grid place-items-center bg-paper text-muted">
        <div className="flex items-center gap-2.5 text-[13px]"><span className="waiting-spinner" aria-hidden="true" />正在加载简历库…</div>
      </main>
    );
  }

  if (resumes.length === 0 && !error) {
    return (
      <main className="oc-page oc-profile flex-1 grid place-items-center bg-paper px-8">
        <div className="max-w-md text-center">
          <div className="oc-empty-icon w-14 h-14 mx-auto mb-5">
            <Icon name="file" size={24} />
          </div>
          <h1>尚未建立求职档案</h1>
          <p className="text-sm text-muted mt-2 leading-relaxed">{/* 产品说明移至代码：可以导入多份 PDF 或 DOCX 简历，分别用于不同岗位。 */}导入 PDF 或 DOCX 简历。</p>
          <button
            className="oc-btn oc-btn-primary mt-6"
            onClick={onImportResume}
          >
            <Icon name="plus" size={15} />
            导入简历
          </button>
          <ul className="mt-8 grid gap-2 text-left text-[12.5px] text-muted">
            {["支持多份简历，分别用于不同岗位方向", "导入后逐项确认经历，AI 只引用已确认的事实", "原始文件仅保存在本机，可随时删除"].map((tip) => (
              <li key={tip} className="flex items-start gap-2.5 rounded-[10px] border border-line bg-panel px-3.5 py-2.5"><span className="mt-1.5 w-1.5 h-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />{tip}</li>
            ))}
          </ul>
        </div>
      </main>
    );
  }

  return (
    <main className="oc-page oc-profile flex-1 min-w-0 overflow-y-auto bg-paper">
      <div className="max-w-6xl mx-auto px-4 py-5 sm:px-7 sm:py-6">
        <header className="flex flex-col items-start justify-between gap-4 mb-5 sm:flex-row">
          <div>
            <h1>我的求职档案</h1>
            <p className="oc-page-subtitle">共 {resumes.length} 份简历 · 所有内容基于已确认的真实经历</p>
            {/* 产品说明移至代码：管理多份定制简历；所有内容仍基于已确认的真实经历。 */}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="oc-btn oc-btn-primary oc-btn-sm"
              onClick={onImportResume}
            >
              <Icon name="plus" size={14} />
              新增简历
            </button>
            <button
              className="oc-btn oc-btn-danger oc-btn-sm"
              onClick={() => setDeleteOpen(true)}
            >
              删除全部档案
            </button>
          </div>
        </header>

        {error && (
          <div className="mb-4 oc-alert">
            {error}
          </div>
        )}

        <div
          className="grid grid-cols-1 gap-4 items-start lg:grid-cols-[240px_minmax(0,1fr)]"
          data-testid="career-profile-layout"
        >
          <aside className="rounded-[14px] border border-line bg-panel p-2 space-y-1 shadow-xs lg:sticky lg:top-4">
            <div className="px-2 py-1.5 text-[11px] font-semibold tracking-[0.06em] text-faint">
              简历库 · {resumes.length}
            </div>
            {resumes.map((item) => (
              <button
                key={item.id}
                className={
                  "profile-resume-item w-full rounded-[10px] px-3 py-2.5 text-left border " +
                  (selectedId === item.id
                    ? ""
                    : "border-transparent hover:bg-paper")
                }
                aria-current={selectedId === item.id ? "true" : undefined}
                onClick={() => setSelectedId(item.id)}
              >
                <div className="text-[12.5px] font-medium break-words">
                  {item.display_name}
                </div>
                <div className="text-[10.5px] text-muted mt-1">
                  {item.source_kind.toUpperCase()} ·{" "}
                  {formatDate(item.updated_at)}
                </div>
                {item.target_roles.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {item.target_roles.map((role) => (
                      <span
                        key={role}
                        className="rounded-full bg-accentSoft px-2 py-0.5 text-[10px] text-accent"
                      >
                        {role}
                      </span>
                    ))}
                  </div>
                )}
              </button>
            ))}
          </aside>

          <section className="min-w-0">
            <div className="oc-tabs mb-5" role="group" aria-label="简历视图">
              {(
                [
                  ["profile", "简历内容"],
                  ["original", "原始简历"],
                  ["versions", "版本记录"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  aria-pressed={tab === key}
                  onClick={() => setTab(key)}
                >
                  {label}
                </button>
              ))}
            </div>

            {detailLoading && (
              <div className="text-center text-muted py-16">
                正在加载简历…
              </div>
            )}

            {!detailLoading && tab === "profile" && resume && (
              <div className="space-y-3">
                <div className="rounded-lg border border-line bg-panel p-5 flex flex-col items-start justify-between gap-3 shadow-xs sm:flex-row sm:items-center">
                  <div className="min-w-0">
                    <div className="text-lg font-semibold">
                      {resume.display_name}
                    </div>
                    <div className="text-[11.5px] text-muted mt-1">
                      原文件：{resume.filename} · 更新于{" "}
                      {formatDate(resume.updated_at)}
                    </div>
                    {resume.target_roles.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {resume.target_roles.map((role) => (
                          <span
                            key={role}
                            className="rounded-full bg-accentSoft px-2 py-0.5 text-[10.5px] text-accent"
                          >
                            {role}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      className="oc-btn oc-btn-sm"
                      onClick={openEdit}
                    >
                      <Icon name="pencil" size={13} />
                      编辑信息
                    </button>
                    <button
                      className="oc-btn oc-btn-sm"
                      onClick={() => void loadResume(true)}
                    >
                      <Icon name="shield" size={13} />
                      显示敏感信息
                    </button>
                    <button
                      className="oc-btn oc-btn-danger oc-btn-sm"
                      onClick={() => setResumeDeleteOpen(true)}
                    >
                      <Icon name="trash" size={13} />
                      删除此简历
                    </button>
                  </div>
                </div>
                {Object.entries(resume.sections || {}).map(
                  ([section, value]) => (
                    <section
                      key={section}
                      className="rounded-lg border border-line bg-panel p-4"
                    >
                      <h2 className="oc-section-title">
                        {SECTION_NAMES[section] || section}
                      </h2>
                      <FactValue value={value} section={section} />
                    </section>
                  ),
                )}
              </div>
            )}

            {tab === "original" && (
              <section className="rounded-xl border border-line bg-panel overflow-hidden">
                <div className="px-4 py-3 border-b border-line flex items-center justify-between">
                  <div>
                    <div className="text-sm font-medium">
                      {original?.filename || (previewError ? "原始简历预览失败" : "正在读取原始简历…")}
                    </div>
                    {original && (
                      <div className="text-[11px] text-muted mt-0.5">
                        {Math.ceil(original.size / 1024)} KB ·{" "}
                        {original.source_kind.toUpperCase()}
                      </div>
                    )}
                  </div>
                  {original && (
                    <button
                      className="oc-btn oc-btn-sm"
                      onClick={() =>
                        void downloadCareerResumeOriginal(
                          selectedId,
                          original.filename,
                        )
                      }
                    >
                      <Icon name="download" size={13} />
                      下载原文件
                    </button>
                  )}
                </div>
                {previewError ? (
                  <div className="h-64 flex flex-col items-center justify-center gap-3">
                    <p role="alert" className="text-danger text-sm">{previewError}</p>
                    <button
                      className="oc-btn oc-btn-sm"
                      onClick={() => setPreviewAttempt((attempt) => attempt + 1)}
                    >
                      重新加载预览
                    </button>
                  </div>
                ) : previewHtml !== null ? (
                  <iframe
                    title="原始简历预览"
                    srcDoc={previewHtml}
                    sandbox=""
                    className="w-full h-[680px] bg-white"
                  />
                ) : previewUrl ? (
                  <iframe
                    title="原始简历预览"
                    src={previewUrl}
                    className="w-full h-[680px] bg-white"
                  />
                ) : (
                  <div className="h-64 grid place-items-center text-muted">
                    正在生成安全预览…
                  </div>
                )}
              </section>
            )}

            {tab === "versions" && (
              <div className="space-y-3">
                {versions.map((version) => (
                  <article
                    key={version.version}
                    className="rounded-xl border border-line bg-panel p-4"
                  >
                    <div className="flex justify-between gap-3">
                      <div className="font-semibold">
                        版本 {version.version}
                      </div>
                      <time className="text-[11.5px] text-muted">
                        {formatDate(version.created_at)}
                      </time>
                    </div>
                    <div className="text-[12px] text-muted mt-2">
                      确认章节：
                      {version.confirmed_sections
                        .map((section) => SECTION_NAMES[section] || section)
                        .join("、")}
                    </div>
                  </article>
                ))}
                {versions.length === 0 && (
                  <div className="oc-empty">
                    <strong>暂无版本记录</strong>
                  </div>
                )}
              </div>
            )}
          </section>
        </div>

        {editOpen && resume && (
          <div className="oc-dialog-backdrop">
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="resume-edit-title"
              className="oc-dialog max-w-md"
            >
              <h2 id="resume-edit-title" className="text-[17px] font-semibold">
                编辑简历信息
              </h2>
              <label className="block text-sm mt-4">
                <span className="text-muted">简历名称</span>
                <input
                  className="oc-field mt-1.5"
                  value={editName}
                  onChange={(event) => setEditName(event.target.value)}
                />
              </label>
              <label className="block text-sm mt-4">
                <span className="text-muted">目标岗位</span>
                <textarea
                  className="oc-field min-h-24 mt-1.5"
                  placeholder="使用逗号或换行分隔，最多 10 个"
                  value={editRoles}
                  onChange={(event) => setEditRoles(event.target.value)}
                />
              </label>
              <div className="flex justify-end gap-2 mt-4">
                <button
                  className="oc-btn oc-btn-ghost"
                  onClick={() => setEditOpen(false)}
                >
                  取消
                </button>
                <button
                  className="oc-btn oc-btn-primary"
                  disabled={!editName.trim()}
                  onClick={() => void saveResumeMetadata()}
                >
                  保存
                </button>
              </div>
            </div>
          </div>
        )}

        {resumeDeleteOpen && resume && (
          <div className="oc-dialog-backdrop">
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="resume-delete-title"
              className="oc-dialog max-w-md"
            >
              <h2 id="resume-delete-title" className="text-[17px] font-semibold">
                删除此简历
              </h2>
              <p className="text-sm text-muted mt-2">
                原始文件和这份简历的预览将被删除；已确认进入共享求职档案的事实会保留。
              </p>
              <p className="text-sm mt-3">
                请输入“{resume.display_name}”确认。
              </p>
              <label className="block text-sm mt-3">
                <span className="sr-only">输入简历名称</span>
                <input
                  className="oc-field"
                  value={resumeDeleteText}
                  onChange={(event) =>
                    setResumeDeleteText(event.target.value)
                  }
                />
              </label>
              <div className="flex justify-end gap-2 mt-4">
                <button
                  className="oc-btn oc-btn-ghost"
                  onClick={() => {
                    setResumeDeleteOpen(false);
                    setResumeDeleteText("");
                  }}
                >
                  取消
                </button>
                <button
                  className="oc-btn oc-btn-danger-solid"
                  disabled={resumeDeleteText !== resume.display_name}
                  onClick={() => void removeResume()}
                >
                  确认删除
                </button>
              </div>
            </div>
          </div>
        )}

        {deleteOpen && (
          <div className="oc-dialog-backdrop">
            <div role="dialog" aria-modal="true" aria-label="确认删除全部求职档案" className="oc-dialog max-w-md">
              <h2 className="text-[17px] font-semibold">确认删除全部求职档案</h2>
              <p className="text-sm text-muted mt-2">
                此操作会删除全部简历、事实档案、版本记录和私有原文件，无法撤销。
              </p>
              <input
                className="oc-field mt-4"
                placeholder="请输入“删除我的求职档案”"
                value={deleteText}
                onChange={(event) => setDeleteText(event.target.value)}
              />
              <div className="flex justify-end gap-2 mt-4">
                <button
                  className="oc-btn oc-btn-ghost"
                  onClick={() => setDeleteOpen(false)}
                >
                  取消
                </button>
                <button
                  className="oc-btn oc-btn-danger-solid"
                  disabled={deleteText !== "删除我的求职档案"}
                  onClick={() => void removeProfile()}
                >
                  永久删除
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
