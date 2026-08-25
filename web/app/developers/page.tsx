"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useApp } from "@/components/providers";
import { api, ApiError, type ApiKey } from "@/lib/api";
import { Badge } from "@/components/ui/primitives";
import { Copy, Check, Play, ChevronRight } from "lucide-react";

// Developer surface tuned toward Linear chrome + Stripe's API reference:
// hairline-divided sections (not stacked cards), monospace identifiers, real
// key metadata, and a live request runner against the actual API.

const ENDPOINTS: { group: string; rows: { m: string; p: string; verb: string; d: string }[] }[] = [
  { group: "Write", rows: [
    { m: "POST", p: "/v1/assertions", verb: "remember", d: "Record a belief, optionally grounded in events" },
    { m: "POST", p: "/v1/assertions/{id}/supersede", verb: "revise", d: "Replace a belief; closes the prior interval" },
    { m: "POST", p: "/v1/assertions/{id}/retract", verb: "forget", d: "Retract a belief (RETRACTED marker)" },
    { m: "POST", p: "/v1/coreference", verb: "same", d: "Assert two entities are the same referent" },
  ]},
  { group: "Query", rows: [
    { m: "POST", p: "/v1/queries/proposition-state", verb: "believes", d: "The four-valued belief state at time T" },
    { m: "GET", p: "/v1/assertions/{id}/why", verb: "why", d: "State, provenance, contradictions, revisions" },
    { m: "GET", p: "/v1/entities/{id}/beliefs", verb: "beliefs_about", d: "Every belief about an entity at time T" },
    { m: "GET", p: "/v1/conflicts", verb: "conflicts", d: "Propositions in a CONTRADICTED state" },
    { m: "GET", p: "/v1/timeline", verb: "timeline", d: "Events ordered by event-time" },
  ]},
];

function Copyable({ text, className = "" }: { text: string; className?: string }) {
  const [c, setC] = useState(false);
  return (
    <button onClick={() => { navigator.clipboard.writeText(text); setC(true); setTimeout(() => setC(false), 1200); }}
      className={`rounded p-1 text-muted transition hover:text-fg ${className}`} aria-label="Copy">
      {c ? <Check className="h-3.5 w-3.5 text-believed" /> : <Copy className="h-3.5 w-3.5" />}
    </button>
  );
}

function SectionLabel({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b pb-2">
      <h2 className="tech-label">{children}</h2>
      {right}
    </div>
  );
}

