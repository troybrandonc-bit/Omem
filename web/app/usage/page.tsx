"use client";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton } from "@/components/ui/primitives";

// Every number here is a real usage_events count from the backend. No estimates.
export default function Usage() {
  const { project } = useApp();
  const { data } = useQuery({ queryKey: ["usage", project], queryFn: () => api.usageMetrics(project), refetchInterval: 5000 });
  const { data: billing } = useQuery({ queryKey: ["billing"], queryFn: api.billing });
  if (!data) return <div className="space-y-5"><Skeleton className="h-40" /></div>;

  const METRICS: [string, string][] = [
    ["assertions_created", "Memories created"], ["source_records", "Source records"],
    ["agent_queries", "Agent queries"], ["provenance_queries", "Provenance queries"],
    ["api_requests", "API requests"], ["llm_tokens", "LLM tokens"],
  ];
  const has = Object.keys(data.metrics).length > 0;

  return (
    <div className="space-y-5">
      <div className="flex items-baseline justify-between">
        <h1 className="display text-2xl">Usage</h1>
        {billing && <span className="text-sm text-muted">Plan: <span className="font-semibold text-fg">{billing.plans[billing.plan]?.name ?? billing.plan}</span></span>}
      </div>

      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5"><h2 className="text-sm font-semibold">This project</h2></header>
        {!has ? <div className="empty m-5">No usage yet. Connect a source or send an assertion to start metering.</div> : (
          <div className="grid grid-cols-2 divide-x divide-y sm:grid-cols-3 lg:grid-cols-6 lg:divide-y-0">
            {METRICS.map(([k, label]) => (
              <div key={k} className="px-4 py-3">
                <div className="text-2xs text-faint">{label}</div>
                <div className="num mt-1 text-lg leading-none">{data.metrics[k] ?? 0}</div>
                <Spark values={data.series[k] ?? []} />
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function Spark({ values }: { values: number[] }) {
  if (values.length < 2) return <div className="mt-2 h-6" />;
  const W = 90, H = 22, peak = Math.max(...values, 1);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * W},${H - (v / peak) * (H - 3)}`).join(" ");
  return <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 h-6 w-full"><polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth="1.5" /></svg>;
}
