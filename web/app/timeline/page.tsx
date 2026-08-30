"use client";
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, formatWhen, type Assertion } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton, EmptyState, ErrorState } from "@/components/ui/primitives";
import { Clock, MessagesSquare, Sparkles, RefreshCw, Undo2, AlertTriangle,
  GitBranch, Radio, type LucideIcon } from "lucide-react";

// The rail used to be a column of identical blue squares. An event now carries
// an ICON for what kind of thing happened, and a COLOUR for who it happened
// through -- the observing agent -- so the timeline reads at a glance the way
// Linear's does: shape tells you what, hue tells you who.

const KIND_ICON: Record<string, LucideIcon> = {
  observation: MessagesSquare,
  assert: Sparkles, belief: Sparkles,
  supersede: RefreshCw, retract: Undo2,
  contradiction: AlertTriangle, conflict: AlertTriangle,
  derive: GitBranch, rule: GitBranch,
};

// Full literal class strings -- Tailwind only ships classes it can see written
// out, so these cannot be built from a colour variable.
const TONES = [
  { icon: "text-indigo-500",  bg: "bg-indigo-500/15",  dot: "bg-indigo-500" },
  { icon: "text-violet-500",  bg: "bg-violet-500/15",  dot: "bg-violet-500" },
  { icon: "text-sky-500",     bg: "bg-sky-500/15",     dot: "bg-sky-500" },
  { icon: "text-emerald-500", bg: "bg-emerald-500/15", dot: "bg-emerald-500" },
  { icon: "text-amber-500",   bg: "bg-amber-500/15",   dot: "bg-amber-500" },
  { icon: "text-rose-500",    bg: "bg-rose-500/15",    dot: "bg-rose-500" },
  { icon: "text-cyan-500",    bg: "bg-cyan-500/15",    dot: "bg-cyan-500" },
];

function agentName(a: string): string {
  return a.replace(/^agent:/, "").replace(/@.*/, "");
}
function subjectLabel(id: string): string {
  const rest = id.includes(":") ? id.slice(id.indexOf(":") + 1) : id;
  return rest.split("@")[0].replace(/[-_.]/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

export default function Timeline() {
  const { project, asOf } = useApp();
  const tl = useQuery({
    queryKey: ["timeline", project, asOf],
    queryFn: () => api.timeline(project, asOf ?? "now"), enabled: !!project });
  // The event knows WHEN it happened; the assertion it produced knows WHO and
  // ABOUT WHOM. They share event_time, so one pass joins them with no extra call.
  const asserts = useQuery({
    queryKey: ["timeline-assertions", project],
    queryFn: () => api.assertions(project, { as_of: "now" }), enabled: !!project });

  const { events, byTime, agentTone } = useMemo(() => {
    const byTime = new Map<number, Assertion>();
    for (const a of asserts.data?.data ?? []) {
      if (a.event_time != null && !byTime.has(a.event_time)) byTime.set(a.event_time, a);
    }
    // Stable colour per agent: sort the distinct agents and hand out tones in
    // order, so the same bot keeps the same hue across a session.
    const agents = [...new Set([...byTime.values()].map(a => a.agent))].sort();
    const agentTone = new Map(agents.map((a, i) => [a, TONES[i % TONES.length]]));
    return { events: tl.data?.events ?? [], byTime, agentTone };
  }, [tl.data, asserts.data]);

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-1 display text-2xl">Timeline</h1>
      <p className="mb-5 text-sm text-muted">Every event OMEM recorded, newest work at the bottom, coloured by the agent it came through.</p>
      {tl.isLoading ? <Skeleton className="h-40" /> :
        tl.isError || !tl.data ? <ErrorState title="Could not read the timeline" onRetry={() => tl.refetch()} /> :
        events.length === 0 ? <EmptyState icon={Clock} title="No events yet" /> :
        <div className="relative pl-1">
          <div className="absolute left-[13px] top-3 bottom-3 w-px bg-border" />
          {events.map(e => {
            const src = e.event_time != null ? byTime.get(e.event_time) : undefined;
            const tone = (src && agentTone.get(src.agent)) || TONES[0];
            const Icon = KIND_ICON[e.kind ?? ""] ?? Radio;
            const w = formatWhen(e.recorded_at, e.event_time);
            return (
              <div key={e.id} className="relative mb-2.5 flex items-start gap-3">
                <div className={`relative z-10 mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ring-4 ring-[color:var(--bg)] ${tone.bg}`}>
                  <Icon className={`h-3.5 w-3.5 ${tone.icon}`} aria-hidden="true" />
                </div>
                <div className="panel flex-1 px-3.5 py-2.5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 text-sm font-medium leading-snug">{e.label || e.id}</div>
                    <span className="shrink-0 text-2xs text-faint" title={w.title}>{w.text}</span>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-2xs text-muted">
                    <span className="capitalize">{e.kind || "event"}</span>
                    {src && <><span className="text-faint">·</span>
                      <span className={"font-medium " + tone.icon}>{agentName(src.agent)}</span></>}
                    {src?.subjects?.[0] && <><span className="text-faint">·</span>
                      <span>about <span className="text-fg">{subjectLabel(src.subjects[0])}</span></span></>}
                  </div>
                </div>
              </div>
            );
          })}
        </div>}
    </div>
  );
}
