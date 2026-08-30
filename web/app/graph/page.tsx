"use client";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { api, isGrounded, type Entity, type NeighborNode } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton, EmptyState, Badge } from "@/components/ui/primitives";
import { Search, Network, Building2, User, Box, ExternalLink, ShieldCheck, ShieldAlert } from "lucide-react";

/* The belief graph, built to scale.
 *
 * A force-directed picture of every node is a lie at a million entities: it
 * cannot lay out, cannot render, cannot be read. So the graph is an explorer
 * instead. You search and sort the entities SERVER-SIDE -- the browser only
 * ever holds a page -- pick one, and see its bounded neighbourhood (it plus the
 * entities one or two relations away) with a summary beside it. Clicking a
 * neighbour re-centres on it. You navigate a million entities one small,
 * legible graph at a time, and never leave the page. */

const SORTS = [
  { key: "name", label: "Name" },
  { key: "connections", label: "Most connected" },
  { key: "type", label: "Type" },
  { key: "id", label: "ID" },
];
const PAGE = 50;

function humanize(id: string): string {
  const rest = id.includes(":") ? id.slice(id.indexOf(":") + 1) : id;
  return rest.split("@")[0].replace(/[-_.]/g, " ").replace(/\b\w/g, c => c.toUpperCase());
}
function labelOf(e: { id: string; label?: string | null }): string {
  return e.label || humanize(e.id);
}
function kindPrefix(id: string): string {
  return id.includes(":") ? id.slice(0, id.indexOf(":")).toLowerCase() : "";
}
function iconFor(id: string, type?: string | null) {
  const k = (type || kindPrefix(id) || "").toLowerCase();
  if (["organization", "organisation", "company", "org", "vendor", "account"].includes(k)) return Building2;
  if (["person", "contact", "customer", "people", "user", "employee"].includes(k)) return User;
  return Box;
}
function humanizeRel(rel: string): string {
  return rel.replace(/^rel_/, "").replace(/_/g, " ");
}

// Radial layout: focus at the centre, hop-1 on an inner ring, hop-2 outside it.
// The neighbourhood is bounded (depth <= 2, fanned out per node), so no physics
// is needed -- a ring per distance reads more clearly than a relaxed cloud.
function layoutNeighbors(nodes: NeighborNode[]): Record<string, { x: number; y: number }> {
  const pos: Record<string, { x: number; y: number }> = {};
  const byHop = new Map<number, NeighborNode[]>();
  for (const n of nodes) { const g = byHop.get(n.hops) ?? []; g.push(n); byHop.set(n.hops, g); }
  for (const [hop, group] of byHop) {
    if (hop === 0) { group.forEach(n => (pos[n.id] = { x: 0, y: 0 })); continue; }
    const R = hop * 230;
    const start = -Math.PI / 2;
    group.forEach((n, i) => {
      const a = start + (i / group.length) * Math.PI * 2;
      pos[n.id] = { x: Math.cos(a) * R, y: Math.sin(a) * R };
    });
  }
  return pos;
}

