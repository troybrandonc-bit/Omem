"use client";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api, isGrounded, formatWhen, type Assertion } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Badge, Skeleton, EmptyState, IntervalStrip } from "@/components/ui/primitives";
import { Brain, ShieldCheck, ShieldAlert, Bot, User, ScanSearch } from "lucide-react";
import { useMemo, useState } from "react";

// The memory list answers, per row: WHAT is believed, WHO it is about, WHO
// said it (human correspondence vs connector/automation vs API), WHEN, and its
// CURRENT engine state. "View evidence" opens the full why-view with the
// original email. Every field is real engine/pipeline data.

function saidBy(agent: string): { label: string; kind: "human" | "automated" | "system" } {
  if (agent.startsWith("connector:gmail")) return { label: "Email (Gmail)", kind: "human" };
  if (agent.startsWith("connector:")) return { label: agent.replace("connector:", "Connector: "), kind: "automated" };
  if (agent.startsWith("scanner:")) return { label: "Memory scanner", kind: "system" };
  if (agent.startsWith("agent:") || agent.startsWith("assistant:")) return { label: agent.split(":")[1], kind: "system" };
  return { label: agent, kind: "human" };
}

function subjectLabel(id: string): string {
  const [kind, rest] = id.includes(":") ? [id.slice(0, id.indexOf(":")), id.slice(id.indexOf(":") + 1)] : ["", id];
  const pretty = rest.replace(/[-_]/g, " ");
  if (kind === "company") return pretty.replace(/\b\w/g, c => c.toUpperCase());
  if (kind === "customer") return `Customer ${pretty}`;
  if (kind === "person") return pretty.split("@")[0].replace(/\b\w/g, c => c.toUpperCase());
  return id;
}

export default function Memory() {
  const { project, asOf, now } = useApp();
  const [openOnly, setOpenOnly] = useState(true);
  const [q, setQ] = useState("");
  const [roleFilter, setRoleFilter] = useState<string | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["assertions", project, asOf, openOnly],
    queryFn: () => api.assertions(project, { as_of: asOf ?? "now", open: openOnly }),
  });
  // relationship map: entity_id -> role, from contact aggregation (which folds
  // in user corrections). Roles are user-taught, never guessed.
  const { data: contacts } = useQuery({
    queryKey: ["contacts", project],
    queryFn: () => api.contacts(project),
  });
  const roleOf = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of contacts?.data ?? []) {
      if (c.role && !m.has(c.entity_id)) m.set(c.entity_id, c.role);
      if (c.role) m.set(`customer:${c.email.split("@")[0]}`, c.role);
    }
    return m;
  }, [contacts]);

  const rows = useMemo(() => {
    let all = (data?.data ?? []).filter(a => !a.is_retraction);
    if (roleFilter === "gmail") {
      all = all.filter(a => a.agent.startsWith("connector:gmail"));
    } else if (roleFilter) {
      all = all.filter(a => a.subjects.some(s => roleOf.get(s) === roleFilter));
    }
    if (!q.trim()) return all;
    const needle = q.toLowerCase();
    return all.filter(a =>
      a.proposition.toLowerCase().includes(needle) ||
      (a.label ?? "").toLowerCase().includes(needle) ||
      a.subjects.some(s => s.toLowerCase().includes(needle)) ||
      a.agent.toLowerCase().includes(needle));
  }, [data, q, roleFilter, roleOf]);

  const availableRoles = useMemo(() => {
    const seen = new Set<string>();
    for (const a of data?.data ?? [])
      for (const s of a.subjects) {
        const r = roleOf.get(s);
        if (r) seen.add(r);
      }
    return [...seen].sort();
  }, [data, roleOf]);

  // Grouped by who the belief is about, so everything known about one customer
  // sits together instead of scattered through the log by time.
  const groups = useMemo(() => {
    const m = new Map<string, { key: string; label: string; items: Assertion[] }>();
    for (const a of rows) {
      const key = a.subjects[0] || "unknown";
      const g = m.get(key) ?? { key, label: subjectLabel(key), items: [] };
      g.items.push(a);
      m.set(key, g);
    }
    return [...m.values()].sort((x, y) => x.label.localeCompare(y.label));
  }, [rows]);

  return (
    <div className="mx-auto max-w-6xl space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="display text-lg">Memory</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Each row is one belief: what an agent claims, who it is about, when
            it was recorded, and whether it is grounded in evidence. Open the row
            to see the source and the full chain of why it is believed.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <input value={q} onChange={e => setQ(e.target.value)} placeholder="Filter by subject, proposition, source…"
            className="w-64 rounded-md border bg-panel px-3 py-1.5 text-sm outline-none focus:border-accent" />
          <label className="flex items-center gap-2 text-sm text-muted">
            <input type="checkbox" checked={openOnly} onChange={e => setOpenOnly(e.target.checked)} className="accent-[color:var(--accent)]" />
            Currently-believed only
          </label>
          <Link href="/memory-health" className="flex items-center gap-1.5 text-sm font-semibold text-accent hover:underline">
            <ScanSearch className="h-4 w-4" />Memory health
          </Link>
        </div>
      </div>

      {(availableRoles.length > 0 || (data?.data ?? []).some(a => a.agent.startsWith("connector:gmail"))) && (
        <div className="flex flex-wrap gap-1.5">
          <FilterPill active={roleFilter === null} onClick={() => setRoleFilter(null)}>All</FilterPill>
          {availableRoles.map(r => (
            <FilterPill key={r} active={roleFilter === r} onClick={() => setRoleFilter(roleFilter === r ? null : r)}>
              {r.replace(/_/g, " ").toLowerCase()}s
            </FilterPill>
          ))}
          {(data?.data ?? []).some(a => a.agent.startsWith("connector:gmail")) && (
            <FilterPill active={roleFilter === "gmail"} onClick={() => setRoleFilter(roleFilter === "gmail" ? null : "gmail")}>
              from Gmail
            </FilterPill>
          )}
        </div>
      )}

      {isLoading ? <Skeleton className="h-64" /> :
        rows.length === 0 ?
          <EmptyState icon={Brain} title={q || roleFilter ? "No matching memories" : "No beliefs yet"}
            body={q || roleFilter ? "Try a different filter." : "Record your first memory from the Playground, or connect Gmail in Sources."} /> :
          <div className="space-y-5">
            {groups.map(g => (
              <section key={g.key}>
                <div className="mb-1.5 flex items-baseline gap-2 px-1">
                  <h2 className="text-sm font-semibold">{g.label}</h2>
                  <span className="text-2xs text-faint">
                    {g.items.length} {g.items.length === 1 ? "belief" : "beliefs"}
                  </span>
                </div>
                <div className="panel divide-y overflow-hidden">
                  {g.items.map(a => <MemoryRow key={a.id} a={a} now={now} primary={g.key}
                    role={a.subjects.map(s => roleOf.get(s)).find(Boolean) ?? null} />)}
                </div>
              </section>
            ))}
          </div>}
    </div>
  );
}

