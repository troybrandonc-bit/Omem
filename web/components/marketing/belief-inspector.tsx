"use client";
import { useId, useState } from "react";
import { cn } from "@/lib/cn";
import {
  Ticket, GitBranch, FileText, GitPullRequestClosed, ShieldCheck,
  ArrowRight, Clock3,
} from "lucide-react";

/* The landing page's one interactive object.
 *
 * It mirrors the live demo project the API serves: a:alice-email (conf 0.62),
 * grounded in ticket:8842, contradicted at t=3 by import-bot via crm:sync:19.
 *
 * WHAT THIS REDESIGN FIXED
 *
 * - THE `.led` SQUARES ARE GONE. Every row was marked with a 9px square —
 *   filled, hollow or struck. As a state encoding in a dense dashboard table
 *   that is a good idea and it stays there. On a marketing page, blown up as
 *   the hero object, three tiny squares read as unrendered debug marks: they
 *   look like something failed to load rather than something meaning anything.
 *   Each row now carries the icon for what it actually IS — a ticket, a
 *   derivation, a document — in a tinted well sized to be seen.
 *
 * - IT USES ICONS AT ALL. The rest of the site runs on lucide and this
 *   component used none, which is most of why it looked like it belonged to a
 *   different codebase.
 *
 * - THE EMPTY HALF IS GONE. Provenance and Contradictions were a 50/50 grid.
 *   Provenance is three entries; Contradictions is four short lines. At the
 *   width the landing page gives this, the right column was ~60% empty and the
 *   panel read as a layout that failed rather than one that was composed. The
 *   contradiction is now the thing it actually is — a second claim set AGAINST
 *   the first — so it sits opposite it across a divider, which is also what the
 *   product is trying to say.
 *
 * - CONFIDENCE IS A QUANTITY, SO IT IS DRAWN AS ONE. 0.62 as bare text is a
 *   number you read; as a filled track it is a level you see.
 *
 * WHAT WAS DELIBERATELY KEPT
 *
 * - No dead buttons. It used to carry three that were styled as controls and
 *   did nothing. On a page whose argument is "this tells you the truth about
 *   what it knows", buttons that lie about being buttons are the worst possible
 *   place to spend trust.
 * - The `as of` control is the demo, so all three states stay visible at once
 *   rather than hiding behind a menu, and it stays a radiogroup with arrow keys.
 * - The state change stays in a live region, so it reaches somebody who is not
 *   watching the pixels.
 */

type T = 1 | 3 | 99; // 99 = now
const TIMES: { at: T; label: string; caption: string }[] = [
  { at: 1, label: "t=1", caption: "asserted" },
  { at: 3, label: "t=3", caption: "contradicted" },
  { at: 99, label: "now", caption: "current" },
];

/** Provenance entries, in derivation order. `icon` says what the thing is;
 *  the old version encoded that in the colour of a square, which meant the
 *  reader had to learn a legend that was never shown. */
const CHAIN = [
  { icon: Ticket, id: "ticket:8842", kind: "Event", line: "“prefer email please”", tone: "believed" as const },
  { icon: GitBranch, id: "d:1", kind: "Derivation", line: "extraction from event", tone: "neutral" as const },
  { icon: FileText, id: "a:alice-email", kind: "Assertion", line: "prefers_email_over_phone", tone: "accent" as const },
];

const TONE = {
  believed: "text-believed bg-[color:var(--believed-bg)]",
  neutral: "text-faint bg-[color:var(--chip)]",
  accent: "text-accent bg-[color:var(--accent-bg)]",
  conflict: "text-conflict bg-[color:var(--conflict-bg)]",
};