export default function Developers() {
  const { project } = useApp();
  const qc = useQueryClient();
  const [tryOpen, setTryOpen] = useState(true);
  const [running, setRunning] = useState(false);
  const [resp, setResp] = useState<{ status: string; body: string } | null>(null);
  const { data: keys } = useQuery({ queryKey: ["keys", project], queryFn: () => api.keys(project) });
  const [newSecret, setNewSecret] = useState<ApiKey | null>(null);
  const [creating, setCreating] = useState(false);

  async function makeKey() {
    setCreating(true);
    try {
      const k = await api.createKey(project, `Key ${new Date().toISOString().slice(0, 10)}`);
      setNewSecret(k);
      qc.invalidateQueries({ queryKey: ["keys", project] });
    } catch {}
    setCreating(false);
  }
  async function revoke(id: string) {
    await api.revokeKey(project, id);
    qc.invalidateQueries({ queryKey: ["keys", project] });
  }
  const ago = (ts: number | null) => ts ? `${Math.max(1, Math.round((Date.now() / 1000 - ts) / 60))}m ago` : "never";

  async function runTry() {
    setRunning(true); setResp(null);
    try {
      const r = await api.why(project, "a:alice-email");
      setResp({ status: "200 OK", body: JSON.stringify({
        state: r.state, grounded: r.grounded,
        provenance: r.provenance.nodes.map(n => n.id),
        contradictions: r.contradictions.map(c => c.proposition),
      }, null, 2) });
    } catch (e) {
      const err = e as ApiError;
      setResp({ status: `${err.code} ${err.reason_code ?? ""}`.trim(), body: err.message });
    }
    setRunning(false);
  }

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-8">
        <h1 className="display text-lg">Developers</h1>
        <p className="mt-1 text-sm text-muted">Integrate OMEM in a few minutes. Keys below are scoped to <span className="mono text-fg">{project}</span> / development.</p>
      </div>

      {/* API keys: real, hashed at rest, secret shown once at creation */}
      <section className="mb-10">
        <SectionLabel right={
          <button onClick={makeKey} disabled={creating} className="text-2xs font-semibold text-accent hover:underline disabled:opacity-40">
            + Create key
          </button>}>API keys</SectionLabel>
        {newSecret?.secret && (
          <div className="mt-3 flex items-center gap-2 rounded-md border border-believed/40 bg-believedBg px-3 py-2.5">
            <span className="text-2xs font-semibold text-believed">New key (shown once):</span>
            <code className="mono min-w-0 flex-1 truncate text-xs">{newSecret.secret}</code>
            <Copyable text={newSecret.secret} />
          </div>
        )}
        <div className="divide-y">
          {(keys?.data ?? []).map(k => (
            <div key={k.id} className="flex items-center gap-4 py-3">
              <span className="w-40 truncate text-sm font-medium">{k.name}</span>
              <code className="mono flex-1 truncate text-xs text-muted">{k.prefix}…</code>
              <span className="hidden text-2xs text-muted sm:inline">last used {ago(k.last_used)}</span>
              {k.revoked
                ? <span className="text-2xs text-faint">revoked</span>
                : <button onClick={() => revoke(k.id)} className="text-2xs font-medium text-conflict hover:underline">Revoke</button>}
            </div>
          ))}
          {(keys?.data ?? []).length === 0 && (
            <div className="empty mt-2">No API keys yet. Create one to call the API from your code.</div>
          )}
        </div>
      </section>

      {/* Connection: base url + install, inline not boxed */}
      <section className="mb-10">
        <SectionLabel>Connection</SectionLabel>
        <dl className="divide-y">
          {/* Four rows, four corrections. api.omem.dev does not resolve — OMEM
              is the server you are running, and this is its address. The
              package is omem-infrastructure, not omem. The TypeScript SDK has
              never been published to npm. And "CTS 29/29" was a conformance
              figure that ENGINE_VALIDATION.md explicitly says "should not be
              read as independent validation", because the suite it refers to
              is not in this repository. */}
          {[
            { k: "Base URL", v: "http://127.0.0.1:8787" },
            { k: "Python", v: "pip install omem-infrastructure" },
            { k: "TypeScript", v: "sdk/typescript/ (not on npm yet)" },
            { k: "Engine", v: "omem_engine 1.0.0 (frozen, hash-checked)" },
          ].map(row => (
            <div key={row.k} className="flex items-center gap-4 py-2.5">
              <dt className="w-28 shrink-0 text-xs text-muted">{row.k}</dt>
              <dd className="mono flex-1 text-xs">{row.v}</dd>
              {row.v.includes(" ") && !row.v.includes("·") ? <Copyable text={row.v} /> : row.k === "Base URL" ? <Copyable text={row.v} /> : <span className="w-6" />}
            </div>
          ))}
        </dl>
      </section>

      {/* Live try-it against the real API */}
      <section className="mb-10">
        <SectionLabel right={
          <button onClick={() => setTryOpen(v => !v)} className="flex items-center gap-1 text-2xs text-muted hover:text-fg">
            <ChevronRight className={`h-3 w-3 transition ${tryOpen ? "rotate-90" : ""}`} /> {tryOpen ? "hide" : "show"}
          </button>
        }>Try it: GET /v1/assertions/&#123;id&#125;/why</SectionLabel>
        {tryOpen && (
          <div className="pt-3">
            <div className="flex items-center gap-3 rounded-md border bg-bg px-3 py-2">
              <span className="mono text-2xs font-semibold text-believed">GET</span>
              <code className="mono flex-1 truncate text-xs">/v1/assertions/a:alice-email/why</code>
              <button onClick={runTry} disabled={running}
                className="tap inline-flex h-8 items-center gap-1.5 rounded-md bg-accent px-3 text-xs font-medium text-accentFg transition hover:opacity-90 disabled:opacity-40">
                <Play className="h-3 w-3" /> {running ? "Running" : "Send"}
              </button>
            </div>
            {resp && (
              <div className="mt-2 overflow-hidden rounded-md border">
                <div className="flex items-center justify-between border-b bg-panel px-3 py-1.5">
                  <span className="text-2xs text-faint">response</span>
                  <span className={`mono text-2xs ${resp.status.startsWith("2") ? "text-believed" : "text-conflict"}`}>{resp.status}</span>
                </div>
                <pre className="mono overflow-x-auto bg-bg p-3 text-xs leading-relaxed"><code>{resp.body}</code></pre>
              </div>
            )}
            <p className="mt-2 text-2xs text-muted">Runs against your live project, the same response your SDK receives.</p>
          </div>
        )}
      </section>

      {/* Endpoint reference: grouped dense table */}
      <section>
        <SectionLabel>API reference</SectionLabel>
        <div className="pt-1">
          {ENDPOINTS.map(g => (
            <div key={g.group} className="mb-5">
              <div className="mb-1 px-0 pt-2 text-2xs font-medium text-muted/70">{g.group}</div>
              <div className="divide-y">
                {g.rows.map(e => (
                  <div key={e.p} className="grid grid-cols-[3rem_1fr_auto] items-center gap-3 py-2 sm:grid-cols-[3rem_20rem_1fr]">
                    <span className={`mono text-2xs font-semibold ${e.m === "GET" ? "text-believed" : "text-accent"}`}>{e.m}</span>
                    <code className="mono truncate text-xs">{e.p}</code>
                    <div className="hidden items-center gap-2 sm:flex">
                      <span className="mono rounded bg-[color:var(--accent)]/10 px-1.5 py-0.5 text-2xs text-accent">{e.verb}</span>
                      <span className="truncate text-xs text-muted">{e.d}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        <p className="mt-2 text-2xs text-muted">Ergonomic verbs map 1:1 to frozen OMEM operations. No hidden semantics.</p>
      </section>
    </div>
  );
}
