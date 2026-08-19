# OMEM dashboard — design system

## Direction: "the register"

An evidentiary record, not a SaaS dashboard. Someone opens this mid-incident
asking why an agent said a thing, so the interface is built like a registry —
dated, ruled, quotable. Authoritative and cold, not friendly.

**What was rejected.** The previous palette was Stripe's verbatim (`#635bff` is
Stripe indigo, `#1a1f36` is Stripe ink; the file said "matched to the reference
shot"), on Inter, with hue-only status dots and a flat 20-link admin sidebar.
Do not drift back toward any of those.

## Rules

1. **Warm ground, cool ink.** Surfaces are paper-neutral, never blue-white. Text
   and the single accent are iron-gall blue-black.
2. **Belief state is the only chroma.** Buttons and links are ink, not brand
   colour. The four state colours are the only hues that compete for the eye,
   because they are the only things on screen that mean anything.
3. **Borders, never shadows.** One depth strategy, committed. No box-shadows.
4. **Shape before colour for state.** State must survive a black-and-white
   screenshot and a colour-blind reader.

## Tokens (`app/globals.css`)

Surfaces step ~2%: `--bg` `--panel` `--panel-raised` `--chip`. Sidebar shares
`--bg` with the canvas — a differently-coloured sidebar splits the screen into
two worlds. Ink has four levels: `--fg` `--muted` `--faint` `--disabled`; two is
not a hierarchy. Borders are low-opacity warm greys (`--border`,
`--line-strong`), stepping up in dark mode where shadows do not read.

Dark mode is warm charcoal, not blue-black: one hue, lightness only.

## Type

IBM Plex Sans / Mono / Serif. Plex was drawn for institutional and technical
documentation, which is what this is.

- Scale: **1.25 from a 13px base** → 11 · 13 · 16 · 20 · 25 · 31. Every
  `fontSize` entry carries its own line-height; overriding a key in
  `extend.fontSize` discards Tailwind's paired leading.
- Hierarchy comes from **size + weight + colour together**, never size alone.
- Tracking tightens as size grows (optical sizing); `.display` is -0.021em.
- **Everything identifying or numeric is `.mono`** — propositions, ids,
  timestamps, figures. A proposition is a token, not prose.
- `.claim` (Plex Serif, 20px) is the *only* serif, used only where a claim is
  quoted at size. There, the claim is the evidence.

## Density and space

Base unit 4px, workbench-tight. Panel padding 12–16px, control height **32px**
(`h-8`), row height 32px. Sidebar **232px** — wide enough for "Where it came
from" on one line.

## Depth and radius

Borders only. Radius is small and **concentric: 6px outer, 4px inner**. A
register is squared off. `rounded-pill` is not used except for genuine dots.

## Signature elements

**The belief rail** (`.rail`, `<BeliefRail>`). A claim's interval on a ruled
span. An **open interval gets no right terminator and fades out** — "still
believed, nothing has ended it" is a real engine state, and a bar that simply
stopped would read as "ended here", the most consequential thing a reader could
misread. Closed spans get a hard end-cap; contradicted spans are hatched. `now`
is a full-height ink tick.

**State marks** (`.led`). Filled = believed · dotted outline = unknown ·
struck through = contradicted · hollow = closed. Shape first, colour second.

## Navigation

Grouped by the question you arrived with, not by feature name: *What is
believed · What disagrees · Where it came from · Build · Account*. Active row is
marked with a 2px ink rule at the left edge, not a coloured pill.

## Components

- `Button` — 32px h (`h-8`) · 12px px · 4px radius · 12px/500. Primary is **ink**
  (`bg-accent text-accentFg`), never a brand hue. `active:scale-[0.97]`, 150ms,
  `ease-out`.
- `StateBadge` — mark + the engine's own word in mono (`believed`,
  `contradicted`), not an uppercase pill. It is the answer, not a label.
- `Th` — 11px/600 uppercase, 0.06em tracking, `bg-raised`.
- Panels: `.panel` = 1px border, 6px radius, no shadow.

## Motion

Under 300ms, `cubic-bezier(0.23, 1, 0.32, 1)`, never `ease-in`. Only `transform`
and `opacity`. `prefers-reduced-motion` is honoured globally in globals.css.

## Consistency checks

- No hardcoded `text-white` on an accent fill — use `text-accentFg`, or dark
  mode breaks (`--accent-fg` is near-black there).
- No `bg-white` / `border-gray-*` / raw hex — bind to tokens.
- Colour only where it carries belief state.
