import { MarketingShell } from "@/components/marketing/chrome";
import { Section, CodeBlock, ButtonLink } from "@/components/marketing/ui";

export const metadata = {
  title: "EU AI Act Article 12 for AI agents: what to log, with working code",
  description:
    "Article 12 requires high-risk AI systems to automatically record events over their lifetime, verifiable after the fact and kept at least six months. What that means for AI agents in practice, why ordinary logs fail the reading, and a working self-hosted implementation.",
};

/* The flagship regulatory guide. The Article 12 query space is owned by
 * process-compliance vendors selling frameworks; nobody answers it from the
 * builder side with running code. This page does, honestly: what the article
 * says, what it implies for agents, and how OMEM maps to each requirement.
 * FAQPage JSON-LD included for AI-answer extraction. Not legal advice, and it
 * says so. No em dashes. */

const FAQ = [
  {
    q: "Does the EU AI Act require logging for AI agents?",
    a: "For high-risk AI systems, yes. Article 12 requires the system to technically allow automatic recording of events over its lifetime, and the logs must make it possible to identify risky situations, support post-market monitoring, and monitor operation. Providers and deployers must keep the logs, at least six months under Articles 19 and 26, longer if other law such as GDPR applies.",
  },
  {
    q: "Are ordinary application logs enough for Article 12?",
    a: "Usually not for agents. A log line records that an action happened, but an agent's consequential event is why it believed the action was right. If the memory behind the agent overwrites facts on conflict, the state that explains a past decision is gone, and the record cannot support the after-the-fact verification the article expects.",
  },
  {
    q: "How long must AI agent logs be kept under the EU AI Act?",
    a: "At least six months, per Article 19 for providers and Article 26 for deployers, and longer where other applicable law requires it. GDPR can also require deletion of personal data, so the record needs to support both retention and lawful erasure at once.",
  },
  {
    q: "What should an AI agent audit log contain?",
    a: "Four things, at minimum: what the agent believed at the moment it acted and where each belief came from; what conflicted and which side was believed; who authorised any risky action, by name; and enough integrity protection that the record can be shown not to have been quietly rewritten afterwards.",
  },
];

const JSONLD = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: FAQ.map(f => ({
    "@type": "Question",
    name: f.q,
    acceptedAnswer: { "@type": "Answer", text: f.a },
  })),
};

