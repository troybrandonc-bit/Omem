import { MarketingShell } from "@/components/marketing/chrome";
import { Section, CodeBlock, ButtonLink } from "@/components/marketing/ui";

export const metadata = {
  title: "Human-in-the-loop approvals for AI agents",
  description:
    "How to gate an AI agent's risky actions behind human approval: what a defensible approval gate needs, why a yes/no prompt is not enough, and a working self-hosted pattern where unregistered actions cannot execute.",
};

/* Buyer-intent guide: "human in the loop ai agents" / "agent approval workflow"
 * is what a team searches when a client asks "can a human approve before it
 * acts". Direct answers early, question headings, no em dashes. */

export default function Guide() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <article className="prose-omem max-w-3xl">
          <div className="tech-label mb-3">Guide</div>
          <h1 className="display text-3xl">Human-in-the-loop approvals for AI agents</h1>

          <p className="lede">
            &ldquo;Can a human approve before the agent acts?&rdquo; is the
            question that decides whether an agent is allowed into production
            with a client. This guide covers what a defensible approval gate
            actually requires, why a confirm dialog is not one, and a working
            pattern you can run locally.
          </p>

          <h2>What does a real approval gate need?</h2>
          <p>Four properties separate a gate a reviewer will accept from a speed bump:</p>
          <ul>
            <li>
              <strong>A closed set of actions.</strong> Only action types
              registered in code can execute at all. The model can propose
              anything; proposing a name does not bring an action into
              existence.
            </li>
            <li>
              <strong>Risk decided by the system, not the plan.</strong> The
              risk class of an action comes from your registry, never from the
              model&rsquo;s own description of what it wants to do.
            </li>
            <li>
              <strong>A named approver.</strong> High-risk actions wait for a
              specific human, and the approval is recorded under that
              person&rsquo;s name. &ldquo;Someone clicked yes&rdquo; is not
              accountability.
            </li>
            <li>
              <strong>Refusals on the record.</strong> A denied action is
              written down with its reason. The refusal is evidence, and it is
              the half of the story most systems throw away.
            </li>
          </ul>

          <h2>Why is a confirm dialog not enough?</h2>
          <p>
            A yes/no prompt fails all four properties: it approves whatever
            string the model produced (open set), trusts the model&rsquo;s
            framing of risk, records no approver identity, and leaves no trace
            when someone clicks no. It creates the <em>feeling</em> of control
            and none of the record. Under review, the difference is fatal.
          </p>

          <h2>A working pattern: propose, decide, record</h2>
          <CodeBlock label="The model proposes; the system decides" single={`result = mem.healing.handle(
    error={"component": "billing-sync", "error_type": "AuthError"},
    plan={"diagnosis": "credentials rotated upstream",
          "actions": [{"type": "reload_config"},
                      {"type": "exec_shell"}]},
)

result["status"]
# "denied"  - nothing executed

result["decisions"]
# reload_config  permitted      (low risk, registered)
# exec_shell     unknown action type (not registered)
#
# the refusal is recorded with a reason for every action`} />
          <p>
            The model proposed <span className="mono">exec_shell</span>. It was
            not registered, so it could not run, whatever the plan claimed
            about it. The decision, including the refusal, is written to the
            record. That is the shape of a defensible gate: the authority lives
            in code you wrote, and every exercise of it leaves evidence.
          </p>

          <h2>Where do the waiting questions go?</h2>
          <p>
            A gate produces questions a human has to answer: approve this
            high-risk repair, resolve this rule violation, decide whether two
            records are the same person. In OMEM those wait in a judgment
            queue; each decision is recorded under the decider&rsquo;s name,
            and a dismissed question is never asked twice. The queue ships in
            the open-source dashboard.
          </p>

          <h2>How does this connect to the audit trail?</h2>
          <p>
            Approvals are one half of accountability; the other half is proving
            <em> why the agent believed what it believed</em> when it acted.
            Together they answer the two questions every client review asks:
            who allowed it, and on what basis. The belief half has its own
            guide: <a href="/guides/ai-agent-audit-trail">an audit trail for AI
            agents</a>.
          </p>

          <div className="mt-10 flex flex-wrap gap-3">
            <ButtonLink href="/docs/quickstart">Run it locally in a minute</ButtonLink>
            <ButtonLink href="/pilot" variant="secondary">Get it wired into your stack</ButtonLink>
          </div>
        </article>
      </Section>
    </MarketingShell>
  );
}
