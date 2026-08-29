"use client";
import { Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Badge, Card, Skeleton } from "@/components/ui/primitives";
import { ChevronDown, ChevronRight } from "lucide-react";

// The full decision trace for one email: raw message -> participants ->
// identity -> classification -> analysis -> per-sentence speech acts ->
// fact decisions -> final assertions. Every value is computed from the stored
// source record and persisted pipeline state; nothing is fabricated. This is
// how we debug "why did OMEM (not) remember this?"

const ACT_TONE: Record<string, "believed" | "unknown" | "conflict" | "muted" | "closed"> = {
  DECISION: "believed", COMPLETED: "believed", STATEMENT: "believed",
  INTENTION: "unknown", CONSIDERATION: "unknown", REQUEST: "unknown",
  QUESTION: "muted", SUGGESTION: "muted", MARKETING_CTA: "conflict",
};

function Stage({ title, children, defaultOpen = true }:
  { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card className="overflow-hidden">
      <button onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 border-b px-4 py-2.5 text-left">
        {open ? <ChevronDown className="h-3.5 w-3.5 text-muted" /> : <ChevronRight className="h-3.5 w-3.5 text-muted" />}
        <span className="text-sm font-semibold">{title}</span>
      </button>
      {open && <div className="px-4 py-3">{children}</div>}
    </Card>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex gap-2 text-sm">
      <span className="w-36 shrink-0 text-2xs capitalize text-faint">{k}</span>
      <span className="min-w-0 break-words">{v ?? <span className="text-faint">not recorded</span>}</span>
    </div>
  );
}