export default function Graph() {
  const { project } = useApp();
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("connections");
  const [limit, setLimit] = useState(PAGE);
  const [selected, setSelected] = useState<string | null>(null);

  // Debounce the search so a keystroke is not a scan -- it matters at scale.
  useEffect(() => {
    const t = setTimeout(() => { setQ(qInput.trim()); setLimit(PAGE); }, 250);
    return () => clearTimeout(t);
  }, [qInput]);

  const list = useQuery({
    queryKey: ["entities", project, q, sort, limit],
    queryFn: () => api.entities(project, { q, sort, limit }),
    enabled: !!project, placeholderData: keepPreviousData,
  });
  const entities = useMemo(
    () => (list.data?.data ?? []).filter(e => !e.id.startsWith("cohort:")),
    [list.data]);
  const total = list.data?.total ?? 0;

  useEffect(() => {
    if (!selected && entities.length) setSelected(entities[0].id);
  }, [entities, selected]);

  const graph = useQuery({
    queryKey: ["entity-graph", project, selected],
    queryFn: () => api.entityGraph(project, selected!, 2),
    enabled: !!project && !!selected,
  });
  const beliefs = useQuery({
    queryKey: ["entity-beliefs", project, selected],
    queryFn: () => api.beliefsAbout(project, selected!, "now"),
    enabled: !!project && !!selected,
  });

  const selEntity = entities.find(e => e.id === selected);
  const focusNode = graph.data?.nodes.find(n => n.hops === 0);
  const selLabel = selEntity ? labelOf(selEntity)
    : focusNode?.label || (selected ? humanize(selected) : "");
  const SelIcon = iconFor(selected ?? "", selEntity?.type);

  const relations = useMemo(() => {
    const g = graph.data;
    if (!g || !selected) return [] as { text: string; other: string }[];
    const labelById = new Map(g.nodes.map(n => [n.id, n.label]));
    const here = labelById.get(selected) || humanize(selected);
    return g.edges.map(e => {
      const out = e.src === selected;
      const other = out ? e.dst : e.src;
      const ol = labelById.get(other) || humanize(other);
      return { text: out ? `${humanizeRel(e.relation)} ${ol}` : `${ol} ${humanizeRel(e.relation)} ${here}`, other };
    });
  }, [graph.data, selected]);

  return (
    <div className="mx-auto max-w-7xl">
      <div className="mb-4">
        <h1 className="display text-2xl">Belief graph</h1>
        <p className="mt-1 text-sm text-muted">
          Search for anyone or anything OMEM tracks, then explore the memory around them one neighbourhood at a time.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[17rem_1fr_20rem]">
        {/* Left: search, sort, the paginated entity list */}
        <aside className="panel flex h-[620px] flex-col overflow-hidden">
          <div className="border-b p-2.5">
            <div className="flex items-center gap-2 rounded-md border bg-panel px-2.5">
              <Search className="h-3.5 w-3.5 shrink-0 text-faint" />
              <input value={qInput} onChange={e => setQInput(e.target.value)} placeholder="Search entities…"
                className="h-8 w-full bg-transparent text-sm outline-none placeholder:text-faint" />
            </div>
            <div className="mt-2 flex items-center gap-2">
              <label className="text-2xs text-faint">Sort</label>
              <select value={sort} onChange={e => { setSort(e.target.value); setLimit(PAGE); }}
                className="h-7 flex-1 rounded-md border bg-panel px-2 text-2xs outline-none focus:border-accent">
                {SORTS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {list.isLoading ? <div className="p-2.5"><Skeleton className="h-72" /></div> :
              entities.length === 0 ? <div className="empty m-4 text-2xs">No entity matches “{q}”.</div> :
              <ul className="divide-y">
                {entities.map(e => {
                  const Icon = iconFor(e.id, e.type);
                  const on = e.id === selected;
                  return (
                    <li key={e.id}>
                      <button onClick={() => setSelected(e.id)}
                        className={"flex w-full items-center gap-2 px-3 py-2 text-left transition-colors " +
                          (on ? "bg-accentBg" : "hover:bg-[color:var(--border)]/20")}>
                        <Icon className={"h-3.5 w-3.5 shrink-0 " + (on ? "text-accent" : "text-muted")} />
                        <span className={"min-w-0 flex-1 truncate text-sm " + (on ? "font-semibold text-accent" : "")}>{labelOf(e)}</span>
                        {sort === "connections" && e.connections != null && e.connections > 0 &&
                          <span className="num shrink-0 text-2xs text-faint">{e.connections}</span>}
                      </button>
                    </li>
                  );
                })}
              </ul>}
          </div>
          <div className="border-t px-3 py-2 text-2xs text-faint">
            {entities.length < total ? (
              <button onClick={() => setLimit(l => l + PAGE)} className="font-semibold text-accent hover:underline">
                Load more ({entities.length} of {total})
              </button>
            ) : `${total} ${total === 1 ? "entity" : "entities"}`}
          </div>
        </aside>

        {/* Centre: the selected entity's bounded neighbourhood */}
        <section className="panel relative h-[620px] overflow-hidden">
          {!selected ? <EmptyState icon={Network} title="Pick an entity to explore its neighbourhood." /> :
            graph.isLoading ? <div className="p-4"><Skeleton className="h-full" /></div> :
            <NeighborhoodGraph nodes={graph.data?.nodes ?? []} edges={graph.data?.edges ?? []}
              focus={selected} onPick={setSelected} />}
        </section>

        {/* Right: the summary, without leaving the page */}
        <aside className="panel flex h-[620px] flex-col overflow-hidden">
          {!selected ? <div className="empty m-4 text-2xs">Select an entity for its summary.</div> : <>
            <div className="border-b p-3.5">
              <div className="flex items-center gap-2">
                <SelIcon className="h-4 w-4 shrink-0 text-accent" />
                <span className="min-w-0 truncate text-sm font-semibold">{selLabel}</span>
              </div>
              <div className="mono mt-1 text-2xs text-faint">{selected}</div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-3.5">
              {relations.length > 0 && (
                <div className="mb-4">
                  <div className="tech-label mb-1.5">Relations</div>
                  <ul className="space-y-1">
                    {relations.map((r, i) => (
                      <li key={i}>
                        <button onClick={() => setSelected(r.other)}
                          className="text-2xs text-muted hover:text-accent">{r.text}</button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="tech-label mb-1.5">
                Beliefs {beliefs.data && <span className="text-faint">{beliefs.data.data.length}</span>}
              </div>
              {beliefs.isLoading ? <Skeleton className="h-24" /> :
                (beliefs.data?.data.length ?? 0) === 0 ? <div className="text-2xs text-faint">Nothing recorded about this entity yet.</div> :
                <ul className="space-y-1.5">
                  {beliefs.data!.data.filter(b => !b.is_retraction).map(b => (
                    <li key={b.id}>
                      <Link href={`/assertion?id=${encodeURIComponent(b.id)}`}
                        className="group flex items-center justify-between gap-2 rounded-sm px-1.5 py-1 hover:bg-[color:var(--border)]/20">
                        <span className="num min-w-0 truncate text-2xs group-hover:text-accent">{b.proposition}</span>
                        {isGrounded(b.grounded)
                          ? <ShieldCheck className="h-3 w-3 shrink-0 text-believed" />
                          : <ShieldAlert className="h-3 w-3 shrink-0 text-unknown" />}
                      </Link>
                    </li>
                  ))}
                </ul>}
            </div>
            <div className="border-t px-3.5 py-2.5">
              <Link href={`/entity?id=${encodeURIComponent(selected)}`}
                className="inline-flex items-center gap-1 text-2xs font-semibold text-accent hover:underline">
                Open full entity page <ExternalLink className="h-3 w-3" />
              </Link>
            </div>
          </>}
        </aside>
      </div>
    </div>
  );
}

function NeighborhoodGraph({ nodes, edges, focus, onPick }: {
  nodes: NeighborNode[]; edges: { src: string; relation: string; dst: string }[];
  focus: string; onPick: (id: string) => void;
}) {
  const pos = useMemo(() => layoutNeighbors(nodes), [nodes]);
  if (nodes.length <= 1) {
    return (
      <div className="grid h-full place-items-center p-6 text-center">
        <div>
          <div className="mx-auto mb-2 grid h-11 w-11 place-items-center rounded-full bg-accentBg">
            <Network className="h-5 w-5 text-accent" />
          </div>
          <div className="text-sm font-medium">{nodes[0]?.label || humanize(focus)}</div>
          <div className="mt-1 text-2xs text-muted">No relations recorded yet — its beliefs are on the right.</div>
        </div>
      </div>
    );
  }
  const xs = nodes.map(n => pos[n.id]?.x ?? 0);
  const ys = nodes.map(n => pos[n.id]?.y ?? 0);
  const pad = 150;
  const minX = Math.min(...xs) - pad, maxX = Math.max(...xs) + pad;
  const minY = Math.min(...ys) - pad, maxY = Math.max(...ys) + pad;
  const labelById = new Map(nodes.map(n => [n.id, n.label]));
  const nodeW = (label: string) => Math.max(70, Math.min(220, label.length * 7 + 40));

  return (
    <svg viewBox={`${minX} ${minY} ${maxX - minX} ${maxY - minY}`}
      className="block h-full w-full select-none" style={{ background: "var(--bg)" }}>
      {edges.map((e, i) => {
        const a = pos[e.src], b = pos[e.dst];
        if (!a || !b) return null;
        const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        return (
          <g key={i}>
            <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="var(--line-strong)" strokeWidth={1.25} strokeOpacity={0.55} />
            <text x={mx} y={my - 4} textAnchor="middle" fontSize={10} fill="var(--faint)"
              className="pointer-events-none">{humanizeRel(e.relation)}</text>
          </g>
        );
      })}
      {nodes.map(n => {
        const p = pos[n.id]; if (!p) return null;
        const isFocus = n.id === focus;
        const label = (labelById.get(n.id) || n.id).slice(0, 26);
        const w = nodeW(label), h = 34;
        return (
          <g key={n.id} transform={`translate(${p.x},${p.y})`} style={{ cursor: "pointer" }}
            onClick={() => onPick(n.id)}>
            <rect x={-w / 2} y={-h / 2} width={w} height={h} rx={h / 2}
              fill={isFocus ? "var(--accentBg)" : "var(--panel)"}
              stroke={isFocus ? "var(--accent)" : "var(--line-strong)"} strokeWidth={isFocus ? 2 : 1.5}
              style={{ filter: "drop-shadow(0 3px 8px rgba(13,15,18,0.10))" }} />
            <text x={0} y={4.5} textAnchor="middle" fontSize={12.5} fontWeight={isFocus ? 600 : 500}
              fill={isFocus ? "var(--accent)" : "var(--fg)"} className="pointer-events-none">{label}</text>
          </g>
        );
      })}
    </svg>
  );
}
