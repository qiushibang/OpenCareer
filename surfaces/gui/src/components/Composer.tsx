import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { Attachment, SessionUsage } from "../types";
import { isPdfFile, readFile } from "../attach";
import {
  getSettings,
  inspectPdf,
  sessionSkills,
  stageResume,
  type SessionSkillRow,
} from "../api";
import { skillZhDescription, skillZhTitle } from "../careerSkillLabels";
import { formatTokens, totalTokens } from "../usage";
import {
  careerResumeImportDisplay,
  careerResumeImportError,
  careerResumeImportNotice,
  careerResumeImportPrompt,
} from "../careerResumeImport";
import { Dropdown, type Option } from "./Dropdown";
import { Icon } from "./Icon";
import { Toggle } from "./Toggle";
import { VoiceRecordingMeter } from "./VoiceRecordingMeter";
import {
  cancelDictation,
  getDictationLevel,
  getDictationStatus,
  isTauri,
  startDictation,
  stopDictation,
  type DictationStatus,
} from "../tauri";

// Custom reuses the reviewed tool allowlist, not unrestricted full access.
const PERMISSION_OPTIONS: Option[] = [
  { value: "custom", label: "自动审批", description: "常规求职与面试操作自动通过，重要数据写入仍需确认" },
  { value: "interactive", label: "执行前询问", description: "编辑文件和执行命令前请求确认" },
];

// No hardcoded model fallback: until the server supplies the list (a few seconds after a
// cold app boot), the picker renders a disabled "Loading models…" chip. A baked-in list
// goes stale and silently offers ids the backend never confirmed (caught 2026-07-21).

// Drop the provider prefix for display (anthropic:claude-opus-4-8 → claude-opus-4-8); full id on hover.
const shortModel = (m: string) => (m.includes(":") ? m.split(":").slice(1).join(":") : m);

// Identify an attachment by name + payload size so duplicates (e.g. the same file picked twice,
// or a prefill applied twice) collapse to one chip.
const attKey = (a: Attachment) =>
  a.kind === "text"
    ? `t:${a.name}:${a.text?.length ?? 0}`
    : `${a.kind[0]}:${a.name}:${a.data_url?.length ?? 0}`;
const mergeAttachments = (cur: Attachment[], add: Attachment[]): Attachment[] => {
  const seen = new Set(cur.map(attKey));
  return [...cur, ...add.filter((a) => !seen.has(attKey(a)))].slice(0, 8);
};

interface Props {
  mode: string;
  model: string;
  models?: string[];
  modelLabels?: Record<string, string>; // curated display names (raw id when absent)
  // The model is FIXED once the session has history (§17): the picker renders ONLY on a fresh
  // session; after the first turn the fact lives in the topbar subtitle (§22) — no
  // interactive-then-disabled control.
  running: boolean;
  connected: boolean;
  // False when the default model's provider has no key — the composer shows a "connect a model"
  // banner and routes sends to setup (preserving the draft) instead of dropping them.
  modelReady?: boolean;
  onConnectModel?: () => void;
  onConfigureVoiceInput?: () => void;
  // 模型选择器底部的「配置自定义模型」动作（云端 BYOK：跳设置 → 模型）。
  onConfigureModels?: () => void;
  onSend: (
    text: string,
    attachments?: Attachment[],
    skill?: string,
    display?: string,
  ) => void;
  // Feeds the "/" force-run popup (SKILLS-SPEC §4.1 #3): the popup lists this session's
  // effective skill menu. Absent (e.g. tests without sessions) → the popup never opens.
  sessionId?: string;
  personaId?: string;
  onInterrupt: () => void;
  onModeChange: (mode: string) => void;
  onModelChange: (model: string) => void;
  // When set (Code/Cowork), the Mode menu is shown. The folder/roots + branch controls left the
  // composer for the Session settings drawer (§22) — folder access is standing session config.
  workspace?: string;
  // Unattended / send-approvals-to-Inbox — folded into the Mode menu (§22): "who approves, and
  // when" is one mental model. Absent handler = no toggle (e.g. Chat).
  unattended?: boolean;
  onUnattendedChange?: (on: boolean) => void;
  approvalSlot?: ReactNode;
  browserVoiceSlot?: ReactNode;
  // Push text + attachments into the composer (e.g. a start-panel task card). The `nonce` makes
  // repeated identical prefills re-apply; the user can still edit before sending.
  prefill?: { text: string; attachments?: Attachment[]; nonce: number };
  // Incremented by Career surfaces to open the dedicated private resume importer.
  resumeImportNonce?: number;
  // Changes when the active conversation changes; clears any unsent draft.
  resetKey?: string;
  // Surface-specific hint shown in the empty textarea.
  placeholder?: string;
  // Per-session token usage (OPE-42) — absent/empty hides the usage chip entirely
  // (older servers, backends that don't report usage, fresh sessions).
  usage?: SessionUsage;
  // Context-window size (tokens) of the ACTIVE model, from the curated matrix;
  // undefined hides the fill meter (unverified/custom models) but keeps the counts.
  contextWindow?: number;
  // Settings toggle (default off): true shows the fill bar instead of the session total.
  contextBar?: boolean;
}

