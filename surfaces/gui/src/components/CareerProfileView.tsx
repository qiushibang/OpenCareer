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

function FactValue({ value }: { value: unknown }) {
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
            <FactValue value={item} />
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
              <dt className="text-muted">{careerProfileFieldLabel(key)}</dt>
              <dd className="min-w-0 break-words">
                <FactValue value={entry} />
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
    if (previewUrl && typeof URL.revokeObjectURL === "function") {
      URL.revokeObjectURL(previewUrl);
    }
    setPreviewUrl("");
    void loadResume();
  }, [selectedId]);

  useEffect(() => {
    if (!selectedId) return;
    if (tab === "versions" && versions.length === 0) {
      getCareerResumeVersions(selectedId)
        .then((result) => setVersions(result.versions || []))
        .catch(() => setError("无法读取版本记录。"));
    }
    if (tab === "original" && !original) {
      Promise.all([
        getCareerResumeOriginal(selectedId),
        getCareerResumeOriginalContent(selectedId),
      ])
        .then(([result, url]) => {
          if (result.original) setOriginal(result.original);
          setPreviewUrl(url);
        })
        .catch(() => setError("无法预览原始简历。"));
    }
  }, [tab, selectedId, versions.length, original]);

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
      <main className="flex-1 grid place-items-center bg-paper text-muted">
        正在加载简历库…
      </main>
    );
  }

  if (resumes.length === 0 && !error) {
    return (
      <main className="flex-1 grid place-items-center bg-paper px-8">
        <div className="max-w-md text-center">
          <div className="w-12 h-12 rounded-xl bg-panel border border-line grid place-items-center mx-auto mb-4">
            <Icon name="file" size={22} />
          </div>
          <h1 className="text-xl font-semibold">尚未建立求职档案</h1>
          <p className="text-sm text-muted mt-2">
            可以导入多份 PDF 或 DOCX 简历，分别用于不同岗位。
          </p>
          <button
            className="mt-5 px-4 py-2 rounded-lg bg-accent text-white text-sm"
            onClick={onImportResume}
          >
            导入简历
          </button>
        </div>
      </main>
    );
  }

  return (
    <main className="flex-1 min-w-0 overflow-y-auto bg-paper">
      <div className="max-w-6xl mx-auto px-4 py-5 sm:px-7 sm:py-6">
        <header className="flex flex-col items-start justify-between gap-4 mb-5 sm:flex-row">
          <div>
            <h1 className="text-xl font-semibold">我的求职档案</h1>
            <p className="text-[12.5px] text-muted mt-1">
              管理多份定制简历；所有内容仍基于已确认的真实经历。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              className="px-3 py-2 rounded-lg bg-accent text-white text-[12.5px]"
              onClick={onImportResume}
            >
              新增简历
            </button>
            <button
              className="px-3 py-2 rounded-lg border border-line text-red-600 text-[12.5px]"
              onClick={() => setDeleteOpen(true)}
            >
              删除全部档案
            </button>
          </div>
        </header>

        {error && (
          <div className="mb-4 rounded-lg bg-red-50 text-red-700 px-3 py-2 text-sm">
            {error}
          </div>
        )}

        <div
          className="grid grid-cols-1 gap-4 items-start lg:grid-cols-[240px_minmax(0,1fr)]"
          data-testid="career-profile-layout"
        >
          <aside className="rounded-lg border border-line bg-panel p-2 space-y-1">
            <div className="px-2 py-1.5 text-[11px] font-semibold text-muted">
              简历库 · {resumes.length}
            </div>
            {resumes.map((item) => (
              <button
                key={item.id}
                className={
                  "w-full rounded-lg px-3 py-2.5 text-left border " +
                  (selectedId === item.id
                    ? "border-accent bg-paper"
                    : "border-transparent hover:bg-paper")
                }
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
            <div className="flex gap-4 overflow-x-auto border-b border-line mb-5 sm:gap-5">
              {(
                [
                  ["profile", "简历内容"],
                  ["original", "原始简历"],
                  ["versions", "版本记录"],
                ] as const
              ).map(([key, label]) => (
                <button
                  key={key}
                  className={
                    "pb-2.5 text-[13px] " +
                    (tab === key
                      ? "text-accent border-b-2 border-accent font-medium"
                      : "text-muted")
                  }
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
                <div className="rounded-lg border border-line bg-panel p-4 flex flex-col items-start justify-between gap-3 sm:flex-row sm:items-center">
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
                      className="px-3 py-1.5 rounded-lg border border-line text-[12px]"
                      onClick={openEdit}
                    >
                      编辑信息
                    </button>
                    <button
                      className="px-3 py-1.5 rounded-lg border border-red-200 text-red-600 text-[12px]"
                      onClick={() => setResumeDeleteOpen(true)}
                    >
                      删除此简历
                    </button>
                    <button
                      className="px-3 py-1.5 rounded-lg border border-line text-[12px]"
                      onClick={() => void loadResume(true)}
                    >
                      显示敏感信息
                    </button>
                  </div>
                </div>
                {Object.entries(resume.sections || {}).map(
                  ([section, value]) => (
                    <section
                      key={section}
                      className="rounded-lg border border-line bg-panel p-4"
                    >
                      <h2 className="text-sm font-semibold mb-3">
                        {SECTION_NAMES[section] || section}
                      </h2>
                      <FactValue value={value} />
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
                      {original?.filename || "正在读取原始简历…"}
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
                      className="px-3 py-1.5 rounded-lg border border-line text-[12px]"
                      onClick={() =>
                        void downloadCareerResumeOriginal(
                          selectedId,
                          original.filename,
                        )
                      }
                    >
                      下载原文件
                    </button>
                  )}
                </div>
                {previewUrl ? (
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
                  <div className="text-center text-muted py-16">
                    暂无版本记录
                  </div>
                )}
              </div>
            )}
          </section>
        </div>

        {editOpen && resume && (
          <div className="fixed inset-0 z-50 bg-black/30 grid place-items-center px-5">
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="resume-edit-title"
              className="w-full max-w-md rounded-xl bg-panel border border-line p-5 shadow-xl"
            >
              <h2 id="resume-edit-title" className="font-semibold">
                编辑简历信息
              </h2>
              <label className="block text-sm mt-4">
                <span className="text-muted">简历名称</span>
                <input
                  className="w-full mt-1.5 px-3 py-2 rounded-lg border border-line bg-paper"
                  value={editName}
                  onChange={(event) => setEditName(event.target.value)}
                />
              </label>
              <label className="block text-sm mt-4">
                <span className="text-muted">目标岗位</span>
                <textarea
                  className="w-full min-h-24 mt-1.5 px-3 py-2 rounded-lg border border-line bg-paper"
                  placeholder="使用逗号或换行分隔，最多 10 个"
                  value={editRoles}
                  onChange={(event) => setEditRoles(event.target.value)}
                />
              </label>
              <div className="flex justify-end gap-2 mt-4">
                <button
                  className="px-3 py-2 text-sm"
                  onClick={() => setEditOpen(false)}
                >
                  取消
                </button>
                <button
                  className="px-3 py-2 rounded-lg bg-accent text-white text-sm disabled:opacity-40"
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
          <div className="fixed inset-0 z-50 bg-black/30 grid place-items-center px-5">
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="resume-delete-title"
              className="w-full max-w-md rounded-xl bg-panel border border-line p-5 shadow-xl"
            >
              <h2 id="resume-delete-title" className="font-semibold">
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
                  className="w-full px-3 py-2 rounded-lg border border-line bg-paper"
                  value={resumeDeleteText}
                  onChange={(event) =>
                    setResumeDeleteText(event.target.value)
                  }
                />
              </label>
              <div className="flex justify-end gap-2 mt-4">
                <button
                  className="px-3 py-2 text-sm"
                  onClick={() => {
                    setResumeDeleteOpen(false);
                    setResumeDeleteText("");
                  }}
                >
                  取消
                </button>
                <button
                  className="px-3 py-2 rounded-lg bg-red-600 text-white text-sm disabled:opacity-40"
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
          <div className="fixed inset-0 z-50 bg-black/30 grid place-items-center px-5">
            <div className="w-full max-w-md rounded-xl bg-panel border border-line p-5 shadow-xl">
              <h2 className="font-semibold">确认删除全部求职档案</h2>
              <p className="text-sm text-muted mt-2">
                此操作会删除全部简历、事实档案、版本记录和私有原文件，无法撤销。
              </p>
              <input
                className="w-full mt-4 px-3 py-2 rounded-lg border border-line bg-paper text-sm"
                placeholder="请输入“删除我的求职档案”"
                value={deleteText}
                onChange={(event) => setDeleteText(event.target.value)}
              />
              <div className="flex justify-end gap-2 mt-4">
                <button
                  className="px-3 py-2 text-sm"
                  onClick={() => setDeleteOpen(false)}
                >
                  取消
                </button>
                <button
                  className="px-3 py-2 rounded-lg bg-red-600 text-white text-sm disabled:opacity-40"
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
