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
  const shared = status?.mode === "shared";
  const running = status?.state === "running" && Date.now() / 1000 - status.updated_at < 1200;
  const current = status?.sources.find(s => s.status === "running");
  const failed = status?.sources.filter(s => s.status === "failed" || ["failed", "degraded"].includes(s.upstream_status || "")) || [];
  return (
    <div className="mb-3 rounded-xl border border-line bg-paper px-3 py-2.5 text-[12px]" aria-label="官方岗位采集">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p role="status">
          {status?.error_code === "FEED_UNAVAILABLE" ? "公共岗位目录暂时无法同步，请检查网络并稍后重试；已保存的数据不会清除。"
            : status?.error_code === "LOCAL_CRAWL_UNAVAILABLE" ? "本地采集暂时无法运行，请检查启动终端；已保存的数据不会清除。"
            : running ? `正在${shared ? "同步公共岗位目录" : "采集官方岗位"} · 已完成 ${status?.completed}/${status?.total_sources} 个来源${current ? ` · ${current.name}` : ""}`
            : status?.state === "completed" ? `${shared ? "公共岗位目录已同步" : "官方岗位已更新"} · ${status.completed} 个来源 · ${new Date(status.updated_at * 1000).toLocaleString("zh-CN")}`
            : status?.state === "partial" ? `岗位已分批入库 · ${status.completed} 个来源成功，${status.failed} 个来源暂不可用`
            : "等待后台加载官方岗位…"}
        </p>
        <button type="button" disabled={running || pending} className="shrink-0 rounded-lg border border-line px-2.5 py-1 text-ink disabled:opacity-40"
          onClick={async () => {
            setPending(true);
            try {
              const result = await refreshLocalJobs();
              if (!result.ok) throw new Error();
              setError(result.queued ? "已请求更新，后台将开始处理。" : "后台正在处理，或距上次更新不足一分钟，请稍后再试。");
            } catch { setError("无法请求更新，请确认本地服务仍在运行。"); }
            finally { setPending(false); }
          }}>
          {pending ? "正在请求…" : failed.length ? (shared ? "重试同步" : "重试采集") : "更新岗位"}
        </button>
      </div>
      <p className="mt-1 text-muted">{shared ? "从服务器下载公开岗位，无需登录或模型密钥；运行期间每 24 小时检查更新，失败后 15 分钟重试。" : "本地独立采集可能需要数十分钟，岗位会自动显示；运行期间每 12 小时更新一次。"}</p>
      {shared && status?.published_at && <p className="mt-1 text-muted">公共快照发布于 {new Date(status.published_at).toLocaleString("zh-CN")}；岗位的实际确认时间见各岗位详情。</p>}
      {failed.length > 0 && <details className="mt-1 text-muted"><summary className="cursor-pointer">查看更新暂不可用的来源</summary><p className="mt-1">{failed.map(s => s.name).join("、")}。{shared ? "部分官网最近更新未成功，服务器与本机仍保留上次可用的岗位。" : "可能是网络、官网限制或浏览器组件未就绪；已有岗位会保留。"}</p></details>}
      {status?.state === "running" && !running && <p className="mt-1 text-muted">{shared ? "同步较久没有进度更新，请检查网络和本地启动终端。" : "采集进程可能已停止，请检查本地启动终端。"}</p>}
      {error && <p className="mt-1 text-muted">{error}</p>}
    </div>
  );
}
