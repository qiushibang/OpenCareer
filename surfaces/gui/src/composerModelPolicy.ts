export const AIDEN_MODEL = "aiden:deepseek-v4-flash";

/** 云端界面精选的 provider：国内求职用户可直接上手的主流选择。其余桌面/本地
 *  provider（Ollama、Aiden、Bedrock、Vertex 等）不在云端展示。 */
export const CLOUD_PROVIDERS = new Set([
  "deepseek",
  "kimi",
  "qwen",
  "zai",
  "minimax",
  "openai",
  "anthropic",
  "gemini",
  "openrouter",
]);

/** BYOK：从已配置 provider 的建议模型推导 composer 可选列表（openai 裸名，其余带前缀）。 */
export function byokModelsFromProviders(
  providers: { name: string; configured: boolean; suggested_models: string[] }[],
): string[] {
  const out: string[] = [];
  for (const p of providers) {
    if (!p.configured) continue;
    for (const m of p.suggested_models || []) {
      const id = p.name === "openai" ? m : `${p.name}:${m}`;
      if (!out.includes(id)) out.push(id);
    }
  }
  return out;
}

export function composerModelPolicy(
  configuredModels: string[],
  alpha = false,
  backendModel = "",
  localProviders?: string[],
) {
  // 云端 Alpha：模型来自两端——health 的 backendModel（未配置 BYOK 时的服务器
  // 默认）和用户已配置 provider 推导的模型列表（BYOK）。绝不能回退到桌面专用
  // 的 Aiden provider；/v1/settings 仍被 403，列表不来自 settings。
  if (alpha) {
    const list = backendModel
      ? [backendModel, ...configuredModels.filter((m) => m !== backendModel)]
      : configuredModels;
    const selected = backendModel || list[0] || "";
    const provider = selected.includes(":") ? selected.split(":", 1)[0] : "openai";
    return {
      model: selected,
      models: list,
      // Standalone has no server-provided model credentials. A name from health
      // is only a default, not evidence that this provider has been configured.
      modelReady: Boolean(selected) && (localProviders === undefined || localProviders.includes(provider)),
    };
  }
  const modelReady = configuredModels.includes(AIDEN_MODEL);
  return {
    model: AIDEN_MODEL,
    models: modelReady ? [AIDEN_MODEL] : [],
    modelReady,
  };
}
