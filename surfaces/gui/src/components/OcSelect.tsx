import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Icon } from "./Icon";

// Fixed tag palette (see .oc-tag in design-system.css). Each tone has a light and a dark
// variant, so a value keeps the same colour everywhere it appears.
export type TagTone = "gray" | "blue" | "green" | "purple" | "orange" | "red" | "yellow" | "teal" | "pink";

export interface OcSelectOption {
  value: string;
  label: string;
  /** Faint number on the right (e.g. how many jobs match). */
  count?: number;
  /** Renders the option (and the selected value) as a coloured tag. */
  tone?: TagTone;
  /** Quiet second line under the label. */
  hint?: string;
}

export function Tag({ tone = "gray", children, className }: { tone?: TagTone; children: ReactNode; className?: string }) {
  return <span className={"oc-tag" + (className ? " " + className : "")} data-tone={tone}>{children}</span>;
}

interface Props {
  value: string;
  onChange: (value: string) => void;
  options: OcSelectOption[];
  ariaLabel: string;
  placeholder?: string;
  /** Defaults to true when there are more than 8 options. */
  searchable?: boolean;
  /** field = form control; cell = borderless table cell; compact = small toolbar control. */
  variant?: "field" | "cell" | "compact";
  disabled?: boolean;
  className?: string;
  id?: string;
  menuMinWidth?: number;
}

const MENU_GAP = 6;
const MENU_MAX_H = 320;

/** Custom single select: listbox popover with search, tags and keyboard support.
 *  The popover is portalled to <body> so tables, drawers and dialogs never clip it. */
