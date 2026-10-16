import { useState } from "react";
import { setWorkspaceTrusted, type WorkspaceCommandTrust } from "../api";

export function WorkspaceTrustPrompt({
  request,
  onClose,
}: {
  request: WorkspaceCommandTrust;
  onClose: () => void;
}) {
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const trust = async () => {
    setSaving(true);
    setError("");
    const result = await setWorkspaceTrusted(request.workspace, true).catch(() => null);
    setSaving(false);
    if (!result?.ok) {
      setError(result?.error || "无法保存工作区信任设置。");
      return;
    }
    onClose();
  };

  return (
    <div className="gate-overlay" role="dialog" aria-modal="true" aria-labelledby="workspace-trust-title">
      <div className="gate max-w-[560px]">
        <div className="gate-mark">✦</div>
        <h2 id="workspace-trust-title">信任此工作区的命令？</h2>
        <p className="gate-sub">
          此项目请求 OpenCareer 无需逐次批准即可执行以下命令。信任将持续应用于此文件夹，直到你在设置中撤销。
        </p>
        <div className="rounded-lg border border-line bg-paper px-3 py-2.5 max-h-48 overflow-y-auto">
          {request.requested_commands.map((command) => (
            <code key={command} className="block text-[12.5px] py-1 text-ink">
              {command}
            </code>
          ))}
        </div>
        <div className="text-[11.5px] text-muted mt-2 break-all">{request.workspace}</div>
        {error && <div className="gate-error">{error}</div>}
        <div className="gate-foot justify-end gap-2">
          <button className="btn" onClick={onClose} disabled={saving}>
            继续逐次询问
          </button>
          <button className="btn primary" onClick={() => void trust()} disabled={saving}>
            {saving ? "正在保存…" : "信任工作区"}
          </button>
        </div>
      </div>
    </div>
  );
}
