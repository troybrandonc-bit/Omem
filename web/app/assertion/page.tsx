"use client";
/* Query-param route, not /assertions/[id].
 *
 * `output: "export"` emits a file per route at build time, and a route whose id
 * only exists at runtime has no file to emit — Next needs generateStaticParams,
 * which cannot enumerate ids that have not been created yet. So the id moves
 * into the query string, which is a client-side concern and needs no file.
 *
 * The singular path (/assertion, not /assertions) keeps it from colliding with
 * the list page that already lives at the plural one.
 *
 * useSearchParams() suspends during prerender, so the body sits inside a
 * Suspense boundary. Without it the export fails with "useSearchParams() should
 * be wrapped in a suspense boundary" — a build error, not a runtime one.
 */
import { Suspense, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { api, isGrounded, type WhyResult } from "@/lib/api";
import { useApp } from "@/components/providers";
import { StateBadge, Badge, Card, Skeleton, IntervalStrip, Button } from "@/components/ui/primitives";
import { ProvenanceDAG } from "@/components/viz/provenance-dag";
import {
  ArrowLeft, AlertTriangle, History, ExternalLink, Mail, FileText } from "lucide-react";

function AssertionDetailInner() {
  const id = useSearchParams().get("id") || "";
  const { project, asOf, now } = useApp();
  const T = asOf ?? undefined;

  const { data: why, isLoading } = useQuery({
    queryKey: ["why", project, id, asOf],
    queryFn: () => api.why(project, id, T),
  });

  if (isLoading || !why) return <WhySkeleton />;

  const a = why.assertion;
  const explanation = explainState(why);

  return (
    <div className="mx-auto max-w-5xl">
      <Link href="/memory" className="mb-4 inline-flex items-center gap-1.5 text-2xs text-muted hover:text-fg">
        <ArrowLeft className="h-3.5 w-3.5" /> Memory
      </Link>

      {/* Header: claim, state, and the facts that matter — one dense block. */}
      <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="display text-[24px] leading-tight">{titleOf(a)}</h1>
          <div className="mono mt-1 text-2xs text-muted">{a.proposition}</div>
        </div>
        <div className="flex items-center gap-2">
          {asOf !== null && <Badge tone="unknown">as of t={asOf}</Badge>}
          <StateBadge state={why.state} />
        </div>
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-x-5 gap-y-1.5 border-y py-2.5 text-2xs text-muted">
        <span>about <Link href={`/entity?id=${encodeURIComponent(why.subjects[0]?.id ?? "")}`}
          className="font-medium text-fg hover:text-accent">{why.subjects[0]?.label || why.subjects[0]?.id || "—"}</Link></span>
        <span>asserted by <Link href={`/agent?id=${encodeURIComponent(a.agent)}`}
          className="font-medium text-fg hover:text-accent">{why.agent?.label || a.agent}</Link></span>
        <span>at <span className="num text-fg">t={a.assertion_time}</span></span>
        {a.confidence !== null && <span>source confidence <span className="num text-fg">{a.confidence}</span></span>}
        <span className={isGrounded(why.grounded) ? "text-believed" : "text-unknown"}>
          {isGrounded(why.grounded) ? "grounded in an event" : "not grounded"}
        </span>
        {!a.open && <span className="text-muted">no longer believed</span>}
        <span className="mono ml-auto text-faint">{a.id}</span>
      </div>

      <p className="mb-5 max-w-3xl text-[13px] leading-relaxed text-muted">{explanation}</p>

      <div className="grid grid-cols-3 gap-4">
        {/* left: facts */}
        <div className="space-y-4">
          <Card className="overflow-hidden">
            <header className="border-b px-4 py-2.5"><div className="tech-label">Belief over time</div></header>
            <div className="px-4 py-3">
              <IntervalStrip start={a.belief_interval.start} end={a.belief_interval.end} now={now} min={0} max={Math.max(now, a.belief_interval.start + 1)} />
              <div className="mono mt-1.5 text-2xs text-muted">
                [{a.belief_interval.start}, {a.belief_interval.end ?? "open"})
              </div>
              <p className="mt-2 text-2xs leading-relaxed text-faint">
                Half-open interval: believed from t={a.belief_interval.start}
                {a.belief_interval.end === null ? " with no end recorded." : ` until t=${a.belief_interval.end}.`}
              </p>
            </div>
            {why.subjects.length > 1 && (
              <div className="border-t px-4 py-3">
                <div className="tech-label mb-1.5">Also about</div>
                <div className="flex flex-wrap gap-1">
                  {why.subjects.slice(1).map((s, i) => s && (
                    <Link key={i} href={`/entity?id=${encodeURIComponent(s.id)}`}>
                      <Badge tone="accent">{s.label || s.id}</Badge>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </Card>
        </div>

        {/* center+right: original source, then provenance DAG */}
        <div className="col-span-2 space-y-4">
          <SourceMessage why={why} />
          <Card className="p-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="tech-label">Supporting evidence / provenance</div>
              {isGrounded(why.grounded)
                ? <Badge tone="believed">reaches an event</Badge>
                : <Badge tone="unknown">no event root</Badge>}
            </div>
            {why.provenance.nodes.length > 0
              ? <ProvenanceDAG nodes={why.provenance.nodes} edges={why.provenance.edges} rootId={a.id} />
              : <div className="py-6 text-center text-sm text-muted">No derivations recorded. This belief was asserted directly, without cited evidence.</div>}
          </Card>

          {/* contradictions */}
          {why.contradictions.length > 0 && (
            <Card className="border-[color:var(--conflict)]/40 p-4">
              <div className="mb-2 flex items-center gap-1.5 tech-label text-conflict">
                <AlertTriangle className="h-3.5 w-3.5" /> Contradicted by
              </div>
              {why.contradictions.map(c => (
                <Link key={c.id} href={`/assertion?id=${encodeURIComponent(c.id)}`}
                  className="mb-2 flex items-center justify-between rounded-md border border-[color:var(--conflict)]/30 bg-[color:var(--conflict)]/5 px-3 py-2 hover:bg-[color:var(--conflict)]/10">
                  <div>
                    <div className="text-sm font-medium">{c.label || c.proposition}</div>
                    <div className="text-2xs text-faint">by {c.agent} / t={c.assertion_time}</div>
                  </div>
                  <Badge tone="conflict">opposing</Badge>
                </Link>
              ))}
              <div className="mt-1 text-2xs text-muted">
                Both sides are open at this time, so the proposition is CONTRADICTED. OMEM keeps both. It never silently picks a winner.
              </div>
            </Card>
          )}

          {/* revision chain */}
          {why.revision_chain.length > 1 && (
            <Card className="p-4">
              <div className="mb-3 flex items-center gap-1.5 tech-label">
                <History className="h-3.5 w-3.5" /> Revision history
              </div>
              <div className="space-y-0">
                {why.revision_chain.map((r, i) => (
                  <div key={r.id} className="flex items-center gap-3">
                    <div className="flex flex-col items-center">
                      <div className={`h-2.5 w-2.5 rounded-full ${r.id === a.id ? "bg-accent" : r.is_retraction ? "bg-conflict" : "bg-closed"}`} />
                      {i < why.revision_chain.length - 1 && <div className="h-8 w-px bg-border" />}
                    </div>
                    <Link href={`/assertion?id=${encodeURIComponent(r.id)}`} className="flex-1 py-1 hover:text-accent">
                      <div className="text-sm">{r.is_retraction ? <span className="text-conflict">retracted</span> : (r.label || r.proposition)}</div>
                      <div className="text-2xs text-faint">t={r.assertion_time} {r.id === a.id && "· viewing"}</div>
                    </Link>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

// A readable title. Extraction labels are "<subject line> \u2192 <proposition>";
// when the source had no subject line the label degrades to a bare arrow, so we
// fall back to the proposition rather than rendering "\u2192 something".
function titleOf(a: { label?: string | null; proposition: string }): string {
  const raw = (a.label ?? "").trim();
  const cleaned = raw.replace(/^[\u2192>\-\s]+/, "").trim();
  if (!cleaned || cleaned === a.proposition) return a.proposition;
  return cleaned;
}

// State explanation. Every branch maps exactly onto the frozen proposition_state
// semantics — stated plainly, with nothing inferred beyond the query result.
function explainState(why: { state: string; contradictions: unknown[]; assertion: { open: boolean }; grounded: boolean }): string {
  const grounded = isGrounded(why.grounded);
  switch (why.state) {
    case "BELIEVED_TRUE":
      return grounded
        ? "An open assertion affirms this and nothing open denies it. The claim traces to a recorded event, so it is grounded."
        : "An open assertion affirms this and nothing open denies it. No event backs the claim, so it is ungrounded.";
    case "CONTRADICTED":
      return `Open assertions both affirm and deny this claim, so the engine reports CONTRADICTED. Both sides are kept; OMEM does not pick a winner. ${why.contradictions.length === 1 ? "The opposing assertion is" : "The opposing assertions are"} listed below.`;
    case "BELIEVED_FALSE":
      return "An open assertion denies this and nothing open affirms it.";
    default:
      return "No assertion carries this claim at the selected time. It was either never asserted, or the assertion that carried it was superseded or retracted, closing its belief interval.";
  }
}

function WhySkeleton() {
  return (
    <div className="mx-auto max-w-5xl">
      <Skeleton className="mb-4 h-4 w-24" />
      <Skeleton className="mb-2 h-8 w-96" />
      <Skeleton className="mb-6 h-6 w-64" />
      <Skeleton className="mb-6 h-20 w-full" />
      <div className="grid grid-cols-3 gap-4">
        <Skeleton className="h-64" /><Skeleton className="col-span-2 h-64" />
      </div>
    </div>
  );
}


// The original source material behind a memory. This is what lets a business
// answer "which email did this come from?" — rendered from the stored source
// record, never reconstructed or paraphrased.
function SourceMessage({ why }: { why: WhyResult }) {
  const [open, setOpen] = useState(false);
  const v = why.source?.view;
  const evidence = why.evidence?.evidence;
  if (!v && !evidence) return null;

  // Highlight the exact evidence span inside the real body. The span comes
  // from the stored extraction evidence (a verbatim sentence, possibly quoted);
  // if it isn't found we highlight nothing rather than approximating.
  const evText = (evidence ?? "").replace(/^"+|"+$/g, "").trim();
  const body = v?.body ?? "";
  const hit = evText && body ? body.indexOf(evText.slice(0, 120)) : -1;
  const renderBody = (text: string) => {
    if (hit < 0 || !evText) return <>{text}</>;
    const start = body.indexOf(evText.slice(0, 120));
    const end = Math.min(start + evText.length, body.length);
    // map highlight range onto the (possibly truncated) text being shown
    if (start >= text.length) return <>{text}</>;
    const s = Math.min(start, text.length), e = Math.min(end, text.length);
    return (<>
      {text.slice(0, s)}
      <mark className="rounded-sm bg-[color:var(--accent)]/20 px-0.5 text-inherit">{text.slice(s, e)}</mark>
      {text.slice(e)}
    </>);
  };

  const isEmail = v?.kind === "gmail";
  return (
    <Card className="overflow-hidden">
      <header className="flex items-center justify-between border-b px-4 py-2.5">
        <div className="flex items-center gap-2">
          {isEmail ? <Mail className="h-3.5 w-3.5 text-muted" /> : <FileText className="h-3.5 w-3.5 text-muted" />}
          <span className="tech-label">{v ? (isEmail ? "Original email" : "Original source") : "Source evidence"}</span>
        </div>
        <div className="flex items-center gap-3">
          {why.source?.id && (
            <Link href={`/diagnostics?source=${encodeURIComponent(why.source.id)}`}
              className="text-2xs font-medium text-accent hover:underline">Pipeline diagnostics</Link>
          )}
          {v?.link && (
            <a href={v.link} target="_blank" rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-2xs font-medium text-accent hover:underline">
              Open in {isEmail ? "Gmail" : "source"} <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      </header>

      {v && (
        <div className="space-y-2 px-4 py-3">
          <div className="text-[14px] font-semibold leading-snug">{v.title}</div>
          <div className="grid gap-x-6 gap-y-1 text-2xs text-muted sm:grid-cols-2">
            {v.from && <div><span className="text-faint">From</span> {v.from}</div>}
            {v.to && <div><span className="text-faint">To</span> {v.to}</div>}
            {v.sent_at && <div><span className="text-faint">Sent</span> {v.sent_at}</div>}
            <div><span className="text-faint">Via</span> {v.connector}</div>
          </div>
          {v.body ? (
            <div className="rounded-md bg-raised px-3 py-2.5">
              <p className={"whitespace-pre-wrap break-words text-[13px] leading-relaxed " + (open ? "max-h-[420px] overflow-y-auto" : "")}>
                {renderBody(open ? v.body : v.body.slice(0, hit >= 0 ? Math.max(320, hit + evText.length + 40) : 320))}
                {!open && v.body.length > 320 && "\u2026"}
              </p>
              {v.body.length > 320 && (
                <button onClick={() => setOpen(!open)}
                  className="mt-1.5 text-2xs font-medium text-accent hover:underline">
                  {open ? "Show less" : "Show full message"}
                </button>
              )}
            </div>
          ) : (
            <div className="empty">No readable text in this message.</div>
          )}
        </div>
      )}

      {evidence && (
        <div className={v ? "border-t px-4 py-2.5" : "px-4 py-2.5"}>
          <div className="tech-label mb-1">Matched evidence</div>
          <p className="text-[13px] leading-relaxed">{evidence}</p>
          <div className="mt-1 flex flex-wrap gap-x-4 text-2xs text-muted">
            {why.evidence?.extractor && <span>extractor <span className="mono">{why.evidence.extractor}</span></span>}
            {why.source?.external_id && <span>source <span className="mono">{why.source.external_id}</span></span>}
          </div>
        </div>
      )}
    </Card>
  );
}

export default function AssertionDetail() {
  return (
    <Suspense fallback={null}>
      <AssertionDetailInner />
    </Suspense>
  );
}
