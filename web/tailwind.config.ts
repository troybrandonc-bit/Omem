import type { Config } from "tailwindcss";
const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)", panel: "var(--panel)", raised: "var(--panel-raised)", chip: "var(--chip)", "line-strong": "var(--line-strong)", border: "var(--border)", faint: "var(--faint)",
        fg: "var(--fg)", muted: "var(--muted)", accent: "var(--accent)",
        // semantic belief-state palette (fixed mapping, canonical spec §25)
        believed: "var(--believed)", unknown: "var(--unknown)",
        conflict: "var(--conflict)", closed: "var(--closed)",
        believedBg: "var(--believed-bg)", unknownBg: "var(--unknown-bg)",
        conflictBg: "var(--conflict-bg)", accentBg: "var(--accent-bg)", closedBg: "var(--closed-bg)",
      },
      fontFamily: { sans: ["Inter","system-ui","sans-serif"], mono: ["ui-monospace","SF Mono","Cascadia Code","Consolas","monospace"] },
      fontSize: { "2xs": "11px" },
      borderRadius: { xl: "12px", lg: "10px", md: "8px", DEFAULT: "6px", pill: "999px" },
    },
  },
  plugins: [],
};
export default config;
