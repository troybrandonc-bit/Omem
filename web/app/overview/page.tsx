"use client";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api, formatWhen } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton, StateBadge } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { TrendingUp } from "lucide-react";

// Stripe-style titled panels. Every number and the sparkline come from the
// live store and its request log; nothing is synthesized.
export default function Overview() {
  const { project } = useApp();
  const { data } = useQuery({ queryKey: ["overview", project], queryFn: () => api.overview(project) });
  const { data: onb } = useQuery({ queryKey: ["onboarding", project], queryFn: () => api.onboardingState(project), refetchInterval: 6000 });
  const { data: logs } = useQuery({ queryKey: ["logs", project], queryFn: () => api.logs(project), refetchInterval: 5000 });
  const { data: beliefs } = useQuery({ queryKey: ["assertions", project, "recent"], queryFn: () => api.assertions(project, { open: true }) });

  if (!data) return <div className="space-y-5"><Skeleton className="h-40" /><Skeleton className="h-64" /></div>;
  const c = data.counts;
  const groundPct = Math.round(data.grounded_ratio * 100);
  const entries = logs?.data ?? [];
  const ok = entries.filter(l => l.status < 400).length;
  const rejected = entries.filter(l => l.status >= 400).length;
  const latest = (beliefs?.data ?? []).slice(-5).reverse();

  return (
    <div className="space-y-5">
      {/* Getting set up, without the onboarding-checklist cliche. A grid of
          check marks, hollow circles and struck-through labels over an "3/8"
          progress count is the template every generated dashboard ships. This
          says the same thing in one quiet line: the next milestone, and how
          many remain, with a way to see them all. */}
      {onb && onb.completed < onb.total && (() => {
        const next = onb.steps.find(s => !s.done);
        const left = onb.total - onb.completed;
        return (
          <section className="panel flex flex-wrap items-center gap-x-2.5 gap-y-1 px-4 py-2.5 text-sm">
            <span className="font-medium">Getting set up.</span>
            {next && <span className="text-muted">Next up: {next.label.toLowerCase()}.</span>}
            <Link href="/onboarding" className="link-underline ml-auto text-xs text-muted">
              {left} {left === 1 ? "step" : "steps"} left
            </Link>
          </section>
        );
      })()}
      {/* The state of the record.
          Six identical boxes gave every number the same voice, so nothing led
          and the eye had nowhere to go. There is one question on this screen.
          "Is anything wrong?", so conflicts take the focal position whenever
          there are any, and the counts that are merely context drop to a
          tertiary row. Three tiers, built from size + weight + colour. */}
      <section className="panel overflow-hidden">
        <header className="flex items-center justify-between border-b px-4 py-2.5">
          <h2 className="text-xs font-semibold">The record</h2>
          <Link href="/memory" className="link-underline text-xs text-muted">Open memory</Link>
        </header>

        <div className="grid sm:grid-cols-[1.2fr_1fr] sm:divide-x">
          {/* focal: what is currently believed, and how much of it is grounded */}
          <Link href="/memory" className="block px-5 py-4 transition-colors duration-150 ease-out hover:bg-raised">
            <div className="tech-label">Open beliefs</div>
            <div className="num mt-1.5 text-2xl leading-none tracking-[-0.02em]">{c.open_beliefs}</div>
            <div className="mt-3 flex items-center gap-2">
              <div className="h-1 flex-1 rounded-sm bg-chip">
                <div className="h-1 rounded-sm bg-believed" style={{ width: `${groundPct}%` }} />
              </div>
              <span className="num text-2xs text-muted">{groundPct}% grounded</span>
            </div>
          </Link>

          {/* the thing you came to find out. Loud only when it is real */}
          <Link href="/conflicts" className="block px-5 py-4 transition-colors duration-150 ease-out hover:bg-raised">
            <div className="tech-label">Unresolved conflicts</div>
            <div className={cn("num mt-1.5 text-2xl leading-none tracking-[-0.02em]",
                               c.conflicts > 0 ? "text-conflict" : "text-faint")}>
              {c.conflicts}
            </div>
            <div className="mt-3 flex items-center gap-1.5 text-2xs">
              {c.conflicts > 0
                ? <><span className="led conflict" aria-hidden="true" />
                    <span className="text-conflict">needs adjudication</span></>
                : <><span className="led believed" aria-hidden="true" />
                    <span className="text-muted">nothing contradicts</span></>}
            </div>
          </Link>
        </div>

        {/* tertiary: context, deliberately quiet */}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t px-5 py-2.5">
          {[["Agents", c.agents, "/agents"], ["Entities", c.entities, "/entities"],
            ["Events", c.events, "/timeline"], ["Assertions", c.assertions, "/memory"]]
            .map(([label, value, href]) => (
            <Link key={label as string} href={href as string}
              className="flex items-baseline gap-1.5 text-2xs text-muted transition-colors duration-150 ease-out hover:text-fg">
              <span className="num font-medium text-fg">{value as number}</span>{label}
            </Link>
          ))}
        </div>
      </section>

      {/* Monitoring panel */}
      <section className="panel overflow-hidden">
        <header className="flex items-center justify-between border-b px-4 py-2.5">
          <h2 className="text-sm font-semibold">Monitoring</h2>
          <Link href="/logs" className="text-sm font-medium text-accent hover:underline">View logs →</Link>
        </header>
        <div className="grid lg:grid-cols-2 lg:divide-x">
          <div className="px-4 py-3">
            <div className="mb-2 flex items-center gap-4 text-sm">
              <span className="flex items-center gap-1.5 font-medium">
                <TrendingUp className="h-3.5 w-3.5 text-accent" /> <span className="num">{ok}</span> requests
              </span>
              <span className="flex items-center gap-1.5 font-medium text-conflict">
                <TrendingUp className="h-3.5 w-3.5" /> <span className="num">{rejected}</span> rejected
              </span>
              <span className="num ml-auto text-muted">
                {entries.length ? `${Math.round((ok / entries.length) * 100)}% accepted` : "no traffic yet"}
              </span>
            </div>
            <Sparkline entries={entries} />
          </div>
          <div className="border-t px-4 py-3 lg:border-t-0">
            <div className="mb-2 text-sm font-semibold">Recent beliefs</div>
            <div className="divide-y">
              {latest.length === 0 && <div className="py-4 text-sm text-muted">No open beliefs yet.</div>}
              {latest.map(b => (
                <Link key={b.id} href={`/assertion?id=${encodeURIComponent(b.id)}`}
                  className="flex items-center justify-between gap-3 py-2 transition-colors hover:bg-raised">
                  <span className="truncate text-sm font-medium">{b.label || b.proposition}</span>
                  {(() => { const w = formatWhen(b.recorded_at, b.assertion_time);
                    return <span className="shrink-0 text-2xs text-faint" title={w.title}>{w.text}</span>; })()}
                </Link>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}

// Real request activity, bucketed by time from the live log. Chart SVG only.
function Sparkline({ entries }: { entries: { ts: number; status: number }[] }) {
  const W = 480, H = 96, N = 32;
  if (entries.length < 2) return <div className="grid h-24 place-items-center rounded-md bg-raised text-2xs text-faint">Waiting for traffic</div>;
  const ts = entries.map(e => e.ts);
  const min = Math.min(...ts), max = Math.max(...ts) || min + 1;
  const bins = Array(N).fill(0);
  entries.forEach(e => { bins[Math.min(N - 1, Math.floor(((e.ts - min) / (max - min || 1)) * N))]++; });
  const peak = Math.max(...bins, 1);
  const pts = bins.map((v, i) => `${(i / (N - 1)) * W},${H - 6 - (v / peak) * (H - 16)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-24 w-full">
      {[0.25, 0.5, 0.75].map(f => (
        <line key={f} x1="0" x2={W} y1={H * f} y2={H * f} stroke="var(--border)" strokeWidth="1" />
      ))}
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth="1.75" strokeLinejoin="round" />
    </svg>
  );
}
