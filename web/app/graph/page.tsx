"use client";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { api, type GraphData } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton, EmptyState, Button } from "@/components/ui/primitives";
import { AlertTriangle, Network, Plus, Minus, Maximize2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

/* The belief graph as an instrument you can move through, not a static diagram.
 *
 * Agents assert claims about entities, grounded in events. Those are the four
 * node kinds. The layout is a dependency-free force relaxation (radial seed,
 * then springs pull connected nodes together and a repulsion keeps chips from
 * overlapping), so structure emerges from the edges rather than being imposed
 * by a column per kind. Nodes are chips, not dots: a kind-tinted ring, a soft
 * lift off the canvas, the label legible at a glance. Zoom, pan, fit, filter by
 * kind, and click a belief to open it.
 *
 * The lift on a node is a drop-shadow on ~a few dozen shapes, which rasterises
 * once; it is not the per-frame backdrop blur the rest of the product removed. */

const KIND: Record<string, { color: string; label: string }> = {
  agent: { color: "var(--accent)", label: "Agent" },
  assertion: { color: "var(--fg)", label: "Belief" },
  entity: { color: "var(--believed)", label: "Entity" },
  event: { color: "var(--unknown)", label: "Event" },
};
const KIND_ORDER = ["agent", "assertion", "entity", "event"] as const;

type Pos = Record<string, { x: number; y: number }>;

const NODE_H = 30;
function nodeWidth(n: { label?: string | null; proposition?: string; id: string }): number {
  const label = (n.label || n.proposition || n.id).slice(0, 26);
  return Math.max(66, Math.min(240, label.length * 7 + 42));
}

function layout(nodes: GraphData["nodes"], edges: GraphData["edges"]): Pos {
  const n = nodes.length;
  const pos: Pos = {};
  if (!n) return pos;
  const w: Record<string, number> = {};
  nodes.forEach(nd => { w[nd.id] = nodeWidth(nd); });
  const R = Math.max(280, Math.sqrt(n) * 96);
  nodes.forEach((nd, i) => {
    const a = (i / n) * Math.PI * 2;
    pos[nd.id] = { x: Math.cos(a) * R, y: Math.sin(a) * R };
  });
  const adj: Record<string, string[]> = {};
  edges.forEach(e => {
    (adj[e.from] = adj[e.from] || []).push(e.to);
    (adj[e.to] = adj[e.to] || []).push(e.from);
  });
  // Rectangle-aware separation: pills are wide, so a circular repulsion let
  // long labels overlap. Two chips that overlap in BOTH axes are pushed apart
  // along the axis of least penetration, which resolves the collision exactly
  // without exploding the layout.
  const separate = () => {
    let moved = 0;
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const a = pos[nodes[i].id], b = pos[nodes[j].id];
      const dx = a.x - b.x, dy = a.y - b.y;
      const needX = (w[nodes[i].id] + w[nodes[j].id]) / 2 + 34;
      const needY = NODE_H + 30;
      const ox = needX - Math.abs(dx), oy = needY - Math.abs(dy);
      if (ox > 0 && oy > 0) {
        if (ox < oy) { const s = (ox / 2) * (dx < 0 ? -1 : 1); a.x += s; b.x -= s; }
        else { const s = (oy / 2) * (dy < 0 ? -1 : 1); a.y += s; b.y -= s; }
        moved++;
      }
    }
    return moved;
  };
  // Springs pull connected nodes together; separation keeps chips off each
  // other. They fight, so springs run first.
  for (let pass = 0; pass < 120; pass++) {
    nodes.forEach(nd => {
      const nb = adj[nd.id];
      if (!nb || !nb.length) return;
      let cx = 0, cy = 0;
      nb.forEach(id => { if (pos[id]) { cx += pos[id].x; cy += pos[id].y; } });
      cx /= nb.length; cy /= nb.length;
      pos[nd.id].x += (cx - pos[nd.id].x) * 0.055;
      pos[nd.id].y += (cy - pos[nd.id].y) * 0.055;
    });
    separate();
  }
  // Then separation alone until nothing overlaps (or a cap), so the FINAL
  // positions a person sees have no collisions, whatever the springs wanted.
  for (let pass = 0; pass < 200 && separate() > 0; pass++) { /* settle */ }
  return pos;
}

