"use client";
import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  api, type HealFailure, type HealthState, type HealComponent,
  type HealRecovery, type HealActionRun, type HealDiagnosis,
} from "@/lib/api";
import { useApp } from "@/components/providers";
import { Card, Skeleton, EmptyState, SectionLabel } from "@/components/ui/primitives";
import { cn } from "@/lib/cn";
import { ShieldPlus, ChevronRight, CircleCheck, CircleX, AlertTriangle, CircleDashed, RefreshCw, Circle } from "lucide-react";

/* Self-healing, made visible.
 *
 * OMEM records failures, runs a repair loop under policy, and verifies the
 * result, and none of it appeared anywhere in the dashboard. It was a feature
 * you had to read the source to know existed.
 *
 * The screen answers, in this order: is anything wrong right now, which part,
 * and what did the server already do about it. A healthy system is the normal
 * case, so the healthy state is deliberately calm rather than a wall of green
 * ticks. Nothing to do here is information, and it should look like it.
 *
 * Two things this screen refuses to do, both of which it did in its first draft:
 *
 *   1. Present a component's self-report as the whole truth. A component's last
 *      reported status and its unresolved failures are separate facts and can
 *      disagree. Showing the green mark alone, on the product that exists to
 *      surface contradictions, was the worst version of this page.
 *   2. Imply OMEM is watching things it is not. Components an agent registers
 *      are labelled as the agent's; the five OMEM reports about itself are
 *      labelled as OMEM's; and when an agent has reported nothing, the page
 *      says so rather than saying "nothing has failed".
 */

// Health maps onto the belief-state palette rather than inventing a second one.
// Same grammar as everywhere else: shape first, colour second.
// Written out in full, never built as `text-${tone}`. Tailwind scans source for
// complete class names, so an interpolated one is never generated and the style
// silently does not exist. It looks fine in the editor and renders unstyled.
// `unknown` deliberately does NOT use text-closed: --closed is 3.58:1 on a panel,
// which fails WCAG for text, and "not reporting" is this page's default headline.
const HEALTH_TEXT: Record<HealthState, string> = {
  healthy: "text-believed", degraded: "text-unknown", failed: "text-conflict",
  recovering: "text-unknown", unknown: "text-muted",
};
const HEALTH_WORD: Record<HealthState, string> = {
  healthy: "healthy", degraded: "degraded", failed: "failed",
  recovering: "recovering", unknown: "not reporting",
};
const HEALTH_LINE: Record<HealthState, string> = {
  // Not "every component is reporting healthy": a component with nothing to say
  // yet (a backup that has never run) does not outvote a verdict, so the healthy
  // headline can sit above a row marked unknown. This wording is true either way.
  healthy: "Nothing is reporting a problem.",
  degraded: "Something is working but not correctly.",
  failed: "A component has failed and could not be recovered.",
  recovering: "A repair is in progress.",
  unknown: "Nothing has reported a state yet.",
};

// The recovery loop, in order.
const LOOP = ["claimed", "diagnosing", "repairing", "verifying", "recovered"] as const;
type Step = (typeof LOOP)[number];
type StepState = "done" | "failed" | "active" | "pending";

// The two states the engine writes when a repair ends badly. Everything else in
// RecoveryState is a stage the recovery passes through while it is still running,
// and an in-flight recovery must never be drawn as a failed one.
const TERMINAL_FAILURE = new Set(["escalated", "failed"]);

/** How far a repair actually got, derived from what it left behind rather than
 *  from its terminal state.
 *
 *  This is the whole reason the first version of this screen lied. It used
 *  `LOOP.indexOf(r.state)`, and the two states the engine writes when a repair
 *  fails ("escalated" and "failed") are not in LOOP, so indexOf returned -1 and
 *  every step rendered as unreached. A repair that claimed the component,
 *  diagnosed it, ran two actions and failed verification displayed as though
 *  nothing had been attempted, on a page whose entire argument is that a fix is
 *  not finished until it has been verified.
 *
 *  Evidence, in order: a recovery row exists only because a claim won, so
 *  `claimed` is always reached. A plan means it was diagnosed. Actions in
 *  `actions_run` mean it was repaired. A verification object means verification
 *  ran. `recovered` is the one step that requires the state to say so.
 *
 *  Nothing after the failure point is ever drawn as done. Verification runs even
 *  when an action already failed, so the literal reading would put a green mark
 *  on `verifying` directly after a red one on `repairing`, which reads as "the
 *  repair failed but verifying it went fine". The rail stops where the repair
 *  stopped mattering. */
