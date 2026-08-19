"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton } from "@/components/ui/primitives";
import Link from "next/link";

// Enterprise memory intelligence. Grounding/provenance coverage and conflicts
// are computed by the engine over live data — never synthesized.
export default function Intelligence() {
  const { project } = useApp();
  const { data } = useQuery({ queryKey: ["intelligence", project], queryFn: () => api.intelligence(project), refetchInterval: 5000 });
  if (!data) return <div className="space-y-5"><Skeleton className="h-40" /><Skeleton className="h-40" /></div>;
  const h = data.memory_health;
  const pct = (n: number) => `${Math.round(n * 100)}%`;

  return (
    <div className="space-y-5">
      <h1 className="display text-[24px]">Memory intelligence</h1>

      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-[14px] font-semibold">Memory health</h2></header>
        <div className="grid grid-cols-2 divide-x lg:grid-cols-4">
          {[["Total beliefs", String(h.total_assertions)],
            ["Grounding coverage", pct(h.grounding_coverage)],
            ["Provenance coverage", pct(h.provenance_coverage)],
            ["Unresolved conflicts", String(h.unresolved_conflicts)]].map(([l, v]) => (
            <div key={l} className="px-4 py-3">
              <div className="text-2xs text-faint">{l}</div>
              <div className="num mt-1 text-[20px] leading-none">{v}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-[14px] font-semibold">Unresolved conflicts</h2></header>
        <div className="divide-y">
          {data.conflicts.length === 0 && <div className="empty m-5">No contradictions detected across current memory.</div>}
          {data.conflicts.map((c, i) => (
            <div key={i} className="flex items-center justify-between px-4 py-2.5.5">
              <div>
                <div className="text-[14px] font-medium">{c.proposition}</div>
                <div className="text-2xs text-faint">{c.subjects.join(", ")}</div>
              </div>
              <Link href="/conflicts" className="text-2xs font-semibold text-accent hover:underline">Inspect →</Link>
            </div>
          ))}
        </div>
      </section>

      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-[14px] font-semibold">Source authority</h2></header>
        <div className="divide-y">
          {data.sources.length === 0 && <div className="empty m-5">No ingestion sources connected.</div>}
          {data.sources.map((s, i) => (
            <div key={i} className="flex items-center justify-between px-4 py-2.5.5">
              <div>
                <div className="text-[14px] font-medium">{s.name}</div>
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
