import type { Config } from "tailwindcss";

/* Every colour is a CSS variable so light/dark is one source of truth, and so
   that reading this file tells you what the product is about: the only named
   hues are the four belief states. Everything else is ink and paper. */
const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)", panel: "var(--panel)", raised: "var(--panel-raised)", chip: "var(--chip)",
        border: "var(--border)", "line-strong": "var(--line-strong)",
        // four levels of ink; two is not a hierarchy
        fg: "var(--fg)", muted: "var(--muted)", faint: "var(--faint)", disabled: "var(--disabled)",
        accent: "var(--accent)", accentFg: "var(--accent-fg)",
        // semantic belief-state palette (fixed mapping, canonical spec §25)
        believed: "var(--believed)", unknown: "var(--unknown)",
        conflict: "var(--conflict)", closed: "var(--closed)",
        believedBg: "var(--believed-bg)", unknownBg: "var(--unknown-bg)",
        conflictBg: "var(--conflict-bg)", accentBg: "var(--accent-bg)", closedBg: "var(--closed-bg)",
      },
      fontFamily: {
        sans: ["'IBM Plex Sans'", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "ui-monospace", "SF Mono", "Menlo", "monospace"],
        serif: ["'IBM Plex Serif'", "Georgia", "serif"],
      },
      // 1.25 ratio from a 13px base, rounded to whole pixels
      fontSize: {
        "2xs": "11px", xs: "12px", sm: "13px", base: "13px",
        md: "16px", lg: "20px", xl: "25px", "2xl": "31px",
      },
      // small and concentric: outer 6, inner 4. A register is squared off.
      borderRadius: { xl: "10px", lg: "8px", md: "6px", DEFAULT: "4px", sm: "3px", pill: "999px" },
      transitionTimingFunction: {
        // entering/interactive; never ease-in, which stalls the first frame
        out: "cubic-bezier(0.23, 1, 0.32, 1)",
      },
    },
  },
  plugins: [],
};
export default config;
