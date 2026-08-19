"use client";
import { useState } from "react";
import { cn } from "@/lib/cn";
import { ChevronRight, MoreHorizontal } from "lucide-react";

// Matches the live demo project the API serves: a:alice-email (conf 0.62),
// grounded in ticket:8842, contradicted at t=3 by import-bot via crm:sync:19.
// The revisions strip shows the store's real revision chain (Bob's plan).

type T = 1 | 3 | 99; // 99 = now
const LABEL: Record<T, string> = { 1: "t=1", 3: "t=3", 99: "now" };

export function BeliefInspector() {
  const [t, setT] = useState<T>(99);
  const contradicted = t >= 3;

  return (
    <div className="panel overflow-hidden text-[13px]">
      {/* breadcrumb header */}
      <div className="flex items-center justify-between border-b px-4 py-2.5">
        <div className="flex items-center gap-1 text-[13px]">
          <span className="text-muted">Assertions</span>
          <span className="text-faint">/</span>
          <span className="font-medium text-accent">a:alice-email</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-2xs text-faint">as of</span>
          <select value={t} onChange={e => setT(Number(e.target.value) as T)}
            className="rounded-md border bg-panel px-2 py-1 text-2xs font-medium">
            <option value={99}>now</option>
            <option value={3}>t=3</option>
            <option value={1}>t=1</option>
          </select>
          <MoreHorizontal className="h-4 w-4 text-faint" />
        </div>
      </div>

      {/* state + claim + confidence */}
      <div className="border-b px-4 py-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="mb-1.5 flex items-center gap-2.5">
              <span className="tech-label">Belief state</span>
              <span className="inline-flex items-center gap-1.5 rounded-pill bg-chip px-2.5 py-1 text-2xs font-semibold uppercase tracking-[0.04em]">
                <span className={cn("led", contradicted ? "conflict" : "believed")} style={{ width: 7, height: 7 }} />
                {contradicted ? "Contradicted" : "Believed true"}
              </span>
            </div>
            <div className="display text-[19px]">Customer prefers email over phone</div>
          </div>
          <div className="shrink-0 text-right">
            <div className="tech-label mb-1">Confidence</div>
            <div className="num text-[15px]">0.62</div>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          <span className="chip">id <b>a:alice-email</b></span>
          <span className="chip">asserted by <b>support-bot@v2.1</b></span>
          <span className="chip">asserted <b>t=1</b></span>
          <span className="chip">event <b>t=1</b></span>
        </div>
      </div>

      {/* provenance | contradictions + timeline */}
      <div className="grid border-b md:grid-cols-[1.15fr_1fr]">
        <div className="border-b px-4 py-3.5 md:border-b-0 md:border-r">
          <div className="mb-3 text-[13px] font-semibold">Provenance</div>
          <div className="space-y-3">
            <Node dot="believed" id="ticket:8842" kind="event / source" line={'"prefer email please"'} time="t=1" />
            <Node dot="hollow" id="d:1" kind="derivation" line="extraction from event" time="t=1" />
            <Node dot="accent" id="a:alice-email" kind="assertion / current belief" line="prefers_email_over_phone" time="t=1" />
          </div>
          <button className="mt-3.5 rounded-lg border bg-panel px-3 py-1.5 text-2xs font-medium transition-colors hover:bg-raised">
            View full provenance
          </button>
        </div>

        <div className="px-4 py-3.5">
          <div className="mb-2.5 text-[13px] font-semibold">Contradictions</div>
          {contradicted ? (
            <>
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">not:prefers_email_over_phone</div>
                  <div className="mt-1 flex flex-wrap gap-x-3 text-2xs text-muted">
                    <span>import-bot@v1</span><span>t=3</span><span>crm:sync:19</span>
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-faint" />
              </div>
              <button className="mt-3 rounded-lg border bg-panel px-3 py-1.5 text-2xs font-medium transition-colors hover:bg-raised">
                View contradiction
              </button>
            </>
          ) : (
            <div className="text-2xs text-muted">None at {LABEL[t]}. The CRM sync that disputes this arrives at t=3.</div>
          )}

          <div className="mt-4 border-t pt-3.5">
            <div className="mb-3 text-[13px] font-semibold">Timeline</div>
            <div className="relative mx-2 h-14">
              {/* the track, drawn at the exact y of every dot center (5px) */}
              <div className="absolute left-0 right-0 top-[5px] h-px bg-line-strong" style={{ background: "var(--line-strong)" }} />
              {[
                { at: 1 as T, pos: "0%", tone: "bg-fg", label: "asserted", cls: "text-muted" },
                { at: 3 as T, pos: "52%", tone: "bg-conflict", label: "contradicted", cls: "text-conflict" },
                { at: 99 as T, pos: "100%", tone: "bg-accent", label: "current", cls: "text-muted" },
              ].map(p => (
                <button key={p.at} onClick={() => setT(p.at)} aria-label={`as of ${LABEL[p.at]}`}
                  className="absolute top-0 flex -translate-x-1/2 flex-col items-center p-0"
                  style={{ left: p.pos }}>
                  <span className={cn("block h-2.5 w-2.5 rounded-full transition-shadow", p.tone,
                    t === p.at && "ring-2 ring-accentBg")} />
                  <span className={cn("num mt-1.5 block text-2xs leading-none", p.cls)}>{LABEL[p.at]}</span>
                  <span className={cn("mt-1 block text-2xs leading-none", p.cls)}>{p.label}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* revisions: the store's real revision chain */}
      <div className="px-4 py-3.5">
        <div className="mb-2.5 flex items-center justify-between">
          <span className="text-[13px] font-semibold">Revisions</span>
          <span className="text-2xs text-faint">from this store: customer:bob</span>
        </div>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <Rev id="a:bob-free" time="t=4" note="asserted" />
          <span className="text-faint">→</span>
          <Rev id="a:bob-pro" time="t=6" note="superseded plan" />
          <button className="ml-auto rounded-lg border bg-panel px-3 py-1.5 text-2xs font-medium transition-colors hover:bg-raised">
            Explore in timeline
          </button>
        </div>
      </div>
    </div>
  );
}

function Node({ dot, id, kind, line, time }: { dot: string; id: string; kind: string; line: string; time: string }) {
  return (
    <div className="flex gap-2.5">
      <span className={cn("led mt-1", dot)} />
      <div className="min-w-0">
        <div className="font-medium">{id}</div>
        <div className="text-2xs text-muted">{kind}</div>
        <div className="truncate text-2xs text-muted">{line}</div>
        <div className="num text-2xs text-faint">{time}</div>
      </div>
    </div>
  );
}
function Rev({ id, time, note }: { id: string; time: string; note: string }) {
  return (
    <div>
      <div className="text-[13px] font-medium">{id}</div>
      <div className="text-2xs text-muted"><span className="num">{time}</span> {note}</div>
    </div>
  );
}
