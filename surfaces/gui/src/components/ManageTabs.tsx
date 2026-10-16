import { useEffect, useState } from "react";
import {
  addMcpServer,
  allowUser,
  connectConnector,
  connectManaged,
  connectMcpBacked,
  connectMcp,
  deleteMcpServer,
  disallowUser,
  getMcpServers,
  getMcpTools,
  getHealth,
  isAlpha,
  isLocal,
  signoutMcp,
  getSettings,
  getSubscriptions,
  removeModel,
  resolveUnauthorized,
  unsubscribeChannel,
  patchMcpServer,
  reloadMcp,
  setDefaultModel,
  updateConnectorTools,
  type CloudStatus,
  type Connector,
  type Subscription,
  type McpServer,
  type ModelSettings,
  type ProviderInfo,
} from "../api";
import { CloudSignInInline, CloudStatusPending } from "./connectors/CloudSignIn";
import { ModelChecklist } from "./ModelChecklist";
import { ProviderCards, ProviderForm, ProviderMark, useProviderSetup, type ProviderSetupState } from "../providers/ProviderSetup";
import { byokModelsFromProviders, CLOUD_PROVIDERS } from "../composerModelPolicy";
import { removeProvider, verifyProvider } from "../api";
import { Toggle } from "./Toggle";