export default function Graph() {
  const { project, asOf } = useApp();
  const router = useRouter();
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["graph", project, asOf],
    queryFn: () => api.graph(project, asOf ?? "now"),
    enabled: !!project,
  });

  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const svgRef = useRef<SVGSVGElement>(null);
  const vpRef = useRef<SVGGElement>(null);
  const view = useRef({ x: 0, y: 0, k: 1 });

  const pos = useMemo(() => (data ? layout(data.nodes, data.edges) : {}), [data]);

  const shown = useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    const nodes = data.nodes.filter(n => !hidden.has(n.kind));
    const keep = new Set(nodes.map(n => n.id));
    const edges = data.edges.filter(e => keep.has(e.from) && keep.has(e.to));
    return { nodes, edges };
  }, [data, hidden]);

  const apply = () => {
    if (vpRef.current) vpRef.current.setAttribute("transform",
      `translate(${view.current.x},${view.current.y}) scale(${view.current.k})`);
  };

  const fit = () => {
    const svg = svgRef.current;
    if (!svg || !shown.nodes.length) return;
    const xs = shown.nodes.map(n => pos[n.id]?.x ?? 0);
    const ys = shown.nodes.map(n => pos[n.id]?.y ?? 0);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const r = svg.getBoundingClientRect();
    const w = maxX - minX + 300, h = maxY - minY + 180;
    const k = Math.min(1.3, Math.max(0.4, Math.min(r.width / w, r.height / h)));
    view.current = { k, x: r.width / 2 - ((minX + maxX) / 2) * k, y: r.height / 2 - ((minY + maxY) / 2) * k };
    apply();
  };

  // Fit whenever the shown set changes (first load, filter toggles).
  useEffect(() => { fit(); /* eslint-disable-next-line */ }, [shown, pos]);

  // Pan and wheel-zoom, imperative so a drag does not re-render the graph.
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    let panning = false, sx = 0, sy = 0;
    const down = (e: PointerEvent) => {
      const t = e.target as Element;
      if (t === svg || t.classList.contains("g-canvas") || t.tagName === "path" || t.tagName === "line") {
        panning = true; sx = e.clientX - view.current.x; sy = e.clientY - view.current.y;
        svg.style.cursor = "grabbing"; svg.setPointerCapture(e.pointerId);
      }
    };
    const move = (e: PointerEvent) => {
      if (!panning) return;
      view.current.x = e.clientX - sx; view.current.y = e.clientY - sy; apply();
    };
    const up = () => { panning = false; svg.style.cursor = "grab"; };
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      const r = svg.getBoundingClientRect();
      const mx = e.clientX - r.left, my = e.clientY - r.top;
      const k2 = Math.min(3, Math.max(0.2, view.current.k * (e.deltaY < 0 ? 1.1 : 0.9)));
      view.current.x = mx - (mx - view.current.x) * (k2 / view.current.k);
      view.current.y = my - (my - view.current.y) * (k2 / view.current.k);
      view.current.k = k2; apply();
    };
    svg.addEventListener("pointerdown", down);
    svg.addEventListener("pointermove", move);
    svg.addEventListener("pointerup", up);
    svg.addEventListener("wheel", wheel, { passive: false });
    return () => {
      svg.removeEventListener("pointerdown", down);
      svg.removeEventListener("pointermove", move);
      svg.removeEventListener("pointerup", up);
      svg.removeEventListener("wheel", wheel);
    };
  }, []);

  const zoom = (f: number) => {
    const svg = svgRef.current; if (!svg) return;
    const r = svg.getBoundingClientRect();
    const k2 = Math.min(3, Math.max(0.2, view.current.k * f));
    view.current.x = r.width / 2 - (r.width / 2 - view.current.x) * (k2 / view.current.k);
    view.current.y = r.height / 2 - (r.height / 2 - view.current.y) * (k2 / view.current.k);
    view.current.k = k2; apply();
  };

  if (!project || isLoading) return <Skeleton className="h-[600px]" />;

  if (isError || !data) {
    return (
      <div className="mx-auto max-w-6xl">
        <h1 className="mb-4 display text-lg">Belief graph</h1>
        <EmptyState icon={AlertTriangle} title="Could not load the graph."
          body={error instanceof Error ? error.message : "The OMEM server did not answer."}
          action={<Button variant="secondary" size="sm" onClick={() => refetch()}>Retry</Button>} />
      </div>
    );
  }

  if (!data.nodes.length) {
    return (
      <div className="mx-auto max-w-6xl">
        <h1 className="mb-1 display text-lg">Belief graph</h1>
        <p className="mb-4 text-sm text-muted">Agents assert claims about entities, grounded in events.</p>
        <EmptyState icon={Network} title="Nothing to graph yet."
          body="This project has no assertions. Write one with mem.remember(…), or start the server with OMEM_SEED_DEMO=1 for a sample project."
          action={<Button variant="secondary" size="sm" onClick={() => router.push("/playground")}>Open playground</Button>} />
      </div>
    );
  }

  const counts: Record<string, number> = {};
  data.nodes.forEach(n => { counts[n.kind] = (counts[n.kind] || 0) + 1; });

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div>
          <h1 className="display text-lg">Belief graph</h1>
          <p className="mt-1 text-sm text-muted">
            Agents assert claims about entities, grounded in events. Drag to pan, scroll to zoom, click a belief to open it.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {KIND_ORDER.filter(k => counts[k]).map(k => {
            const off = hidden.has(k);
            return (
              <button key={k}
                onClick={() => setHidden(s => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; })}
                className="tap inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-2xs font-medium transition-colors duration-1 ease-out hover:bg-raised"
                style={{ opacity: off ? 0.4 : 1, borderColor: off ? "var(--border)" : "var(--line-strong)" }}>
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: KIND[k].color }} />
                {KIND[k].label}
                <span className="num text-faint">{counts[k]}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="relative overflow-hidden rounded-lg border bg-panel">
        <div className="absolute left-3 top-3 z-10 flex gap-1.5">
          {[[Plus, () => zoom(1.2), "Zoom in"], [Minus, () => zoom(0.83), "Zoom out"], [Maximize2, fit, "Fit"]].map(
            ([Icon, fn, label]: any, i) => (
              <button key={i} onClick={fn} aria-label={label} title={label}
                className="tap grid h-8 w-8 place-items-center rounded-md border bg-panel text-muted shadow-sm transition-colors duration-1 ease-out hover:bg-raised hover:text-fg">
                <Icon className="h-4 w-4" />
              </button>
            ))}
        </div>
        <svg ref={svgRef} className="g-canvas block h-[600px] w-full cursor-grab select-none"
          style={{ background: "var(--bg)", touchAction: "none" }}>
          <g ref={vpRef}>
            {shown.edges.map((e, i) => {
              const a = pos[e.from], b = pos[e.to];
              if (!a || !b) return null;
              return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke="var(--line-strong)" strokeWidth={1.25} strokeOpacity={0.5} />;
            })}
            {shown.nodes.map(n => {
              const p = pos[n.id]; if (!p) return null;
              const kind = KIND[n.kind] || KIND.assertion;
              const label = (n.label || n.proposition || n.id).slice(0, 26);
              const w = nodeWidth(n);
              const h = NODE_H;
              const clickable = n.kind === "assertion";
              return (
                <g key={n.id} transform={`translate(${p.x},${p.y})`}
                  style={{ cursor: clickable ? "pointer" : "default" }}
                  onClick={() => clickable && router.push(`/assertion?id=${encodeURIComponent(n.id)}`)}>
                  <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={h / 2}
                    fill="var(--panel)" stroke={kind.color} strokeWidth={1.5}
                    style={{ filter: "drop-shadow(0 3px 8px rgba(13,15,18,0.10))" }} />
                  <circle cx={-w / 2 + 16} cy={0} r={4.5} fill={kind.color} />
                  <text x={-w / 2 + 28} y={4} fontSize={12.5} fontWeight={500}
                    fill="var(--fg)" className="pointer-events-none">{label}</text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
    </div>
  );
}
