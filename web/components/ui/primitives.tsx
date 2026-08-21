"use client";
import { cn } from "@/lib/cn";
import type { PropositionState } from "@/lib/api";
import { Loader2 } from "lucide-react";

/* OMEM design language, product side. See app/globals.css for the direction.
   Two rules do most of the work here:
     - State is SHAPE first and colour second, so it survives a black-and-white
       screenshot and colour-blind vision. Hue-only dots fail both.
     - Colour is data. Buttons and links are ink; the only chroma on screen is
       belief state, so the four things that mean something are the four things
       the eye is drawn to. */

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

/** Primary is ink, not a brand hue, see the colour rule above. 32px high at
 *  md, which is the row height everywhere else in the app. */
export function Button({ children, onClick, variant = "primary", size = "md", disabled, type = "button", className }:
  { children: React.ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "ghost" | "danger"; size?: "sm" | "md"; disabled?: boolean; type?: "button" | "submit"; className?: string }) {
  const v: Record<string, string> = {
    primary: "bg-accent text-accentFg hover:opacity-90",
    secondary: "border border-[color:var(--line-strong)] bg-panel hover:bg-raised",
    ghost: "text-muted hover:bg-chip hover:text-fg",
    danger: "border border-[color:var(--conflict)]/50 text-conflict hover:bg-conflictBg",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={cn(
        "inline-flex items-center justify-center gap-1.5 rounded font-medium",
        "transition-[background-color,opacity,transform] duration-150 ease-out",
        "active:scale-[0.97] disabled:opacity-40 disabled:pointer-events-none disabled:active:scale-100",
        size === "sm" ? "h-7 px-2.5 text-2xs" : "h-8 px-3 text-xs",
        v[variant], className)}>
      {children}
    </button>
  );
}

export function Table({ children }: { children: React.ReactNode }) {
  return <div className="overflow-x-auto rounded-md border"><table className="w-full text-sm">{children}</table></div>;
}
export function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <th className={cn("border-b bg-raised px-3 py-1.5 text-left text-2xs font-semibold uppercase tracking-[0.06em] text-faint", className)}>{children}</th>;
}
export function Td({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <td className={cn("border-b border-[color:var(--border)]/70 px-3 py-2 align-middle", className)}>{children}</td>;
}

export function EmptyState({ icon: _icon, title, body, action }: { icon?: any; title: string; body?: string; action?: React.ReactNode }) {
  return (
    <div className="empty">
      <span className="font-medium text-fg">{title}</span>
      {body && <span> {body}</span>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded bg-[color:var(--border)]", className)} />;
}
export function Spinner() { return <Loader2 className="h-4 w-4 animate-spin text-muted" />; }

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
