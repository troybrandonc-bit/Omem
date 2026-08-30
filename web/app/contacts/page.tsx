"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Contact } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Badge, Skeleton, EmptyState } from "@/components/ui/primitives";
import { Users } from "lucide-react";

// People and organisations derived from REAL email interaction: message counts,
// first/last contact, stored facts. Setting a role here is a user correction.
// It is stored as reusable intelligence and changes how FUTURE mail from that
// sender/domain is classified. Roles are never guessed by the system.

const ROLE_TONE: Record<string, "believed" | "unknown" | "conflict" | "muted" | "closed" | "accent"> = {
  CUSTOMER: "believed", PROSPECT: "unknown", SUPPLIER: "accent", PARTNER: "accent",
  SERVICE_PROVIDER: "muted", MARKETING: "conflict", IGNORE: "conflict",
  PERSONAL: "closed", EMPLOYEE: "closed",
};

export default function Contacts() {
  const { project } = useApp();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["contacts", project],
    queryFn: () => api.contacts(project),
  });
  const { data: rels } = useQuery({
    queryKey: ["relationships", project],
    queryFn: () => api.relationships(project),
  });
  const roles = rels?.roles ?? [];

  async function setRole(c: Contact, scope: "email" | "domain", role: string) {
    setBusy(c.email);
    try {
      await api.setRelationship(project, {
        key_type: scope, key: scope === "email" ? c.email : c.domain,
        role: role === "" ? null : role,
      });
    } finally {
      qc.invalidateQueries({ queryKey: ["contacts", project] });
      qc.invalidateQueries({ queryKey: ["relationships", project] });
      setBusy(null);
    }
  }

  const rows = (data?.data ?? []).filter(c =>
    !q.trim() ||
    c.email.toLowerCase().includes(q.toLowerCase()) ||
    (c.name ?? "").toLowerCase().includes(q.toLowerCase()) ||
    c.domain.toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="mx-auto max-w-5xl space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="display text-2xl">Contacts</h1>
        <input value={q} onChange={e => setQ(e.target.value)} placeholder="Filter contacts…"
          className="w-64 rounded-md border bg-panel px-3 py-1.5 text-sm outline-none focus:border-accent" />
      </div>
      <p className="text-sm text-muted">
        Derived from real email interaction. Setting a role teaches OMEM how to treat
        future mail from that sender or domain, it never guesses relationships.
      </p>

      {isLoading ? <Skeleton className="h-64" /> :
        rows.length === 0 ?
          <EmptyState icon={Users} title="No contacts yet"
            body="Connect Gmail in Sources; contacts appear from real correspondence." /> :
          <div className="panel divide-y overflow-hidden">
            {rows.map(c => (
              <div key={c.email} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium">{c.name || c.email.split("@")[0]}</span>
                    {c.role
                      ? <Badge tone={ROLE_TONE[c.role] ?? "muted"}>{c.role.replace(/_/g, " ")}</Badge>
                      : <Badge tone="muted">unclassified</Badge>}
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-x-3 text-2xs text-muted">
                    <span>{c.email}</span>
                    <span className="num">{c.messages} msg · {c.threads} thread{c.threads === 1 ? "" : "s"}</span>
                    {c.last_contact && <span>last {new Date(c.last_contact * 1000).toLocaleDateString()}</span>}
                    {c.facts_stored > 0 && <span className="text-accent">{c.facts_stored} memories</span>}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <select disabled={busy === c.email} value={c.role ?? ""}
                    onChange={e => setRole(c, "domain", e.target.value)}
                    className="rounded-md border bg-panel px-2 py-1 text-2xs outline-none"
                    title={`Applies to everyone @${c.domain}`}>
                    <option value="">Set domain role…</option>
                    {roles.map(r => <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}
                  </select>
                </div>
              </div>
            ))}
          </div>}
    </div>
  );
}