export function BeliefInspector() {
  const [t, setT] = useState<T>(99);
  const contradicted = t >= 3;
  const groupId = useId();

  function move(dir: 1 | -1) {
    const i = TIMES.findIndex(x => x.at === t);
    setT(TIMES[(i + dir + TIMES.length) % TIMES.length].at);
  }

  return (
    <div className="panel overflow-hidden">
      {/* ── header ───────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3 border-b px-5 py-3.5">
        <div className="flex min-w-0 items-center gap-2">
          <FileText aria-hidden="true" className="h-4 w-4 shrink-0 text-faint" />
          <span className="mono truncate text-sm font-medium">a:alice-email</span>
        </div>

        <div role="radiogroup" aria-label="View this assertion as of"
          onKeyDown={e => {
            const d = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1
              : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
            if (!d) return;
            e.preventDefault();
            move(d as 1 | -1);
          }}
          className="flex shrink-0 items-center gap-0.5 rounded-lg border bg-[color:var(--panel-raised)] p-1">
          <Clock3 aria-hidden="true" className="ml-1 mr-0.5 h-3.5 w-3.5 text-faint" />
          <span id={groupId} className="sr-only">as of</span>
          {TIMES.map(x => (
            <button key={x.at} role="radio" aria-checked={t === x.at}
              tabIndex={t === x.at ? 0 : -1}
              onClick={() => setT(x.at)}
              className={cn(
                "mono h-7 rounded-md px-2.5 text-2xs transition-all duration-1 ease-out",
                t === x.at
                  ? "on-accent bg-accent text-accentFg shadow-[var(--lift-1)]"
                  : "text-muted hover:bg-[color:var(--chip)] hover:text-fg")}>
              {x.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── the answer ───────────────────────────────────────────────────── */}
      <div className="border-b px-5 py-5">
        <div className="flex flex-wrap items-start justify-between gap-x-8 gap-y-5">
          <div className="min-w-0 flex-1">
            <StateBadge contradicted={contradicted} />
            {/* The claim is the subject of the whole panel, so it is the
                largest thing in it. */}
            <p className="claim mt-3.5 max-w-[30ch] text-fg">Customer prefers email over phone</p>
            <div className="mt-4 flex flex-wrap gap-1.5">
              <Chip k="by" v="support-bot@v2.1" />
              <Chip k="asserted" v="t=1" />
            </div>
          </div>
          <Confidence value={0.62} />
        </div>

        <p role="status" aria-live="polite" className="sr-only">
          As of {TIMES.find(x => x.at === t)?.label}, this assertion is{" "}
          {contradicted ? "contradicted" : "believed true"}.
        </p>
      </div>

      {/* ── provenance, and what disputes it ─────────────────────────────── */}
      <div className="grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <section className="border-b px-5 py-5 lg:border-b-0 lg:border-r">
          <Heading icon={GitBranch}>Provenance</Heading>
          <ol className="mt-4 space-y-0">
            {CHAIN.map((n, i) => (
              <li key={n.id} className="relative flex gap-3 pb-4 last:pb-0">
                {/* The derivation chain, drawn. A line between two marks is the
                    claim that one came from the other. */}
                {i < CHAIN.length - 1 && (
                  <span aria-hidden="true"
                    className="absolute left-[15px] top-8 bottom-1 w-px bg-[color:var(--border)]" />
                )}
                <span aria-hidden="true"
                  className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-lg", TONE[n.tone])}>
                  <n.icon className="h-4 w-4" />
                </span>
                <div className="min-w-0 pt-0.5">
                  <div className="mono truncate text-sm font-medium">{n.id}</div>
                  <div className="mt-0.5 text-xs text-muted">
                    {n.kind} <span aria-hidden="true" className="text-faint">·</span> {n.line}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section className="px-5 py-5">
          <Heading icon={contradicted ? GitPullRequestClosed : ShieldCheck}>
            {contradicted ? "Contradicted by" : "Contradictions"}
          </Heading>
          {contradicted ? (
            <div className="mt-4">
              {/* The two claims, set against each other. This is the product's
                  whole argument, so it is drawn as an opposition rather than as
                  two paragraphs in separate columns. */}
              <div className="rounded-lg border bg-[color:var(--panel-raised)] p-3.5">
                <div className="mono truncate text-xs text-muted line-through decoration-[color:var(--line-strong)]">
                  prefers_email_over_phone
                </div>
                <ArrowRight aria-hidden="true" className="my-1.5 h-3.5 w-3.5 rotate-90 text-faint" />
                <div className="mono truncate text-sm font-medium text-conflict">
                  not:prefers_email_over_phone
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                <Chip k="by" v="import-bot@v1" />
                <Chip k="at" v="t=3" />
                <Chip k="src" v="crm:sync:19" />
              </div>
              <p className="mt-4 text-xs leading-relaxed text-muted">
                Both claims are kept. Neither was deleted, and either can be
                reconstructed at any point in the past.
              </p>
            </div>
          ) : (
            <div className="mt-4">
              <div className="rounded-lg border border-dashed bg-[color:var(--panel-raised)] p-3.5 text-xs text-muted">
                None at {TIMES.find(x => x.at === t)?.label}.
              </div>
              <p className="mt-4 text-xs leading-relaxed text-muted">
                The CRM sync that disputes this arrives at{" "}
                <button onClick={() => setT(3)}
                  className="mono rounded text-accent underline decoration-[color:var(--line-strong)] underline-offset-2 hover:decoration-[color:var(--accent)]">
                  t=3
                </button>.
              </p>
            </div>
          )}
        </section>
      </div>

      {/* ── the belief interval ──────────────────────────────────────────── */}
      <Interval t={t} onPick={setT} />
    </div>
  );
}

/**
 * The belief interval, drawn on the rail.
 *
 * This replaces a "Timeline" strip that was three plain dots on a hairline with
 * two lines of caption under each — which is what the screenshot showed being
 * clipped, and which said nothing the segmented control at the top did not
 * already say.
 *
 * `.rail` is the design system's signature element and this component was not
 * using it. It draws a claim's belief interval as a span rather than as points:
 * believed from t=1, hatched from t=3 where the contradiction lands. That is
 * the actual story — a claim is believed over a PERIOD, and the period is the
 * thing a vector store cannot represent. Three dots could never show it.
 *
 * The hatched right half is `.rail-span.is-conflict`, whose 45° stripe is a
 * texture and not a colour, so the contradicted stretch is distinguishable in
 * greyscale and to a colour-blind reader.
 */
function Interval({ t, onPick }: { t: T; onPick: (t: T) => void }) {
  const POS: Record<T, string> = { 1: "0%", 3: "50%", 99: "100%" };
  return (
    <div className="border-t px-5 py-5">
      <Heading icon={Clock3}>Belief interval</Heading>

      <div className="relative mt-5 px-1">
        <div className="rail" aria-hidden="true">
          <span className="rail-span is-believed" style={{ left: "0%", width: "50%" }} />
          <span className="rail-span is-conflict" style={{ left: "50%", width: "50%" }} />
          <span className="rail-cap" style={{ left: "0%" }} />
          <span className="rail-now transition-[left] duration-3 ease-out" style={{ left: POS[t] }} />
        </div>

        {/* The stops. Buttons, because they move the clock — the same state the
            segmented control drives, reachable from the picture of it. */}
        <div className="relative mt-3 h-9">
          {TIMES.map(x => {
            const on = t === x.at;
            const end = x.at === 99;
            return (
              <button key={x.at} onClick={() => onPick(x.at)} aria-pressed={on}
                aria-label={`View as of ${x.label}, ${x.caption}`}
                className={cn(
                  "tap absolute top-0 flex flex-col rounded px-1 text-left transition-colors duration-1 ease-out",
                  x.at === 1 && "left-0 items-start",
                  x.at === 3 && "left-1/2 -translate-x-1/2 items-center",
                  end && "right-0 items-end")}>
                <span className={cn("mono text-2xs leading-none", on ? "text-fg" : "text-muted")}>{x.label}</span>
                <span className={cn("mt-1 text-2xs leading-none",
                  x.at === 3 ? "text-conflict" : "text-faint")}>{x.caption}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/* ── parts ─────────────────────────────────────────────────────────────── */

function Heading({ icon: Icon, children }: { icon: React.ElementType; children: React.ReactNode }) {
  return (
    <h3 className="flex items-center gap-2 text-xs font-semibold text-fg">
      <Icon aria-hidden="true" className="h-3.5 w-3.5 text-faint" />
      {children}
    </h3>
  );
}

/** The answer, as a badge rather than a coloured word beside a square.
 *  Shape and icon carry it as well as colour, so it survives greyscale. */
function StateBadge({ contradicted }: { contradicted: boolean }) {
  const Icon = contradicted ? GitPullRequestClosed : ShieldCheck;
  return (
    <span className={cn(
      "inline-flex items-center gap-1.5 rounded-pill px-2.5 py-1 text-xs font-medium",
      contradicted ? TONE.conflict : TONE.believed)}>
      <Icon aria-hidden="true" className="h-3.5 w-3.5" />
      {contradicted ? "Contradicted" : "Believed"}
    </span>
  );
}

function Chip({ k, v }: { k: string; v: string }) {
  return (
    <span className="chip">
      {k} <b className="mono">{v}</b>
    </span>
  );
}

/** 0.62 as bare text is a number you read. As a track it is a level you see —
 *  and the number stays, because a bar alone cannot be quoted in an incident. */
function Confidence({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  return (
    <div className="shrink-0">
      <div className="text-2xs text-faint">Confidence</div>
      <div className="num mt-1 text-2xl leading-none tabular-nums">{value.toFixed(2)}</div>
      <div role="img" aria-label={`Confidence ${pct} percent`}
        className="mt-2.5 h-1 w-24 overflow-hidden rounded-pill bg-[color:var(--chip)]">
        <span className="block h-full rounded-pill bg-accent transition-[width] duration-3 ease-out"
          style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
