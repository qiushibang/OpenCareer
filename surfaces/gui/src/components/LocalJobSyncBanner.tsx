import { useEffect, useRef, useState } from "react";
import { getLocalJobSync, refreshLocalJobs, isLocal, type LocalJobSyncStatus } from "../api";

export function LocalJobSyncBanner({ onUpdated }: { onUpdated: () => void }) {
  const [status, setStatus] = useState<LocalJobSyncStatus | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const signature = useRef<string | null>(null);
  const local = isLocal();

  useEffect(() => {
    if (!local) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const result = await getLocalJobSync();
        if (!active || !result.ok) return;
        setStatus(result);
        setError("");
        const next = JSON.stringify(result.sources.filter(s => s.status === "succeeded").map(s => [s.slug, s.checked_at]));
        if (signature.current !== next && (signature.current !== null || next !== "[]")) onUpdated();
        signature.current = next;
      } catch {
        if (active) setError("暂时无法读取采集进度，请确认本地启动终端仍在运行。");
      } finally {
        if (active) timer = setTimeout(poll, 3000);
      }
    };
    void poll();
    return () => { active = false; clearTimeout(timer); };
  }, [local, onUpdated]);

  if (!local) return null;
  const running = status?.state === "running" && Date.now() / 1000 - status.updated_at < 1200;
  const current = status?.sources.find(s => s.status === "running");
  const failed = status?.sources.filter(s => s.status === "failed") || [];
  return (
    <div className="mb-3 rounded-xl border border-line bg-paper px-3 py-2.5 text-[12px]" aria-label="官方岗位采集">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p role="status">
          {running ? `正在采集官方岗位 · 已完成 ${status?.completed}/${status?.total_sources} 个来源${current ? ` · ${current.name}` : ""}`
            : status?.state === "completed" ? `官方岗位已更新 · ${status.completed} 个来源 · ${new Date(status.updated_at * 1000).toLocaleString("zh-CN")}`
            : status?.state === "partial" ? `岗位已分批入库 · ${status.completed} 个来源成功，${status.failed} 个来源暂不可用`
            : "等待后台采集官方岗位…"}
        </p>
        <button type="button" disabled={running || pending} className="shrink-0 rounded-lg border border-line px-2.5 py-1 text-ink disabled:opacity-40"
          onClick={async () => {
            setPending(true);
            try {
              const result = await refreshLocalJobs();
              if (!result.ok) throw new Error();
              setError(result.queued ? "已请求更新，后台将开始采集。" : "后台正在处理，或距上次更新不足一分钟，请稍后再试。");
            } catch { setError("无法请求更新，请确认本地服务仍在运行。"); }
            finally { setPending(false); }
          }}>
          {pending ? "正在请求…" : failed.length ? "重试采集" : "更新岗位"}
        </button>
      </div>
      <p className="mt-1 text-muted">首次采集可能需要数十分钟，岗位会自动显示；无需模型密钥。运行期间每 12 小时更新一次。</p>
      {failed.length > 0 && <details className="mt-1 text-muted"><summary className="cursor-pointer">查看暂不可用的来源</summary><p className="mt-1">{failed.map(s => s.name).join("、")}。可能是网络、官网限制或浏览器组件未就绪；已有岗位会保留。</p></details>}
      {status?.state === "running" && !running && <p className="mt-1 text-muted">采集进程可能已停止，请重启本地启动器后重试。</p>}
      {error && <p className="mt-1 text-muted">{error}</p>}
    </div>
  );
}
