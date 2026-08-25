"use client";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton, Badge, EmptyState, Button } from "@/components/ui/primitives";
import { AlertTriangle, Network } from "lucide-react";
import { useMemo } from "react";

// Deterministic radial layout by node kind (agents left, entities right, events bottom,
// assertions center). Purely presentational over the /graph endpoint's nodes+edges.
const KIND_COLOR: Record<string, string> = {
  agent: "var(--accent)", assertion: "var(--fg)", entity: "var(--believed)", event: "var(--unknown)",
};

export default function Graph() {
  const { project, asOf } = useApp();
  const router = useRouter();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["graph", project, asOf],
    queryFn: () => api.graph(project, asOf ?? "now"),
    // Without a project id there is nothing to ask for, and asking anyway is
    // what produced a permanent skeleton on first load while Providers was
    // still resolving which project to use.
    enabled: !!project,
  });

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

  /* Three outcomes, three answers.
   *
   * This was one line — `if (isLoading || !data || !layout) return <Skeleton/>`
   * — which collapsed loading, failed and empty into a shimmering grey box that
   * never resolved. Two of those three are lies. A query that has ERRORED is not
   * loading, and telling somebody it still is means they wait for something that
   * is never going to arrive; a project with no memories in it is not loading
   * either, and it is the state every single new install starts in.
   *
   * The empty case is the important one. The graph is the first page most people
   * open after starting the server, the database is empty until they write
   * something, and what they got was an indefinite skeleton — indistinguishable
   * from a hung page. It now says the graph is empty and what to do about it. */
  /* `!project` FIRST, and it is not the same as loading.
   * In react-query v5 a disabled query reports isPending with fetchStatus idle,
   * so `isLoading` is FALSE while `enabled` is false. Without this guard the
   * disabled state would fall straight through to the error branch below and
   * accuse the server of failing before a single request had been made. */
  if (!project) return <Skeleton className="h-[560px]" />;

  if (isLoading) return <Skeleton className="h-[560px]" />;

  if (isError || !data || !layout) {
    return (
      <div className="mx-auto max-w-6xl">
        <h1 className="mb-4 display text-lg">Memory graph</h1>
        <EmptyState
          icon={AlertTriangle}
          title="Could not load the graph."
          body={error instanceof Error ? error.message : "The OMEM server did not answer. Check that it is running on port 8787."}
          action={<Button variant="secondary" size="sm" onClick={() => refetch()}>Retry</Button>}
        />
      </div>
    );
  }

  if (!data.nodes.length) {
    return (
      <div className="mx-auto max-w-6xl">
        <h1 className="mb-1 display text-lg">Memory graph</h1>
        <p className="mb-4 text-sm text-muted">
          Agents assert claims about entities, grounded in events.
        </p>
        <EmptyState
          icon={Network}
          title="Nothing to graph yet."
          body="This project has no assertions. Write one with mem.remember(…), or start the server with OMEM_SEED_DEMO=1 for a sample project."
          action={<Button variant="secondary" size="sm" onClick={() => router.push("/playground")}>Open playground</Button>}
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl">
      <h1 className="mb-1 display text-lg">Memory graph</h1>
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
                onClick={() => clickable && router.push(`/assertion?id=${encodeURIComponent(n.id)}`)}>
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
