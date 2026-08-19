"use client";
import type { ProvNode, ProvEdge } from "@/lib/api";
import { cn } from "@/lib/cn";
import { FileText, Zap, Layers } from "lucide-react";

// Layered top-down DAG. The consequent assertion at top; antecedents below; Event
// roots at the bottom, colored green (grounding). Pure layout over the edges the
// engine returned. No semantic computation here.
export function ProvenanceDAG({ nodes, edges, rootId }: { nodes: ProvNode[]; edges: ProvEdge[]; rootId: string }) {
  // assign layers by longest distance from root following consequent->antecedent edges
  const adj: Record<string, string[]> = {};
  edges.forEach(e => { (adj[e.from] ||= []).push(e.to); });
  const layer: Record<string, number> = {};
  const visit = (id: string, d: number, seen: Set<string>) => {
    layer[id] = Math.max(layer[id] ?? 0, d);
    if (seen.has(id)) return; seen.add(id);
    (adj[id] || []).forEach(n => visit(n, d + 1, seen));
  };
  visit(rootId, 0, new Set());
  nodes.forEach(n => { if (layer[n.id] === undefined) layer[n.id] = 0; });

  const byLayer: Record<number, ProvNode[]> = {};
  nodes.forEach(n => { (byLayer[layer[n.id]] ||= []).push(n); });
  const maxLayer = Math.max(...Object.keys(byLayer).map(Number), 0);

  const W = 680, rowH = 96, nodeW = 190, nodeH = 54;
  const H = (maxLayer + 1) * rowH + 20;
  const pos: Record<string, { x: number; y: number }> = {};
  for (let l = 0; l <= maxLayer; l++) {
    const row = byLayer[l] || [];
    row.forEach((n, i) => {
      const gap = W / (row.length + 1);
      pos[n.id] = { x: gap * (i + 1), y: l * rowH + 40 };
    });
  }

  const iconFor = (k: string) => k === "event" ? Zap : k === "assertion" ? FileText : Layers;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: 420 }}>
      {edges.map((e, i) => {
        const a = pos[e.from], b = pos[e.to];
        if (!a || !b) return null;
        return (
          <g key={i}>
            <line x1={a.x} y1={a.y + nodeH / 2} x2={b.x} y2={b.y - nodeH / 2}
              stroke="var(--border)" strokeWidth={1.5} markerEnd="url(#arrow)" />
            <text x={(a.x + b.x) / 2 + 6} y={(a.y + b.y) / 2} className="mono" fontSize={9} fill="var(--muted)">{e.kind}</text>
          </g>
        );
      })}
      <defs>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6" fill="var(--muted)" />
        </marker>
      </defs>
      {nodes.map(n => {
        const p = pos[n.id]; if (!p) return null;
        const Icon = iconFor(n.kind);
        const isRoot = n.kind === "event";
        return (
          <foreignObject key={n.id} x={p.x - nodeW / 2} y={p.y - nodeH / 2} width={nodeW} height={nodeH}>
            <div className={cn("flex h-full items-center gap-2 rounded-md border px-2.5 text-xs",
              isRoot ? "border-[color:var(--believed)]/50 bg-[color:var(--believed)]/10" :
              n.id === rootId ? "border-accent bg-[color:var(--accent)]/10" : "bg-panel")}>
              <Icon className={cn("h-3.5 w-3.5 shrink-0", isRoot ? "text-believed" : "text-muted")} />
              <div className="min-w-0">
                <div className="truncate font-medium">{n.label || n.id}</div>
                <div className="mono truncate text-2xs text-muted">{n.kind}{isRoot ? " / root" : ""}</div>
              </div>
            </div>
          </foreignObject>
        );
      })}
    </svg>
  );
}