// "2h ago"-style label for the providers' Last-used line (null when never used).
const relTime = (epoch?: number | null): string | null => {
  if (!epoch) return null;
  const secs = Math.max(0, Math.floor(Date.now() / 1000 - epoch));
  if (secs < 90) return "刚刚";
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins} 分钟前`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 48) return `${hrs} 小时前`;
  return `${Math.floor(hrs / 24)} 天前`;
};

// Shared tab bodies for the Settings and Integrations pages (the old top-tab ManageModal was retired
// when Settings/Activity became full-page surfaces): ModelsTab → Settings ▸ Models; ConnectorsTab +
// McpTab → Integrations ▸ Connectors / MCP servers.
const SEC_H = "text-[11px] uppercase tracking-[0.05em] text-faint font-semibold";
const CARD = "rounded-xl2 border border-line bg-panel";
const BTN_BORDERED =
  "text-[12.5px] px-3 py-1.5 rounded-lg border border-line bg-paper hover:border-lineStrong shrink-0";
const BTN_ACCENT = "text-[12.5px] px-3 py-1.5 rounded-lg bg-accent text-white shrink-0 disabled:opacity-50";
const BTN_DANGER = "text-[12.5px] text-danger/80 hover:text-danger shrink-0";

/** Two-letter initials for a chip/avatar (first+last word, else first two chars). */
function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

const EXAMPLE = `{
  "filesystem": {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"],
    "enabled": true
  }
}`;

// -- Configure Models tab (UX-021: the shared provider gallery + key form) ----
// Settings ▸ Models reuses onboarding §39's ProviderCards/ProviderForm so the two
// surfaces can't drift. Settings-only extras: per-card "used Nh ago", a "Remove
// key…" affordance, the global composer-picker card (gallery view), and the
// per-provider ModelChecklist / read-only model preview (form view).
// 云端 BYOK 密钥管理卡：只列「用户自己配置的」密钥（source === "store"）。
// 服务器内置（env）的 provider 删除个人配置后依然可用、依然显示已连接——那是
// 服务器 key 在兜底，不属于本卡管理范围，单独在下方说明。每行提供
// 测试（用已存密钥做只读校验，结果就地显示）/ 更换 Key / 删除。
function ConfiguredKeysCard({
  ps,
  onChanged,
}: {
  ps: ProviderSetupState;
  onChanged: () => void;
}) {
  const configured = ps.providers.filter(
    (p) => p.configured && p.needs_key && p.source === "store",
  );
  const serverProvided = ps.providers.filter(
    (p) => p.configured && p.needs_key && p.source === "env",
  );
  const [results, setResults] = useState<Record<string, { state: "testing" | "ok" | "error"; msg?: string }>>({});
  if (configured.length === 0 && serverProvided.length === 0) return null;
  const test = async (name: string) => {
    setResults((r) => ({ ...r, [name]: { state: "testing" } }));
    try {
      const res = await verifyProvider(name, {});
      setResults((r) => ({
        ...r,
        [name]: res.ok
          ? { state: "ok" }
          : { state: "error", msg: res.error ? `测试失败：${res.error}` : "测试失败，请检查 API Key" },
      }));
    } catch {
      setResults((r) => ({ ...r, [name]: { state: "error", msg: "无法连接服务器" } }));
    }
  };
  const remove = async (p: ProviderInfo) => {
    if (!window.confirm(`确定删除 ${p.title} 的 API Key 吗？删除后该 Provider 恢复为未配置。`)) return;
    await removeProvider(p.name).catch(() => {});
    await ps.refreshProviders();
    onChanged();
  };
  return (
    <div className="mb-6" data-testid="configured-keys">
      {configured.length > 0 && (
        <>
          <div className={SEC_H + " mb-1.5"}>已配置的密钥</div>
          <div className="rounded-xl2 border border-line bg-panel divide-y divide-line">
            {configured.map((p) => {
              const result = results[p.name];
              return (
                <div key={p.name} className="flex items-center gap-3 px-3.5 py-3">
                  <ProviderMark name={p.name} title={p.title} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-semibold leading-tight truncate">{p.title}</span>
                    <span className="block text-[11.5px] text-faint truncate">
                      {p.key_set_at ? `密钥配置于 ${p.key_set_at}` : "已配置"}
                      {p.last_used_at ? ` · 最近使用 ${relTime(p.last_used_at)}` : ""}
                    </span>
                  </span>
                  {result?.state === "ok" ? (
                    <span className="text-[12px] font-medium text-ok shrink-0" data-testid={`key-test-ok-${p.name}`}>✓ 连接成功，密钥可用</span>
                  ) : result?.state === "testing" ? (
                    <span className="text-[12px] text-muted shrink-0">测试中…</span>
                  ) : result?.state === "error" ? (
                    <span className="text-[12px] text-warnInk truncate max-w-[40%] shrink-0" data-testid={`key-test-error-${p.name}`}>{result.msg}</span>
                  ) : null}
                  <button
                    className="text-[12.5px] px-3 py-1.5 rounded-lg border border-line bg-paper hover:border-lineStrong shrink-0"
                    data-testid={`key-test-${p.name}`}
                    disabled={result?.state === "testing"}
                    onClick={() => test(p.name)}
                  >
                    测试
                  </button>
                  <button
                    className="text-[12.5px] px-3 py-1.5 rounded-lg border border-line bg-paper hover:border-lineStrong shrink-0"
                    data-testid={`key-edit-${p.name}`}
                    onClick={() => ps.openProvider(p.name)}
                  >
                    更换 Key
                  </button>
                  <button
                    className="text-[12.5px] px-3 py-1.5 rounded-lg text-danger/80 hover:text-danger hover:underline underline-offset-2 shrink-0"
                    data-testid={`key-remove-${p.name}`}
                    onClick={() => remove(p)}
                  >
                    删除
                  </button>
                </div>
              );
            })}
          </div>
        </>
      )}
      {serverProvided.length > 0 && (
        <p className="text-[12px] text-muted mt-2 leading-relaxed" data-testid="server-provided-note">
          {serverProvided.map((p) => p.title).join("、")}
          {" "}由服务器内置密钥提供，无需配置即可使用；配置你自己的 API Key 后会优先使用你的。
        </p>
      )}
    </div>
  );
}

export function ModelsTab() {
  const alphaMode = isAlpha();
  const [settings, setSettings] = useState<ModelSettings | null>(null);
  // 云端 BYOK：/v1/settings 被 403，默认模型从 health 读（set_default_model 后即时变化）。
  const [alphaDefault, setAlphaDefault] = useState("");
  const refreshSettings = () => {
    if (alphaMode) {
      getHealth().then((h) => setAlphaDefault(h.model)).catch(() => {});
      return;
    }
    getSettings().then(setSettings).catch(() => setSettings(null));
  };
  const ps = useProviderSetup({ onSaved: refreshSettings });
  useEffect(() => {
    refreshSettings();
  }, []);

  if (!alphaMode && !settings) return <div className="text-[13px] text-muted">正在加载…</div>;

  const info = ps.info;
  const knownNames = ps.providers.map((p) => p.name);

  if (ps.sel === null) {
    return (
      <div>
        {alphaMode ? (
          <>
            <ConfiguredKeysCard ps={ps} onChanged={refreshSettings} />
            <ProviderCards
              ps={{ ...ps, ordered: ps.ordered.filter((p) => CLOUD_PROVIDERS.has(p.name) && !p.configured) }}
              tp="set"
              gridClass="grid grid-cols-2 xl:grid-cols-3 gap-2.5"
            />
            <AlphaDefaultModelCard providers={ps.providers} current={alphaDefault} onChanged={refreshSettings} />
          </>
        ) : (
          <>
            <ProviderCards ps={ps} tp="set" gridClass="grid grid-cols-2 xl:grid-cols-3 gap-2.5" lastUsed />
            {/* 到达这里时 loading gate 已保证 settings 非 null。 */}
            <ComposerPickerCard settings={settings!} providers={ps.providers} onChanged={refreshSettings} />
          </>
        )}
      </div>
    );
  }

  if (alphaMode) {
    // 云端：key 表单照常；模型勾选走桌面 /v1/settings/models/*（被 403），默认
    // 模型由 gallery 视图的「默认模型」卡片写入，建议模型只读展示。
    return (
      <div>
        <ProviderForm
          ps={ps}
          tp="set"
          footer={
            ps.credentialed ? (
              <button
                className="text-[12.5px] text-danger/80 hover:text-danger hover:underline underline-offset-2"
                data-testid="set-remove-key"
                onClick={() => {
                  if (window.confirm(`确定删除 ${info?.title} 的 API Key 吗？删除后该 Provider 恢复为未配置。`)) ps.removeKey();
                }}
              >
                删除密钥…
              </button>
            ) : null
          }
        />
        {(info?.suggested_models?.length || 0) > 0 && (
          <div className="mt-6" data-testid="model-preview">
            <div className={SEC_H + " mb-1.5"}>包含的模型</div>
            <p className="text-[12px] text-muted mb-2.5 leading-relaxed">
              保存 API Key 后，可在「默认模型」卡片中选择这些模型。
            </p>
            <div className="space-y-1">
              {(info?.suggested_models || []).map((m) => {
                const full = ps.sel === "openai" ? m : `${ps.sel}:${m}`;
                return (
                  <div
                    key={m}
                    className="px-2.5 py-1.5 rounded-lg border border-line bg-paper text-[13px] text-muted"
                    title={full}
                  >
                    {m}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (!settings) return <div className="text-[13px] text-muted">正在加载…</div>;

  return (
    <div>
      <ProviderForm
        ps={ps}
        tp="set"
        footer={
          ps.credentialed ? (
            <button
              className="text-[12.5px] text-danger/80 hover:text-danger hover:underline underline-offset-2"
              data-testid="set-remove-key"
              onClick={() => {
                if (window.confirm(`确定删除 ${info?.title} 的 API Key 吗？删除后该 Provider 恢复为未配置。`)) ps.removeKey();
              }}
            >
              删除密钥…
            </button>
          ) : null
        }
      />

      {ps.sel === "openai" && settings.source === "env" && (
        <p className="text-[12px] text-muted mt-3 leading-relaxed">
          A key is set via <code>OPENAI_API_KEY</code> in this server's environment. You can override
          it above; the stored key is used only when the environment variable is absent.
        </p>
      )}

      {info?.configured ? (
        <div className="mt-6">
          <div className={SEC_H + " mb-1.5"}>模型</div>
          <p className="text-[12px] text-muted mb-2.5 leading-relaxed">
            Ticked models show in the composer's picker; the black badge marks the default for new
            sessions.
          </p>
          <ModelChecklist
            provider={ps.sel}
            knownProviders={knownNames}
            suggested={info?.suggested_models || []}
            curated={settings.models}
            defaultModel={settings.model}
            labels={settings.model_labels}
            onChanged={(next) => setSettings((s) => (s ? { ...s, models: next.models, model: next.model } : s))}
          />
        </div>
      ) : (
        // Unconfigured providers still show their curated models as a read-only preview — what a
        // key unlocks is part of deciding to get one at all (owner ask, 2026-07-04).
        (info?.suggested_models?.length || 0) > 0 && (
          <div className="mt-6" data-testid="model-preview">
            <div className={SEC_H + " mb-1.5"}>包含的模型</div>
            <p className="text-[12px] text-muted mb-2.5 leading-relaxed">
              Curated, agent-capable models this provider serves — add your key above to enable them.
            </p>
            <div className="space-y-1">
              {(info?.suggested_models || []).map((m) => {
                const full = ps.sel === "openai" ? m : `${ps.sel}:${m}`;
                return (
                  <div
                    key={m}
                    className="px-2.5 py-1.5 rounded-lg border border-line bg-paper text-[13px] text-muted"
                    title={full}
                  >
                    {settings.model_labels?.[full] || m}
                  </div>
                );
              })}
            </div>
          </div>
        )
      )}
    </div>
  );
}

// The gallery view's "In the composer's picker" card: every curated model across providers,
// with its provider tag. Unticking removes it from the picker; adding happens from a
// provider's card (the ModelChecklist there has the suggested list + free-type add).
function ComposerPickerCard({
  settings,
  providers,
  onChanged,
}: {
  settings: ModelSettings;
  providers: ProviderInfo[];
  onChanged: () => void;
}) {
  const names = providers.map((p) => p.name);
  const provOf = (id: string) => {
    const i = id.indexOf(":");
    return i > 0 && names.includes(id.slice(0, i)) ? id.slice(0, i) : "openai";
  };
  const tag = (id: string) => {
    const p = providers.find((x) => x.name === provOf(id));
    return (p?.title || provOf(id)).split(" (")[0];
  };
  return (
    <div className="mt-6" data-testid="composer-picker">
      <div className={SEC_H + " mb-1.5"}>输入框模型选择器</div>
      <p className="text-[12px] text-muted mb-2.5 leading-relaxed">
        The models offered when starting a session; the black badge marks the default. Add more
        from a provider's card above.
      </p>
      <div className="mlist">
        {settings.models.map((id) => {
          const isDefault = id === settings.model;
          return (
            <div className="mlist-row" key={id}>
              <label className="mlist-main">
                <input
                  type="checkbox"
                  checked
                  disabled={isDefault}
                  title={isDefault ? "The default model is always shown — make another model default first" : "Remove from the picker"}
                  onChange={() => removeModel(id).then((r) => r.ok && onChanged())}
                />
                <span className="mlist-name" title={id}>
                  {settings.model_labels?.[id] || id}
                </span>
              </label>
              <span className="text-[11px] text-faint mr-2 shrink-0">{tag(id)}</span>
              {isDefault ? (
                <span className="mlist-default">默认</span>
              ) : (
                <button className="mlist-make" onClick={() => setDefaultModel(id).then(() => onChanged())}>
                  Make default
                </button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// 云端 BYOK 的默认模型卡片：/v1/settings/models/* 是桌面接口（alpha 403），
// 云端直接 POST /v1/settings/default-model。选项来自已配置 provider 的建议
// 模型，也允许自由输入（自定义 base_url 的兼容端点模型名）。
function AlphaDefaultModelCard({
  providers,
  current,
  onChanged,
}: {
  providers: ProviderInfo[];
  current: string;
  onChanged: () => void;
}) {
  const [value, setValue] = useState(current);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => setValue(current), [current]);
  const options = byokModelsFromProviders(providers);
  const save = async () => {
    const model = value.trim();
    if (!model || busy) return;
    setBusy(true);
    setError("");
    try {
      const r = await setDefaultModel(model);
      if (r.ok) onChanged();
      else setError(r.error || "保存失败");
    } catch {
      setError("保存失败");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mt-6" data-testid="alpha-default-model">
      <div className={SEC_H + " mb-1.5"}>默认模型</div>
      <p className="text-[12px] text-muted mb-2.5 leading-relaxed">
        {isLocal()
          ? "新会话使用的模型。请先配置自己的模型服务密钥；本地版不提供共享密钥或免费模型额度。"
          : "新会话使用的模型。配置好自己的 API Key 后可切换到对应模型；不配置则继续使用服务器提供的默认模型。"}
      </p>
      <div className="flex gap-2 items-center">
        <input
          className="flex-1 min-w-0 px-3 py-2 rounded-lg border border-line bg-paper text-[13px] text-ink outline-none focus:border-accent"
          list="byok-models"
          value={value}
          placeholder="例如 deepseek:deepseek-chat"
          onChange={(e) => setValue(e.target.value)}
        />
        <datalist id="byok-models">
          {options.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
        <button
          className="text-[12.5px] px-3 py-2 rounded-lg bg-accent text-white shrink-0 disabled:opacity-40"
          disabled={busy || !value.trim() || value.trim() === current}
          onClick={save}
        >
          保存
        </button>
      </div>
      {error ? <p className="text-[12px] text-danger mt-2">{error}</p> : null}
    </div>
  );
}

// Curated OAuth quick-adds: remote MCP servers with browser sign-in (OAuth 2.1 + DCR) —
// no keys to paste, tokens stay in the local secret store. First: Granola.
const MCP_PRESETS: { name: string; label: string; blurb: string; config: Record<string, any> }[] = [
  {
    name: "granola",
    label: "Granola",
    blurb: "Meeting notes & transcripts — sign in with your Granola account.",
    config: { type: "http", url: "https://mcp.granola.ai/mcp", auth: "oauth" },
  },
];

export function McpTab() {
  const [servers, setServers] = useState<McpServer[]>([]);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => getMcpServers().then(setServers).catch(() => setServers([]));
  useEffect(() => {
    refresh();
  }, []);

  // While a browser sign-in is in flight, poll so the row flips to connected (or
  // surfaces the error) without the user having to touch anything.
  const authorizing = servers.some((s) => s.status === "authorizing");
  useEffect(() => {
    if (!authorizing) return;
    const t = window.setInterval(refresh, 2000);
    return () => window.clearInterval(t);
  }, [authorizing]);

  const toggle = async (s: McpServer) => {
    await patchMcpServer(s.name, { enabled: !s.enabled });
    refresh();
  };
  const remove = async (s: McpServer) => {
    await deleteMcpServer(s.name);
    refresh();
  };

  return (
    <div className="space-y-3">
      <p className="text-[12.5px] text-muted leading-relaxed">
        External tool servers (stdio or HTTP), shared across all agents. Enabled servers' tools are
        permission-gated. Changes apply to new sessions —{" "}
        <button
          className="text-accent font-medium hover:underline"
          onClick={() => reloadMcp().then(refresh)}
        >
          reload now
        </button>
        .
      </p>

      {servers.length === 0 && !adding ? (
        <div className={CARD + " p-4 text-[13px] text-muted"}>
          No MCP servers configured.{" "}
          <button className="text-accent font-medium" onClick={() => setAdding(true)}>
            Add a server
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          {servers.map((s) => (
            <McpRow
              key={s.name}
              server={s}
              onToggle={() => toggle(s)}
              onRemove={() => remove(s)}
              onRefresh={refresh}
            />
          ))}
        </div>
      )}

      {/* One-click OAuth presets not yet configured. */}
      {MCP_PRESETS.filter((p) => !servers.some((s) => s.name === p.name)).map((p) => (
        <div key={p.name} className={CARD + " p-3.5 flex items-center gap-3"} data-testid={`mcp-preset-${p.name}`}>
          <div className="flex-1 min-w-0">
            <div className="text-[14px] font-medium">{p.label}</div>
            <div className="text-[11.5px] text-faint">{p.blurb}</div>
          </div>
          <button
            className={BTN_ACCENT}
            onClick={async () => {
              await addMcpServer(p.name, p.config);
              await connectMcp(p.name); // opens the browser sign-in right away
              refresh();
            }}
          >
            Connect
          </button>
        </div>
      ))}

      {adding ? (
        <AddForm
          onCancel={() => {
            setAdding(false);
            setError(null);
          }}
          onError={setError}
          onAdded={() => {
            setAdding(false);
            setError(null);
            refresh();
          }}
        />
      ) : servers.length > 0 ? (
        <button className={BTN_ACCENT} onClick={() => setAdding(true)}>
          + Add server
        </button>
      ) : null}
      {error && <div className="text-[12.5px] text-danger">{error}</div>}
    </div>
  );
}

function McpRow({
  server,
  onToggle,
  onRemove,
  onRefresh,
}: {
  server: McpServer;
  onToggle: () => void;
  onRemove: () => void;
  onRefresh: () => void;
}) {
  const [tools, setTools] = useState<{ name: string; description: string }[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [toolErr, setToolErr] = useState<string | null>(null);

  const isOauth = server.auth === "oauth";
  const authorizing = server.status === "authorizing";
  const signIn = async () => {
    await connectMcp(server.name); // browser opens; the tab's poll flips the status
    onRefresh();
  };
  const signOut = async () => {
    await signoutMcp(server.name);
    onRefresh();
  };

  const loadTools = async () => {
    if (tools) {
      setTools(null);
      return;
    }
    setBusy(true);
    setToolErr(null);
    const res = await getMcpTools(server.name);
    setBusy(false);
    if (res.ok) setTools(res.tools);
    else setToolErr(res.error || "failed to connect");
  };

  return (
    <div className={CARD + " p-3.5"}>
      <div className="flex items-center gap-3">
        <Toggle checked={server.enabled} onChange={onToggle} title="启用此服务" />
        <div className="flex-1 min-w-0">
          <div className="text-[14px] font-medium">{server.name}</div>
          <div className="text-[11.5px] text-faint">
            {server.transport} · {authorizing ? "signing in…" : server.status.replace("_", " ")}
            {server.tool_count != null ? ` · ${server.tool_count} tools` : ""}
            {server.requires_approval ? " · asks" : ""}
            {isOauth ? " · oauth" : ""}
          </div>
        </div>
        {isOauth &&
          (server.status === "needs_auth" ? (
            <button className={BTN_ACCENT} onClick={signIn} data-testid={`mcp-signin-${server.name}`}>
              Sign in
            </button>
          ) : authorizing ? (
            <span className="text-[12px] text-muted shrink-0">等待浏览器确认…</span>
          ) : server.status === "connected" ? (
            <button
              className="text-[12px] text-muted hover:text-ink shrink-0"
              onClick={signOut}
              data-testid={`mcp-signout-${server.name}`}
            >
              sign out
            </button>
          ) : null)}
        <button
          className="text-[12px] text-muted hover:text-ink shrink-0"
          onClick={loadTools}
          disabled={busy}
        >
          {busy ? "…" : tools ? "hide tools" : "tools"}
        </button>
        <button className={BTN_DANGER} onClick={onRemove}>
          remove
        </button>
      </div>
      {server.last_error && server.status !== "connected" && (
        <div className="text-[12.5px] text-danger mt-1.5">{server.last_error}</div>
      )}
      {toolErr && <div className="text-[12.5px] text-danger mt-1.5">{toolErr}</div>}
      {tools && (
        <div className="mt-2.5 pt-2.5 border-t border-line flex flex-wrap gap-1.5">
          {tools.length === 0 && <div className="text-[12px] text-faint">暂无工具。</div>}
          {tools.map((t) => (
            <span
              key={t.name}
              title={t.description}
              className="font-mono text-[11.5px] px-1.5 py-0.5 rounded-md bg-paper border border-line"
            >
              {t.name}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function AddForm({
  onCancel,
  onAdded,
  onError,
}: {
  onCancel: () => void;
  onAdded: () => void;
  onError: (e: string | null) => void;
}) {
  const [text, setText] = useState(EXAMPLE);

  const save = async () => {
    onError(null);
    let parsed: any;
    try {
      parsed = JSON.parse(text);
    } catch (e: any) {
      onError("Invalid JSON: " + e.message);
      return;
    }
    // Accept either {mcpServers:{...}}, {name:{...}}, or a single bare config.
    const map = parsed.mcpServers || parsed;
    const entries =
      map && typeof map === "object" && !map.command && !map.url
        ? Object.entries(map)
        : null;
    if (!entries || entries.length === 0) {
      onError('Paste a `{ "<name>": { … } }` object (or a full mcpServers block).');
      return;
    }
    for (const [name, config] of entries) {
      await addMcpServer(name, config as Record<string, any>);
    }
    onAdded();
  };

  return (
    <div className="space-y-2">
      <div className="text-[12.5px] text-muted">粘贴服务 JSON（名称 → 配置）：</div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        spellCheck={false}
        rows={9}
        className="w-full font-mono text-[12px] px-3 py-2.5 rounded-lg border border-line bg-paper text-ink outline-none focus:border-accent resize-y"
      />
      <div className="flex items-center gap-3">
        <button className={BTN_ACCENT} onClick={save}>
          Add
        </button>
        <button className="text-[12.5px] text-muted hover:text-ink" onClick={onCancel}>
          cancel
        </button>
      </div>
    </div>
  );
}

// -- Connectors ---------------------------------------------------------------
// The Connectors tab body moved to connectors/ConnectorsSection.tsx (UX-DECISIONS
// §21: connected-first list + per-connector detail subpages). This file keeps the
// shared building blocks the detail pages reuse: ConnectSetup, ConnectorTools, and
// the two-way blocks (Allowlist/Unauthorized/ListeningSessions).

// Parked messages from senders not on the allow-list (§19). The gateway keeps what they said
// instead of dropping it, so first contact is one step: Allow & deliver replays the original
// message through the normal inbound path — no "message the bot again".
// With `teamId` (the Slack-workspaces page) only that workspace's parked messages show;
// resolving routes the allow to the right workspace server-side (the item carries its team).
export function UnauthorizedBlock({
  c,
  onChanged,
  teamId,
}: {
  c: Connector;
  onChanged: () => void;
  teamId?: string;
}) {
  const items = (c.unauthorized ?? []).filter(
    (m) => teamId === undefined || m.team_id === teamId,
  );
  if (items.length === 0) return null;
  const act = async (id: string, action: "dismiss" | "allow" | "allow_deliver") => {
    await resolveUnauthorized(c.name, id, action);
    onChanged();
  };
  return (
    <div
      className="border-t border-line px-3.5 py-3"
      data-testid={teamId ? `unauthorized-${c.name}-${teamId}` : `unauthorized-${c.name}`}
    >
      <div className={SEC_H + " mb-2"}>
        Messages from senders you haven't allowed · {items.length}
      </div>
      <div className="space-y-2">
        {items.map((m) => (
          <div key={m.id} className="rounded-xl border border-line bg-paper p-2.5">
            <div className="flex items-center gap-2 text-[12px] text-muted">
              <span className="font-medium text-ink">{m.user_name || m.user_id}</span>
              <span>in {m.chat_name || m.chat_id}</span>
              <span className="ml-auto shrink-0">{relTime(m.ts) || ""}</span>
            </div>
            <div className="text-[12.5px] mt-1 break-words">{m.text}</div>
            <div className="flex items-center gap-1.5 mt-2">
              <button
                className="text-[11.5px] px-2 py-1 rounded-md bg-accent text-white"
                data-testid={`parked-allow-deliver-${m.id}`}
                title="将发送者加入允许列表并立即投递此消息"
                onClick={() => act(m.id, "allow_deliver")}
              >
                Allow & deliver
              </button>
              <button
                className={BTN_BORDERED}
                data-testid={`parked-allow-${m.id}`}
                title="将发送者加入允许列表，但丢弃此消息"
                onClick={() => act(m.id, "allow")}
              >
                Allow only
              </button>
              <button
                className="text-[11.5px] px-2 py-1 rounded-md text-faint hover:text-danger"
                data-testid={`parked-dismiss-${m.id}`}
                title="丢弃此消息"
                onClick={() => act(m.id, "dismiss")}
              >
                Dismiss
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// Which sessions listen to this connector's channels — the per-connector cut of the global
// Channel-subscriptions table (Integrations ▸ Messaging routing). Subscribing happens from a
// session's Sources ▸ Channels panel; here the owner can see and revoke.
export function ListeningSessionsBlock({ c }: { c: Connector }) {
  const [subs, setSubs] = useState<Subscription[] | null>(null);
  const load = () => getSubscriptions().then(setSubs).catch(() => setSubs([]));
  useEffect(() => {
    load();
  }, [c.name]);
  const platformOf = (channel: string) =>
    channel.includes(":") ? channel.split(":")[0] : "slack";
  const mine = (subs ?? []).filter((s) => platformOf(s.channel) === c.name);
  return (
    <div className="border-t border-line px-3.5 py-3" data-testid={`listening-${c.name}`}>
      <div className={SEC_H + " mb-2"}>Sessions listening to {c.title} channels · {mine.length}</div>
      {mine.length === 0 ? (
        <div className="text-[12px] text-faint">
          None yet — open a session's Sources ▸ Channels to subscribe it to a channel.
        </div>
      ) : (
        <div className="space-y-1.5">
          {mine.map((s) => (
            <div className="flex items-center gap-2 text-[12.5px]" key={s.session_id + s.channel}>
              <span className="min-w-0 truncate" title={s.session_id}>
                {s.session_title || s.session_id}
                {s.agent ? <span className="text-faint"> · {s.agent}</span> : null}
              </span>
              <span className="text-muted shrink-0" title={s.channel}>
                ← {s.channel_name ? `#${s.channel_name}` : s.channel}
              </span>
              <button
                className="ml-auto text-faint hover:text-danger shrink-0"
                title="取消此对话的订阅"
                onClick={async () => {
                  await unsubscribeChannel(s.session_id, s.channel);
                  load();
                }}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Who may message this two-way bot. Recent senders surface here once they DM/mention the bot, so you
