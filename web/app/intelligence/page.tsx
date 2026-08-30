"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton } from "@/components/ui/primitives";
import { Lightbulb, HelpCircle } from "lucide-react";
import Link from "next/link";

// Enterprise memory intelligence. Everything here is computed by the engine over
// live data, never synthesized: the health metrics and conflicts from current
// belief state, the priors mined across subjects, the hunches leapt from them.

function humanizeProp(p: string): string {
  return p.replace(/^not:/, "not ").replace(/_/g, " ");
}
function subjectLabel(id: string): string {
  const rest = id.includes(":") ? id.slice(id.indexOf(":") + 1) : id;
  return rest.replace(/[-_.]/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}

export default function Intelligence() {
  const { project } = useApp();
  const { data } = useQuery({ queryKey: ["intelligence", project], queryFn: () => api.intelligence(project), refetchInterval: 5000 });
  const priors = useQuery({ queryKey: ["priors", project], queryFn: () => api.priors(project), enabled: !!project });
  const hunches = useQuery({ queryKey: ["expectations", project], queryFn: () => api.expectations(project), enabled: !!project });
  if (!data) return <div className="space-y-5"><Skeleton className="h-40" /><Skeleton className="h-40" /></div>;
  const h = data.memory_health;
  const pct = (n: number) => `${Math.round(n * 100)}%`;
  const learned = (priors.data?.data ?? []).filter(p => p.fires);
  const suspected = [...(hunches.data?.data ?? [])].sort((a, b) => b.strength - a.strength);

  return (
    <div className="space-y-5">
      <h1 className="display text-2xl">Memory intelligence</h1>

      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-sm font-semibold">Memory health</h2></header>
        <div className="grid grid-cols-2 divide-x lg:grid-cols-4">
          {[["Total beliefs", String(h.total_assertions)],
            ["Grounding coverage", pct(h.grounding_coverage)],
            ["Provenance coverage", pct(h.provenance_coverage)],
            ["Unresolved conflicts", String(h.unresolved_conflicts)]].map(([l, v]) => (
            <div key={l} className="px-4 py-3">
              <div className="text-2xs text-faint">{l}</div>
              <div className="num mt-1 text-lg leading-none">{v}</div>
            </div>
          ))}
        </div>
      </section>

      {/* What OMEM has LEARNED: regularities mined across subjects. Counts about
          people in general, never a fact about any one person. */}
      <section className="panel overflow-hidden">
        <header className="flex items-center gap-2 border-b px-4 py-2.5">
          <Lightbulb className="h-3.5 w-3.5 text-amber-500" />
          <h2 className="text-sm font-semibold">What OMEM has learned</h2>
          <span className="text-2xs text-faint">patterns across subjects, not a fact about anyone</span>
        </header>
        <div className="divide-y">
          {priors.isLoading ? <div className="p-4"><Skeleton className="h-16" /></div> :
            learned.length === 0 ? <div className="empty m-5">No pattern has repeated across enough subjects to learn from yet.</div> :
            learned.map(pr => {
              const denom = pr.in_population.support + pr.in_population.refute;
              return (
                <div key={pr.id} className="flex items-center justify-between gap-4 px-4 py-3">
                  <div className="text-sm">
                    <span className="font-medium">{humanizeProp(pr.antecedent)}</span>
                    <span className="text-faint"> → usually </span>
                    <span className="font-medium">{humanizeProp(pr.consequent)}</span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2.5">
                    <div className="h-1.5 w-16 rounded-sm bg-chip"><div className="h-1.5 rounded-sm bg-amber-500" style={{ width: pct(pr.in_population.rate) }} /></div>
                    <span className="num w-24 text-right text-2xs text-muted">{pct(pr.in_population.rate)} of {denom}</span>
                  </div>
                </div>
              );
            })}
        </div>
      </section>

      {/* What OMEM SUSPECTS: hunches leapt from those patterns onto subjects that
          hold the antecedent but have said nothing about the consequent. Never a
          belief -- each is a question with a live case file. */}
      <section className="panel overflow-hidden">
        <header className="flex items-center gap-2 border-b px-4 py-2.5">
          <HelpCircle className="h-3.5 w-3.5 text-violet-500" />
          <h2 className="text-sm font-semibold">What OMEM suspects</h2>
          <span className="text-2xs text-faint">hunches, never beliefs — each is a question with a case file</span>
        </header>
        <div className="divide-y">
          {hunches.isLoading ? <div className="p-4"><Skeleton className="h-16" /></div> :
            suspected.length === 0 ? <div className="empty m-5">Nothing suspected. OMEM only guesses where a learned pattern meets a silence.</div> :
            suspected.map(hy => (
              <div key={hy.id} className="px-4 py-3">
                <div className="flex items-center justify-between gap-4">
                  <div className="text-sm">
                    <Link href={`/entity?id=${encodeURIComponent(hy.subject)}`} className="font-medium hover:text-accent">{subjectLabel(hy.subject)}</Link>
                    <span className="text-faint"> — probably </span>
                    <span className="font-medium">{humanizeProp(hy.proposition)}</span>
                  </div>
                  <div className="flex shrink-0 items-center gap-2.5">
                    <div className="h-1.5 w-16 rounded-sm bg-chip"><div className="h-1.5 rounded-sm bg-violet-500" style={{ width: pct(hy.strength) }} /></div>
                    <span className="num w-16 text-right text-2xs text-muted">{pct(hy.strength)} · {hy.status}</span>
                  </div>
                </div>
                <div className="mt-1 text-2xs leading-relaxed text-faint">{hy.because}</div>
              </div>
            ))}
        </div>
      </section>

      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-sm font-semibold">Unresolved conflicts</h2></header>
        <div className="divide-y">
          {data.conflicts.length === 0 && <div className="empty m-5">No contradictions detected across current memory.</div>}
          {data.conflicts.map((c, i) => (
            <div key={i} className="flex items-center justify-between px-4 py-2.5">
              <div>
                <div className="text-sm font-medium">{c.proposition}</div>
                <div className="text-2xs text-faint">{c.subjects.join(", ")}</div>
              </div>
              <Link href="/conflicts" className="text-2xs font-semibold text-accent hover:underline">Inspect →</Link>
            </div>
          ))}
        </div>
      </section>

      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-sm font-semibold">Source authority</h2></header>
        <div className="divide-y">
          {data.sources.length === 0 && <div className="empty m-5">No ingestion sources connected. Facts here came through observe(), which carries no external source to rank.</div>}
          {data.sources.map((s, i) => (
            <div key={i} className="flex items-center justify-between px-4 py-2.5">
              <div>
                <div className="text-sm font-medium">{s.name}</div>
                <div className="text-2xs text-faint">{s.kind}</div>
              </div>
              <div className="flex items-center gap-3">
                <div className="h-1.5 w-24 rounded-sm bg-chip"><div className="h-1.5 rounded-sm bg-accent" style={{ width: pct(s.authority) }} /></div>
                <span className="num w-9 text-right text-2xs text-muted">{s.authority}</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
