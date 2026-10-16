import { useEffect, useRef } from "react";
import { CLOUD_PROVIDERS } from "../composerModelPolicy";
import {
  ProviderCards,
  ProviderForm,
  useProviderSetup,
  type ProviderSetupState,
} from "../providers/ProviderSetup";

// 输入框「配置自定义模型」的就地快配弹窗（云端 BYOK）：不离开对话——选服务商、
// 填 Key、测试通过即自动保存、自动选中新模型并关闭。与设置 ▸ 模型共享同一套
// useProviderSetup 状态机与后端 API，管理类操作（测试已存密钥/更换/删除/默认
// 模型）仍以设置页为完整入口，弹窗底部提供深链。

const SEC_H = "text-[11px] uppercase tracking-[0.05em] text-faint font-semibold";

export function QuickModelSetup({
  onClose,
  onOpenSettings,
  onSaved,
  onUseModel,
}: {
  onClose: () => void;
  // 深链到设置 ▸ 模型（管理已配置的密钥与默认模型）。
  onOpenSettings: () => void;
  // 任一 provider 保存成功（刷新选择器模型列表）。
  onSaved?: () => void;
  // 测试通过后建议立即使用的新模型（provider 的推荐模型）。
  onUseModel?: (model: string) => void;
}) {
  const ps = useProviderSetup({ onSaved });
  // verify 翻到 ok 即测试并保存成功：推荐模型直接选中；稍候自动关闭（先让
  // hook 回到画廊显示 ✓ 卡片，再收起弹窗，回到对话即可发送）。
  const reported = useRef(false);
  const closeTimer = useRef<number | null>(null);
  useEffect(() => {
    if (ps.verify.state === "ok" && !reported.current) {
      reported.current = true;
      const rec = ps.info?.recommended_model;
      if (rec && ps.sel) {
        onUseModel?.(ps.sel === "openai" ? rec : `${ps.sel}:${rec}`);
      }
      closeTimer.current = window.setTimeout(onClose, 1100);
    }
    if (ps.verify.state !== "ok") reported.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ps.verify.state]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (closeTimer.current) window.clearTimeout(closeTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const curated: ProviderSetupState = {
    ...ps,
    ordered: ps.ordered.filter((p) => CLOUD_PROVIDERS.has(p.name)),
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-label="配置自定义模型">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} data-testid="quick-setup-backdrop" />
      <div className="relative w-full max-w-xl rounded-xl2 border border-line bg-panel p-5 shadow-xl max-h-[85vh] overflow-y-auto" data-testid="quick-setup">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-[15px] font-semibold text-ink">配置自定义模型</div>
            <p className="text-[12px] text-muted mt-1 leading-relaxed">
              选择模型服务商，填入你的 API Key。密钥保存在服务器上你的私人目录，仅本人可见；测试通过即保存并切换到新模型。
            </p>
          </div>
          <button
            className="text-muted hover:text-ink text-[15px] shrink-0"
            onClick={onClose}
            aria-label="关闭"
            data-testid="quick-setup-close"
          >
            ✕
          </button>
        </div>

        {ps.sel === null ? (
          <div className="mt-4">
            <div className={SEC_H + " mb-1.5"}>选择服务商</div>
            <ProviderCards ps={curated} tp="qm" gridClass="grid grid-cols-2 gap-2.5" lastUsed />
          </div>
        ) : (
          <div className="mt-4">
            <ProviderForm ps={ps} tp="qm" />
          </div>
        )}

        <div className="mt-5 pt-3 border-t border-line flex items-center justify-between gap-3">
          <button
            className="text-[12.5px] text-muted hover:text-ink underline underline-offset-2"
            data-testid="quick-setup-manage"
            onClick={() => {
              onClose();
              onOpenSettings();
            }}
          >
            管理已配置的密钥与默认模型 →
          </button>
          <button
            className="text-[12.5px] px-4 py-1.5 rounded-lg bg-accent text-white disabled:opacity-40"
            onClick={onClose}
            data-testid="quick-setup-done"
          >
            完成
          </button>
        </div>
      </div>
    </div>
  );
}