export default function Guide() {
  return (
    <MarketingShell>
      <script type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(JSONLD) }} />
      <Section className="page-y">
        <article className="prose-omem max-w-3xl">
          <div className="tech-label mb-3">Guide</div>
          <h1 className="display text-3xl">EU AI Act Article 12 for AI agents: what to log, with working code</h1>

          <p className="lede">
            Since August 2026, the EU AI Act&rsquo;s high-risk obligations are
            enforceable, and Article 12 is the one that lands on engineering:
            the system must automatically record events over its lifetime, the
            record has to hold up to after-the-fact verification, and it must be
            kept for at least six months. This guide covers what that means for
            AI agents specifically, why ordinary logs fail the reading, and a
            working, self-hosted implementation. It is written by a builder,
            not a lawyer, and it is not legal advice.
          </p>

          <h2>What does Article 12 actually require?</h2>
          <p>
            Read plainly, Article 12 requires high-risk AI systems to
            technically allow the automatic recording of events (logs) over the
            system&rsquo;s lifetime, and those logs must make three things
            possible: identifying situations where the system may present a
            risk, supporting post-market monitoring, and monitoring the
            system&rsquo;s operation. The companion duties in Articles 19 and
            26 make providers and deployers keep those logs for at least six
            months, longer where other law applies.
          </p>
          <p>
            Two words in that reading carry most of the weight for agents:
            <em> events</em>, and <em>verification</em>. An agent&rsquo;s
            consequential event is not &ldquo;an HTTP request happened&rdquo;.
            It is &ldquo;the agent decided to do something, on the basis of
            what it believed&rdquo;. And a record you cannot verify after the
            fact, because the system could have rewritten it, is a diary, not
            evidence.
          </p>

          <h2>Why do ordinary logs fail for agents?</h2>
          <ul>
            <li>
              <strong>They record actions, not reasons.</strong> The regulator
              question, and the client security review question, is why the
              agent acted. If the memory that produced the intent overwrote its
              own history when facts changed, the reason is unrecoverable.
            </li>
            <li>
              <strong>They lose the conflict.</strong> When two sources
              disagreed and the system silently picked a winner, the log shows
              the winner acting and nothing else. The risky situation Article
              12 wants identifiable is exactly that disagreement, and it is
              gone.
            </li>
            <li>
              <strong>They are editable.</strong> A mutable store fails the
              verification reading. The record needs to be append-only, and
              ideally provably so.
            </li>
            <li>
              <strong>They collide with GDPR instead of coexisting.</strong>{" "}
              Article 12 wants retention; GDPR wants erasure on request. A
              record that cannot execute a real deletion without destroying its
              own verifiability fails one law to satisfy the other.
            </li>
          </ul>

          <h2>The four properties a compliant agent record needs</h2>
          <p>
            Strip the legal text to engineering requirements and you get four
            properties. Each maps to a concrete mechanism below.
          </p>
          <ul>
            <li><strong>Reconstructable belief:</strong> what did the agent believe at the moment it acted, with provenance per belief.</li>
            <li><strong>Preserved conflict:</strong> when sources disagreed, both sides on record, with which one was believed.</li>
            <li><strong>Named authority:</strong> who approved a risky action, recorded with the decision, refusals included.</li>
            <li><strong>Tamper evidence:</strong> proof the record was not quietly rewritten afterwards.</li>
          </ul>

          <h2>A working implementation</h2>
          <p>
            The following runs on your own infrastructure with{" "}
            <span className="mono">pip install omem-infrastructure</span>. OMEM
            is an open-source (MIT) memory and accountability layer for agents;
            each block below is the mechanism for one property.
          </p>

          <CodeBlock label="Reconstructable belief, with provenance" single={`from omem import Memory
mem = Memory(api_key="omem_sk_...", project="proj_...",
             base_url="http://127.0.0.1:8787")

a = mem.remember("agent:claims-bot", "case:1042",
                 "eligible_for_fast_track")

mem.why(a["id"])
# -> who asserted it, when, the evidence chain, and anything
#    on record that contradicts it. This is the exportable
#    answer to "why did it act".

# the agent acted last Tuesday; reconstruct last Tuesday
mem.recall(about="case:1042", as_of="2026-08-25T14:00:00Z")`} />

          <CodeBlock label="Preserved conflict" single={`mem.remember("agent:intake", "case:1042",
             "not:eligible_for_fast_track")

mem.conflicts()
# -> both claims, each with source and recency. Nothing was
#    overwritten. The "risky situation" Article 12 wants
#    identifiable is exactly this, and it stays identifiable.`} />

          <CodeBlock label="Named authority over risky actions" single={`result = mem.healing.handle(
    error={"component": "payout", "error_type": "AuthError"},
    plan={"actions": [{"type": "reload_config"},
                      {"type": "exec_shell"}]})

result["status"]     # "denied" - nothing executed
result["decisions"]  # per action: permitted / refused, with reason
# High-risk actions wait for a NAMED approver; the approval and
# every refusal are recorded alongside the beliefs behind them.`} />

          <p>
            <strong>Tamper evidence</strong> is structural rather than an API
            call: the record is an append-only operations log, and the engine
            that interprets it is frozen. It must replay the log to a
            byte-identical state, and that replay is verified continuously (a
            CI test also tampers with one operation and requires the check to
            fail, so the proof is proven able to fail). An upgrade cannot
            rewrite recorded history.
          </p>
          <p>
            <strong>And the GDPR coexistence:</strong> erasure is a real,
            first-class operation, not a soft delete. One request rewrites the
            person&rsquo;s data out of the record, replay-verified before
            anything is touched; what remains is a hash, counts, and a date. So
            the record satisfies retention and lawful deletion at the same
            time.
          </p>

          <h2>Frequently asked questions</h2>
          {FAQ.map(f => (
            <div key={f.q}>
              <h3>{f.q}</h3>
              <p>{f.a}</p>
            </div>
          ))}

          <h2>The honest caveats</h2>
          <p>
            Whether your agent is a high-risk system under the Act is a legal
            classification that depends on what it does; ask a lawyer, not a
            README. And no tool makes a system compliant by itself: Article 12
            sits inside a wider set of obligations (risk management, human
            oversight, documentation). What a builder controls is whether the
            technical record can support those obligations at all. That is the
            part this page, and OMEM, is about.
          </p>

          <div className="mt-10 flex flex-wrap gap-3">
            <ButtonLink href="/docs/quickstart">Run it locally in a minute</ButtonLink>
            <ButtonLink href="/accountability" variant="secondary">The accountability overview</ButtonLink>
            <ButtonLink href="/pilot" variant="quiet">Get it wired into your stack</ButtonLink>
          </div>
        </article>
      </Section>
    </MarketingShell>
  );
}
