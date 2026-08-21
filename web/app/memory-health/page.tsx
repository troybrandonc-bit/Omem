"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { api, type MemoryScan, type MemoryScanResult } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton, Button, Badge } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";

// Memory hygiene control plane. Every number comes from the scanner's persisted
// state; scans are dry-runs until "Apply corrections" is pressed. Corrections
// are engine retractions. History stays auditable, nothing is deleted.

const CLS_TONE: Record<string, "believed" | "unknown" | "conflict" | "closed" | "muted"> = {
  VALID: "believed",
  DUPLICATE: "unknown",
  UNSUPPORTED: "conflict",
  IRRELEVANT: "unknown",
  AUTOMATED_NOISE: "conflict",
  LOW_VALUE: "unknown",
  SUPERSEDED: "closed",
  CONTRADICTED: "conflict",
  STALE: "closed",
  UNKNOWN: "muted",
};

const CLS_ORDER = ["VALID", "DUPLICATE", "UNSUPPORTED", "AUTOMATED_NOISE", "LOW_VALUE",
  "IRRELEVANT", "SUPERSEDED", "CONTRADICTED", "STALE", "UNKNOWN"];

export default function MemoryHealth() {
  const { project } = useApp();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [openScan, setOpenScan] = useState<string | null>(null);
  const [resultFilter, setResultFilter] = useState<string | null>(null);

  const { data: health } = useQuery({
    queryKey: ["memory-health", project],
    queryFn: () => api.memoryHealth(project), refetchInterval: 8000,
  });
  const { data: scans } = useQuery({
    queryKey: ["memory-scans", project],
    queryFn: () => api.memoryScans(project), refetchInterval: 8000,
  });
  const { data: queue } = useQuery({
    queryKey: ["review-queue", project],
    queryFn: () => api.reviewQueue(project), refetchInterval: 8000,
  });
  const { data: scanDetail } = useQuery({
    queryKey: ["memory-scan", project, openScan, resultFilter],
    queryFn: () => api.memoryScan(project, openScan!, resultFilter ?? undefined),
    enabled: !!openScan,
  });

  function refresh() {
    for (const k of ["memory-health", "memory-scans", "review-queue", "memory-scan",
      "overview", "assertions", "intelligence"]) {
      qc.invalidateQueries({ queryKey: [k, project] });
    }
    qc.invalidateQueries({ queryKey: ["memory-scan"] });
  }

  async function act(label: string, fn: () => Promise<unknown>) {
    setBusy(label); setErr(null);
    try { await fn(); } catch (e) { setErr((e as Error).message); }
    finally { refresh(); setBusy(null); }
  }

  const scanNow = (scope: "all" | "recent") =>
    act(`scan-${scope}`, async () => {
      const s = await api.startMemoryScan(project, scope);
      setOpenScan(s.id);
      setResultFilter(null);
    });

  const applyScan = (id: string) => {
    const s = (scans?.data ?? []).find(x => x.id === id);
    const proposed = s?.summary?.proposed_retractions ?? 0;
    const review = s?.summary?.proposed_review ?? 0;
    if (!window.confirm(
      `Apply corrections from this scan?\n\n` +
      `${proposed} memories will be RETRACTED (via the engine's append-only retract. History stays auditable).\n` +
      `${review} borderline memories will be sent to the review queue.\n\n` +
      `This cannot be undone silently, but every retraction is recorded and inspectable.`)) return;
    return act(`apply-${id}`, () => api.applyMemoryScan(project, id));
  };

  const decide = (qid: string, decision: "approve" | "reject") =>
    act(`decide-${qid}`, () => api.reviewDecide(project, qid, decision));

  const [gmailRescan, setGmailRescan] = useState<Awaited<ReturnType<typeof api.gmailRescan>> | null>(null);
  const [rescanWindow, setRescanWindow] = useState<7 | 30 | 90 | 365 | 0>(0);
  const runGmailRescan = () =>
    act("gmail-rescan", async () => setGmailRescan(
      await api.gmailRescan(project, rescanWindow ? { window_days: rescanWindow } : {})));

  const { data: quality } = useQuery({
    queryKey: ["memory-quality", project],
    queryFn: () => api.memoryQuality(project), refetchInterval: 10000,
  });

  if (!health) return <div className="space-y-5"><Skeleton className="h-40" /><Skeleton className="h-64" /></div>;

  const byCls = health.by_classification ?? {};
  const nonzero = CLS_ORDER.filter(c => (byCls[c] ?? 0) > 0);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="display text-[24px]">Memory health</h1>
        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="secondary" onClick={() => scanNow("recent")}
            disabled={busy !== null}>
            {busy === "scan-recent" ? "Scanning…" : "Scan recent"}
          </Button>
          <Button size="sm" onClick={() => scanNow("all")} disabled={busy !== null}>
            {busy === "scan-all" ? "Scanning…" : "Scan all memory"}
          </Button>
        </div>
      </div>

      {err && (
        <div className="rounded-md border border-[color:var(--conflict)]/50 bg-[color:var(--conflict)]/10 px-4 py-2.5 text-[13px] text-conflict">
          {err}
        </div>
      )}

      {/* Health summary. Real counts only */}
      <section className="panel overflow-hidden">
        <header className="flex items-center justify-between border-b px-4 py-2.5">
          <h2 className="text-[14px] font-semibold">Current state</h2>
          {health.last_scan_ts
            ? <span className="text-2xs text-faint">Last scan {new Date(health.last_scan_ts * 1000).toLocaleString()}</span>
            : <span className="text-2xs text-faint">Never scanned</span>}
        </header>
        <div className="grid grid-cols-2 divide-x lg:grid-cols-4">
          {[["Active memories", health.active_memories],
            ["All-time assertions", health.total_assertions_ever],
            ["Pending review", health.pending_review],
            ["Recent corrections", health.recent_corrections.length]].map(([l, v]) => (
            <div key={l as string} className="px-4 py-3">
              <div className="text-2xs text-faint">{l}</div>
              <div className="num mt-1 text-[20px] leading-none">{v}</div>
            </div>
          ))}
        </div>
        {health.needs_scan && (
          <div className="border-t px-4 py-2.5 text-[13px] text-muted">
            No recent scan. Run one to check memory quality against current classification rules.
          </div>
        )}
        {nonzero.length > 0 && (
          <div className="flex flex-wrap gap-2 border-t px-4 py-2.5">
            {nonzero.map(c => (
              <Badge key={c} tone={CLS_TONE[c]}>{c.replace(/_/g, " ")} · {byCls[c]}</Badge>
            ))}
          </div>
        )}
      </section>

      {/* Quality funnel, every number from persisted pipeline state */}
      {quality && quality.emails_scanned > 0 && (
        <section className="panel overflow-hidden">
          <header className="border-b px-4 py-2.5">
            <h2 className="text-[14px] font-semibold">Memory quality funnel</h2>
          </header>
          <div className="grid grid-cols-2 divide-x lg:grid-cols-5">
            {[["Emails scanned", quality.emails_scanned],
              ["Candidate facts", quality.candidate_facts],
              ["Stored", quality.facts_stored],
              ["Rejected by gate", quality.facts_rejected],
              ["Active memories", quality.active_memories]].map(([l, v]) => (
              <div key={l as string} className="px-4 py-3">
                <div className="text-2xs text-faint">{l}</div>
                <div className="num mt-1 text-[20px] leading-none">{v}</div>
              </div>
            ))}
          </div>
          {Object.keys(quality.by_category).length > 0 && (
            <div className="flex flex-wrap gap-2 border-t px-4 py-2.5">
              {Object.entries(quality.by_category).sort((a, b) => b[1] - a[1]).map(([c, n]) => (
                <Badge key={c} tone={c.startsWith("BUSINESS") ? "believed" : "muted"}>
                  {c.replace(/_/g, " ").toLowerCase()} · {n}
                </Badge>
              ))}
            </div>
          )}
          {Object.keys(quality.by_quality).length > 0 && (
            <div className="flex flex-wrap gap-2 border-t px-4 py-2.5">
              {Object.entries(quality.by_quality).map(([qq, n]) => (
                <Badge key={qq} tone={qq.startsWith("HIGH") ? "believed" : qq === "DO_NOT_STORE" ? "conflict" : "unknown"}>
                  {qq.replace(/_/g, " ").toLowerCase()} · {n}
                </Badge>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Review queue */}
      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5">
          <h2 className="text-[14px] font-semibold">Review queue</h2>
        </header>
        <div className="divide-y">
          {(queue?.data ?? []).length === 0 &&
            <div className="empty m-5">No memories awaiting review.</div>}
          {(queue?.data ?? []).map(q => (
            <div key={q.id} className="px-4 py-2.5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Badge tone={CLS_TONE[q.classification] ?? "muted"}>{q.classification.replace(/_/g, " ")}</Badge>
                    <Link href={`/assertion?id=${encodeURIComponent(q.assertion_id)}`}
                      className="num text-[13px] text-accent hover:underline">{q.assertion_id}</Link>
                  </div>
                  <div className="num mt-1 text-[13px]">{q.proposition}</div>
                  <div className="mt-0.5 text-2xs text-muted">{q.reason}</div>
                  {q.source_evidence && (
                    <div className="mt-1 rounded bg-chip px-2 py-1 text-2xs text-muted">
                      {q.source_evidence}
                    </div>
                  )}
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button size="sm" variant="danger" disabled={busy !== null}
                    onClick={() => decide(q.id, "approve")}>
                    {busy === `decide-${q.id}` ? "…" : "Retract"}
                  </Button>
                  <Button size="sm" variant="secondary" disabled={busy !== null}
                    onClick={() => decide(q.id, "reject")}>Keep</Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Scan history + dry-run reports */}
      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5">
          <h2 className="text-[14px] font-semibold">Scans</h2>
        </header>
        <div className="divide-y">
          {(scans?.data ?? []).length === 0 &&
            <div className="empty m-5">No scans yet. Run one above.</div>}
          {(scans?.data ?? []).map(s => (
            <ScanRow key={s.id} scan={s}
              open={openScan === s.id}
              onToggle={() => { setOpenScan(openScan === s.id ? null : s.id); setResultFilter(null); }}
              onApply={() => applyScan(s.id)}
              busy={busy === `apply-${s.id}`} />
          ))}
        </div>
      </section>

      {/* Scan detail: per-memory results */}
      {openScan && scanDetail && (
        <section className="panel overflow-hidden">
          <header className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5">
            <h2 className="text-[14px] font-semibold">Scan results <span className="num text-muted">{openScan}</span></h2>
            <div className="flex flex-wrap gap-1.5">
              <FilterChip active={resultFilter === null} onClick={() => setResultFilter(null)}>All</FilterChip>
              {CLS_ORDER.filter(c => (scanDetail.scan.summary?.by_classification?.[c] ?? 0) > 0).map(c => (
                <FilterChip key={c} active={resultFilter === c} onClick={() => setResultFilter(c)}>
                  {c.replace(/_/g, " ")} · {scanDetail.scan.summary?.by_classification?.[c]}
                </FilterChip>
              ))}
            </div>
          </header>
          <div className="divide-y">
            {scanDetail.results.length === 0 &&
              <div className="empty m-5">No results for this filter.</div>}
            {scanDetail.results.map(r => <ResultRow key={r.id} r={r} />)}
          </div>
        </section>
      )}

      {/* Gmail source rescan */}
      <section className="panel overflow-hidden">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b px-4 py-2.5">
          <h2 className="text-[14px] font-semibold">Gmail source rescan</h2>
          <div className="flex items-center gap-2">
            <select value={rescanWindow}
              onChange={e => setRescanWindow(Number(e.target.value) as 7 | 30 | 90 | 365 | 0)}
              className="rounded-md border bg-panel px-2 py-1 text-2xs outline-none">
              <option value={0}>All stored mail</option>
              <option value={7}>Last 7 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={365}>Last year</option>
            </select>
            <Button size="sm" variant="secondary" onClick={runGmailRescan} disabled={busy !== null}>
              {busy === "gmail-rescan" ? "Rescanning…" : "Rescan stored mail"}
            </Button>
          </div>
        </header>
        <div className="px-4 py-2.5 text-[13px] text-muted">
          Re-runs the current relevance classifier over already-stored Gmail messages
          (no re-fetch). Finds mail the old rules missed, and mail that should not
          have entered the pipeline.
        </div>
        {gmailRescan && !gmailRescan.error && (
          <div className="border-t">
            <div className="grid grid-cols-2 divide-x lg:grid-cols-4">
              {[["Examined", gmailRescan.sources_examined],
                ["Newly relevant", gmailRescan.newly_relevant],
                ["Newly excluded", gmailRescan.newly_excluded],
                ["Unchanged", gmailRescan.unchanged]].map(([l, v]) => (
                <div key={l as string} className="px-4 py-3">
                  <div className="text-2xs text-faint">{l}</div>
                  <div className="num mt-1 text-[20px] leading-none">{v}</div>
                </div>
              ))}
            </div>
            {[...gmailRescan.reclassified_include.map(i => ({ ...i, dir: "include" as const })),
              ...gmailRescan.reclassified_exclude.map(i => ({ ...i, dir: "exclude" as const }))]
              .map((i, idx) => (
              <div key={idx} className="flex items-start justify-between gap-3 border-t px-4 py-2.5">
                <div className="min-w-0">
                  <div className="truncate text-[13px] font-medium">{i.subject || "(no subject)"}</div>
                  <div className="truncate text-2xs text-faint">{i.from}</div>
                  {i.reasons.length > 0 &&
                    <div className="mt-0.5 text-2xs text-muted">{i.reasons[0]}</div>}
                </div>
                <div className="flex shrink-0 items-center gap-2 text-2xs">
                  <span className="text-faint">{i.old_classification.replace(/_/g, " ")}</span>
                  <span className="text-faint">→</span>
                  <Badge tone={i.dir === "include" ? "believed" : "conflict"}>
                    {i.new_classification.replace(/_/g, " ")}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Recent corrections, from the ops log, not synthesized */}
      <section className="panel overflow-hidden">
        <header className="border-b px-4 py-2.5">
          <h2 className="text-[14px] font-semibold">Recent corrections</h2>
        </header>
        <div className="divide-y">
          {health.recent_corrections.length === 0 &&
            <div className="empty m-5">No scanner corrections recorded yet.</div>}
          {health.recent_corrections.map((c, i) => (
            <div key={i} className="flex items-center justify-between px-4 py-2.5">
              <div>
                <div className="num text-[13px]">{c.proposition}</div>
                <div className="text-2xs text-faint">{c.subjects.join(", ")}</div>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-2xs text-faint">{new Date(c.ts * 1000).toLocaleString()}</span>
                {c.assertion_id && (
                  <Link href={`/assertion?id=${encodeURIComponent(c.assertion_id)}`}
                    className="text-2xs font-semibold text-accent hover:underline">Inspect →</Link>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function ScanRow({ scan, open, onToggle, onApply, busy }:
  { scan: MemoryScan; open: boolean; onToggle: () => void; onApply: () => void; busy: boolean }) {
  const s = scan.summary ?? {};
  const proposed = (s.proposed_retractions ?? 0) + (s.proposed_review ?? 0);
  return (
    <div className="px-4 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <button onClick={onToggle} className="min-w-0 text-left">
          <div className="flex items-center gap-2">
            <span className={cn("num text-[13px]", open ? "text-accent" : "")}>{scan.id}</span>
            <Badge tone={scan.state === "complete" ? "believed" : scan.state === "error" ? "conflict" : "unknown"}>
              {scan.state}
            </Badge>
            <span className="text-2xs text-faint">scope: {scan.scope}</span>
            {scan.applied === 1 && <Badge tone="closed">applied</Badge>}
          </div>
          <div className="mt-0.5 text-2xs text-muted">
            {scan.examined}/{scan.total} examined · {new Date(scan.started * 1000).toLocaleString()}
            {proposed > 0 && !scan.applied &&
              ` · ${s.proposed_retractions ?? 0} to retract, ${s.proposed_review ?? 0} to review`}
          </div>
        </button>
        {scan.state === "complete" && scan.applied === 0 && proposed > 0 && (
          <Button size="sm" variant="danger" onClick={onApply} disabled={busy}>
            {busy ? "Applying…" : "Apply corrections"}
          </Button>
        )}
      </div>
    </div>
  );
}

function ResultRow({ r }: { r: MemoryScanResult }) {
  return (
    <div className="px-4 py-2.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Badge tone={CLS_TONE[r.classification] ?? "muted"}>{r.classification.replace(/_/g, " ")}</Badge>
            <Link href={`/assertion?id=${encodeURIComponent(r.assertion_id)}`}
              className="num text-[13px] text-accent hover:underline">{r.assertion_id}</Link>
            {r.proposed_action &&
              <span className="text-2xs text-faint">→ {r.proposed_action}</span>}
            {r.applied === 1 && <Badge tone="closed">done</Badge>}
            {r.apply_error && <Badge tone="conflict">apply failed</Badge>}
          </div>
          <div className="mt-0.5 text-2xs text-muted">{r.reason}</div>
          {r.evidence && (
            <div className="mt-1 rounded bg-chip px-2 py-1 text-2xs text-muted">{r.evidence}</div>
          )}
        </div>
      </div>
    </div>
  );
}

function FilterChip({ children, active, onClick }:
  { children: React.ReactNode; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick}
      className={cn("rounded-sm border px-2 py-px text-2xs font-semibold uppercase tracking-[0.05em] transition-colors",
        active ? "border-accent text-accent" : "border-line-strong text-muted hover:text-ink")}>
      {children}
    </button>
  );
}