function progress(r: HealRecovery): { step: Step; state: StepState }[] {
  const hasPlan = !!(r.plan?.diagnosis || r.plan?.actions?.length);
  const ran = r.actions_run ?? [];
  const verified = !!r.verification && Object.keys(r.verification).length > 0;
  const reached: Record<Step, boolean> = {
    claimed: true,
    diagnosing: hasPlan,
    repairing: ran.length > 0,
    verifying: verified,
    recovered: r.state === "recovered",
  };
  const lastReached = [...LOOP].reverse().find(s => reached[s]) ?? "claimed";

  // Where it stopped. Only for a recovery that has actually ended badly. An
  // action that returned not-ok stops at `repairing`; otherwise a verification
  // that did not pass stops at `verifying`; otherwise it gave up wherever it got.
  let failedAt: Step | null = null;
  if (TERMINAL_FAILURE.has(r.state)) {
    if (ran.some(a => a.ok === false)) failedAt = "repairing";
    else if (verified && r.verification.ok === false) failedAt = "verifying";
    else failedAt = lastReached;
  }

  let past = false;   // set once we are beyond the point the recovery stopped
  return LOOP.map(step => {
    if (step === failedAt) { past = true; return { step, state: "failed" as StepState }; }
    if (past || !reached[step]) return { step, state: "pending" as StepState };
    // Still running: the furthest step reached is in progress, not complete.
    if (!failedAt && r.state !== "recovered" && step === lastReached) {
      return { step, state: "active" as StepState };
    }
    return { step, state: "done" as StepState };
  });
}

/** The model's own stated confidence, as a word.
 *  Never the number: trust is shown as ordering, never numerically, and this
 *  figure is a claim the model made about itself, not a measurement OMEM took. */
function confidenceWord(c: number | undefined): string | null {
  if (typeof c !== "number" || Number.isNaN(c)) return null;
  if (c >= 0.75) return "high";
  if (c >= 0.4) return "moderate";
  return "low";
}

/* Full class names, same reason as HEALTH_TEXT above. `unknown` (dotted outline)
   for the step in progress and `hollow` for one not reached keeps the loop inside
   the existing mark grammar: filled = done, struck = failed, dotted = in flight,
   hollow = not reached. All four survive a greyscale screenshot, which the
   previous version, a `bg-chip` tint measuring 1.15:1 against the panel. Did
   not. The screen-reader line carries the same distinction in words. */
// The loop as glyphs, same grammar as the health marks: a filled check for a
// step completed, a cross for the one it failed at, a dashed ring spinning for
// the step in flight, a hollow ring for one not yet reached. Filled/struck/
// dotted/hollow all survive a greyscale screenshot; colour is the second signal.
const STEP_ICON: Record<StepState, typeof CircleCheck> = {
  done: CircleCheck, failed: CircleX, active: CircleDashed, pending: Circle,
};
const STEP_TONE: Record<StepState, string> = {
  done: "text-believed", failed: "text-conflict", active: "text-unknown", pending: "text-faint",
};
const STEP_TEXT: Record<StepState, string> = {
  done: "text-fg", failed: "font-medium text-conflict",
  active: "text-unknown", pending: "text-muted",
};
const STEP_SR: Record<StepState, string> = {
  done: "completed", failed: "failed here", active: "in progress", pending: "not reached",
};

// Status as a glyph, not a coloured square: a check when healthy, a triangle
// when degraded, a cross when failed, a spinner while recovering, a dashed ring
// when nothing has reported. Shape first, colour second.
const HEALTH_ICON: Record<HealthState, typeof CircleCheck> = {
  healthy: CircleCheck, degraded: AlertTriangle, failed: CircleX,
  recovering: RefreshCw, unknown: CircleDashed,
};
const HM_SIZE = { sm: "h-4 w-4", md: "h-[18px] w-[18px]", lg: "h-5 w-5" };
function HealthMark({ status, size = "sm" }: { status: HealthState; size?: keyof typeof HM_SIZE }) {
  const Icon = HEALTH_ICON[status] ?? CircleDashed;
  return <Icon className={cn(HM_SIZE[size], "shrink-0", HEALTH_TEXT[status],
    status === "recovering" && "animate-spin")}
    role="img" aria-label={HEALTH_WORD[status]} />;
}