function FilterPill({ children, active, onClick }:
  { children: React.ReactNode; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} aria-pressed={active}
      className={"tap inline-flex h-7 items-center rounded-sm border px-2.5 text-2xs font-semibold capitalize transition-colors duration-1 ease-out " +
        (active ? "border-accent bg-accentBg text-accent" : "border-line-strong text-muted hover:text-ink")}>
      {children}
    </button>
  );
}

function MemoryRow({ a, now, role, primary }: { a: Assertion; now: number; role: string | null; primary?: string }) {
  const src = saidBy(a.agent);
  const closed = !a.open;
  const when = formatWhen(a.recorded_at, a.assertion_time);
  // The group header already names the primary subject; a row only adds the
  // OTHER subjects it touches (a relation's counterparty), if any.
  const others = a.subjects.filter(s => s !== primary);
  return (
    <div className="px-4 py-3 hover:bg-[color:var(--border)]/20">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link href={`/assertion?id=${encodeURIComponent(a.id)}`} className="group block">
            <div className="flex flex-wrap items-center gap-2">
              <span className="num text-sm font-medium group-hover:text-accent">{a.proposition}</span>
              {role && <Badge tone={role === "CUSTOMER" ? "believed" : role === "MARKETING" || role === "IGNORE" ? "conflict" : "accent"}>{role.replace(/_/g, " ")}</Badge>}
              {closed && <Badge tone="closed">no longer believed</Badge>}
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-2xs text-muted">
              {others.length > 0 && (
                <span>with{" "}
                  {others.map((s, i) => (
                    <span key={s} className="font-semibold text-ink">
                      {i > 0 && ", "}{subjectLabel(s)}
                    </span>
                  ))}
                </span>
              )}
              <span className="flex items-center gap-1">
                {src.kind === "human" ? <User className="h-3 w-3" /> : <Bot className="h-3 w-3" />}
                said by {src.label}
              </span>
              {when.text && <span title={when.title}>{when.text}</span>}
              {a.confidence != null && <span>{Math.round(a.confidence * 100)}% confidence</span>}
            </div>
          </Link>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          {isGrounded(a.grounded)
            ? <Badge tone="believed"><ShieldCheck className="h-3 w-3" />grounded</Badge>
            : <Badge tone="unknown"><ShieldAlert className="h-3 w-3" />ungrounded</Badge>}
          <div className="w-32"><IntervalStrip start={a.belief_interval.start} end={a.belief_interval.end} now={now} min={0} max={Math.max(now, a.belief_interval.start + 1)} /></div>
          <Link href={`/assertion?id=${encodeURIComponent(a.id)}`}
            className="text-2xs font-semibold text-accent hover:underline">View evidence →</Link>
        </div>
      </div>
    </div>
  );
}
