# OMEM Design System

The goal: OMEM reads as infrastructure. Precision, trust, intelligence, control. Not a
SaaS template, not an AI-startup aesthetic.

## Identity

- Wordmark: a memory-node glyph (one filled node deriving two others) shared by the
  marketing site, dashboard, and onboarding. One mark everywhere.
- The product is the identity. The strongest visuals are OMEM's own structures:
  assertions, provenance chains, belief states, intervals, revision chains. No stock
  illustration, no decorative imagery, no fake social proof, no invented metrics.

## Typography

- UI and prose: Inter (400 / 500 / 600). Display headlines use `.display`
  (weight 560, tracking -0.022em, tight leading). Headlines are strong, never huge.
- Data: the native system monospace stack (Cascadia Code / SF Mono / Menlo / Consolas)
  via `.mono`. Monospace is reserved for machine values only: ids, times, states, code.
  Labels and prose around them are always Inter. This split is the core typographic rule.
- Labels: `.tech-label` (Inter 12px / 500 / muted). No uppercase tracking, no mono caps.

## Color

Near-black and warm near-white bases, neutral grey ramps, hairline borders, and one
accent (cobalt, #2b5cd9 light / #5b8aff dark) reserved for interaction, links, focus, and temporal markers only. Conflict state is a serious red (#d92d20 / #f26d6d), not pink. Semantic state colors
are fixed everywhere and never used decoratively:

- emerald: grounded / BELIEVED_TRUE
- amber: ungrounded / UNKNOWN
- rose: conflict / CONTRADICTED / BELIEVED_FALSE
- slate: closed / RETRACTED

Color always means the same thing in the inspector, the tables, the graphs, and the site.

## Shape and elevation

Two registers, never mixed:

1. Flat editorial structure: sections separated by hairline rules (`.rule`,
   `.spec-row`), left-aligned, no boxes. Used for page structure and prose.
2. Rounded objects: panels, code blocks, tables, and controls that represent real UI
   objects get the radius scale (8px panels, 6px controls, 4px small) with hairline
   borders and at most `shadow-sm`. `overflow-hidden` keeps internal borders clean.

No gradients, no glassmorphism, no glow, no pills, no cards-inside-cards.

## Spacing

4px base scale. Content max-widths: 1120px (marketing), 64rem (dashboard work surfaces),
narrower for reading (42-48rem). Chrome: 48px header, 224px sidebar. Section rhythm on
marketing: py-20/24; dashboard: mb-6/8 blocks.

## Navigation model

The sidebar teaches the product: Workspace (Overview, Memory, Agents, Entities,
Timeline, Conflicts, Graph) / Developer (Playground, API, Logs) / Organization
(Usage, Settings). The global "As of" replay slider is permanent chrome: time travel is
an instrument, not a feature page.

## Motion and accessibility

Motion communicates state only (150ms color transitions, palette open, timeline moves).
`prefers-reduced-motion` collapses all animation. `:focus-visible` outlines on
everything, ARIA labels on dialogs/controls, semantic landmarks.

## Honesty rules (product, not just design)

- Every displayed explanation maps to a real engine query. No fabricated reasoning.
- Trust is shown as ordering only, never numeric.
- Search is retrieval ("find"), never a belief decision.
- Unwired capabilities (billing metering, team management) are labeled as such on the
  Usage and Settings pages instead of showing fake data.
