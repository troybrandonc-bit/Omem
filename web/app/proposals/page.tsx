"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, type ResolveReport } from "@/lib/api";
import { useApp } from "@/components/providers";
import { Skeleton, Button, Badge, EmptyState } from "@/components/ui/primitives";
import { GitMerge } from "lucide-react";

// The judgment queue. Two kinds of question wait here, and neither touches
// the engine until somebody decides. Merge proposals: the machine suspects
// two entities are one person. Tensions: live relations break a declared
// shape (works_at was declared one-employer-at-a-time, and Sarah has two).
// Every decision is recorded under the decider's name, and a rejection or
// dismissal is permanent for the machine: never the same question twice.

function Pair({ a, b }: { a: string; b: string }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="mono text-sm">{a}</span>
      <span className="text-2xs text-faint">is the same person as</span>
      <span className="mono text-sm">{b}</span>
    </div>
  );
}

export default function Proposals() {
  const { project } = useApp();
  const qc = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [report, setReport] = useState<ResolveReport | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["merge-proposals", project],
    queryFn: () => api.mergeProposals(project), refetchInterval: 8000,
    enabled: !!project,
  });
  const { data: tensionData } = useQuery({
    queryKey: ["tensions", project],
    queryFn: () => api.tensions(project), refetchInterval: 8000,
    enabled: !!project,
  });
  const { data: questionData } = useQuery({
    queryKey: ["expectations-asking", project],
    queryFn: () => api.expectations(project, "asking"), refetchInterval: 8000,
    enabled: !!project,
  });

  function refresh() {
    qc.invalidateQueries({ queryKey: ["merge-proposals", project] });
    qc.invalidateQueries({ queryKey: ["tensions", project] });
    qc.invalidateQueries({ queryKey: ["expectations-asking", project] });
    qc.invalidateQueries({ queryKey: ["entities", project] });
  }

  async function act(label: string, fn: () => Promise<unknown>) {
    setBusy(label); setErr(null);
    try { await fn(); } catch (e) { setErr((e as Error).message); }
    setBusy(null); refresh();
  }

  const runPass = () =>
    act("resolve", async () => {
      setReport(await api.runResolve(project));
      await api.runCheck(project);
    });
  const decide = (id: string, decision: "approve" | "reject") =>
    act(`${decision}-${id}`, () => api.mergeDecide(project, id, decision));
  const keepTension = (id: string, keep: string) =>
    act(`keep-${id}-${keep}`, () => api.tensionResolve(project, id, keep));
  const dismissTension = (id: string) =>
    act(`dismiss-${id}`, () => api.tensionDismiss(project, id));
  const answerQ = (id: string, answer: "yes" | "no") =>
    act(`answer-${id}-${answer}`, () => api.answerExpectation(project, id, answer));
  const questions = questionData?.data ?? [];

  const rows = data?.data ?? [];
  const open = rows.filter(p => p.status === "open");
  const decided = rows.filter(p => p.status !== "open")
    .sort((a, b) => (b.decided ?? 0) - (a.decided ?? 0));
  const tensions = tensionData?.data ?? [];
  const openTensions = tensions.filter(t => t.status === "open");
  const decidedTensions = tensions
    .filter(t => t.status === "resolved" || t.status === "dismissed")
    .sort((a, b) => (b.decided ?? 0) - (a.decided ?? 0));

  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="mb-1 display text-lg">Proposals</h1>
          <p className="max-w-lg text-sm text-muted">
            The machine suspects two records are one person, and waits. Approving records
            the merge under your name; rejecting is permanent, and a merge a person later
            splits is never proposed again.
          </p>
        </div>
        <Button size="sm" variant="secondary" disabled={busy !== null} onClick={runPass}>
          {busy === "resolve" ? "…" : "Run resolution pass"}
        </Button>
      </div>

      {err && (
        <div className="mb-4 rounded-md border border-[color:var(--conflict)]/50 bg-[color:var(--conflict)]/10 px-4 py-2.5 text-sm text-conflict">
          {err}
        </div>
      )}

      {report && (
        <div className="mb-5 overflow-hidden rounded-lg border">
          <div className="flex items-center justify-between border-b px-4 py-2">
            <span className="text-xs font-medium">Last pass</span>
            <span className="text-2xs text-faint">
              {report.examined} people examined · {report.merged.length} merged ·{" "}
              {report.proposed.length} proposed · {report.refused.length} refused
            </span>
          </div>
          {report.merged.length > 0 && (
            <div className="border-b px-4 py-2.5 text-sm">
              {report.merged.map((m, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2 py-0.5">
                  <Badge tone="believed">merged</Badge>
                  <span className="text-2xs text-muted">{m.evidence}</span>
                </div>
              ))}
            </div>
          )}
          {report.refused.length > 0 && (
            <div className="px-4 py-2.5">
              {report.refused.map((r, i) => (
                <div key={i} className="flex flex-wrap items-center gap-2 py-0.5 text-2xs text-muted">
                  <span className="mono">{r.pair[0]}</span>
                  <span className="text-faint">×</span>
                  <span className="mono">{r.pair[1]}</span>
                  <span className="text-faint">· {r.reason}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {isLoading ? <Skeleton className="h-40" /> :
        open.length === 0 ?
          <EmptyState icon={GitMerge} title="Nothing awaiting judgment"
            body="When a pass finds suggestive evidence that two entities are one person, the pair waits here. Decisive evidence merges on its own, with provenance." /> :
          <div className="space-y-3">
            {open.map(p => (
              <div key={p.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4">
                <div className="min-w-0">
                  <Pair a={p.entity_a} b={p.entity_b} />
                  <div className="mt-1.5 text-2xs text-muted">{p.evidence}</div>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button size="sm" variant="secondary" disabled={busy !== null}
                    onClick={() => decide(p.id, "approve")}>
                    {busy === `approve-${p.id}` ? "…" : "Same person"}
                  </Button>
                  <Button size="sm" variant="danger" disabled={busy !== null}
                    onClick={() => decide(p.id, "reject")}>
                    {busy === `reject-${p.id}` ? "…" : "Different people"}
                  </Button>
                </div>
              </div>
            ))}
          </div>}

      {questions.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-1 text-sm font-medium">Questions</h2>
          <p className="mb-3 max-w-lg text-2xs text-muted">
            Hunches OMEM could not settle on its own. Your answer becomes real
            evidence under your name, and the verdict still comes from
            interrogation, never by decree.
          </p>
          <div className="space-y-3">
            {questions.map(h => (
              <div key={h.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border p-4">
                <div className="min-w-0">
                  <div className="text-sm">{h.docket.gaps[0] ?? h.because}</div>
                  <div className="mt-1.5 text-2xs text-faint">
                    strength {h.strength} · {h.docket.supports.length} supporting ·{" "}
                    {h.docket.undermines.length} undermining
                  </div>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button size="sm" variant="secondary" disabled={busy !== null}
                    onClick={() => answerQ(h.id, "yes")}>
                    {busy === `answer-${h.id}-yes` ? "…" : "Yes"}
                  </Button>
                  <Button size="sm" variant="danger" disabled={busy !== null}
                    onClick={() => answerQ(h.id, "no")}>
                    {busy === `answer-${h.id}-no` ? "…" : "No"}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {openTensions.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-1 text-sm font-medium">Tensions</h2>
          <p className="mb-3 max-w-lg text-2xs text-muted">
            Live relations break a declared shape. Keep the one that is current,
            and the others are retracted under your name, or dismiss if both are
            genuinely true.
          </p>
          <div className="space-y-3">
            {openTensions.map(t => (
              <div key={t.id} className="rounded-lg border p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="mono text-sm">{t.entity}</span>
                  <span className="text-2xs text-faint">
                    has {Object.keys(t.holders).length} live «{t.relation}» where the
                    declared shape allows one
                  </span>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {Object.keys(t.holders).sort().map(cp => (
                    <Button key={cp} size="sm" variant="secondary" disabled={busy !== null}
                      onClick={() => keepTension(t.id, cp)}>
                      {busy === `keep-${t.id}-${cp}` ? "…" : `Keep ${cp.split(":").pop()}`}
                    </Button>
                  ))}
                  <Button size="sm" variant="danger" disabled={busy !== null}
                    onClick={() => dismissTension(t.id)}>
                    {busy === `dismiss-${t.id}` ? "…" : "Both are fine"}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {decidedTensions.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-2 text-sm font-medium">Judged tensions</h2>
          <div className="overflow-hidden rounded-lg border">
            {decidedTensions.map(t => (
              <div key={t.id} className="flex flex-wrap items-center gap-2 border-b px-4 py-2 text-2xs last:border-b-0">
                <Badge tone={t.status === "resolved" ? "believed" : "closed"}>{t.status}</Badge>
                <span className="mono">{t.entity}</span>
                <span className="text-faint">{t.relation}</span>
                {t.kept && <span className="text-faint">kept {t.kept}</span>}
                {t.decided_by && <span className="ml-auto text-faint">by {t.decided_by}</span>}
              </div>
            ))}
          </div>
        </section>
      )}

      {decided.length > 0 && (
        <section className="mt-8">
          <h2 className="mb-2 text-sm font-medium">Decided</h2>
          <div className="overflow-hidden rounded-lg border">
            {decided.map(p => (
              <div key={p.id} className="flex flex-wrap items-center gap-2 border-b px-4 py-2 text-2xs last:border-b-0">
                <Badge tone={p.status === "approved" ? "believed" : "closed"}>{p.status}</Badge>
                <span className="mono">{p.entity_a}</span>
                <span className="text-faint">×</span>
                <span className="mono">{p.entity_b}</span>
                {p.decided_by && <span className="ml-auto text-faint">by {p.decided_by}</span>}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