// A pass/fail mark for the repair detail: permitted actions, verified checks,
// completed steps. A check when it held, a cross when it did not.
function OkMark({ ok, className }: { ok: boolean; className?: string }) {
  const Icon = ok ? CircleCheck : CircleX;
  return <Icon className={cn("h-4 w-4 shrink-0", ok ? "text-believed" : "text-conflict", className)}
    role="img" aria-label={ok ? "ok" : "failed"} />;
}

function ago(ts: number) {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

/** Relative time is what you read; absolute time is what you correlate with a log
 *  line at 3am. On a product built on assertion-time and as-of replay, showing
 *  only "4m ago" gives up the more useful half for no reason. */
function Ago({ ts }: { ts: number }) {
  const d = new Date(ts * 1000);
  return <time dateTime={d.toISOString()} title={d.toLocaleString()}>{ago(ts)}</time>;
}

export default function Healing() {
  const { project } = useApp();
  const health = useQuery({
    queryKey: ["healing", project],
    queryFn: () => api.healing(project),
    refetchInterval: 10000,
    enabled: !!project,
  });
  const failures = useQuery({
    queryKey: ["healing-failures", project],
    queryFn: () => api.healingFailures(project),
    refetchInterval: 10000,
    enabled: !!project,
  });

  if (health.isPending) {
    return <div className="space-y-5"><Skeleton className="h-32" /><Skeleton className="h-48" /></div>;
  }
  // A query that errored leaves `data` undefined forever. The first version of
  // this page tested `isLoading || !health` and returned a skeleton, so a 403 or
  // an unreachable server pulsed two grey blocks indefinitely, telling the
  // operator "still loading" during exactly the incident this page exists for.
  if (health.isError || !health.data) {
    return (
      <Card className="px-5 py-5">
        <div className="tech-label">Component health</div>
        <p className="mt-1.5 text-sm text-conflict">Health could not be read.</p>
        <p className="mt-1 max-w-lg text-xs text-muted">
          {health.error instanceof Error ? health.error.message : "The request failed."}
          {" "}This is the dashboard failing to reach the server, not a report about
          the server&rsquo;s health.
        </p>
        <button onClick={() => health.refetch()}
          className="mt-3 text-xs font-medium text-accent hover:underline">
          Try again
        </button>
      </Card>
    );
  }

  const { overall, components, reported_count } = health.data;
  const all = failures.data?.data ?? [];
  const open = all.filter(f => !f.resolved);
  const handled = all.filter(f => f.resolved);

  // A component's own status and its unresolved failures are separate facts.
  // Where they disagree, the page shows both rather than picking one.
  const openByComponent = new Map<string, number>();
  for (const f of open) openByComponent.set(f.component, (openByComponent.get(f.component) ?? 0) + 1);

  const omem = components.filter(c => c.origin === "omem");
  const agent = components.filter(c => c.origin === "agent");

  return (
    <div className="space-y-5">
      {/* Focal: one answer to "is anything wrong". */}
      <section className="panel overflow-hidden">
        <div className="flex items-start gap-4 px-5 py-5">
          <span className="mt-0.5"><HealthMark status={overall} size="lg" /></span>
          <div className="min-w-0 flex-1">
            <div className="tech-label">Component health</div>
            <h1 className={cn("display mt-1 text-lg", overall !== "healthy" && HEALTH_TEXT[overall])}>
              {HEALTH_WORD[overall]}
            </h1>
            <p className="mt-1.5 max-w-lg text-xs text-muted">{HEALTH_LINE[overall]}</p>
          </div>
          <ShieldPlus className={cn("h-4 w-4 shrink-0", overall === "healthy" ? "text-faint" : "text-conflict")} />
        </div>

        {omem.length > 0 && (
          <div className="border-t">
            <div className="tech-label px-5 pb-1.5 pt-3">OMEM&rsquo;s own infrastructure</div>
            {omem.map(c => <ComponentRow key={c.component} c={c} openFailures={openByComponent.get(c.component) ?? 0} />)}
          </div>
        )}

        <div className="border-t">
          <div className="tech-label px-5 pb-1.5 pt-3">Components your agents report</div>
          {agent.length > 0
            ? agent.map(c => <ComponentRow key={c.component} c={c} openFailures={openByComponent.get(c.component) ?? 0} />)
            : <NothingReported />}
        </div>
      </section>

      <section>
        <SectionLabel className="mb-2">
          Open failures{open.length > 0 && <span className="mono ml-1.5 text-muted">{open.length}</span>}
        </SectionLabel>
        {open.length === 0 ? (
          <EmptyState
            title="No open failures."
            body={reported_count === 0
              ? "Nothing has reported a failure. Once an agent reports one, it is recorded here with what the server tried, whether the repair verified, and what it escalated if it could not fix it."
              : "Everything reported so far has been resolved."}
          />
        ) : (
          <div className="space-y-2">
            {open.map(f => <Failure key={f.id} f={f} project={project} />)}
          </div>
        )}
      </section>

      {handled.length > 0 && (
        <section>
          <SectionLabel className="mb-2">
            Handled<span className="mono ml-1.5 text-muted">{handled.length}</span>
          </SectionLabel>
          {/* Kept separate from open failures on purpose: these answer different
              questions. This list is the record of what self-healing actually
              fixed, which is the evidence for the feature and was previously
              concatenated into the same list as the things still broken. */}
          <div className="space-y-2">
            {handled.map(f => <Failure key={f.id} f={f} project={project} />)}
          </div>
        </section>
      )}
    </div>
  );
}

function ComponentRow({ c, openFailures }: { c: HealComponent; openFailures: number }) {
  return (
    <div className="flex items-center gap-3 border-b px-5 py-2.5 last:border-b-0">
      <HealthMark status={c.status} />
      <span className="mono shrink-0 text-xs">{c.component}</span>
      {/* The check already says healthy; the word is kept only when the status
          is one worth calling out. */}
      {c.status !== "healthy" && (
        <span className={cn("shrink-0 text-2xs font-medium", HEALTH_TEXT[c.status])}>{HEALTH_WORD[c.status]}</span>
      )}
      {c.reason && <span className="truncate text-2xs text-muted">{c.reason}</span>}
      {/* The disagreement, shown rather than resolved. A component can report
          healthy while carrying unresolved failures. Both readings are honest,
          and which one is right is the operator's call, not this page's. */}
      {openFailures > 0 && c.status === "healthy" && (
        <span className="chip shrink-0 text-conflict">
          {openFailures} unresolved {openFailures === 1 ? "failure" : "failures"}
        </span>
      )}
      <span className="mono ml-auto shrink-0 text-2xs text-muted"><Ago ts={c.ts} /></span>
    </div>
  );
}

function NothingReported() {
  return (
    <div className="px-5 pb-4 pt-1">
      <p className="max-w-xl text-xs text-muted">
        None yet. OMEM records failures and runs repairs for components your agent
        registers. The loop is infrastructure OMEM provides, not something it runs
        on your behalf until you point it at something.
      </p>
      <pre className="mono mt-2.5 overflow-x-auto rounded border bg-raised px-3 py-2 text-2xs text-muted">
{`mem.healing().report_health("vector-index", "healthy")`}
      </pre>
    </div>
  );
}

function Failure({ f, project }: { f: HealFailure; project: string }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  // Recoveries are only fetched when a row is opened, a project with hundreds
  // of failures should not issue hundreds of requests to render a list.
  const { data, isPending, isError, error } = useQuery({
    queryKey: ["healing-failure", project, f.id],
    queryFn: () => api.healingFailure(project, f.id),
    enabled: open,
  });
  // Only the plans that produced no recovery. "recovered" and "failed" diagnoses
  // describe runs that already have a recovery row of their own, and showing them
  // twice would double-count the history.
  const refused = (data?.diagnoses ?? [])
    .filter(d => d.outcome === "denied" || d.outcome === "escalated");

  return (
    <Card>
      <button onClick={() => setOpen(v => !v)}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={`${f.component}, ${f.error_type}, ${f.occurrences} ${f.occurrences === 1 ? "occurrence" : "occurrences"}. Show recovery history.`}
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors duration-150 ease-out hover:bg-raised">
        <OkMark ok={f.resolved} />
        <span className="mono shrink-0 text-xs">{f.component}</span>
        <span className="truncate text-xs text-muted">{f.error_type}: {f.message}</span>
        {f.occurrences > 1 && (
          // Fingerprinting is why this is one row and not f.occurrences rows.
          <span className="chip shrink-0">&times;{f.occurrences}</span>
        )}
        <span className="mono ml-auto shrink-0 text-2xs text-muted"><Ago ts={f.ts} /></span>
        <ChevronRight className={cn("h-3.5 w-3.5 shrink-0 text-faint transition-transform duration-150",
                                    open && "rotate-90")} aria-hidden="true" />
      </button>

      {open && (
        <div id={panelId} className="space-y-4 border-t px-4 py-3">
          {isPending && <Skeleton className="h-12" />}
          {isError && (
            <p className="text-2xs text-conflict">
              Recovery history could not be read
              {error instanceof Error ? `: ${error.message}` : "."}
            </p>
          )}
          {/* Plans OMEM refused before anything ran. These come first: a repair
              that was blocked is a more important thing to have happened than a
              repair that was allowed, and it has no recovery row to appear in. */}
          {refused.map((d, i) => <Refused key={i} d={d} />)}

          {data && data.recoveries.length === 0 && refused.length === 0 && (
            <p className="text-2xs text-muted">No repair was proposed for this failure.</p>
          )}
          {data?.recoveries.map(r => <Recovery key={r.id} r={r} />)}
        </div>
      )}
    </Card>
  );
}

/** A plan that OMEM refused, and why, per action, in the policy's own words.
 *
 *  This is the load-bearing screen for the whole safety argument. The engine will
 *  accept a diagnosis from a model and then decline to run it: an action type
 *  nobody registered cannot execute, risk comes from OMEM's registry rather than
 *  from the plan claiming its own risk, and high-risk needs a named approver. All
 *  of that already worked and none of it was visible, a plan proposing
 *  `exec_shell` was blocked, and the row read "no recovery was attempted",
 *  which describes the outcome as an absence rather than as a decision. */
function Refused({ d }: { d: HealDiagnosis }) {
  const noPlan = d.outcome === "escalated";
  return (
    <div className="space-y-2 border-l-2 border-[color:var(--conflict)] pl-3">
      <div className="flex items-center gap-2">
        <CircleX className="h-4 w-4 shrink-0 text-conflict" role="img" aria-label="refused" />
        <span className="text-2xs font-medium text-conflict">
          {noPlan ? "Escalated: no repair available" : "Refused by policy: nothing was executed"}
        </span>
        <span className="mono ml-auto text-2xs text-muted"><Ago ts={d.ts} /></span>
      </div>

      {d.diagnosis && <p className="claim">{d.diagnosis}</p>}

      {d.decisions.length > 0 && (
        <ul className="space-y-0.5">
          {d.decisions.map((dec, i) => (
            <li key={i} className="flex items-start gap-1.5 text-2xs">
              <OkMark ok={dec.permit} className="mt-0.5" />
              <span className="mono shrink-0">
                {d.actions[dec.index ?? i]?.type ?? `action ${(dec.index ?? i) + 1}`}
              </span>
              {dec.risk && <span className="chip shrink-0">{dec.risk} risk</span>}
              <span className={cn(dec.permit ? "text-muted" : "text-conflict")}>{dec.reason}</span>
            </li>
          ))}
        </ul>
      )}

      <p className="text-2xs text-muted">
        {noPlan
          ? "OMEM had no prior repair for this signature and no plan was proposed, so it escalated rather than improvising one."
          : "The plan was recorded and the actions were not run. Risk class comes from OMEM's action registry, not from the plan, a proposal cannot authorise itself."}
      </p>
    </div>
  );
}

function Recovery({ r }: { r: HealRecovery }) {
  const [raw, setRaw] = useState(false);
  const steps = progress(r);
  const conf = confidenceWord(r.plan?.confidence);
  const exhausted = r.attempts >= r.max_attempts;

  return (
    <div className="space-y-2.5">
      {/* The diagnosis first. It is the reasoning behind everything below it, it
          is the one field on this screen that came from a model rather than from
          OMEM, and the first version of this page fetched it and drew none of
          it. Set in the serif used wherever a claim is quoted as evidence. */}
      {r.plan?.diagnosis && <p className="claim">{r.plan.diagnosis}</p>}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-muted">
        {/* Where the plan came from. "A prior repair that already verified" and
            "something the model just proposed" are the same actions on screen
            and very different things to have authorised. */}
        <span>
          {r.plan_source === "memory" ? "Reused a prior repair that verified"
            : r.plan_source === "llm" ? "Proposed by the model"
            : "Plan source not recorded"}
        </span>
        {conf && <span>&middot; stated confidence {conf}</span>}
        {/* Only high-risk actions require this, so when it is present it is the
            most consequential fact in the block: something ran that OMEM would
            not have run on its own. "named" is deliberate, the caller asserts
            the approver, and the record should not imply more than it verified. */}
        {r.approved_by && (
          <span className="text-unknown">
            &middot; high-risk, approved by <span className="mono">{r.approved_by}</span>
            <span className="text-muted"> (named by the caller)</span>
          </span>
        )}
        <span className={cn("mono", exhausted && "text-conflict")}>
          &middot; attempt {r.attempts} of {r.max_attempts}
          {exhausted && ", strategy exhausted"}
        </span>
      </div>

      {/* How far the repair got. The point of the loop is that a fix is not
          finished until it has been verified, so the step it stopped at is the
          single most important thing in this block. Marks carry the state, not
          colour alone, a struck mark survives a greyscale screenshot. */}
      <ol className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {steps.map(({ step, state }) => {
          const Icon = STEP_ICON[state];
          return (
            <li key={step} className="flex items-center gap-1.5">
              <Icon className={cn("h-3.5 w-3.5 shrink-0", STEP_TONE[state], state === "active" && "animate-spin")}
                aria-hidden="true" />
              <span className={cn("text-2xs", STEP_TEXT[state])}>{step}</span>
              <span className="sr-only">{STEP_SR[state]}</span>
            </li>
          );
        })}
      </ol>

      {r.actions_run?.length > 0 && (
        <div>
          <div className="tech-label mb-1">Actions run</div>
          <ul className="space-y-0.5">
            {r.actions_run.map((a, i) => <ActionLine key={i} a={a} />)}
          </ul>
        </div>
      )}

      {r.verification?.checks && r.verification.checks.length > 0 && (
        <div>
          <div className="tech-label mb-1">Verification</div>
          <ul className="space-y-0.5">
            {r.verification.checks.map((c, i) => (
              <li key={i} className="flex items-start gap-1.5 text-2xs">
                <OkMark ok={c.status === "healthy" || c.status === "recovering"} className="mt-0.5" />
                <span className="mono shrink-0">{c.check}</span>
                <span className="text-muted">{c.status}{c.reason ? `, ${c.reason}` : ""}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* The payload is still one click away for whoever wants it. It just is not
          the interface any more. */}
      <div>
        <button onClick={() => setRaw(v => !v)} aria-expanded={raw}
          className="text-2xs text-muted hover:text-fg">
          {raw ? "Hide" : "Show"} raw record
        </button>
        {raw && (
          <pre className="mono mt-1.5 overflow-x-auto rounded border bg-raised px-3 py-2 text-2xs text-muted">
            {JSON.stringify({ plan: r.plan, actions_run: r.actions_run,
                              verification: r.verification }, null, 2)}
          </pre>
        )}
      </div>
    </div>
  );
}

/** One executed action. Was `JSON.stringify(a)`. The two most-read blocks on an
 *  open row were both unformatted machine output. The shape is small and known. */
function ActionLine({ a }: { a: HealActionRun }) {
  const detail = a.error
    ?? (typeof a.detail === "string" ? a.detail
        : typeof a.detail === "object" && a.detail && typeof a.detail.error === "string"
          ? a.detail.error : null);
  return (
    <li className="flex items-start gap-1.5 text-2xs">
      <OkMark ok={a.ok} className="mt-0.5" />
      <span className="mono shrink-0">{a.type}</span>
      <span className={cn(a.ok ? "text-muted" : "text-conflict")}>
        {a.ok ? "ok" : detail ?? "failed"}
      </span>
    </li>
  );
}
