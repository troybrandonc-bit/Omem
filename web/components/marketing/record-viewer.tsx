"use client";
import { useCallback, useMemo, useRef, useState } from "react";
import {
  FileText, MessageSquare, Zap, Plug, User, Sparkles,
  Check, X, AlertTriangle, HelpCircle, Upload, ShieldCheck,
  GitPullRequestClosed, Fingerprint, Eye,
} from "lucide-react";
import { cn } from "@/lib/cn";
import { validate, LEVELS, type Entry, type Level } from "@/lib/testimony";

/* Reading a Testimony Record without installing anything.
 *
 * WHY THIS EXISTS. Until now the only reason to emit a record was to claim a
 * conformance level, and nobody wants a badge. Everything built around the
 * format so far serves CHECKING a record: a validator, a CI action, a
 * register. Nothing made a record useful to the person who produced it.
 *
 * A record is a good account of what an agent believed, what disagreed with
 * what, and what was approved. That is hard to get out of ordinary logs and
 * genuinely useful while debugging. If reading one is a drag and drop, the
 * conformance level becomes a side effect of a thing somebody already wanted.
 *
 * NOTHING IS UPLOADED. Records carry real data, and a viewer that posted them
 * to a server would be asking people to hand over exactly what the format
 * exists to protect. Parsing, validation and rendering all happen here. There
 * is no endpoint to send it to. */

const EVIDENCE_ICON: Record<string, typeof FileText> = {
  document: FileText, message: MessageSquare, event: Zap,
  api: Plug, human: User, derived: Sparkles,
};

const STATE_LABEL: Record<string, string> = {
  believed_true: "held", believed_false: "no longer held",
  contradicted: "contradicted", unknown: "unknown",
};

function s(v: unknown) {
  return typeof v === "string" ? v : "";
}
function a(v: unknown) {
  return Array.isArray(v) ? v : [];
}
function o(v: unknown) {
  return v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>) : {};
}

function Verdict({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      {ok
        ? <Check className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-600" aria-hidden />
        : <X className="mt-0.5 h-3.5 w-3.5 shrink-0 text-red-600" aria-hidden />}
      <span className={cn("text-note", ok ? "text-muted" : "text-fg")}>{children}</span>
    </div>
  );
}

