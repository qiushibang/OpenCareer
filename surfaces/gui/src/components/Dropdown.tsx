import { useState, type ReactNode } from "react";
import { Icon } from "./Icon";

export interface Option {
  value: string;
  label: string;
  description?: string;
}

interface Props {
  prefix?: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
  align?: "left" | "right";
  // Extra classes appended to the trigger pill (e.g. "chip" for a bordered composer-head chip).
  className?: string;
  // Optional action row pinned below the options (e.g. "配置自定义模型") — separated by a
  // divider, never rendered as a selectable option.
  footer?: ReactNode;
}

export function Dropdown({ prefix, value, options, onChange, align = "left", className, footer }: Props) {
  const [open, setOpen] = useState(false);
  const current = options.find((o) => o.value === value);
  const label = (prefix ? `${prefix}: ` : "") + (current?.label || value);
  return (
    <div className="dd">
      <button
        className={"pill" + (className ? " " + className : "")}
        onClick={() => setOpen((v) => !v)}
        title={label}
      >
        <span className="pill-label">{label}</span>
        <Icon name="chevronDown" size={13} className="caret" />
      </button>
      {open && (
        <>
          <div className="dd-backdrop" onClick={() => setOpen(false)} />
          <div className={"dd-menu " + align}>
            {options.map((o) => (
              <div
                key={o.value}
                className={"dd-item" + (o.value === value ? " sel" : "")}
                onClick={() => {
                  onChange(o.value);
                  setOpen(false);
                }}
              >
                <div className="dd-label">
                  {o.label}
                  {o.value === value && <span className="chk">✓</span>}
                </div>
                {o.description && <div className="dd-desc">{o.description}</div>}
              </div>
            ))}
            {/* Bubble phase, NOT capture: a capture-phase setState re-renders and unmounts
                this subtree before the footer button's own onClick runs in a real DOM
                (owner-hit: the click closed the menu and nothing else happened). Bubbling
                lets the footer act first, then the menu closes. */}
            {footer && <div onClick={() => setOpen(false)}>{footer}</div>}
          </div>
        </>
      )}
    </div>
  );
}
