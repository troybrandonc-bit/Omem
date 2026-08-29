"use client";
import { cn } from "@/lib/cn";
import type { PropositionState } from "@/lib/api";
import { Loader2, AlertTriangle } from "lucide-react";

/* OMEM design language, product side. See app/globals.css for the direction.
   Three rules do most of the work here:

     - State is SHAPE first and colour second, so it survives a black-and-white
       screenshot and colour-blind vision. Hue-only dots fail both.
     - Colour is data. Buttons and links are ink; the only chroma on screen is
       belief state, so the four things that mean something are the four things
       the eye is drawn to.
     - A dense control keeps its 32px look and gets a 44px HIT area on touch
       (`.tap`). Density is a desktop affordance, not an excuse for a target a
       finger misses. */

const STATE_TONE: Record<PropositionState, string> = {
  BELIEVED_TRUE: "believed", BELIEVED_FALSE: "conflict",
  CONTRADICTED: "conflict", UNKNOWN: "unknown",
};
/* Read aloud rather than shouted in caps: the engine's answer, in the engine's
   vocabulary, so what the dashboard says matches what /v1/queries returns. */
const STATE_WORD: Record<PropositionState, string> = {
  BELIEVED_TRUE: "believed",
  BELIEVED_FALSE: "believed false",
  CONTRADICTED: "contradicted",
  UNKNOWN: "unknown",
};
const TXT: Record<string, string> = {
  believed: "text-believed", unknown: "text-unknown", conflict: "text-conflict",
  closed: "text-closed", accent: "text-accent", muted: "text-muted",
};

/** The mark + the engine's own word for the state. Replaces the uppercase pill:
 *  a pill is a label you skim, and this is the answer you came for. */
export function StateBadge({ state, size = "md" }: { state: PropositionState; size?: "sm" | "md" }) {
  const tone = STATE_TONE[state];
  return (
    <span className={cn("inline-flex items-center gap-1.5 font-medium", TXT[tone],
      size === "sm" ? "text-2xs" : "text-xs")}>
      <span className={cn("led", tone)} aria-hidden="true" />
      <span className="mono">{STATE_WORD[state]}</span>
    </span>
  );
}

export function Badge({ children, tone = "muted", className }:
  { children: React.ReactNode; tone?: "muted" | "accent" | "believed" | "unknown" | "conflict" | "closed"; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-sm border px-1.5 py-px text-2xs font-medium",
      tone === "muted" ? "border-line-strong text-muted" : TXT[tone], className)}
      style={tone !== "muted" ? { borderColor: "currentColor" } : undefined}>
      {children}
    </span>
  );
}

export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("panel", className)}>{children}</div>;
}

export function SectionLabel({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cn("tech-label", className)}>{children}</div>;
}

/**
 * The page title block every dashboard screen shares.
 *
 * Twenty pages each hand-rolled this, so `text-[24px]`, `text-[21px]`,
 * `text-[22px]` and `text-[20px]` were all in use for the same element — four
 * answers to "how big is a page title", none of them on the scale, and each one
 * silently discarding the leading and tracking the scale pairs with its steps.
 */
