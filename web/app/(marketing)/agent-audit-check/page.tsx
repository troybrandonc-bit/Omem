"use client";
import { useState } from "react";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section, ButtonLink } from "@/components/marketing/ui";

/* The agent audit-readiness check.
 *
 * The point of this page is to cost a stranger nothing. No install, no signup,
 * no upload: answers are scored in the browser and never leave it, which
 * matters because the people who most need this run regulated systems and will
 * not paste anything about their stack into someone else's server.
 *
 * It grades against the Testimony Record levels rather than against OMEM, so
 * the result is true whatever they built with. Most people will land at TR-1 or
 * below. Say so plainly and without insult: that is the finding, and the gap
 * list is the thing worth having.
 *
 * Deliberately NOT here: a JSON Lines validator. Almost nobody has a record to
 * paste yet, and the Python validator already serves the few who do. One job.
 * No em dashes. */

type Level = "TR-1" | "TR-2" | "TR-3" | "TR-4";

type Q = {
  id: string;
  level: Level;
  question: string;
  options: { label: string; ok: boolean }[];
  gap: string;
};

const QUESTIONS: Q[] = [
  {
    id: "q1", level: "TR-1",
    question: "New information arrives that contradicts something your agent already recorded. What happens to the earlier record?",
    options: [
      { label: "It is updated or overwritten with the newer value", ok: false },
      { label: "The earlier record stays, and the new one is added alongside it", ok: true },
      { label: "I am not certain", ok: false },
    ],
    gap: "Write corrections as new entries instead of editing old ones. Once a record is overwritten, the question of what it believed last March has no answer, and that is the question an audit asks.",
  },
  {
    id: "q2", level: "TR-1",
    question: "Can you reconstruct exactly what your agent believed at a specific moment three months ago?",
    options: [
      { label: "Yes, exactly, as a state rather than as raw logs", ok: true },
      { label: "Roughly, by reading through logs", ok: false },
      { label: "No", ok: false },
    ],
    gap: "Keep beliefs as entries carrying the time they were held, so a past state is reconstructed rather than inferred from log lines after the fact.",
  },
  {
    id: "q3", level: "TR-1",
    question: "Are entries ever edited or deleted after they are written?",
    options: [
      { label: "Never. A correction is a new entry", ok: true },
      { label: "Occasionally, for cleanup or corrections", ok: false },
      { label: "Yes, routinely", ok: false },
    ],
    gap: "Make the store append-only. A trail that can be edited is a document rather than evidence, and reviewers know the difference.",
  },
  {
    id: "q4", level: "TR-2",
    question: "For something your agent currently believes, can you name the specific source it came from?",
    options: [
      { label: "Yes, every belief resolves to the evidence under it", ok: true },
      { label: "Some do, depending which path it came in through", ok: false },
      { label: "No", ok: false },
    ],
    gap: "Attach provenance at write time. Reconstructing where a belief came from afterwards is archaeology, and it is the work nobody can bill for.",
  },
  {
    id: "q5", level: "TR-2",
    question: "Can your system record that something is believed but nothing actually supports it?",
    options: [
      { label: "Yes, an unsupported belief is marked as one", ok: true },
      { label: "No, everything is stored the same way", ok: false },
    ],
    gap: "Make ungroundedness sayable. A system that cannot say nothing supports this will eventually invent support, because it has nowhere else to put the claim.",
  },
  {
    id: "q6", level: "TR-2",
    question: "Two sources disagree about the same fact. What does the record show afterwards?",
    options: [
      { label: "Both sides, marked as in conflict", ok: true },
      { label: "Whichever one won", ok: false },
      { label: "Whichever arrived most recently", ok: false },
    ],
    gap: "Retain both sides and mark the conflict. Silently resolving a disagreement destroys the evidence that there ever was one, which is the specific failure this format exists to prevent.",
  },
  {
    id: "q7", level: "TR-3",
    question: "Your agent proposes a consequential action. Where does the risk level of that action come from?",
    options: [
      { label: "A registry or allowlist you control, outside the model", ok: true },
      { label: "The model's own plan or output", ok: false },
      { label: "Nothing classifies risk", ok: false },
    ],
    gap: "Take the risk class from a registry the model cannot write to. A plan that declares its own risk is not gated, it is asking politely.",
  },
  {
    id: "q8", level: "TR-3",
    question: "Are actions that were blocked or refused recorded as durably as the ones that ran?",
    options: [
      { label: "Yes, with the reason they were refused", ok: true },
      { label: "Only in application logs, if at all", ok: false },
      { label: "No", ok: false },
    ],
    gap: "Record refusals as first-class entries. We stopped it is the most valuable sentence you can say in a review, and it is worth nothing without the record.",
  },
  {
    id: "q9", level: "TR-3",
    question: "A human approves a risky action. Where does that person's identity come from?",
    options: [
      { label: "The authentication layer: a session or a credential that was checked", ok: true },
      { label: "A name supplied in the request", ok: false },
      { label: "There is no human approval step", ok: false },
    ],
    gap: "Take the approver identity from authentication, never from the payload. A name in a request body is written by whoever sent the request.",
  },
  {
    id: "q10", level: "TR-3",
    question: "Could the agent's own credential approve the agent's own action?",
    options: [
      { label: "No. Approval requires a principal that is not the agent", ok: true },
      { label: "Yes, if it holds the right permission", ok: false },
      { label: "I am not certain", ok: false },
    ],
    gap: "Refuse approvals arriving on the acting agent's own credential. This one is easy to get wrong and hard to see: the record looks correct, names a person, and proves nothing.",
  },
  {
    id: "q11", level: "TR-4",
    question: "Can you show a third party that the record has not been altered since it was written?",
    options: [
      { label: "Yes: deterministic replay, a hash chain, signatures or an external anchor", ok: true },
      { label: "No", ok: false },
    ],
    gap: "Publish an integrity scheme. Until an outside party can check the record independently, its trustworthiness rests on your word, which is what an audit exists to replace.",
  },
];

