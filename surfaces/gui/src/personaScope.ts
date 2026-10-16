// A persona is "project-scoped" only when it's code-family: an explicit directory the user
// picks, sessions grouped by project in the sidebar. Everything else (knowledge, chat) runs on
// a transparent per-conversation scratch dir, with real folders added as roots when needed —
// no folder gate, ever. (The old workspace enum — git/project/deliverable/none — collapsed
// into family; owner decision 2026-07-03, UX-DECISIONS §16.)
export function isProjectScoped(p?: { workspace?: string; family?: string }): boolean {
  return p?.family === "code";
}

const PERSONA_NAMES: Record<string, string> = {
  career: "职业 Agent",
  cowork: "通用 Agent",
  code: "编程 Agent",
  ops: "运维 Agent",
  chat: "聊天 Agent",
};

const PERSONA_ORDER = ["career", "cowork", "code", "ops", "chat"];

const PERSONA_TAGLINES: Record<string, string> = {
  career: "发现岗位、分析 JD、准备申请",
  cowork: "研究、分析并生成交付物",
  code: "处理代码仓库任务",
  ops: "处理故障与运行手册",
  chat: "日常对话与问答",
};

export function personaDisplayName(name?: string, id?: string): string {
  if (id && PERSONA_NAMES[id]) return PERSONA_NAMES[id];
  return (name || id || "").trim();
}

export function personaDisplayTagline(tagline?: string, id?: string): string {
  if (id && PERSONA_TAGLINES[id]) return PERSONA_TAGLINES[id];
  return (tagline || "").trim();
}

export function sortPersonasForNewSession<T extends { id: string }>(
  personas: T[],
): T[] {
  return personas
    .map((persona, index) => ({ persona, index }))
    .sort((left, right) => {
      const leftRank = PERSONA_ORDER.indexOf(left.persona.id);
      const rightRank = PERSONA_ORDER.indexOf(right.persona.id);
      const normalizedLeft = leftRank === -1 ? PERSONA_ORDER.length : leftRank;
      const normalizedRight = rightRank === -1 ? PERSONA_ORDER.length : rightRank;
      return normalizedLeft - normalizedRight || left.index - right.index;
    })
    .map(({ persona }) => persona);
}

// Persona naming: the product is "OpenWorker"; the personas are a "Coworker" family — Coworker
// (general), Code Coworker, Ops Coworker. In lists/chrome we use the SHORT label (Coworker / Code /
// Ops); the persona detail page uses the FULL family name. Backend names are left untouched (the
// API + tests keep "OpenWorker" / "Ops Coworker"); this is purely the display layer.

// Short label for the sidebar + top bar: "Coworker" / "Code" / "Ops" / "Chat".
export function shortPersonaName(name?: string, id?: string): string {
  if (id && PERSONA_NAMES[id]) return PERSONA_NAMES[id];
  const n = (name || id || "").trim();
  return n.replace(/\s*coworker$/i, "").trim() || n;
}

// Full family name for the persona detail page: "Coworker" / "Code Coworker" / "Ops Coworker".
// Chat isn't a coworker — left as-is.
export function fullPersonaName(name?: string, id?: string): string {
  if (id && PERSONA_NAMES[id]) return PERSONA_NAMES[id];
  const n = (name || id || "").trim();
  if (id === "chat" || !n) return n;
  return /coworker$/i.test(n) ? n : `${n} Coworker`;
}
