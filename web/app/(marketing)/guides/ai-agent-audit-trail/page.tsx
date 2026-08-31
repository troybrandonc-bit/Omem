import { MarketingShell } from "@/components/marketing/chrome";
import { Section, CodeBlock, ButtonLink } from "@/components/marketing/ui";

export const metadata = {
  title: "An audit trail for AI agents",
  description:
    "How to give an AI agent a real audit trail: what it must contain, why request logs are not enough, and how to record what the agent believed, why, and who approved its actions. Self-hosted, with working code.",
};

/* Buyer-intent guide: "ai agent audit trail" is the query a team types after a
 * client's security review asks how they prove why the agent did something.
 * Question-led headings and direct answers up front, for AI-answer extraction
 * as much as for the reader. No em dashes. */

export default function Guide() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <article className="prose-omem max-w-3xl">
          <div className="tech-label mb-3">Guide</div>
          <h1 className="display text-3xl">An audit trail for AI agents</h1>

          <p className="lede">
            The moment an agent acts for a client, someone will ask the question
            every team dreads: <em>why did it do that?</em> This guide covers
            what an agent audit trail actually has to contain, why a request log
            does not qualify, and how to record one you can hand to a
            compliance reviewer, with working code you can run locally.
          </p>

          <h2>What must an AI agent audit trail contain?</h2>
          <p>
            A defensible audit trail answers four questions about any action the
            agent took, after the fact and under scrutiny:
          </p>
          <ul>
            <li><strong>What did the agent believe</strong> at the moment it acted, not what the database says now.</li>
            <li><strong>Where did each belief come from:</strong> the source, the time, and the evidence chain behind it.</li>
            <li><strong>What disagreed:</strong> if two sources conflicted, both sides, and which one was believed and why.</li>
            <li><strong>Who authorised the action:</strong> a named approver for anything risky, recorded with the decision.</li>
          </ul>
          <p>
            If any of the four is missing, the trail collapses under the first
            real question. Most teams discover this during a client&rsquo;s
            security review, which is the most expensive possible time.
          </p>

          <h2>Why is a request log not an audit trail?</h2>
          <p>
            Logs record what the system <em>did</em>. An audit trail for an
            agent must also record what the system <em>believed</em>, because
            the belief is the reason for the action. Three failures make
            ordinary logging insufficient:
          </p>
          <ul>
            <li>
              <strong>Overwritten state.</strong> Most memory stores keep only
              the current value. When a fact changes, the old value, the one the
              agent actually acted on, is gone. You cannot reconstruct the
              decision.
            </li>
            <li>
              <strong>Silent conflict resolution.</strong> When two facts
              disagree, last-write-wins picks a winner and leaves no trace that
              there was ever a disagreement.
            </li>
            <li>
              <strong>Mutable history.</strong> A trail the system can rewrite
              later is not evidence. Reviewers know this, which is why financial
              systems use append-only ledgers.
            </li>
          </ul>

          <h2>Record beliefs, not just events</h2>
          <CodeBlock label="Every belief carries its receipts" single={`pip install omem-infrastructure
omem-server

# every belief is recorded with source, time, and evidence
from omem import Memory
mem = Memory(api_key="omem_sk_...", project="proj_...",
             base_url="http://127.0.0.1:8787")

a = mem.remember("agent:support", "customer:alice",
                 "prefers_annual_billing")

mem.why(a["id"])
# -> who asserted it, when, its evidence chain,
#    and anything on record that contradicts it`} />
          <p>
            <span className="mono">why()</span> is the core of the trail: for
            any belief, the full chain of assertions and evidence that led
            there. When a client asks why the agent believed something, this is
            the artifact you export and send.
          </p>

          <h2>Keep the disagreement, not just the winner</h2>
          <CodeBlock label="Both sides stay on the record" single={`mem.remember("agent:sales", "customer:alice",
             "not:prefers_annual_billing")

mem.conflicts()
# -> both claims, each with its agent, source, and recency.
#    Nothing was overwritten; the disagreement is part of
#    the record, which is exactly what an auditor wants.`} />

          <h2>Ask what was believed at the time, not what is believed now</h2>
          <CodeBlock label="Time travel is the audit primitive" single={`# the agent acted on Tuesday; reconstruct Tuesday
mem.recall(about="customer:alice", as_of="2026-08-25T14:00:00Z")
# -> the beliefs as they stood then, not as they stand today`} />
          <p>
            This is the capability request logs cannot fake. If the memory
            overwrote the past, the honest answer to &ldquo;what did it know
            when it acted&rdquo; is &ldquo;we no longer know&rdquo;.
          </p>

          <h2>Record who approved the risky actions</h2>
          <p>
            Belief provenance covers <em>why it thought that</em>. The other
            half is <em>who let it act</em>: risky actions should wait for a
            named approver, and both the approval and any refusal should land
            in the same record. That pattern has its own guide:{" "}
            <a href="/guides/human-in-the-loop-ai-agents">human-in-the-loop
            approvals for AI agents</a>.
          </p>

          <h2>Can the trail itself be trusted?</h2>
          <p>
            A trail is only as good as its resistance to revision. In OMEM the
            record is an append-only operations log, and the engine that
            interprets it is frozen: it replays byte-identically, verified on
            every commit, so a software upgrade can never rewrite what was
            believed. Retraction exists, but as a new recorded operation that
            withdraws a belief and cascades to its conclusions, never as an
            edit to history.
          </p>

          <div className="mt-10 flex flex-wrap gap-3">
            <ButtonLink href="/docs/quickstart">Run it locally in a minute</ButtonLink>
            <ButtonLink href="/accountability" variant="secondary">The accountability overview</ButtonLink>
          </div>
        </article>
      </Section>
    </MarketingShell>
  );
}