const LEVELS: Level[] = ["TR-1", "TR-2", "TR-3", "TR-4"];

const MEANING: Record<Level, string> = {
  "TR-1": "Recorded. The record exists and is append-only.",
  "TR-2": "Explained. Beliefs resolve to their evidence, and disagreements survive.",
  "TR-3": "Gated. Actions carry a verdict, and approvals carry a name.",
  "TR-4": "Verifiable. The record can be shown not to have changed.",
};

export default function AuditCheck() {
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [done, setDone] = useState(false);

  const answered = QUESTIONS.filter((q) => answers[q.id] !== undefined).length;
  const failed = QUESTIONS.filter((q) => !q.options[answers[q.id]]?.ok);

  // Levels are cumulative, so the level reached is the last one whose
  // requirements are all met, and the first unmet requirement is the wall.
  let reached: Level | null = null;
  for (const lvl of LEVELS) {
    const unmet = QUESTIONS.some((q) => q.level === lvl && !q.options[answers[q.id]]?.ok);
    if (unmet) break;
    reached = lvl;
  }
  const next: Level | null =
    reached === null ? "TR-1" : LEVELS[LEVELS.indexOf(reached) + 1] ?? null;
  const blocking = failed.filter((q) => q.level === next);
  const later = failed.filter((q) => q.level !== next);

  return (
    <MarketingShell>
      <Section className="page-y">
        <article className="prose-omem max-w-3xl">
          <div className="tech-label mb-3">Free check</div>
          <h1 className="display text-3xl">
            Would your agent&rsquo;s record survive an audit?
          </h1>

          <p className="lede">
            Eleven questions about what your agent actually records, scored
            against the four <a href="/spec/testimony-record">Testimony Record</a>{" "}
            conformance levels. It grades the format rather than any particular
            software, so the answer holds whatever you built with.
          </p>
          <p className="text-note text-muted">
            Everything is scored in your browser. Nothing is uploaded, nothing
            is stored, and there is no signup, because the people who most need
            this run systems they are not allowed to describe to strangers.
          </p>

          {!done && (
            <>
              <ol className="mt-10 space-y-8 list-none pl-0">
                {QUESTIONS.map((q, i) => (
                  <li key={q.id} className="border-t pt-6">
                    <div className="tech-label mb-2">
                      {i + 1} of {QUESTIONS.length} &middot; {q.level}
                    </div>
                    <p className="font-medium">{q.question}</p>
                    <div className="mt-3 space-y-2">
                      {q.options.map((o, oi) => (
                        <label key={oi} className="flex gap-3 items-start cursor-pointer">
                          <input
                            type="radio"
                            name={q.id}
                            className="mt-1"
                            checked={answers[q.id] === oi}
                            onChange={() => setAnswers({ ...answers, [q.id]: oi })}
                          />
                          <span>{o.label}</span>
                        </label>
                      ))}
                    </div>
                  </li>
                ))}
              </ol>

              <div className="mt-10 flex flex-wrap items-center gap-4 border-t pt-6">
                <button
                  type="button"
                  disabled={answered < QUESTIONS.length}
                  onClick={() => setDone(true)}
                  className={
                    "inline-flex h-control-lg items-center justify-center gap-2 rounded-md px-5 " +
                    "text-note font-medium transition-[background-color,color] duration-1 ease-out " +
                    "on-accent bg-accent text-accentFg hover:bg-accentHover " +
                    "disabled:opacity-40 disabled:pointer-events-none"
                  }
                >
                  {answered < QUESTIONS.length
                    ? `${QUESTIONS.length - answered} still to answer`
                    : "Show my level"}
                </button>
                <span className="text-note text-muted">
                  Answering honestly is the only thing that makes this worth anything.
                </span>
              </div>
            </>
          )}

          {done && (
            <div id="result" className="mt-10 border-t pt-8">
              {reached ? (
                <>
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`/badge/testimony-record-${reached.toLowerCase().replace("-", "")}.svg`}
                    alt={`testimony record ${reached}`}
                    width={173}
                    height={20}
                  />
                  <h2 className="mt-4">You are at {reached}</h2>
                  <p>{MEANING[reached]}</p>
                </>
              ) : (
                <>
                  <h2>You are below TR-1</h2>
                  <p>
                    The record is not yet append-only, so what the agent
                    believed at a past moment cannot be reconstructed. This is
                    where most systems shipping today sit, usually without
                    anyone having checked.
                  </p>
                </>
              )}

              {next && blocking.length > 0 && (
                <>
                  <h3 className="mt-8">What stands between you and {next}</h3>
                  <ul>
                    {blocking.map((q) => (
                      <li key={q.id}>{q.gap}</li>
                    ))}
                  </ul>
                </>
              )}

              {later.length > 0 && (
                <>
                  <h3 className="mt-8">Further out</h3>
                  <p className="text-note text-muted">
                    These sit above {next}, so they are not the next thing to
                    fix, but they are on the road.
                  </p>
                  <ul>
                    {later.map((q) => (
                      <li key={q.id}>
                        <span className="mono">{q.level}</span> &middot; {q.gap}
                      </li>
                    ))}
                  </ul>
                </>
              )}

              {failed.length === 0 && (
                <p>
                  Nothing is missing, which is rare enough to be worth checking
                  against a real record rather than against eleven answers. Run
                  the validator over what your system emits, and if it holds up,
                  send it and it gets listed.
                </p>
              )}

              <div className="mt-10 flex flex-wrap gap-3">
                <ButtonLink href="/spec/testimony-record">Read the specification</ButtonLink>
                <ButtonLink href="/spec/testimony-record/implementations" variant="secondary">
                  Get listed
                </ButtonLink>
              </div>

              <p className="text-note text-muted mt-8">
                Closing these gaps does not require anyone&rsquo;s product. The
                format is free to implement and the validator is one file with
                no dependencies. OMEM is the reference implementation if you
                would rather not build it yourself, and{" "}
                <a href="/pilot">a pilot</a> is usually how that starts.
              </p>
            </div>
          )}
        </article>
      </Section>
    </MarketingShell>
  );
}
