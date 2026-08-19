"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type Connector } from "@/lib/api";
import { useApp } from "@/components/providers";
import { ProviderStatus } from "@/components/panels/provider-status";
import { ClassificationPanel } from "@/components/panels/classification-panel";
import { Skeleton } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { Github, FileUp, Mail, RefreshCw, Play, Plug, AlertTriangle } from "lucide-react";

// Every value on this page comes from a real backend endpoint. When a project
// has no sources we show an explicit empty state rather than inventing numbers.
export default function Sources() {
  const { project } = useApp();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const { data: connectors, isLoading } = useQuery({
    queryKey: ["connectors", project], queryFn: () => api.connectors(project), refetchInterval: 5000,
  });

  function refresh() {
    for (const k of ["connectors", "ingest-stats", "overview", "assertions"]) {
      qc.invalidateQueries({ queryKey: [k, project] });
    }
  }

  async function act(label: string, fn: () => Promise<unknown>) {
    setBusy(label); setErr(null);
    try { await fn(); } catch (e) { setErr((e as Error).message); }
    finally { refresh(); setBusy(null); }
  }

  const connectGithub = () => {
    const repo = window.prompt("GitHub repository (owner/name):", "psf/requests");
    if (!repo) return;
    return act("github", async () => {
      const c = await api.connectGithub(project, repo);
      await api.pollConnector(project, c.id);
      await api.processIngest(project);
    });
  };

  const uploadDoc = () => {
    const text = window.prompt("Paste document text:");
    if (!text) return;
    return act("doc", () => api.uploadDocument(project, { filename: "pasted-note.txt", text }));
  };

  const connectGmail = () => act("gmail", async () => {
    const b = await api.beginGmail(project, "Gmail");
    if (b.real && b.auth_url) {
      // real Google OAuth: hand the browser to Google's consent screen.
      window.location.href = b.auth_url;
      return;
    }
    // Not configured on the API server — say so plainly instead of pretending.
    throw new Error(
      b.note ??
        "Gmail is not configured on the API server. Add GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and GOOGLE_REDIRECT_URI to server/.env.local and restart it."
    );
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="display text-[24px]">Sources</h1>
        <div className="flex flex-wrap items-center gap-2">
          <Btn onClick={connectGithub} busy={busy === "github"} icon={<Github className="h-3.5 w-3.5" />}>Connect GitHub</Btn>
          <Btn onClick={uploadDoc} busy={busy === "doc"} icon={<FileUp className="h-3.5 w-3.5" />}>Upload document</Btn>
          <Btn onClick={connectGmail} busy={busy === "gmail"} icon={<Mail className="h-3.5 w-3.5" />}>Connect Gmail</Btn>
          {(connectors?.data.filter(c => c.kind === "gmail").length ?? 0) > 1 && (
            <button
              onClick={() => {
                const n = connectors?.data.filter(c => c.kind === "gmail").length ?? 0;
                if (window.confirm(`Remove all ${n} Gmail connectors?\n\nStored messages and jobs go; recorded memories stay.`)) {
                  act("bulk", () => api.bulkDeleteConnectors(project, { kind: "gmail" }));
                }
              }}
              className="rounded-md border px-3 py-1.5 text-[13px] font-medium text-muted hover:border-conflict hover:text-conflict">
              Remove all Gmail
            </button>
          )}
        </div>
      </div>

      <ProviderStatus />

      <ClassificationPanel />

      <FilteredPanel />

      {err && <div className="panel border-conflict/40 bg-conflictBg px-4 py-2.5 text-2xs text-conflict">{err}</div>}

      {isLoading ? (
        <Skeleton className="h-40" />
      ) : !connectors || connectors.data.length === 0 ? (
        <section className="panel">
          <div className="empty m-5 flex flex-col items-center gap-2 py-8">
            <Plug className="h-5 w-5 text-faint" />
            <div className="text-[13px] font-medium text-fg">Not connected</div>
            <div className="text-2xs text-faint">No sources yet. Connect a repository to start building memory automatically.</div>
          </div>
        </section>
      ) : (
        <div className="space-y-4">
          {connectors.data.map(c => <SourceCard key={c.id} c={c} busy={busy} act={act} />)}
        </div>
      )}
    </div>
  );
}

function Btn({ onClick, busy, icon, children }: { onClick: () => void; busy: boolean; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button onClick={onClick} disabled={busy}
      className="inline-flex items-center gap-2 rounded-md border bg-panel px-3 py-1.5 text-[13px] font-medium transition-colors hover:border-line-strong disabled:opacity-40">
      {busy ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : icon}{children}
    </button>
  );
}

const TONE: Record<string, string> = {
  HEALTHY: "text-believed", SYNCING: "text-accent", ERROR: "text-conflict",
  RATE_LIMITED: "text-unknown", NEEDS_REAUTH: "text-unknown", DISCONNECTED: "text-faint",
  NOT_CONFIGURED: "text-unknown",
};

function SourceCard({ c, busy, act }: { c: Connector; busy: string | null; act: (l: string, f: () => Promise<unknown>) => Promise<void> }) {
  const { project } = useApp();
  const { data: d } = useQuery({
    queryKey: ["conn-detail", project, c.id], queryFn: () => api.connectorDetail(project, c.id), refetchInterval: 5000,
  });
  const { data: s } = useQuery({
    queryKey: ["conn-status", project, c.id], queryFn: () => api.connectorStatus(project, c.id), refetchInterval: 5000,
  });

  const status = c.status === "needs_reauth" ? "NEEDS_REAUTH"
    : c.status === "not_configured" ? "NOT_CONFIGURED"
    : c.status === "rate_limited" ? "RATE_LIMITED"
    : (s?.status ?? "…");
  const running = (d?.jobs.pending ?? 0) + (d?.jobs.running ?? 0) + (d?.jobs.retrying ?? 0);

  return (
    <section className="panel overflow-hidden">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b px-4 py-2.5">
        <div className="flex items-center gap-2.5">
          {c.kind === "github" ? <Github className="h-4 w-4 text-muted" /> : <Plug className="h-4 w-4 text-muted" />}
          <div>
            <div className="text-[14px] font-semibold">{c.name}</div>
            <div className="mono text-2xs text-faint">{c.kind} / {c.agent_id}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className={cn("rounded-pill border px-2 py-px text-2xs font-semibold uppercase tracking-[0.04em]", TONE[status] ?? "text-muted")}
            style={{ borderColor: "currentColor" }}>{status.replace("_", " ")}</span>
          {status === "NEEDS_REAUTH" && (
            <button onClick={() => act(c.id + "re", async () => {
              const b = await api.beginGmail(project, c.name);
              if (b.real && b.auth_url) { window.location.href = b.auth_url; return; }
              throw new Error(b.note ?? "Gmail is not configured on the API server.");
            })}
              className="rounded-md bg-accent px-2.5 py-1 text-2xs font-semibold text-white hover:opacity-[0.88]">
              Reconnect
            </button>
          )}
          <button onClick={() => act(c.id + "sync", async () => { await api.pollConnector(project, c.id); await api.processIngest(project); })}
            disabled={busy === c.id + "sync"}
            className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-2xs font-semibold text-muted hover:border-line-strong disabled:opacity-40">
            {busy === c.id + "sync" ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />} Sync now
          </button>
          <button onClick={() => act(c.id + "re", async () => { await api.resyncConnector(project, c.id); await api.pollConnector(project, c.id); await api.processIngest(project); })}
            className="rounded-md border px-2.5 py-1 text-2xs font-semibold text-muted hover:border-line-strong">Re-sync all</button>
          {(d?.jobs.dead_lettered ?? 0) > 0 && (
            <button onClick={() => act(c.id + "rd", async () => { await api.retryDeadLetters(project); await api.processIngest(project); })}
              disabled={busy === c.id + "rd"}
              className="rounded-md border border-conflict/40 px-2.5 py-1 text-2xs font-semibold text-conflict hover:bg-conflictBg disabled:opacity-40">
              Retry {d?.jobs.dead_lettered} failed
            </button>
          )}
          <button onClick={() => act(c.id + "dc", () => api.disconnectConnector(project, c.id))}
            className="rounded-md border px-2.5 py-1 text-2xs font-semibold text-muted hover:border-line-strong">Disconnect</button>
          <button
            onClick={() => {
              const ok = window.confirm(
                `Remove "${c.name}"?\n\nThis deletes its stored messages and jobs. ` +
                `Memories already recorded stay — they are immutable history.`
              );
              if (ok) act(c.id + "rm", () => api.deleteConnector(project, c.id));
            }}
            className="rounded-md border px-2.5 py-1 text-2xs font-semibold text-muted hover:border-conflict hover:text-conflict">Remove</button>
        </div>
      </header>

      {d?.rate_limit_reset && status === "RATE_LIMITED" && (
        <div className="flex items-center gap-2 border-b bg-conflictBg px-4 py-2 text-2xs text-conflict">
          <AlertTriangle className="h-3.5 w-3.5" />
          Provider rate limit reached. Resets {new Date(d.rate_limit_reset * 1000).toLocaleTimeString()}.
        </div>
      )}
      {d?.last_error && (
        <div className="flex items-start justify-between gap-4 border-b bg-conflictBg px-4 py-2">
          <span className="text-2xs text-conflict">{d.last_error}</span>
          <button onClick={() => act(c.id + "ce", () => api.clearConnectorErrors(project, c.id))}
            className="shrink-0 text-2xs font-medium text-conflict underline hover:no-underline">Dismiss</button>
        </div>
      )}

      <div className="grid grid-cols-2 divide-x divide-y sm:grid-cols-4 sm:divide-y-0">
        <Cell label="Items ingested" value={d?.items_ingested ?? 0} />
        <Cell label="Memories generated" value={d?.memories_generated ?? 0} />
        <Cell label="In flight" value={running} />
        <Cell label="Last sync" value={d?.last_sync ? new Date(d.last_sync * 1000).toLocaleString() : "never"} small />
      </div>

      {d && (
        <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t px-4 py-2 text-2xs text-muted">
          <span>completed <span className="num text-fg">{d.jobs.completed}</span></span>
          <span>retrying <span className="num text-fg">{d.jobs.retrying}</span></span>
          <span>dead-letter <span className="num text-fg">{d.jobs.dead_lettered}</span></span>
          {d.cursor && <span className="mono">cursor {String(d.cursor).slice(0, 24)}</span>}
        </div>
      )}
    </section>
  );
}

function Cell({ label, value, small }: { label: string; value: number | string; small?: boolean }) {
  return (
    <div className="px-4 py-3">
      <div className="text-2xs text-faint">{label}</div>
      <div className={cn("num mt-0.5", small ? "text-[13px]" : "text-xl")}>{value}</div>
    </div>
  );
}


// What the relevance filter excluded, and why. Ingesting a whole mailbox is
// noise; excluding silently is worse. This makes the filter auditable.
function FilteredPanel() {
  const { project } = useApp();
  const { data } = useQuery({ queryKey: ["filtered", project], queryFn: () => api.filteredItems(project), refetchInterval: 10000 });
  const [open, setOpen] = useState(false);
  if (!data || data.data.length === 0) return null;
  const shown = open ? data.data : data.data.slice(0, 5);
  return (
    <section className="panel overflow-hidden">
      <header className="flex items-center justify-between border-b px-4 py-2.5">
        <h2 className="text-[14px] font-semibold">Excluded as non-business mail</h2>
        <span className="num text-2xs text-muted">{data.data.length}</span>
      </header>
      <div className="divide-y">
        {shown.map((f, i) => (
          <div key={i} className="flex items-center justify-between gap-4 px-4 py-2">
            <span className="truncate text-[13px]">{f.subject || f.external_id}</span>
            <span className="shrink-0 text-2xs text-muted">{f.reason}</span>
          </div>
        ))}
      </div>
      {data.data.length > 5 && (
        <button onClick={() => setOpen(!open)} className="w-full border-t px-4 py-2 text-2xs font-medium text-accent hover:bg-raised">
          {open ? "Show less" : `Show all ${data.data.length}`}
        </button>
      )}
    </section>
  );
}