function DiagnosticsInner() {
  const { project } = useApp();
  const params = useSearchParams();
  const source = params.get("source") ?? "";
  const [input, setInput] = useState(source);

  const { data: d, isLoading, error } = useQuery({
    queryKey: ["email-diagnostics", project, source],
    queryFn: () => api.emailDiagnostics(project, source),
    enabled: !!source,
    retry: false,
  });

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="display text-lg">Email diagnostics</h1>
        <form className="flex items-center gap-2"
          onSubmit={e => { e.preventDefault(); window.location.href = `/diagnostics?source=${encodeURIComponent(input)}`; }}>
          <input value={input} onChange={e => setInput(e.target.value)}
            placeholder="source record id (src_…)"
            className="w-64 rounded-md border bg-panel px-3 py-1.5 font-mono text-xs outline-none focus:border-accent" />
          <button type="submit" className="rounded-md bg-accent px-3 py-1.5 text-sm font-semibold text-accentFg">Trace</button>
        </form>
      </div>

      {!source && (
        <div className="empty m-5">
          Open a memory and press &ldquo;Pipeline diagnostics&rdquo; on its evidence, or paste a
          source record id above. The trace shows every decision from raw email to final memory.
        </div>
      )}
      {source && isLoading && <Skeleton className="h-64" />}
      {source && !!error && (
        <div className="rounded-md border border-[color:var(--conflict)]/50 bg-[color:var(--conflict)]/10 px-4 py-2.5 text-sm text-conflict">
          {(error as Error).message}
        </div>
      )}

      {d && (
        <div className="space-y-3">
          <Stage title="1 · Raw email">
            <div className="space-y-1">
              <KV k="From" v={d.source.from} />
              <KV k="To" v={d.source.to} />
              {d.source.cc && <KV k="Cc" v={d.source.cc} />}
              <KV k="Subject" v={<span className="font-medium">{d.source.subject || "(no subject)"}</span>} />
              <KV k="Received" v={new Date(d.source.received * 1000).toLocaleString()} />
              <KV k="Thread" v={<span className="mono text-2xs">{d.source.thread_id}</span>} />
              <KV k="Source id" v={<span className="mono text-2xs">{d.source.id}</span>} />
            </div>
            {d.source.body && (
              <pre className="mt-2 max-h-56 overflow-y-auto whitespace-pre-wrap rounded-md bg-raised px-3 py-2.5 text-xs leading-relaxed">{d.source.body}</pre>
            )}
          </Stage>

          <Stage title="2 · Participants & identity">
            <div className="space-y-1">
              <KV k="Our identity" v={
                <>{d.identity.company_name && <span className="font-medium">{d.identity.company_name} · </span>}
                  {[...d.identity.domains, ...d.identity.emails].join(", ") || "not configured"}</>} />
              <KV k="Sender" v={<>{d.participants.sender_name || d.participants.sender_email}
                {" "}<span className="text-faint">({d.participants.sender_email})</span>
                {d.participants.sender_is_self && <Badge tone="accent" className="ml-2">SELF</Badge>}
                {d.sender_role_override && <Badge tone="believed" className="ml-2">{d.sender_role_override}</Badge>}</>} />
              <KV k="Direction" v={<Badge tone={d.participants.direction === "unknown" ? "muted" : "accent"}>{d.participants.direction}</Badge>} />
              <KV k="Counterparty" v={d.participants.counterparty_email} />
              {d.participants.internal && <KV k="Scope" v={<Badge tone="closed">internal</Badge>} />}
            </div>
          </Stage>

          <Stage title="3 · Business relevance">
            <div className="space-y-1">
              <KV k="Classification" v={<Badge tone={d.classification_now.classification === "BUSINESS_RELEVANT" ? "believed" : d.classification_now.classification === "AUTOMATED_NOISE" ? "conflict" : "unknown"}>{d.classification_now.classification.replace(/_/g, " ")}</Badge>} />
              <KV k="Confidence" v={<span className="num">{d.classification_now.confidence}</span>} />
              <KV k="Category" v={d.analysis.category.replace(/_/g, " ")} />
              {d.analysis.saas_self_notification && <KV k="SaaS self" v={<Badge tone="conflict">platform notification about our own account</Badge>} />}
              <KV k="Marketing score" v={<span className="num">{d.analysis.marketing_score}</span>} />
              <KV k="Reasons" v={(d.classification_now.reasons ?? []).join(" · ")} />
            </div>
          </Stage>

          <Stage title="4 · Sentences & speech acts" defaultOpen={false}>
            <div className="space-y-1.5">
              {d.sentences.length === 0 && <div className="empty">No sentences.</div>}
              {d.sentences.map((s, i) => (
                <div key={i} className="flex items-start gap-2">
                  <Badge tone={ACT_TONE[s.speech_act] ?? "muted"}>{s.speech_act.replace(/_/g, " ")}</Badge>
                  <span className="min-w-0 break-words text-sm">{s.text}</span>
                </div>
              ))}
            </div>
          </Stage>

          <Stage title="5 · Fact decisions (quality gate)">
            {d.fact_decisions.length === 0 &&
              <div className="empty">No candidate facts reached the gate for this email.</div>}
            <div className="space-y-2">
              {d.fact_decisions.map(fd => (
                <div key={fd.id} className="rounded-md border px-3 py-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="num text-sm font-medium">{fd.subject} · {fd.proposition}</span>
                    <Badge tone={fd.stored ? "believed" : "conflict"}>{fd.stored ? "STORED" : "REJECTED"}</Badge>
                    <Badge tone="muted">{fd.quality.replace(/_/g, " ").toLowerCase()}</Badge>
                    {fd.score != null && <span className="num text-2xs text-muted">{fd.score}</span>}
                  </div>
                  <ul className="mt-1 list-inside list-disc text-2xs text-muted">
                    {fd.reasons.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              ))}
            </div>
          </Stage>

          <Stage title="6 · Final memory (engine state)">
            {d.assertions.length === 0 &&
              <div className="empty">This email produced no assertions.</div>}
            <div className="space-y-1.5">
              {d.assertions.map(a => (
                <div key={a.assertion_id} className="flex flex-wrap items-center gap-2 text-sm">
                  <Link href={`/assertion?id=${encodeURIComponent(a.assertion_id)}`}
                    className="num text-accent hover:underline">{a.proposition ?? a.assertion_id}</Link>
                  <span className="text-2xs text-muted">{a.subjects.join(", ")}</span>
                  <Badge tone={a.open ? "believed" : "closed"}>{a.open ? "believed" : "no longer believed"}</Badge>
                  {a.confidence != null && <span className="num text-2xs text-muted">conf {a.confidence}</span>}
                </div>
              ))}
            </div>
          </Stage>
        </div>
      )}
    </div>
  );
}

export default function Diagnostics() {
  return <Suspense fallback={<Skeleton className="h-64" />}><DiagnosticsInner /></Suspense>;
}
