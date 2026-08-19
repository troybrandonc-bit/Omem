"use client";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton, Badge } from "@/components/ui/primitives";
import { useMemo } from "react";

// Deterministic radial layout by node kind (agents left, entities right, events bottom,
// assertions center). Purely presentational over the /graph endpoint's nodes+edges.
const KIND_COLOR: Record<string, string> = {
  agent: "var(--accent)", assertion: "var(--fg)", entity: "var(--believed)", event: "var(--unknown)",
};

export default function Graph() {
  const { project, asOf } = useApp();
  const router = useRouter();
  const { data, isLoading } = useQuery({ queryKey: ["graph", project, asOf], queryFn: () => api.graph(project, asOf ?? "now") });

  const layout = useMemo(() => {
    if (!data) return null;
    const W = 900, H = 560;
    const cols: Record<string, { x: number; items: string[] }> = {
      agent: { x: 130, items: [] }, assertion: { x: 450, items: [] },
      entity: { x: 770, items: [] }, event: { x: 450, items: [] },
    };
    data.nodes.forEach(n => { (cols[n.kind] || cols.assertion).items.push(n.id); });
    const pos: Record<string, { x: number; y: number }> = {};
    (["agent", "assertion", "entity"] as const).forEach(k => {
      const c = cols[k]; const n = c.items.length;
      c.items.forEach((id, i) => { pos[id] = { x: c.x, y: 60 + (i + 1) * (H - 160) / (n + 1) }; });
    });
    cols.event.items.forEach((id, i) => { pos[id] = { x: 220 + (i + 1) * (500) / (cols.event.items.length + 1), y: H - 40 }; });
    return { W, H, pos };
  }, [data]);

  if (isLoading || !data || !layout) return <Skeleton className="h-[560px]" />;

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="mb-1 display text-[21px]">Memory graph</h1>
      <p className="mb-4 text-sm text-muted">Agents assert claims about entities, grounded in events. Click a belief node to inspect it.</p>
      <div className="mb-3 flex gap-3 text-2xs">
        {Object.entries(KIND_COLOR).map(([k, c]) => (
          <span key={k} className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full" style={{ background: c }} />{k}</span>
        ))}
      </div>
      <div className="grid-bg rounded-lg border">
        <svg viewBox={`0 0 ${layout.W} ${layout.H}`} className="w-full">
          {data.edges.map((e, i) => {
            const a = layout.pos[e.from], b = layout.pos[e.to];
            if (!a || !b) return null;
            return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="var(--border)" strokeWidth={1} />;
          })}
          {data.nodes.map(n => {
            const p = layout.pos[n.id]; if (!p) return null;
            const clickable = n.kind === "assertion";
            return (
              <g key={n.id} className={clickable ? "cursor-pointer" : ""}
                onClick={() => clickable && router.push(`/assertions/${encodeURIComponent(n.id)}`)}>
                <circle cx={p.x} cy={p.y} r={n.kind === "assertion" ? 6 : 5} fill={KIND_COLOR[n.kind]} opacity={0.9} />
                <text x={p.x} y={p.y - 10} textAnchor="middle" fontSize={10} fill="var(--fg)" className="pointer-events-none">
                  {(n.label || n.id).slice(0, 22)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
