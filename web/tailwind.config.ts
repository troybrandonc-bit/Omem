import type { Config } from "tailwindcss";

/* Every colour is a CSS variable so light/dark/increased-contrast is one source
   of truth, and so that reading this file tells you what the product is about:
   the only named hues are the four belief states. Everything else is ink and
   paper. */
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
        // `ink` is an alias for `fg`. Three pages already wrote `text-ink` and
        // `hover:text-ink`, which were not colours in this config and therefore
        // compiled to nothing at all: a subject label meant to be the strongest
        // ink on the row silently inherited its parent's muted grey, and a
        // filter pill had no hover state. Naming the alias is cheaper than
        // hunting every future instance of the same slip.
        ink: "var(--fg)",
        accent: "var(--accent)", accentFg: "var(--accent-fg)", accentHover: "var(--accent-hover)",
        // semantic belief-state palette (fixed mapping, canonical spec §25)
        believed: "var(--believed)", unknown: "var(--unknown)",
        conflict: "var(--conflict)", closed: "var(--closed)",
        believedBg: "var(--believed-bg)", unknownBg: "var(--unknown-bg)",
        conflictBg: "var(--conflict-bg)", accentBg: "var(--accent-bg)", closedBg: "var(--closed-bg)",
      },
      fontFamily: {
        // Supplied by next/font (app/fonts.ts) and self-hosted; the tail of each
        // stack is the metrics-matched fallback, not a network fallback.
        //
        // `display` is Inter Tight and is for type set at size — anything from
        // the `lg` step up. It is the same skeleton as `sans` with the spacing
        // drawn for large sizes, which is why a headline in it reads as a
        // headline rather than as enlarged body copy. `.display` in globals.css
        // applies it; you should rarely need this key directly.
        sans: ["var(--font-sans)", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      /* The scale: 11 · 12 · 13 · 15 · 20 · 25 · 31 · 44, EXPRESSED IN rem.
       *
       * Every step used to be a hard pixel, which meant the single most common
       * accessibility setting on the web — "make text bigger" in the browser's
       * own appearance settings — did nothing at all to this product. Not one
       * character changed size. A rem step is the same 13px it always was at
       * the default root, and becomes 16px when somebody asks for 125%.
       * Nothing about the design moves; the design now answers when asked.
       *
       * Each entry still carries its OWN line-height and tracking, because
       * overriding a key here discards the pairing Tailwind ships. That is the
       * reason to use these keys instead of `text-[15px]`: an arbitrary value
       * emits font-size and nothing else, so it silently drops both.
       *
       * TWO SURFACES, TWO KINDS OF STEP.
       *
       * The rem steps (2xs…3xl) are the INSTRUMENT scale: absolute, identical
       * on every surface, used for chrome, controls, tables and headings.
       *
       * The em steps (caption/note/body/lede) are the READING scale: relative,
       * so they follow whichever base they land in. Inside `.reading` — which
       * marketing and docs set once — they resolve against a 16-17px document
       * base rather than the 13px instrument base.
       *
       * That distinction is not academic. The reading surface previously wrote
       * `text-sm` for its body copy 38 times, and `text-sm` is 13px. So every
       * paragraph on the public site rendered at the dense monitor size while
       * the stylesheet's comments described a document. `.reading` was being
       * set and then overridden on almost every element it contained.
       *
       * The top three steps are fluid. A 31px headline is right on a laptop and
       * crowds a 360px phone, and clamp() is the fix that does not need a
       * breakpoint per heading.
       */
      fontSize: {
        // ── instrument scale (rem: absolute, scales with the user's root) ──
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],                        // 11
        xs:    ["0.75rem",   { lineHeight: "1.125rem" }],                    // 12
        sm:    ["0.8125rem", { lineHeight: "1.25rem" }],                     // 13
        base:  ["0.8125rem", { lineHeight: "1.25rem" }],                     // 13
        // comfortable UI text: labels and controls that are read, not scanned
        md:    ["0.9375rem", { lineHeight: "1.4375rem" }],                   // 15

        // ── reading scale (em: relative, follows `.reading`) ───────────────
        // At the 17px document base these are 13.8 · 15.9 · 17 · 18.1px.
        caption: ["0.8125em", { lineHeight: "1.5" }],
        note:    ["0.9375em", { lineHeight: "1.6" }],
        body:    ["1em",      { lineHeight: "1.65" }],
        lede:    ["1.0625em", { lineHeight: "1.55", letterSpacing: "-0.004em" }],

        // ── display steps ─────────────────────────────────────────────────
        lg:    ["1.25rem", { lineHeight: "1.32", letterSpacing: "-0.018em" }],   // 20
        xl:    ["clamp(1.375rem, 1.1rem + 1.4vw, 1.5625rem)", { lineHeight: "1.2", letterSpacing: "-0.024em" }],
        "2xl": ["clamp(1.625rem, 1.2rem + 2.4vw, 1.9375rem)", { lineHeight: "1.12", letterSpacing: "-0.028em" }],
        /* One step above the old ceiling, and the only place it is used is the
           first headline of a page somebody has just arrived on. The landing
           page opened at the same size as a section heading three screens down,
           so nothing on the first screen was visibly the most important thing
           on it. 31 → 44px. */
        "3xl": ["clamp(1.9375rem, 1.25rem + 3.4vw, 2.75rem)", { lineHeight: "1.05", letterSpacing: "-0.032em" }],
        /* The arrival step, and the only one above 3xl.
         *
         * 3xl is the right size for the first heading on a page somebody
         * navigated to. It is NOT the right size for the one sentence the whole
         * site is trying to land, on the screen a stranger sees first. Those
         * were the same step, so the landing headline and the pricing headline
         * carried identical weight and the home page had no summit.
         *
         * 36 → 64px. Still rem, so it still answers the browser's text-size
         * setting; still fluid, so a 64px line does not sit on a 360px phone.
         * Tracking tightens again because optical sizing keeps going: the
         * bigger the face, the less air the counters need.
         *
         * The floor is 36px rather than 40. The whole point of a fluid step is
         * that the TOP end is free; it is the bottom end that has to stay
         * honest. On a 360px phone the measure is ~320px, and at 40px that is
         * barely eight characters to a line — a headline breaking every three
         * words is not emphatic, it is just hard to read. 36px is still the
         * largest thing on the page by a wide margin. */
        "4xl": ["clamp(2.25rem, 1.5rem + 4.6vw, 4.25rem)", { lineHeight: "1.0", letterSpacing: "-0.038em" }],
      },
      // small and concentric: outer 6, inner 4. A register is squared off.
      borderRadius: { "2xl": "18px", xl: "14px", lg: "12px", md: "10px", DEFAULT: "6px", sm: "4px", pill: "999px" },
      // Control geometry, shared with globals.css so a Tailwind height and a CSS
      // height cannot drift apart. 8 = the 32px instrument row, 11 = the 44px
      // platform minimum for a touch target.
      spacing: { control: "var(--control-h)", "control-lg": "var(--control-h-lg)" },
      minHeight: { tap: "44px" },
      minWidth: { tap: "44px" },
      maxWidth: {
        // the marketing measure, the docs measure, and the reading measure
        shell: "1200px",
        page: "72rem",
        read: "34em",
      },
      transitionTimingFunction: {
        // entering/interactive; never ease-in, which stalls the first frame
        out: "var(--ease)",
      },
      transitionDuration: { 1: "var(--dur-1)", 2: "var(--dur-2)", 3: "var(--dur-3)" },
      keyframes: {
        rise: { from: { opacity: "0", transform: "translateY(4px)" }, to: { opacity: "1", transform: "none" } },
      },
      animation: { rise: "rise var(--dur-3) var(--ease) both" },
    },
  },
  plugins: [],
};
export default config;