export function OcSelect({
  value, onChange, options, ariaLabel, placeholder = "请选择", searchable, variant = "field",
  disabled, className, id, menuMinWidth = 200,
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(-1);
  const [position, setPosition] = useState<{ left: number; top?: number; bottom?: number; width: number; maxHeight: number } | null>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const listId = useId();
  const withSearch = searchable ?? options.length > 8;
  const selected = options.find((option) => option.value === value);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return needle ? options.filter((option) => option.label.toLowerCase().includes(needle)) : options;
  }, [options, query]);

  const place = useCallback(() => {
    const box = trigger.current?.getBoundingClientRect();
    if (!box) return;
    const width = Math.min(Math.max(box.width, menuMinWidth), window.innerWidth - 16);
    const left = Math.min(Math.max(8, box.left), Math.max(8, window.innerWidth - width - 8));
    const below = window.innerHeight - box.bottom - MENU_GAP - 8;
    const above = box.top - MENU_GAP - 8;
    if (below >= Math.min(MENU_MAX_H, 220) || below >= above) {
      setPosition({ left, top: box.bottom + MENU_GAP, width, maxHeight: Math.max(160, Math.min(MENU_MAX_H, below)) });
    } else {
      setPosition({ left, bottom: window.innerHeight - box.top + MENU_GAP, width, maxHeight: Math.max(160, Math.min(MENU_MAX_H, above)) });
    }
  }, [menuMinWidth]);

  const close = useCallback((refocus = true) => {
    setOpen(false);
    setQuery("");
    if (refocus) trigger.current?.focus({ preventScroll: true });
  }, []);

  const show = () => {
    if (disabled) return;
    place();
    setOpen(true);
    setActive(Math.max(0, options.findIndex((option) => option.value === value)));
  };

  const choose = (option: OcSelectOption) => {
    if (option.value !== value) onChange(option.value);
    close();
  };

  useLayoutEffect(() => { if (open) place(); }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const outside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (trigger.current?.contains(target) || menu.current?.contains(target)) return;
      close(false);
    };
    const reflow = () => place();
    document.addEventListener("mousedown", outside);
    window.addEventListener("resize", reflow);
    window.addEventListener("scroll", reflow, true);
    if (withSearch) requestAnimationFrame(() => search.current?.focus({ preventScroll: true }));
    else menu.current?.focus({ preventScroll: true });
    return () => {
      document.removeEventListener("mousedown", outside);
      window.removeEventListener("resize", reflow);
      window.removeEventListener("scroll", reflow, true);
    };
  }, [open, close, place, withSearch]);

  useEffect(() => { if (open) setActive(visible.length ? 0 : -1); }, [query]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!open || active < 0) return;
    const row = menu.current?.querySelector<HTMLElement>(`[data-index="${active}"]`);
    if (row && typeof row.scrollIntoView === "function") row.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  const onMenuKey = (event: KeyboardEvent) => {
    // Keep keys inside the popover: the dialog or drawer underneath must not react to them.
    event.stopPropagation();
    if (event.key === "Escape") { event.preventDefault(); close(); }
    else if (event.key === "ArrowDown") { event.preventDefault(); setActive((index) => Math.min(visible.length - 1, index + 1)); }
    else if (event.key === "ArrowUp") { event.preventDefault(); setActive((index) => Math.max(0, index - 1)); }
    else if (event.key === "Home") { event.preventDefault(); setActive(0); }
    else if (event.key === "End") { event.preventDefault(); setActive(visible.length - 1); }
    else if (event.key === "Enter") { event.preventDefault(); if (visible[active]) choose(visible[active]); }
    else if (event.key === "Tab") close(false);
  };

  const onTriggerKey = (event: KeyboardEvent) => {
    if (!open && ["ArrowDown", "ArrowUp", "Enter", " "].includes(event.key)) { event.preventDefault(); show(); }
  };

  const label = selected
    ? selected.tone ? <Tag tone={selected.tone}>{selected.label}</Tag> : <span className="oc-select-value">{selected.label}</span>
    : <span className="oc-select-placeholder">{value || placeholder}</span>;

  return (
    <>
      <button
        ref={trigger}
        id={id}
        type="button"
        role="combobox"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        disabled={disabled}
        className={"oc-select" + " oc-select-" + variant + (open ? " is-open" : "") + (className ? " " + className : "")}
        onClick={() => (open ? close() : show())}
        onKeyDown={onTriggerKey}
      >
        <span className="oc-select-label">{label}</span>
        <Icon name="chevronDown" size={13} className="oc-select-caret" />
      </button>
      {open && position && createPortal(
        <div
          ref={menu}
          className="oc-select-menu"
          tabIndex={-1}
          style={{ left: position.left, top: position.top, bottom: position.bottom, width: position.width, maxHeight: position.maxHeight }}
          onKeyDown={onMenuKey}
          onMouseDown={(event) => event.stopPropagation()}
          onClick={(event) => event.stopPropagation()}
        >
          {withSearch && (
            <div className="oc-select-search">
              <Icon name="search" size={13} />
              <input
                ref={search}
                value={query}
                placeholder="搜索选项"
                aria-label={`搜索${ariaLabel}`}
                aria-controls={listId}
                aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
          )}
          <div role="listbox" id={listId} aria-label={ariaLabel} className="oc-select-list">
            {visible.map((option, index) => {
              const isSelected = option.value === value;
              return (
                <div
                  key={option.value}
                  id={`${listId}-${index}`}
                  data-index={index}
                  role="option"
                  aria-selected={isSelected}
                  className={"oc-select-option" + (index === active ? " is-active" : "") + (isSelected ? " is-selected" : "")}
                  onMouseEnter={() => setActive(index)}
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => choose(option)}
                >
                  <span className="oc-select-option-main">
                    {option.tone ? <Tag tone={option.tone}>{option.label}</Tag> : <span className="truncate">{option.label}</span>}
                    {option.hint && <span className="oc-select-hint">{option.hint}</span>}
                  </span>
                  {option.count !== undefined && <span className="oc-select-count">{option.count.toLocaleString()}</span>}
                  <Icon name="check" size={14} className="oc-select-check" />
                </div>
              );
            })}
            {!visible.length && <div className="oc-select-empty">没有匹配的选项</div>}
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}