// can Allow them; allowed users are chips you can remove. (Was orphaned in the super-agent view.)
// With `teamId` (the Slack-workspaces page) the list is that WORKSPACE's — ids are
// workspace-scoped, so allow/remove target `slack:team:<id>` and recents filter to the team.
export function AllowlistBlock({
  c,
  onChanged,
  teamId,
  allowed,
  allowedNames,
}: {
  c: Connector;
  onChanged: () => void;
  teamId?: string;
  allowed?: string[];
  allowedNames?: Record<string, string | null>;
}) {
  const allowedUsers = allowed ?? c.allowed_users;
  const names = allowedNames ?? c.allowed_user_names;
  const recent = (c.recent ?? []).filter(
    (r) => teamId === undefined || r.team_id === teamId,
  );
  const unknownRecent = recent.filter((r) => !r.authorized);

  return (
    <div className="border-t border-line px-3.5 py-3 grid grid-cols-2 gap-5">
      <div>
        <div className={SEC_H + " mb-2"}>允许发送消息</div>
        <div className="flex flex-wrap gap-1.5">
          {allowedUsers.length === 0 && (
            <span className="text-[12px] text-faint">暂无成员，可允许最近的发送者 →</span>
          )}
          {allowedUsers.map((u) => (
            <span
              key={u}
              className="inline-flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-full bg-paper border border-line text-[12px]"
              title={`id ${u}`}
            >
              <span className="w-4 h-4 rounded-full bg-accentSoft text-accent grid place-items-center text-[9px] font-bold">
                {initials(names?.[u] || u)}
              </span>
              {names?.[u] || u}
              <button
                className="w-4 h-4 grid place-items-center text-faint hover:text-danger"
                title="移除"
                onClick={async () => {
                  await disallowUser(c.name, u, teamId);
                  onChanged();
                }}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      </div>
      <div>
        <div className={SEC_H + " mb-2"}>最近发送者</div>
        {unknownRecent.length === 0 ? (
          <div className="text-[12px] text-faint">暂无记录，向机器人发送一次消息后会显示在此处。</div>
        ) : (
          <div className="space-y-1.5">
            {unknownRecent.map((r) => (
              <div className="flex items-center gap-2 text-[12.5px]" key={r.user_id}>
                <span className="w-5 h-5 rounded-full bg-paper border border-line grid place-items-center text-[9px] font-bold text-muted shrink-0">
                  {initials(r.user_name || "?")}
                </span>
                <span className="min-w-0 truncate" title={`id ${r.user_id}`}>
                  {r.user_name || "unknown"} <span className="text-faint">· {r.chat_type}</span>
                </span>
                <button
                  className="ml-auto text-[11.5px] px-2 py-0.5 rounded-md bg-accent text-white shrink-0"
                  onClick={async () => {
                    await allowUser(c.name, r.user_id, teamId);
                    onChanged();
                  }}
                >
                  Allow
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export function ConnectorTools({ c, onChanged }: { c: Connector; onChanged: () => void }) {
  const toggle = async (toolName: string, enabled: boolean) => {
    await updateConnectorTools(c.name, { [toolName]: enabled });
    onChanged();
  };
  if (!c.tools?.length)
    return (
      <div className="border-t border-line px-3.5 py-3 text-[12.5px] text-muted">
        No tools for this connector yet.
      </div>
    );
  return (
    <div className="border-t border-line px-3.5 py-3">
      <div className={SEC_H + " mb-2"}>向 OpenCareer 开放的工具</div>
      <div className="space-y-1.5">
        {c.tools.map((tool) => (
          <label
            className="flex items-start gap-2.5 p-2 rounded-lg border border-line bg-paper"
            key={tool.name}
          >
            <input
              type="checkbox"
              className="mt-0.5 shrink-0"
              checked={tool.enabled}
              onChange={(e) => toggle(tool.name, e.target.checked)}
            />
            <span className="min-w-0">
              <span className="block text-[13px]">{tool.label}</span>
              <span className="block text-[11.5px] text-faint">
                {tool.name} · {tool.kind} · asks approval
              </span>
              <span className="block text-[11.5px] text-faint">{tool.description}</span>
            </span>
          </label>
        ))}
      </div>
    </div>
  );
}

// Exported: also hosted inside the SourcesDrawer's connect-in-context child panel, so a
// recommended connector can be connected without leaving the session (owner ask, 2026-07-03).
export function ConnectSetup({
  c,
  cloud,
  onConnected,
  manualOnly = false,
}: {
  c: Connector;
  cloud: CloudStatus | null;
  onConnected: () => void;
  // The add-modal's Manual pane: the one-click button lives on the sibling
  // pill, so don't render the managed block again here.
  manualOnly?: boolean;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState(false); // managed flow: browser is open
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    const res = await connectConnector(c.name, values);
    setBusy(false);
    if (res.ok) onConnected();
    else setError(res.error || "could not connect");
  };

  const oneClick = async () => {
    setError(null);
    const res = await connectManaged(c.name);
    // Completion arrives via the tab's poll: the broker form-POSTs the profile
    // to the sidecar, the connector flips to connected, this card closes itself.
    if (res.ok) setWaiting(true);
    else setError(res.error || "could not start managed connect");
  };

  const mcpOneClick = async () => {
    setError(null);
    const res = await connectMcpBacked(c.name);
    // Completion likewise arrives via the poll — the sidecar flips the connector
    // to connected once the local OAuth flow lands.
    if (res.ok) setWaiting(true);
    else setError(res.error || "could not start the connect");
  };

  return (
    <div className="border-t border-line px-3.5 py-3 space-y-3">
      {c.mcp && !manualOnly && (
        /* MCP-backed one-click needs no cloud sign-in — the OAuth flow is local. */
        <div className="space-y-2" data-testid="mcp-connect">
          <button className={BTN_ACCENT} onClick={mcpOneClick} disabled={waiting}>
            {waiting ? "Check your browser…" : `Connect ${c.title} with one click`}
          </button>
          {c.fields.length > 0 && (
            <div className="text-[11.5px] text-faint">或手动连接：</div>
          )}
        </div>
      )}
      {c.managed && !c.mcp && !manualOnly && (
        <div className="space-y-2" data-testid="managed-connect">
          {c.managed_paused ? (
            // One-click temporarily off (e.g. Google pending CASA verification):
            // a visibly-parked button, and the manual path below stays fully live.
            <>
              <button className={BTN_ACCENT + " opacity-50"} disabled data-testid="managed-coming-soon">
                {`Connect ${c.title} with one click`}
                <span className="ml-2 text-[11px] font-medium px-1.5 py-0.5 rounded-full bg-white/25">
                  Coming soon
                </span>
              </button>
              <div className="text-[11.5px] text-faint">
                One-click sign-in is coming soon — connect manually below for now:
              </div>
            </>
          ) : cloud?.signed_in ? (
            <button className={BTN_ACCENT} onClick={oneClick} disabled={waiting}>
              {waiting ? "Check your browser…" : `Connect ${c.title} with one click`}
            </button>
          ) : cloud ? (
            <CloudSignInInline
              blurb={`Sign-in unlocks the one-click ${c.title} connect — or connect manually below.`}
            />
          ) : (
            // Status unknown (fetch pending/failed): never show the sign-in ask to a
            // possibly-signed-in user (FB-013); the host keeps polling.
            <CloudStatusPending />
          )}
          {!c.managed_paused && cloud?.signed_in && (
            <div className="text-[11.5px] text-faint">或手动连接：</div>
          )}
        </div>
      )}
      {c.instructions.length > 0 && (
        <ol className="list-decimal pl-4 text-[12.5px] text-muted leading-relaxed space-y-1">
          {c.instructions.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ol>
      )}
      {c.fields.map((f) => (
        <label className="conn-field" key={f.key}>
          <span className="conn-field-label">
            {f.label}
            {!f.required && <em> (optional)</em>}
          </span>
          <input
            type={f.secret ? "password" : "text"}
            placeholder={f.placeholder}
            value={values[f.key] || ""}
            spellCheck={false}
            onChange={(e) => setValues({ ...values, [f.key]: e.target.value })}
          />
          {f.help && <span className="conn-field-help">{f.help}</span>}
        </label>
      ))}
      <div>
        <button className={BTN_ACCENT} onClick={submit} disabled={busy}>
          {busy ? "Validating…" : "Connect"}
        </button>
      </div>
      {error && <div className="text-[12.5px] text-danger">{error}</div>}
    </div>
  );
}