export function RecordViewer() {
  const [text, setText] = useState("");
  const [dragging, setDragging] = useState(false);
  const [name, setName] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const report = useMemo(() => (text.trim() ? validate(text) : null), [text]);

  const load = useCallback((file: File) => {
    setName(file.name);
    file.text().then(setText);
  }, []);

  const byId = useMemo(() => {
    const m = new Map<string, Entry>();
    report?.entries.forEach((e) => { if ("id" in e) m.set(s(e.id), e); });
    return m;
  }, [report]);

  return (
    <div>
      {/* ── input ─────────────────────────────────────────────────────── */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const f = e.dataTransfer.files?.[0];
          if (f) load(f);
        }}
        className={cn(
          "rounded-lg border border-dashed p-8 text-center transition-colors",
          dragging ? "border-fg bg-subtle" : "border-rule",
        )}
      >
        <Upload className="mx-auto h-5 w-5 text-faint" aria-hidden />
        <p className="mt-3 text-note text-muted">
          Drop a <span className="mono">.jsonl</span> record here, or{" "}
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="underline hover:text-fg"
          >
            choose a file
          </button>
          .
        </p>
        <p className="mt-2 text-caption text-faint">
          Nothing is uploaded. The file is read, checked and drawn in this tab,
          and there is no endpoint to send it to.
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".jsonl,.json,.txt,application/json"
          className="sr-only"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) load(f);
          }}
        />
      </div>

      <details className="mt-3">
        <summary className="cursor-pointer text-caption text-faint hover:text-muted">
          or paste one
        </summary>
        <textarea
          value={text}
          onChange={(e) => { setText(e.target.value); setName(""); }}
          rows={6}
          spellCheck={false}
          placeholder={'{"spec":"testimony-record/0.2","type":"scope", ...}'}
          className="mono mt-2 w-full rounded border border-rule bg-transparent p-3 text-caption"
        />
      </details>

      {!report && (
        <p className="mt-8 text-note text-muted">
          Do not have one to hand? The{" "}
          <a href="/spec/testimony-record/emitting" className="underline">
            emitting guide
          </a>{" "}
          produces one from an ordinary two-table store in about forty lines,
          and the{" "}
          <a href="/testimony-record-example.jsonl" className="underline">
            published example
          </a>{" "}
          is a conforming record you can drop straight in.
        </p>
      )}

      {report && (
        <>
          {/* ── verdict ─────────────────────────────────────────────── */}
          <div className="mt-8 rounded-lg border border-rule p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <div>
                <div className="tech-label">Conformance</div>
                <div className="display mt-1 text-2xl">
                  {report.level ?? "no level reached"}
                  {report.scope === "record only" && report.level && (
                    <span className="text-muted">, record only</span>
                  )}
                </div>
              </div>
              {name && <div className="mono text-caption text-faint">{name}</div>}
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              {LEVELS.map((lvl) => (
                <span
                  key={lvl}
                  className={cn(
                    "mono rounded border px-2 py-1 text-caption",
                    report.levelsMet[lvl]
                      ? "border-emerald-600/40 text-emerald-700 dark:text-emerald-400"
                      : "border-rule text-faint",
                  )}
                >
                  {lvl} {report.levelsMet[lvl] ? "met" : "not met"}
                </span>
              ))}
            </div>

            {report.level !== "TR-4" && LEVELS.some(
              (l) => report.levelsMet[l] &&
                (!report.level || LEVELS.indexOf(l) > LEVELS.indexOf(report.level)),
            ) && (
              <p className="mt-4 text-note text-muted">
                A level above the one reached is satisfied. The levels are
                cumulative, so it does not count yet, but the work is done and
                the checks are listed below either way.
              </p>
            )}

            <div className="mt-5 space-y-4">
              {LEVELS.map((lvl: Level) => {
                const here = report.checks.filter((c) => c.level === lvl);
                if (!here.length) return null;
                return (
                  <div key={lvl}>
                    <div className="mono text-caption text-faint">{lvl}</div>
                    <div className="mt-1.5 space-y-1">
                      {here.map((c) => (
                        <div key={c.check}>
                          <Verdict ok={c.ok}>{c.check}</Verdict>
                          {!c.ok && c.detail && (
                            <p className="ml-[22px] text-caption text-faint">{c.detail}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* ── what the agent believed ─────────────────────────────── */}
          <Timeline report={report} byId={byId} />
        </>
      )}
    </div>
  );
}

function Timeline({
  report, byId,
}: { report: NonNullable<ReturnType<typeof validate>>; byId: Map<string, Entry> }) {
  const entries = report.entries;
  const conflicts = entries.filter((e) => s(e.type) === "conflict");
  const decisions = entries.filter((e) => s(e.type) === "decision");
  const beliefs = entries.filter((e) => s(e.type) === "belief");

  /* Which beliefs are a side of a disagreement, so they can be shown as a pair
   * rather than as two unrelated rows the reader has to notice. */
  const inConflict = new Set(conflicts.flatMap((c) => a(c.sides).map(s)));

  return (
    <div className="mt-10 space-y-10">
      <section>
        <h2 className="display text-lg">
          What it believed{" "}
          <span className="text-muted">({beliefs.length})</span>
        </h2>
        {beliefs.length === 0 && (
          <p className="mt-2 text-note text-muted">No beliefs in this record.</p>
        )}
        <div className="mt-3 space-y-3">
          {beliefs.filter((b) => !inConflict.has(s(b.id))).map((b) => (
            <BeliefCard key={s(b.id)} belief={b} byId={byId} />
          ))}
        </div>
      </section>

      {conflicts.length > 0 && (
        <section>
          <h2 className="display text-lg">
            Where it disagreed with itself{" "}
            <span className="text-muted">({conflicts.length})</span>
          </h2>
          <p className="mt-1 text-note text-muted">
            Both sides are retained. Neither was discarded to produce the other,
            which is the specific thing this format exists to prevent.
          </p>
          <div className="mt-3 space-y-4">
            {conflicts.map((c) => {
              const sides = a(c.sides).map((x) => byId.get(s(x))).filter(Boolean) as Entry[];
              const res = o(c.resolution);
              return (
                <div key={s(c.id)} className="rounded-lg border border-amber-600/30 p-4">
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-amber-600" aria-hidden />
                    <span className="mono text-note">
                      {s(c.subject)} / {s(c.proposition)}
                    </span>
                  </div>
                  <div className="mt-3 grid gap-3 md:grid-cols-2">
                    {sides.map((b) => (
                      <BeliefCard key={s(b.id)} belief={b} byId={byId} bare />
                    ))}
                  </div>
                  <p className="mt-3 text-caption text-faint">
                    {Object.keys(res).length
                      ? `Resolved by ${s(o(res.by).id) || s(res.by)} (${s(res.method)}), keeping ${s(res.kept)}.`
                      : "Unresolved, which is a valid and honest state."}
                  </p>
                </div>
              );
            })}
          </div>
        </section>
      )}

      {decisions.length > 0 && (
        <section>
          <h2 className="display text-lg">
            What it tried to do{" "}
            <span className="text-muted">({decisions.length})</span>
          </h2>
          <div className="mt-3 space-y-2">
            {decisions.map((d) => {
              const refused = s(d.verdict) === "refused";
              const ap = o(byId.get(s(d.approval)));
              const who = o(ap.approver);
              return (
                <div key={s(d.id)} className="rounded border border-rule p-3">
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                    {refused
                      ? <GitPullRequestClosed className="h-4 w-4 text-red-600" aria-hidden />
                      : <ShieldCheck className="h-4 w-4 text-emerald-600" aria-hidden />}
                    <span className="mono text-note">{s(d.action_type)}</span>
                    <span className="mono text-caption text-faint">
                      {s(d.risk_class)} risk, from {s(d.risk_source) || "unstated"}
                    </span>
                    <span className="text-caption text-muted">
                      {refused ? "refused" : d.executed ? "permitted and ran" : "permitted"}
                    </span>
                  </div>
                  {refused && (
                    <p className="mt-1 text-caption text-muted">
                      Reason: {s(d.reason) || <em>none recorded</em>}
                    </p>
                  )}
                  <p className="mt-1 text-caption text-faint">
                    {Object.keys(who).length ? (
                      <>
                        Approved by <span className="mono">{s(who.id)}</span>
                        {s(who.name) && <> ({s(who.name)})</>}, identity from{" "}
                        <span className="mono">{s(ap.identity_source)}</span>
                      </>
                    ) : (
                      "No approval entry."
                    )}
                  </p>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <section>
        <h2 className="display text-lg">Provenance and integrity</h2>
        <div className="mt-3 space-y-2">
          {entries.filter((e) => s(e.type) === "integrity").map((g) => (
            <div key={s(g.id)} className="flex items-start gap-2">
              <Fingerprint className="mt-0.5 h-4 w-4 shrink-0 text-muted" aria-hidden />
              <p className="text-note text-muted">
                <span className="mono">{s(g.scheme)}</span>
                {s(g.engine) && <> via {s(g.engine)} {s(g.engine_version)}</>}, covering{" "}
                {a(g.covers).length || "every"} entr{a(g.covers).length === 1 ? "y" : "ies"}.{" "}
                <span className="mono text-caption text-faint">{s(g.digest)}</span>
              </p>
            </div>
          ))}
          {!entries.some((e) => s(e.type) === "integrity") && (
            <p className="text-note text-muted">
              No integrity entry, so nothing in this record states how alteration
              would be detected.
            </p>
          )}
          <p className="pt-2 text-caption text-faint">
            {entries.filter((e) => s(e.type) === "evidence").length} evidence
            entr{entries.filter((e) => s(e.type) === "evidence").length === 1 ? "y" : "ies"},{" "}
            {entries.filter((e) => s(e.type) === "evidence" && e.redacted === true).length}{" "}
            redacted. A redacted entry still carries its digest, so the cited
            source can be shown unchanged by whoever holds it.
          </p>
        </div>
      </section>
    </div>
  );
}

function BeliefCard({
  belief, byId, bare = false,
}: { belief: Entry; byId: Map<string, Entry>; bare?: boolean }) {
  const cited = a(belief.evidence).map((x) => byId.get(s(x))).filter(Boolean) as Entry[];
  const state = s(belief.state);
  return (
    <div className={cn(!bare && "rounded border border-rule p-3")}>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span className="mono text-note">{s(belief.subject)}</span>
        <span className="text-caption text-faint">
          {s(belief.polarity) === "deny" ? "is not" : "is"}
        </span>
        <span className="mono text-note">{s(belief.proposition)}</span>
        <span
          className={cn(
            "rounded px-1.5 py-0.5 text-caption",
            state === "contradicted"
              ? "bg-amber-600/10 text-amber-700 dark:text-amber-400"
              : "text-faint",
          )}
        >
          {STATE_LABEL[state] ?? state}
        </span>
      </div>
      {s(belief.note) && (
        <p className="mt-1 text-caption text-muted">{s(belief.note)}</p>
      )}
      <div className="mt-2 space-y-1">
        {cited.length === 0 ? (
          <div className="flex items-center gap-1.5 text-caption text-faint">
            <HelpCircle className="h-3.5 w-3.5" aria-hidden />
            Ungrounded, and says so. Nothing in this record supports it.
          </div>
        ) : (
          cited.map((e) => {
            const Icon = EVIDENCE_ICON[s(e.kind)] ?? FileText;
            return (
              <div key={s(e.id)} className="flex items-start gap-1.5">
                <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-faint" aria-hidden />
                <span className="text-caption text-muted">
                  <span className="mono">{s(e.source)}</span>
                  {e.redacted === true && (
                    <span className="text-faint"> (redacted, digest kept)</span>
                  )}
                </span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

export const ViewerIcon = Eye;
