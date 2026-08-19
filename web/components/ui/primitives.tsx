"use client";
import { cn } from "@/lib/cn";
import type { PropositionState } from "@/lib/api";
import { Loader2 } from "lucide-react";

/* OMEM design language, product side.
   State is shown as a dot + raw mono token, never a pill. Color carries meaning
   (believed / unknown / conflict / closed) and nothing else. Rounding only on
   real objects (panels, controls). Labels are quiet Inter; values are mono. */

const STATE_TONE: Record<PropositionState, string> = {
  BELIEVED_TRUE: "believed", BELIEVED_FALSE: "conflict",
  CONTRADICTED: "conflict", UNKNOWN: "unknown",
};
const DOT: Record<string, string> = {
  believed: "bg-believed", unknown: "bg-unknown", conflict: "bg-conflict",
  closed: "bg-closed", accent: "bg-accent", muted: "bg-muted",
};
const TXT: Record<string, string> = {
  believed: "text-believed", unknown: "text-unknown", conflict: "text-conflict",
  closed: "text-closed", accent: "text-accent", muted: "text-muted",
};

export function StateBadge({ state, size = "md" }: { state: PropositionState; size?: "sm" | "md" }) {
  const tone = STATE_TONE[state];
  return (
    <span className={cn("inline-flex items-center rounded-pill border font-semibold uppercase tracking-[0.05em]",
      TXT[tone], size === "sm" ? "px-2 py-px text-2xs" : "px-2.5 py-0.5 text-2xs")}
      style={{ borderColor: "currentColor", opacity: 0.95 }}>
      {state.replace("_", " ")}
    </span>
  );
}

export function Badge({ children, tone = "muted", className }:
  { children: React.ReactNode; tone?: "muted" | "accent" | "believed" | "unknown" | "conflict" | "closed"; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-pill border px-2 py-px text-2xs font-semibold uppercase tracking-[0.05em]",
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

export function Button({ children, onClick, variant = "primary", size = "md", disabled, type = "button", className }:
  { children: React.ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "ghost" | "danger"; size?: "sm" | "md"; disabled?: boolean; type?: "button" | "submit"; className?: string }) {
  const v: Record<string, string> = {
    primary: "rounded-md bg-accent text-white transition-opacity duration-[120ms] hover:opacity-[0.88]",
    secondary: "rounded-lg border bg-panel hover:bg-raised",
    ghost: "hover:bg-[color:var(--border)]/40",
    danger: "border border-[color:var(--conflict)]/50 text-conflict hover:bg-[color:var(--conflict)]/10",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={cn("inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:opacity-40 disabled:pointer-events-none",
        size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-[13px]", v[variant], className)}>
      {children}
    </button>
  );
}

export function Table({ children }: { children: React.ReactNode }) {
  return <div className="overflow-x-auto rounded-lg border"><table className="w-full text-sm">{children}</table></div>;
}
export function Th({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <th className={cn("border-b bg-panel px-3 py-2 text-left text-2xs font-medium text-muted", className)}>{children}</th>;
}
export function Td({ children, className }: { children?: React.ReactNode; className?: string }) {
  return <td className={cn("border-b border-[color:var(--border)]/60 px-3 py-2 align-middle", className)}>{children}</td>;
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
  return <div className={cn("animate-pulse rounded bg-[color:var(--border)]/60", className)} />;
}
export function Spinner() { return <Loader2 className="h-4 w-4 animate-spin text-muted" />; }

export function IntervalStrip({ start, end, now, min, max }: { start: number; end: number | null; now: number; min: number; max: number }) {
  const span = Math.max(1, max - min);
  const l = ((start - min) / span) * 100;
  const r = (((end ?? max) - min) / span) * 100;
  const open = end === null;
  return (
    <div className="relative h-1.5 w-full rounded bg-[color:var(--border)]/50">
      <div className={cn("absolute h-1.5 rounded", open ? "bg-believed" : "bg-closed")}
        style={{ left: `${l}%`, width: `${Math.max(2, r - l)}%` }} title={`[${start}, ${end ?? "open"})`} />
      <div className="absolute -top-[3px] h-3 w-px bg-accent" style={{ left: `${((now - min) / span) * 100}%` }} title={`now = ${now}`} />
    </div>
  );
}