export function PageTitle({ title, children, actions }: {
  title: React.ReactNode; children?: React.ReactNode; actions?: React.ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
      <div className="min-w-0">
        <h1 className="display text-lg">{title}</h1>
        {children && <p className="mt-1.5 max-w-read text-sm leading-relaxed text-muted">{children}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** Primary is ink, not a brand hue — see the colour rule above. 32px at md,
 *  which is the row height everywhere else in the app; `lg` is the 44px touch
 *  size for anything that is the main action on a screen. */
export function Button({ children, onClick, variant = "primary", size = "md", disabled, type = "button", className, title, ariaLabel }:
  { children: React.ReactNode; onClick?: () => void;
    variant?: "primary" | "secondary" | "ghost" | "danger"; size?: "sm" | "md" | "lg";
    disabled?: boolean; type?: "button" | "submit"; className?: string; title?: string; ariaLabel?: string }) {
  const v: Record<string, string> = {
    primary: "on-accent bg-accent text-accentFg hover:bg-accentHover",
    secondary: "border border-[color:var(--line-strong)] bg-panel hover:bg-raised",
    ghost: "text-muted hover:bg-chip hover:text-fg",
    danger: "border border-[color:var(--conflict)]/50 text-conflict hover:bg-conflictBg",
  };
  const s: Record<string, string> = {
    sm: "h-7 px-2.5 text-2xs",
    md: "h-8 px-3 text-xs",
    lg: "h-control-lg px-5 text-sm",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled} title={title} aria-label={ariaLabel}
      className={cn(
        "tap inline-flex items-center justify-center gap-1.5 rounded font-medium",
        "transition-[background-color,color,border-color,opacity,transform] duration-1 ease-out",
        "active:scale-[0.97] disabled:opacity-40 disabled:pointer-events-none disabled:active:scale-100",
        s[size], v[variant], className)}>
      {children}
    </button>
  );
}

/** A labelled input. Pages were repeating six utilities per field and dropping
 *  the label on about half of them, which leaves a screen reader with an
 *  unnamed text box. */
export function Field({ id, label, hint, children, className }: {
  id: string; label: string; hint?: string; children: React.ReactNode; className?: string;
}) {
  return (
    <div className={className}>
      <label htmlFor={id} className="mb-1.5 block text-xs font-medium">{label}</label>
      {children}
      {hint && <p className="mt-1.5 text-2xs text-muted">{hint}</p>}
    </div>
  );
}

export function Table({ children, caption }: { children: React.ReactNode; caption?: string }) {
  return (
    <div className="overflow-x-auto rounded-md border" tabIndex={0}>
      <table className="w-full text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        {children}
      </table>
    </div>
  );
}
export function Th({ children, className, scope = "col" }: { children?: React.ReactNode; className?: string; scope?: "col" | "row" }) {
  // Sentence case, not uppercase: a tracked all-caps column header is the same
  // generated-interface tell as the region label, and a data grid reads better
  // with headers set like the words they are.
  return <th scope={scope} className={cn("border-b bg-raised px-3 py-2 text-left text-xs font-semibold text-faint", className)}>{children}</th>;
}
export function Td({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <td className={cn("border-b border-[color:var(--border)]/70 px-3 py-2 align-middle", className)}>{children}</td>;
}

/** An empty state that says what to do next. A blank screen with no action is
 *  the most daunting screen in any product. */
export function EmptyState({ icon: Icon, title, body, action }:
  { icon?: any; title: string; body?: string; action?: React.ReactNode }) {
  return (
    <div className="empty flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:gap-3">
      {Icon && <Icon className="h-4 w-4 shrink-0 text-faint" aria-hidden="true" />}
      <div className="min-w-0 flex-1">
        <span className="font-medium text-fg">{title}</span>
        {body && <span className="text-muted"> {body}</span>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

/** A query that FAILED, which is not the same thing as a query that returned
 *  nothing — and the gap between those two matters more in this product than in
 *  most.
 *
 *  Every list here used to render `!data || data.length === 0 ? <EmptyState/>`,
 *  which collapses them: a 404, a dropped connection and a genuinely quiet
 *  project all produced the same confident sentence. On the Conflicts screen
 *  that sentence was "Every proposition has a consistent belief state at this
 *  point in time" — an assertion about the user's data, printed when OMEM had
 *  in fact failed to read it. A memory layer whose entire argument is that it
 *  never quietly decides anything cannot afford to quietly decide that.
 *
 *  So: unreadable is its own state, and it says which one it is. */
export function ErrorState({ title = "Could not read this", body, onRetry }:
  { title?: string; body?: string; onRetry?: () => void }) {
  return (
    <div role="alert"
      className="empty flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:gap-3">
      <AlertTriangle className="h-4 w-4 shrink-0 text-conflict" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <span className="font-medium text-fg">{title}</span>
        <span className="text-muted">
          {" "}{body ?? "The request did not succeed, so this is not a statement that there is nothing here."}
        </span>
      </div>
      {onRetry && (
        <button onClick={onRetry}
          className="tap shrink-0 rounded-md border px-2 py-1 text-xs text-muted hover:bg-raised hover:text-fg">
          Retry
        </button>
      )}
    </div>
  );
}

/** Loading placeholder. `aria-hidden` because a skeleton is a picture of
 *  content, not content: announcing it reads out nothing useful. The status is
 *  carried by the live region instead. */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("animate-pulse rounded bg-[color:var(--border)]", className)} />;
}

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center gap-2 py-8 text-sm text-muted">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> {label}…
    </div>
  );
}
export function Spinner() { return <Loader2 className="h-4 w-4 animate-spin text-muted" aria-hidden="true" />; }

/**
 * The belief rail, the signature element.
 *
 * A claim's belief interval drawn against a ruled span. The detail that matters:
 * an OPEN interval (end === null) gets no right-hand terminator and fades out
 * instead. "Still believed, nothing has ended it" is a real state in this
 * engine, and a bar that simply stopped would read as "ended here", which is
 * the single most consequential thing a reader could get wrong on this screen.
 * A closed interval gets a hard end-cap; a contradicted one is hatched.
 *
 * Kept exported as IntervalStrip too, since pages already call it that.
 */
export function BeliefRail({ start, end, now, min, max, state }: {
  start: number; end: number | null; now: number; min: number; max: number;
  state?: PropositionState;
}) {
  const span = Math.max(1, max - min);
  const pct = (t: number) => Math.min(100, Math.max(0, ((t - min) / span) * 100));
  const open = end === null;
  const l = pct(start);
  const r = pct(end ?? max);
  const contradicted = state === "CONTRADICTED" || state === "BELIEVED_FALSE";
  const label = `believed from ${start}${open ? ", still open" : ` to ${end}`}`;

  return (
    <div className="rail" role="img" aria-label={label} title={label}>
      <div
        className={cn("rail-span",
          contradicted ? "is-conflict" : open ? "is-believed is-open" : "is-believed")}
        style={{ left: `${l}%`, width: `${Math.max(1.5, r - l)}%` }}
      />
      {!open && <div className="rail-cap" style={{ left: `${r}%` }} />}
      <div className="rail-cap" style={{ left: `${l}%` }} />
      <div className="rail-now" style={{ left: `${pct(now)}%` }} title={`as of ${now}`} />
    </div>
  );
}

/** @deprecated name kept so existing pages keep working. This is BeliefRail. */
export const IntervalStrip = BeliefRail;
