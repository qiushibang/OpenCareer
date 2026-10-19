/** Tailwind config — mirrors platform/ui-mocks/redesign.html so the app can use the mock's
 *  exact utility classes. Colors map to the CSS custom properties already defined in styles.css
 *  (so light/dark theming flows through one source of truth). */
// Tailwind 4 applies opacity modifiers with color-mix itself. Keep tokens as plain
// CSS variable values so the same classes follow both palettes in styles.css.
const tok = (name) => `var(${name})`;

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["selector", '[data-theme="dark"]'],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        paper: tok("--paper"),
        panel: tok("--panel"),
        ink: tok("--ink"),
        muted: tok("--muted"),
        faint: tok("--faint"),
        line: tok("--line"),
        lineStrong: tok("--line-strong"),
        accent: tok("--accent"),
        accentSoft: tok("--accent-soft"),
        ok: tok("--ok"),
        okSoft: tok("--ok-soft"),
        okLine: tok("--ok-line"),
        warnInk: tok("--warn-ink"),
        warnSoft: tok("--warn-soft"),
        danger: tok("--danger"),
        dangerSoft: tok("--danger-soft"),
        tealInk: tok("--teal-ink"),
        tealSoft: tok("--teal-soft"),
        tealLine: tok("--teal-line"),
        solid: tok("--solid"),
        onSolid: tok("--on-solid"),
      },
      fontFamily: {
        sans: ["-apple-system", "BlinkMacSystemFont", "Segoe UI", "Inter", "system-ui", "sans-serif"],
        display: ["Songti SC", "STSong", "Noto Serif CJK SC", "Georgia", "serif"],
        mono: ["SF Mono", "JetBrains Mono", "Menlo", "monospace"],
      },
      borderRadius: { xl2: "14px" },
    },
  },
  plugins: [],
};
