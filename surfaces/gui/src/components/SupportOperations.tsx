import { useEffect, useState } from "react";
import { supportRequest } from "../api";

const categories: Record<string, string> = {
  health_down: "服务暂时不可达", unexpected_restart: "服务重启待确认", disk_pressure: "磁盘空间不足", memory_pressure: "内存占用偏高",
  http_client_error: "接口请求未成功", http_server_error: "服务端异常", page_crash: "页面崩溃", network_error: "网络异常",
  provider_error: "模型请求失败", tool_error: "工具调用失败", turn_error: "会话处理失败", socket_error: "实时连接异常",
};
const actions: Record<string, string> = { list: "查看列表", detail: "查看问题", update: "处理反馈", merge: "合并反馈", alerts: "检查系统提醒", maintenance: "清理过期技术诊断" };
type Alert = { id: string; category: string; source: string; count: number; active: boolean; updated_at: number };
type Audit = { id: string; action: string; user_id: string; target_id: string | null; created_at: number };

export function SupportOperations() {
  const [tab, setTab] = useState("alerts");
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [audit, setAudit] = useState<Audit[]>([]);
  const [message, setMessage] = useState("");
  const load = async () => {
    setMessage("");
    try {
      if (tab === "alerts") setAlerts((await supportRequest<{ alerts: Alert[] }>("admin/alerts")).alerts);
      else setAudit((await supportRequest<{ audit: Audit[] }>("admin/audit")).audit);
    } catch { setMessage("无法读取管理信息，请确认权限或稍后重试。"); }
  };
  useEffect(() => { void load(); }, [tab]);
  return <section className="space-y-3">
    <div className="flex gap-2"><button className="btn" onClick={() => setTab("alerts")}>系统提醒</button><button className="btn" onClick={() => setTab("audit")}>管理记录</button><button className="btn" onClick={() => void load()}>刷新记录</button></div>
    <p className="text-xs text-muted">不展示用户输入或密钥。浏览器报告不能单独判定服务故障；主机提醒需要启用独立检查任务。默认不外发通知。</p>
    {tab === "alerts" ? <>{alerts.length === 0 && <p className="text-sm text-muted">暂无系统提醒。</p>}{alerts.map((item) => <article key={item.id} className="border border-line rounded-xl p-3"><p>{categories[item.category] || "系统提醒"}</p><p className="text-xs text-muted mt-1">{item.active ? "待确认" : "已恢复"} · {item.source === "host" ? "主机检查" : "最近十五分钟错误聚合"} · 数量或占用比例：{item.count}</p><p className="text-xs text-muted break-all mt-1">编号：{item.id}</p></article>)}</>
      : <>{audit.length === 0 && <p className="text-sm text-muted">暂无管理记录。</p>}{audit.map((item) => <article key={item.id} className="border border-line rounded-xl p-3 text-xs break-all"><p>{actions[item.action] || "管理操作"} · {new Date(item.created_at / 1000).toLocaleString()}</p><p className="text-muted mt-1">操作账号：{item.user_id}{item.target_id ? ` · 反馈编号：${item.target_id}` : ""}</p></article>)}</>}
    {message && <p role="status" className="text-sm">{message}</p>}
  </section>;
}