export function Composer(props: Props) {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const lastResumeImportNonce = useRef(props.resumeImportNonce ?? 0);
  // "/" force-run (SKILLS-SPEC §4.1 #3). The popup derives from the draft: it is open while
  // the text is a bare "/query" (no whitespace yet) and no skill is picked. Selecting a row
  // inserts "/name " INLINE in the box (Claude-Code style — the slash text IS the state);
  // the user keeps typing after it, and on send the prefix is stripped while the skill name
  // rides the user_message as its own field. Editing the prefix away un-picks the skill.
  const [pendingSkill, setPendingSkill] = useState<SessionSkillRow | null>(null);
  const [slashSkills, setSlashSkills] = useState<SessionSkillRow[] | null>(null);
  // 对话框下方的「技能」按钮面板：与 "/" 弹层共用会话技能数据。
  const [skillMenuOpen, setSkillMenuOpen] = useState(false);
  const skillMenuRef = useRef<HTMLDivElement | null>(null);
  const skillButtonRef = useRef<HTMLButtonElement | null>(null);
  const [slashIndex, setSlashIndex] = useState(0);
  // 挂载后输入区保持干净（无 /name 前缀，光标在徽章右侧）。用户手敲 "/"
  // 视为改用斜杠调用，解除当前徽章。
  useEffect(() => {
    if (pendingSkill && text.startsWith("/")) setPendingSkill(null);
  }, [pendingSkill, text]);
  const slashQuery =
    !pendingSkill &&
    props.sessionId &&
    text.startsWith("/") &&
    !/\s/.test(text.slice(1))
      ? text.slice(1).toLowerCase()
      : null;
  const slashMatches = (slashSkills ?? []).filter((s) =>
    s.name.toLowerCase().includes(slashQuery ?? ""),
  );
  useEffect(() => {
    // Fetch on each popup open (fresh menu); drop when closed.
    if (slashQuery === null && !skillMenuOpen) {
      setSlashSkills(null);
      setSlashIndex(0);
      return;
    }
    if (slashSkills === null && props.sessionId) {
      sessionSkills(props.sessionId, props.workspace)
        .then((all) => setSlashSkills(all.filter((s) => s.enabled)))
        .catch(() => setSlashSkills([]));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slashQuery === null, skillMenuOpen]);
  const pickSkill = (s: SessionSkillRow) => {
    setPendingSkill(s);
    setSkillMenuOpen(false);
    // Toolbar selection preserves the draft; slash autocomplete consumes its token.
    if (slashQuery !== null) setText("");
    textareaRef.current?.focus();
  };
  const clearPinnedSkill = () => {
    setPendingSkill(null);
  };
  // 技能面板的标准弹出语义：面板内部点击不关闭；点击面板与按钮以外的任何
  // 位置关闭。
  useEffect(() => {
    if (!skillMenuOpen) return;
    const onDocPointerDown = (e: PointerEvent) => {
      const target = e.target as Node | null;
      if (
        skillMenuRef.current?.contains(target) ||
        skillButtonRef.current?.contains(target)
      ) {
        return;
      }
      setSkillMenuOpen(false);
    };
    document.addEventListener("pointerdown", onDocPointerDown, true);
    return () =>
      document.removeEventListener("pointerdown", onDocPointerDown, true);
  }, [skillMenuOpen]);
  const [dragging, setDragging] = useState(false);
  const [attachMenuOpen, setAttachMenuOpen] = useState(false);
  const [dictation, setDictation] = useState<DictationStatus | null>(null);
  const [dictationLevel, setDictationLevel] = useState(0);
  const [dictationBusy, setDictationBusy] = useState<string | null>(null);
  const [dictationError, setDictationError] = useState<string | null>(null);
  const [attachNotice, setAttachNotice] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const resumeInput = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    const next = props.resumeImportNonce ?? 0;
    if (next > lastResumeImportNonce.current && props.personaId === "career") {
      resumeInput.current?.click();
    }
    lastResumeImportNonce.current = next;
  }, [props.resumeImportNonce, props.personaId]);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const noticeTimer = useRef<number | null>(null);

  // Rejected-attachment notice: visible ~8s, then clears (or on ✕).
  const showAttachNotice = (message: string) => {
    setAttachNotice(message);
    if (noticeTimer.current) window.clearTimeout(noticeTimer.current);
    noticeTimer.current = window.setTimeout(() => setAttachNotice(null), 8000);
  };

  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    const max = parseFloat(getComputedStyle(el).lineHeight || "22") * 4;
    const next = Math.min(el.scrollHeight, max);
    // 空态保留 40px 的呼吸感；一旦输入就收回单行高度，
    // 避免首字下方仍留下近一整行无意义空白。
    const min = text ? 24 : 40;
    el.style.height = `${Math.max(next, min)}px`;
    el.style.overflowY = el.scrollHeight > max ? "auto" : "hidden";
  }, [text]);

  // Clear the draft when the conversation changes, so a half-typed message / picked file doesn't
  // bleed from one session into another. Declared BEFORE the prefill effect: when both fire in
  // the same render (the Skills doorway starts a new session AND prefills it), effects run in
  // declaration order — clear first, then the prefill lands on the fresh session.
  const appliedResetKey = useRef(props.resetKey);
  useEffect(() => {
    if (props.resetKey === appliedResetKey.current) return;
    appliedResetKey.current = props.resetKey;
    setText("");
    setAttachments([]);
    setPendingSkill(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.resetKey]);

  // Apply a prefill (text + attachments) pushed from outside, then focus the composer. Applied at
  // most once per nonce (a ref guards against StrictMode/re-render double-fires), and attachments
  // are de-duplicated so the same file never lands twice.
  const appliedNonce = useRef<number>(-1);
  useEffect(() => {
    const p = props.prefill;
    if (!p || p.nonce === appliedNonce.current) return;
    appliedNonce.current = p.nonce;
    setText(p.text);
    if (p.attachments?.length) setAttachments((cur) => mergeAttachments(cur, p.attachments!));
    textareaRef.current?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [props.prefill?.nonce]);

  // Dictation is intentionally native-only: the browser/dev build remains a local server client
  // and never turns on the browser microphone or ships audio anywhere.
  useEffect(() => {
    if (!isTauri()) return;
    const refresh = (event?: Event) => {
      const supplied = (event as CustomEvent<DictationStatus> | undefined)?.detail;
      if (supplied) {
        setDictation(supplied);
        return;
      }
      void getDictationStatus().then((status) => status && setDictation(status));
    };
    refresh();
    window.addEventListener("coworker:voice-input-changed", refresh);
    return () => window.removeEventListener("coworker:voice-input-changed", refresh);
  }, []);

  useEffect(() => {
    if (!dictation?.recording) return;
    const cancelOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      void cancelDictation()
        .catch(() => undefined)
        .finally(() => {
          void getDictationStatus().then((status) => status && setDictation(status));
        });
    };
    window.addEventListener("keydown", cancelOnEscape);
    return () => window.removeEventListener("keydown", cancelOnEscape);
  }, [dictation?.recording]);

  useEffect(() => {
    if (!dictation?.recording) {
      setDictationLevel(0);
      return;
    }
    const timer = window.setInterval(() => {
      void getDictationLevel()
        .then((level) => {
          if (typeof level === "number") {
            setDictationLevel(Math.max(0, Math.min(1, level)));
          }
        })
        .catch(() => undefined);
    }, 100);
    return () => window.clearInterval(timer);
  }, [dictation?.recording]);

  const voiceReady = !!dictation?.supported && !!dictation?.model_verified && !!dictation?.test_passed;

  // Attach-time PDF thresholds (Settings → Token savings): a PDF over the user's page or
  // size limit is REJECTED with a visible notice — never attached, never silently dropped.
  // The rationale is token cost: a big PDF re-rides every turn of the conversation.
  const addFiles = async (files: FileList | File[]) => {
    const list = Array.from(files);
    let maxPages = 20;
    let maxMb = 10;
    if (list.some(isPdfFile)) {
      try {
        const s = await getSettings();
        if (s.pdf_max_pages) maxPages = s.pdf_max_pages;
        if (s.pdf_max_mb) maxMb = s.pdf_max_mb;
      } catch {
        /* offline settings fetch — fall back to defaults */
      }
    }
    const accepted: File[] = [];
    for (const file of list) {
      if (isPdfFile(file) && file.size > maxMb * 1024 * 1024) {
        showAttachNotice(
          `${file.name} 已跳过：${(file.size / 1024 / 1024).toFixed(1)} MB 超过 ${maxMb} MB 限制（设置 → Token 节省）`,
        );
        continue;
      }
      accepted.push(file);
    }
    const read = (await Promise.all(accepted.map(readFile))).filter(Boolean) as Attachment[];
    const next: Attachment[] = [];
    for (const a of read) {
      if (a.kind === "pdf" && a.data_url) {
        const info = await inspectPdf(a.data_url).catch(() => null);
        if (info?.ok && (info.pages ?? 0) > maxPages) {
          showAttachNotice(
            `${a.name} 已跳过：${info.pages} 页超过 ${maxPages} 页限制（设置 → Token 节省）`,
          );
          continue;
        }
        if (info && !info.ok) {
          showAttachNotice(`${a.name} 已跳过：${info.error || "无法读取 PDF"}`);
          continue;
        }
      }
      next.push(a);
    }
    if (next.length) setAttachments((a) => mergeAttachments(a, next));
  };

  // The "+" menu offers typed shortcuts; each just narrows the OS picker's filter.
  const pickFiles = (accept: string) => {
    setAttachMenuOpen(false);
    if (fileInput.current) {
      fileInput.current.accept = accept;
      fileInput.current.click();
    }
  };

  const stageResumeFile = async (file: File) => {
    setAttachMenuOpen(false);
    if (props.modelReady === false) {
      props.onConnectModel?.();
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      showAttachNotice(`${file.name} 已跳过：简历文件最大为 10 MB`);
      return;
    }
    const suffix = file.name.toLowerCase();
    const isPdf = suffix.endsWith(".pdf");
    const isDocx = suffix.endsWith(".docx");
    if (!isPdf && !isDocx) {
      showAttachNotice("简历必须是 PDF 或 DOCX 文件");
      return;
    }
    const dataBase64 = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("无法读取简历文件"));
      reader.onload = () => {
        const value = String(reader.result);
        resolve(value.slice(value.indexOf(",") + 1));
      };
      reader.readAsDataURL(file);
    }).catch(() => "");
    if (!dataBase64) {
      showAttachNotice(`无法读取 ${file.name}`);
      return;
    }
    showAttachNotice("正在本地读取简历…");
    const result = await stageResume({
      filename: file.name,
      mime: isPdf
        ? "application/pdf"
        : "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      data_base64: dataBase64,
    }).catch(() => null);
    if (!result?.ok || !result.upload_token) {
      showAttachNotice(careerResumeImportError(result?.error?.code));
      return;
    }
    const extractionMethod = result.extraction_method || "native";
    const notice = careerResumeImportNotice({
      extractionMethod,
      reviewRequired: result.review_required,
    });
    if (notice) showAttachNotice(notice);
    else setAttachNotice(null);
    props.onSend(
      careerResumeImportPrompt({
        uploadToken: result.upload_token,
        filename: result.filename || file.name,
        sourceKind: result.source_kind || (isPdf ? "pdf" : "docx"),
        extractionMethod,
        warningCodes: result.warnings || [],
      }),
      [],
      "career-resume-import",
      careerResumeImportDisplay(result.filename || file.name),
    );
  };

  const stagePastedResume = async () => {
    setAttachMenuOpen(false);
    if (props.modelReady === false) {
      props.onConnectModel?.();
      return;
    }
    const resumeText = text.trim();
    if (!resumeText) {
      showAttachNotice("请先将简历文本粘贴到输入框");
      return;
    }
    const result = await stageResume({
      filename: "pasted-resume.txt",
      mime: "text/plain",
      text: resumeText,
    }).catch(() => null);
    if (!result?.ok || !result.upload_token) {
      showAttachNotice(result?.error?.message || "无法暂存简历");
      return;
    }
    setText("");
    props.onSend(
      careerResumeImportPrompt({
        uploadToken: result.upload_token,
        filename: result.filename || "pasted-resume.txt",
        sourceKind: "text",
        extractionMethod: result.extraction_method || "native",
        warningCodes: result.warnings || [],
      }),
      [],
      "career-resume-import",
      careerResumeImportDisplay(result.filename || "pasted-resume.txt"),
    );
  };

  const needsModel = props.modelReady === false;

  const submit = () => {
    // While the "/" popup is open the draft is a query, not a message — never send it.
    if (slashQuery !== null) return;
    // The visible "/name " prefix is UI state, not message text — strip it for the send;
    // the skill rides as its own field; the input stays clean (the chip shows it).
    const skill = pendingSkill?.name;
    const t = text.trim();
    if (
      (!t && attachments.length === 0 && !skill) ||
      props.running ||
      dictation?.recording ||
      dictationBusy
    )
      return;
    // No model connected: keep the draft (don't drop it) and send the user to setup instead.
    if (needsModel) {
      props.onConnectModel?.();
      return;
    }
    props.onSend(t, attachments, skill);
    setText("");
    setAttachments([]);
    setPendingSkill(null);
  };

  const onKey = (e: React.KeyboardEvent) => {
    // 挂载技能 + 空输入：Delete/退格解除技能徽章（光标紧挨徽章，删除感自然）。
    if (pendingSkill && text === "" && (e.key === "Backspace" || e.key === "Delete")) {
      e.preventDefault();
      clearPinnedSkill();
      return;
    }
    if (slashQuery !== null) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSlashIndex((i) => Math.min(i + 1, Math.max(slashMatches.length - 1, 0)));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSlashIndex((i) => Math.max(i - 1, 0));
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setText("");
        return;
      }
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        const chosen = slashMatches[slashIndex];
        if (chosen) pickSkill(chosen);
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const onPaste = (e: React.ClipboardEvent) => {
    const imgs = Array.from(e.clipboardData.items)
      .filter((it) => it.kind === "file" && it.type.startsWith("image/"))
      .map((it) => it.getAsFile())
      .filter(Boolean) as File[];
    if (imgs.length) {
      e.preventDefault();
      addFiles(imgs);
    }
  };

  const toggleDictation = async () => {
    if (!isTauri() || dictationBusy) return;
    setDictationError(null);
    try {
      if (dictation?.recording) {
        setDictationBusy("正在识别…");
        const transcript = await stopDictation();
        if (transcript === null) throw new Error("Could not transcribe your recording.");
        if (transcript.trim()) {
          setText((draft) => (draft.trim() ? `${draft.trimEnd()} ${transcript.trim()}` : transcript.trim()));
        }
        setDictation(await getDictationStatus());
        textareaRef.current?.focus();
        return;
      }

      const status = dictation || (await getDictationStatus());
      if (!status) throw new Error("Voice dictation is unavailable.");
      if (!status.supported || !status.model_verified || !status.test_passed) {
        props.onConfigureVoiceInput?.();
        return;
      }
      setDictationBusy("正在请求麦克风权限…");
      const recording = await startDictation();
      if (!recording?.recording) throw new Error("Could not start the microphone.");
      setDictation(recording);
    } catch (error) {
      setDictationError(error instanceof Error ? error.message : "Voice dictation is unavailable.");
      const status = await getDictationStatus();
      if (status) setDictation(status);
    } finally {
      setDictationBusy(null);
    }
  };

  const modelsLoaded = !!(props.models && props.models.length);
  const modelOptions: Option[] = Array.from(
    new Set([props.model, ...(props.models || [])]),
  ).map((m) => ({
    value: m,
    label: props.modelLabels?.[m] || shortModel(m),
  }));

  const iconBtn =
    "w-7 h-7 grid place-items-center rounded-md text-muted hover:text-ink hover:bg-paper shrink-0";

  // The send button is accent only when there's something to send — subtle grey otherwise, so the
  // composer isn't carrying a constant blue dot.
  // A pinned /skill is sendable content on its own (tester catch 2026-07-26: the arrow
  // stayed grey after picking a skill, reading as "stuck").
  const hasContent = text.trim().length > 0 || attachments.length > 0 || !!pendingSkill;

  return (
    <div className="composer-wrap px-6 pb-5 pt-4">
      {props.approvalSlot}

      {dictationError && (
        <div className="max-w-3xl mx-auto mb-2 px-1 text-[12px] text-red-600" role="alert">
          {dictationError}
        </div>
      )}

      {/* Rejected-attachment notice (PDF over the user's Token-savings thresholds). */}
      {attachNotice && (
        <div
          data-testid="attach-notice"
          className="max-w-3xl mx-auto mb-1.5 flex items-center gap-2 rounded-lg border border-warnInk/30 bg-warnSoft px-3 py-1.5 text-[12.5px] text-warnInk"
        >
          <span className="flex-1">{attachNotice}</span>
          <button
            className="shrink-0 opacity-60 hover:opacity-100"
            onClick={() => setAttachNotice(null)}
            title="关闭"
          >
            ✕
          </button>
        </div>
      )}

      {/* Attachments preview — a strip ABOVE the input box (mock/Claude-style). */}
      {attachments.length > 0 && (
        <div className="max-w-3xl mx-auto mb-1.5 flex flex-wrap gap-2">
          {attachments.map((a, i) => (
            <AttachChip key={i} a={a} onRemove={() => setAttachments((all) => all.filter((_, j) => j !== i))} />
          ))}
        </div>
      )}

      <div
        className={
          "composer max-w-3xl mx-auto rounded-xl border border-line bg-panel" +
          (dragging ? " dragging" : "")
        }
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
        }}
      >
        {/* 已选技能独占输入区上方一行，以分割线明确“上下文”和“正文输入”的层级。 */}
        {pendingSkill && (
          <div
            className="flex items-center gap-2 border-b border-line px-3.5 py-2"
            data-testid="pinned-skill-bar"
          >
            <span
              className="inline-flex min-w-0 items-center gap-1.5 text-[13.5px] leading-5 font-medium text-ink select-none"
              data-testid="pinned-skill-chip"
              title="按 Delete/退格 移除技能"
            >
              <Icon name="book" size={14} className="shrink-0 text-accent" />
              <span className="truncate">{skillZhTitle(pendingSkill.name)}</span>
            </span>
            <button
              className="ml-auto grid h-6 w-6 shrink-0 place-items-center rounded-md text-[12px] text-faint transition-colors hover:bg-paper hover:text-ink"
              aria-label="移除技能"
              data-testid="pinned-skill-remove"
              onClick={clearPinnedSkill}
            >
              ✕
            </button>
          </div>
        )}
        <div className="pt-2.5 pb-2">
        {/* 技能按钮面板：列出会话可用技能的中文名称与说明。 */}
        {skillMenuOpen && (
          <div
            className="w-full border-b border-line px-3.5 pt-1 pb-2"
            data-testid="skill-menu"
            ref={skillMenuRef}
            role="dialog"
            aria-label="可用技能"
          >
            <div className="flex items-center justify-between px-2 pb-1">
              <span className="text-[11px] uppercase tracking-[0.05em] text-faint font-semibold">
                可用技能
              </span>
              <button
                className="text-[11.5px] text-faint hover:text-ink"
                onClick={() => setSkillMenuOpen(false)}
              >
                收起
              </button>
            </div>
            {slashSkills === null ? (
              <div className="px-2 py-1.5 text-[12px] text-faint">正在加载技能…</div>
            ) : slashSkills.length === 0 ? (
              <div className="px-2 py-1.5 text-[12px] text-faint">当前会话没有可用技能。</div>
            ) : (
              <div className="max-h-64 overflow-y-auto">
                {slashSkills.map((s) => (
                  <button
                    key={s.name}
                    className="w-full text-left px-2 py-2 rounded-lg hover:bg-paper"
                    data-testid={`skill-menu-${s.name}`}
                    onClick={() => pickSkill(s)}
                  >
                    <span className="flex items-center gap-2">
                      <span className="text-[13px] font-semibold text-ink">
                        {skillZhTitle(s.name)}
                      </span>
                      <span className="text-[10.5px] px-1.5 py-0.5 rounded-full border border-line text-faint shrink-0">
                        /{s.name}
                      </span>
                    </span>
                    <span className="block text-[12px] text-muted mt-0.5 leading-relaxed">
                      {skillZhDescription(s.name, s.description)}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {/* "/" force-run popup — in-flow above the textarea; rows are the session's
            effective menu only (muted/disabled skills never appear). */}
        {slashQuery !== null && (
          <div
            className="border-b border-line px-3.5 pt-1 pb-2"
            data-testid="skill-popup"
            role="listbox"
            aria-label="可用技能"
          >
            <div className="flex items-center justify-between px-2 pb-1">
              <span className="text-[11px] uppercase tracking-[0.05em] text-faint font-semibold">
                可用技能
              </span>
            </div>
            {slashSkills === null ? (
              <div className="px-2 py-1.5 text-[12px] text-faint">正在加载技能…</div>
            ) : slashMatches.length === 0 ? (
              <div className="px-2 py-1.5 text-[12px] text-faint">没有匹配的技能。</div>
            ) : (
              slashMatches.map((s, i) => (
                <button
                  key={s.name}
                  role="option"
                  aria-selected={i === slashIndex}
                  className={
                    "w-full text-left px-2 py-2 rounded-lg " +
                    (i === slashIndex ? "bg-paper" : "hover:bg-paper")
                  }
                  onMouseEnter={() => setSlashIndex(i)}
                  onClick={() => pickSkill(s)}
                >
                  <span className="flex items-center gap-2">
                    <span className="text-[13px] font-semibold text-ink">
                      {skillZhTitle(s.name)}
                    </span>
                    <span className="text-[10.5px] px-1.5 py-0.5 rounded-full border border-line text-faint shrink-0">
                      /{s.name}
                    </span>
                  </span>
                  <span className="block text-[12px] text-muted mt-0.5 leading-relaxed">
                    {skillZhDescription(s.name, s.description)}
                  </span>
                </button>
              ))
            )}
          </div>
        )}
        <textarea
          ref={textareaRef}
          className={
            "w-full block px-3.5 pt-0 pb-0 text-[14.5px] leading-[22px]" +
            (skillMenuOpen || slashQuery !== null ? " mt-2.5" : "")
          }
          placeholder={
            props.placeholder ||
            (props.personaId === "career"
              ? "告诉我你的求职目标，或直接导入简历…"
              : "向 Agent 提问…（可拖放或粘贴文件）")
          }
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKey}
          onPaste={onPaste}
          rows={1}
        />
        </div>

        {/* Three-control row (§22): + attach · Mode ⌄ …(right)… model (fresh only) · send */}
        <div className="composer-controls px-2.5 pb-2.5 pt-1 flex items-center gap-1.5">
          {/* + attach menu */}
          <div className="relative">
            <button
              className={iconBtn + (attachMenuOpen ? " bg-paper text-ink" : "")}
              title="添加附件"
              aria-label="添加附件"
              onClick={() => setAttachMenuOpen((v) => !v)}
            >
              <Icon name="plus" size={17} />
            </button>
            {attachMenuOpen && (
              <>
                <div className="fixed inset-0 z-30" onClick={() => setAttachMenuOpen(false)} />
                <div className="absolute z-40 bottom-full mb-1 left-0 min-w-[180px] rounded-xl border border-line bg-panel shadow-2xl py-1.5">
                  {attachItem("image", "照片或图片", () => pickFiles("image/*"))}
                  {attachItem(
                    "file",
                    props.personaId === "career" ? "PDF（仅用于对话）" : "PDF",
                    () => pickFiles("application/pdf,.pdf"),
                  )}
                  {attachItem(
                    "fileCode",
                    "其他文件",
                    () => pickFiles("text/*,.md,.csv,.json,.yaml,.yml,.log,.py,.ts,.tsx,.js,.rs,.go,.toml"),
                  )}
                  {props.personaId === "career" &&
                    attachItem(
                      "file",
                      "导入简历到求职档案（PDF/DOCX）",
                      () => {
                        setAttachMenuOpen(false);
                        resumeInput.current?.click();
                      },
                    )}
                  {props.personaId === "career" &&
                    attachItem(
                      "fileCode",
                      "导入已粘贴的简历",
                      stagePastedResume,
                    )}
                </div>
              </>
            )}
          </div>
          <input
            ref={fileInput}
            type="file"
            multiple
            style={{ display: "none" }}
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = "";
            }}
          />
          <input
            ref={resumeInput}
            data-testid="resume-file-input"
            type="file"
            accept="application/pdf,.pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,.docx"
            style={{ display: "none" }}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void stageResumeFile(file);
              e.target.value = "";
            }}
          />

          {/* Listening replaces the quiet middle controls with a LIVE waveform (mic RMS,
              polled ~10Hz, scrolling left) + elapsed time (§37). */}
          {dictation?.recording ? (
            <div className="ml-1 flex-1">
              <VoiceRecordingMeter active level={dictationLevel} />
            </div>
          ) : props.workspace !== undefined ? (
            <ModeMenu
              mode={props.mode}
              onModeChange={props.onModeChange}
              unattended={props.unattended}
              onUnattendedChange={props.onUnattendedChange}
            />
          ) : null}

          {/* 技能 — 权限模式右侧：打开中文技能面板，点选后显示在输入区上方。 */}
          {!dictation?.recording && props.sessionId && (
            <button
              ref={skillButtonRef}
              className={
                "pill transition-colors " +
                (skillMenuOpen ? "bg-accentSoft text-accent" : "")
              }
              onClick={() => setSkillMenuOpen((v) => !v)}
              title="技能"
              aria-label="可用技能"
              aria-expanded={skillMenuOpen}
              data-testid="composer-skill-button"
            >
              <span className="pill-label inline-flex items-center gap-1">
                <Icon name="book" size={14} />
                技能
              </span>
            </button>
          )}

          {dictation?.recording && (
            <span className="text-[11.5px] text-red-600">正在录音</span>
          )}
          {dictationBusy && (
            <span className="text-[11.5px] text-accent">{dictationBusy}</span>
          )}

          <span className="ml-auto" />

          {/* token usage (OPE-42) — a quiet chip; hidden until the server reports usage.
              Shows the context-window fill bar alone (the session total lives in the
              popover), or the session total when there's no window / the bar is off. */}
          {!dictation?.recording && props.usage && totalTokens(props.usage) > 0 && (
            <UsageChip
              usage={props.usage}
              contextWindow={props.contextWindow}
              contextBar={props.contextBar}
              model={props.model}
              modelLabels={props.modelLabels}
            />
          )}

          {/* model — a quiet chip, now for the session's whole life (§17 rev 2026-07-22:
              mid-session switching shipped, so the picker stays actionable; the topbar
              subtitle still states the current model). */}
          {!dictation?.recording && (needsModel ? (
            <button
              className="pill model-warn chip"
              onClick={() => props.onConnectModel?.()}
              title="连接模型"
              aria-label="尚未连接模型，前往连接"
            >
              <span className="pill-label">未连接模型</span>
              <span className="model-warn-ico" aria-hidden>⚠</span>
            </button>
          ) : modelsLoaded ? (
            <Dropdown
              value={props.model}
              options={modelOptions}
              onChange={props.onModelChange}
              align="right"
              footer={
                props.onConfigureModels ? (
                  <button
                    className="dd-item w-full text-left border-t border-line rounded-none"
                    data-testid="composer-configure-models"
                    onClick={() => props.onConfigureModels?.()}
                  >
                    <div className="dd-label text-muted">⚙ 配置自定义模型</div>
                  </button>
                ) : undefined
              }
            />
          ) : (
            <button
              className="pill chip text-faint cursor-default"
              disabled
              data-testid="models-loading"
              title="正在从本地服务获取模型列表"
            >
              <span className="pill-label">正在加载模型…</span>
            </button>
          ))}

          {/* mic — immediately before send (owner call, DMG #28 walkthrough) */}
          {!isTauri() && props.browserVoiceSlot}
          {isTauri() && (
            <button
              className={
                iconBtn +
                (dictation?.recording ? " bg-red-50 text-red-600 hover:bg-red-100" : "") +
                (dictationBusy ? " opacity-60" : "") +
                (!voiceReady && !dictation?.recording ? " opacity-40" : "")
              }
              onClick={() => void toggleDictation()}
              disabled={!!dictationBusy}
              title={
                dictationBusy ||
                (dictation?.recording
                  ? "停止录音并转写"
                  : voiceReady
                    ? "开始本地语音输入"
                    : "在设置中配置语音输入")
              }
              aria-label={dictation?.recording ? "停止语音输入" : voiceReady ? "开始语音输入" : "在设置中配置语音输入"}
              aria-disabled={!voiceReady && !dictation?.recording}
            >
              <Icon name={dictation?.recording ? "stop" : "mic"} size={16} />
            </button>
          )}

          {/* send / stop */}
          {props.running ? (
            <button className="btn danger" onClick={props.onInterrupt}>
              ⏹ 停止
            </button>
          ) : (
            <button
              className={
                "w-7 h-7 rounded-full grid place-items-center shrink-0 transition-colors " +
                (hasContent && props.connected && !dictation?.recording && !dictationBusy
                  ? "bg-accent text-white hover:brightness-105"
                  : "bg-paper border border-line text-faint")
              }
              onClick={submit}
              disabled={!props.connected || !!dictation?.recording || !!dictationBusy}
              title={needsModel ? "连接模型后发送" : undefined}
              aria-label="发送"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 19V5M5 12l7-7 7 7" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// Token-usage chip + popover (OPE-42). Trigger: a tiny context-fill meter (only when the
// active model's window is known) + the session's total token count. Click → per-model
// breakdown. Tokens only, never dollars (true cost is unknowable client-side — discounted
// pricing, per-provider cache billing).
function UsageChip({
  usage,
  contextWindow,
  contextBar,
  model,
  modelLabels,
}: {
  usage: SessionUsage;
  contextWindow?: number;
  contextBar?: boolean;
  model: string;
  modelLabels?: Record<string, string>;
}) {
  const [open, setOpen] = useState(false);
  const total = totalTokens(usage);
  const pct = contextWindow
    ? Math.min(100, Math.round((usage.context / contextWindow) * 100))
    : null;
  // Settings can hide the bar; without a known window there is nothing to fill either.
  const showBar = pct !== null && contextBar === true;
  const labelFor = (id: string) =>
    id === "unknown" ? "Unknown model" : modelLabels?.[id] || shortModel(id);
  // One field per line, session-summed (owner ask 2026-07-28). Values are cumulative
  // across the whole session, never just the last turn; "Input" is the fresh
  // (uncached) share — the cached share sits in the cache rows at its own price.
  const stat = (label: string, value: number) => (
    <div className="flex items-baseline justify-between text-[11.5px] leading-snug">
      <span className="text-faint">{label}</span>
      <span className="text-ink tabular-nums">{formatTokens(value)}</span>
    </div>
  );
  return (
    <div className="relative">
      <button
        className="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-[11.5px] text-muted hover:text-ink hover:bg-paper shrink-0"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Token 用量"
        title={
          showBar
            ? `Context window ${pct}% full · ${formatTokens(total)} tokens this session`
            : `本次对话 Token 用量：${formatTokens(total)}`
        }
        data-testid="usage-chip"
      >
        {/* The bar is the context-window fill; pairing it with the session TOTAL read as
            "total is N% of the window", which it never was. Bar alone when we have a
            window, the session total only when we don't (so the chip is never empty). */}
        {showBar ? (
          <span className="w-12 h-1.5 rounded-full bg-line overflow-hidden" aria-hidden="true">
            <span
              className="block h-full bg-accent transition-all"
              style={{ width: `${Math.max(pct as number, 4)}%` }}
            />
          </span>
        ) : (
          <span className="tabular-nums">{formatTokens(total)}</span>
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div
            className="absolute z-40 bottom-full mb-1 right-0 w-[280px] rounded-xl border border-line bg-panel shadow-2xl p-3"
            role="menu"
            data-testid="usage-popover"
          >
            {contextWindow ? (
              <div className="mb-2.5">
                <div className="text-[10.5px] uppercase tracking-[0.06em] text-faint font-semibold mb-1">
                  上下文窗口
                </div>
                <div className="h-1.5 rounded-full bg-line overflow-hidden">
                  <div
                    className="h-full bg-accent transition-all"
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="mt-1 text-[11.5px] text-muted tabular-nums">
                  {formatTokens(usage.context)} of {formatTokens(contextWindow)} · {pct}%
                </div>
              </div>
            ) : usage.context > 0 ? (
              <div className="mb-2.5 text-[11.5px] text-muted tabular-nums">
                In context now: {formatTokens(usage.context)} tokens
              </div>
            ) : null}
            <div className="text-[10.5px] uppercase tracking-[0.06em] text-faint font-semibold mb-1">
              本次对话合计
            </div>
            <div className="flex flex-col gap-1.5">
              {Object.entries(usage.byModel).map(([id, t]) => (
                <div key={id}>
                  <div className="text-[12px] text-ink font-medium truncate" title={id}>
                    {labelFor(id)}
                  </div>
                  {/* Every row is a session sum. With a cache split, the input rows are
                      the three BILLING CLASSES of input (each priced differently) and
                      read as components: uncached + cache reads + cache writes = total.
                      Without one (Ollama, compat vendors), plain "Input" says it all. */}
                  <div className="mt-0.5 flex flex-col gap-0.5">
                    {t.cache_read + t.cache_write > 0 ? (
                      <>
                        {stat("未缓存输入", t.input)}
                        {stat("缓存读取", t.cache_read)}
                        {stat("缓存写入", t.cache_write)}
                        {stat("输入合计", t.input + t.cache_read + t.cache_write)}
                      </>
                    ) : (
                      stat("输入", t.input)
                    )}
                    {stat("输出", t.output)}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-2 pt-2 border-t border-line flex items-baseline justify-between text-[11.5px]">
              <span className="text-faint">合计</span>
              <span className="text-ink tabular-nums">{formatTokens(total)} tokens</span>
            </div>
            {model && !modelLabels?.[model] && contextWindow === undefined && (
              <div className="mt-1 text-[10.5px] text-faint leading-snug">
                Context meter unavailable for custom models.
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// The composer's Mode menu (§22): a quiet chip opening the permission options with
// the current one marked, plus — when the session supports it — the "Send approvals to Inbox"
// toggle at the bottom (the old standalone InboxControl, folded in).
function ModeMenu({
  mode,
  onModeChange,
  unattended,
  onUnattendedChange,
}: {
  mode: string;
  onModeChange: (mode: string) => void;
  unattended?: boolean;
  onUnattendedChange?: (on: boolean) => void;
}) {
  const [open, setOpen] = useState(false);
  const current = PERMISSION_OPTIONS.find((o) => o.value === mode);
  return (
    <div className="relative">
      {/* Borderless, and it names the CHOSEN mode (owner ask 2026-07-11, competitor composer
          comparison): "Ask for approval ⌄" not a generic "Mode ⌄" pill. aria-label stays
          "Mode" so the accessible name is stable across mode changes. */}
      <button
        className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[12px] text-muted hover:text-ink hover:bg-paper shrink-0 whitespace-nowrap"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="权限模式"
        title={
          `Mode: ${current?.label || mode}` +
          (unattended ? " · 审批将发送到收件箱" : "")
        }
      >
        {current?.label || mode}
        <Icon name="chevronDown" size={11} className="text-faint" />
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} />
          <div
            className="absolute z-40 bottom-full mb-1 left-0 w-[260px] rounded-xl border border-line bg-panel shadow-2xl p-1.5"
            role="menu"
            data-testid="mode-menu"
          >
            {PERMISSION_OPTIONS.map((o) => (
              <button
                key={o.value}
                className="w-full flex flex-col items-start px-2.5 py-1.5 rounded-lg text-left hover:bg-paper"
                onClick={() => {
                  onModeChange(o.value);
                  setOpen(false);
                }}
              >
                <span
                  className={
                    "text-[13px] " + (o.value === mode ? "font-medium text-accent" : "text-ink")
                  }
                >
                  {o.label}
                  {o.value === mode && <span className="ml-1.5">✓</span>}
                </span>
                <span className="text-[11px] text-faint leading-snug">{o.description}</span>
              </button>
            ))}
            {onUnattendedChange && (
              <>
                <div className="my-1 border-t border-line" />
                <div className="flex items-center gap-2 px-2.5 py-1.5">
                  <span className="flex-1 min-w-0">
                    <span className="block text-[13px] text-ink">将审批发送到收件箱</span>
                    <span className="block text-[11px] text-faint leading-snug">
                      审批和问题会进入收件箱，Agent 可继续处理其他工作。
                    </span>
                  </span>
                  <Toggle
                    checked={!!unattended}
                    onChange={onUnattendedChange}
                    title="将审批发送到收件箱"
                  />
                </div>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// A row in the "+" attach menu.
function attachItem(icon: "image" | "file" | "fileCode", label: string, onClick: () => void) {
  return (
    <button
      className="w-full flex items-center gap-2.5 px-3 py-1.5 text-[13px] text-left hover:bg-paper"
      onClick={onClick}
    >
      <Icon name={icon} size={15} className="shrink-0 text-muted" /> {label}
    </button>
  );
}

function AttachChip({ a, onRemove }: { a: Attachment; onRemove: () => void }) {
  return (
    <div className={"attach-chip" + (a.kind === "image" ? " img" : "")}>
      {a.kind === "image" ? (
        <img src={a.data_url} alt={a.name} />
      ) : (
        <>
          <Icon name="file" size={13} />
          <span className="attach-name">{a.name}</span>
        </>
      )}
      <button className="attach-x" onClick={onRemove} title="移除">
        ✕
      </button>
    </div>
  );
}
