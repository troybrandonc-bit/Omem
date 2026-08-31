import { MarketingShell } from "@/components/marketing/chrome";
import { Section, ButtonLink } from "@/components/marketing/ui";

export const metadata = {
  title: "OMEM vs Mem0 vs Zep: an honest comparison of agent memory",
  description:
    "Mem0, Zep, and OMEM solve different problems. Mem0 and Zep are recall layers that manage themselves with an LLM in the write path. OMEM is an accountability layer: no model decides what is true, contradictions stay on the record, and the engine replays byte-identically. Choose by the question you need answered.",
};

/* The comparison page. Rules it was built under (alternatives-pages skill +
 * competitive-positioning.md): be honest enough that a developer who
 * fact-checks it trusts us more afterwards; concede plainly where Mem0 and
 * Zep win; never claim their internals beyond what their public docs say;
 * date the comparison; do not fight the engine-sophistication race. Update
 * triggers: either competitor changes conflict handling or pricing, or a
 * quarter passes. No em dashes. */

const LAST_CHECKED = "September 2026";

const FAQ = [
  {
    q: "Is OMEM an alternative to Mem0?",
    a: "For some uses. Both are open-source memory for AI agents, but they optimize for different questions. Mem0 optimizes recall: it uses an LLM to distill conversations into memories and to decide how a new fact updates the old ones. OMEM optimizes accountability: nothing in the write path is model-decided, contradictions are kept rather than resolved, and every belief can produce the chain of evidence behind it. If you need to prove why an agent believed something, OMEM is the alternative. If you need the best self-managing recall with minimal integration work, Mem0 is a strong choice.",
  },
  {
    q: "What is the difference between OMEM and Zep?",
    a: "Zep builds a temporal knowledge graph from your data: an LLM extracts entities and facts, and when facts conflict, edges are invalidated with validity intervals rather than deleted. That gives real temporal provenance. OMEM differs in the write path: no LLM extracts or invalidates anything. Claims are asserted explicitly, a contradiction exists only when a caller declares one, and the engine that reads the record is frozen and must replay it byte-identically, which is verified in CI on every commit.",
  },
  {
    q: "Can I run OMEM alongside Mem0 or Zep?",
    a: "Yes, and for many teams that is the honest architecture: keep the recall layer you have, and record the beliefs and approvals that matter for accountability in OMEM. They occupy different positions, one behind the model for recall, one in front of the action for the record. There is no importer between them today.",
  },
  {
    q: "Which agent memory should I choose?",
    a: "Choose by the question you need answered. If the question is 'what does the agent remember about this user', choose Mem0 or Zep. If the question is 'why did the agent believe that, who approved the action, and can I prove the record was never rewritten', that is the question OMEM was built for.",
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

const ROWS: [string, string, string, string][] = [
  ["What it optimizes", "Recall quality with minimal integration work", "Temporal knowledge graph over your data", "A defensible record of belief and action"],
  ["On conflicting facts", "An LLM decides how the new fact updates the old", "An LLM invalidates edges, with validity intervals", "Both sides kept; a contradiction must be declared, never inferred"],
  ["LLM in the write path", "Yes, it distills and updates memories", "Yes, it extracts entities and facts", "No. Nothing stored is model-decided"],
  ["History of a belief", "Memory history is available", "Validity intervals on graph edges", "Append-only log; ask what was believed at any past moment"],
  ["Why-provenance", "Similarity and source metadata", "Graph paths with time bounds", "Evidence chain per belief: source, time, basis, what it contradicted"],
  ["Action gating", "Not its job", "Not its job", "Named-approver gate; refusals recorded with reasons"],
  ["Tamper evidence", "Standard database guarantees", "Standard database guarantees", "Frozen engine, byte-identical replay verified in CI on every commit"],
  ["Network posture", "Hosted service, or self-host the OSS core", "Hosted cloud; the Graphiti engine is OSS", "Self-hosted only; a CI test fails the build on any non-loopback connection"],
  ["Erasure", "Delete APIs", "Delete APIs", "Right-to-be-forgotten with replay-verified erasure"],
  ["Adoption and ecosystem", "The widest: default memory in AWS's Agent SDK, many framework integrations", "Established, funded, latency-focused", "Early. Small community, one maintainer, integrations growing"],
  ["License and cost", "OSS core plus paid hosted tiers", "OSS engine plus paid cloud", "MIT, free, self-hosted; the paid offering is hands-on pilot time"],
];

export default function Compare() {
  return (
    <MarketingShell>
      <script type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(JSONLD) }} />
      <Section className="page-y">
        <article className="prose-omem max-w-3xl">
          <div className="tech-label mb-3">Comparison</div>
          <h1 className="display text-3xl">OMEM vs Mem0 vs Zep: which agent memory answers your question?</h1>

          <p className="lede">
            These three tools get compared because they all say &ldquo;memory
            for AI agents,&rdquo; but they are built for different questions.
            This page is the comparison we would want to read: specific,
            dated, and honest about where each one wins, including where we
            lose. Last checked: {LAST_CHECKED}.
          </p>

          <h2>The short version</h2>
          <p>
            <strong>Mem0</strong> is the most widely adopted: you hand it
            conversations, an LLM distills them into memories and decides how
            new facts update old ones, and recall quality with near-zero
            integration work is the product. <strong>Zep</strong> builds a
            temporal knowledge graph: an LLM extracts entities and facts, and
            conflicting facts are invalidated with validity intervals instead
            of deleted, which gives real temporal provenance.{" "}
            <strong>OMEM</strong> is an accountability layer: no model decides
            what is stored or what is true, contradictions stay on the record
            with both sides, a named human approves risky actions, and the
            engine that reads the record must replay it byte-identically,
            verified in CI on every commit.
          </p>
          <p>
            The structural difference underneath every row of the table: Mem0
            and Zep put an LLM in the write path, because their job is to
            manage memory for you. OMEM refuses to, because its job is to be
            evidence. Both designs are correct for their question.
          </p>

          <h2>Side by side</h2>
          <div className="overflow-x-auto">
            <table>
              <thead>
                <tr>
                  <th></th>
                  <th>Mem0</th>
                  <th>Zep</th>
                  <th>OMEM</th>
                </tr>
              </thead>
              <tbody>
                {ROWS.map(r => (
                  <tr key={r[0]}>
                    <td><strong>{r[0]}</strong></td>
                    <td>{r[1]}</td>
                    <td>{r[2]}</td>
                    <td>{r[3]}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-note text-muted">
            Descriptions of Mem0 and Zep come from their public documentation
            as of {LAST_CHECKED}; if something is out of date,{" "}
            <a href="https://github.com/troybrandonc-bit/Omem/issues">open an
            issue</a> and it gets fixed.
          </p>

          <h2>Where Mem0 and Zep genuinely win</h2>
          <p>
            If you want memory that manages itself from raw conversation, both
            beat OMEM today. OMEM makes you assert claims explicitly, subjects
            and proposition, which is more integration work; that explicitness
            is where its guarantees come from, but it is honest to call it a
            cost. Mem0&rsquo;s ecosystem is far larger, and if you want a
            hosted service with an SLA, OMEM does not offer one: it is
            self-hosted by design. Zep&rsquo;s graph gives you entity-level
            queries OMEM does not attempt. If your agent is a chatbot whose
            worst failure is a wrong preference, their trade is the right one.
          </p>

          <h2>Where OMEM wins</h2>
          <p>
            The stakes change when an agent acts on someone&rsquo;s behalf and
            a client, an auditor, or a regulator can ask &ldquo;why did it do
            that?&rdquo; An LLM-curated memory cannot fully answer, because
            the curation itself is an unrecorded judgment: the model that
            decided the new fact should replace the old one left no
            defensible reason behind. OMEM&rsquo;s answer is structural. Every
            belief carries its evidence chain. Contradictions keep both sides.
            Risky actions wait for a named approver, and refusals are recorded
            with reasons. The engine is frozen: it must replay the whole log
            byte-identically, checked in CI on every commit, so not even an
            upgrade can change what was said. And a CI test fails the build if
            the server ever makes a non-loopback connection, so &ldquo;nothing
            leaves your environment&rdquo; is a test result, not a promise.
          </p>
          <p>
            We also benchmark this differently, and publish it:{" "}
            <a href="https://github.com/troybrandonc-bit/Omem/tree/main/benchmarks/witness">Witness</a>{" "}
            measures truthfulness duties, keeping contradictions, refusing
            unsupported claims, surviving retraction, rather than recall
            accuracy. It ships adapters for Mem0 and Graphiti so you can run
            the comparison yourself, with your own keys, rather than trusting
            our numbers.
          </p>

          <h2>Choose honestly</h2>
          <ul>
            <li>
              <strong>Choose Mem0</strong> for the best self-managing recall
              with the least work, the biggest ecosystem, and a hosted option.
            </li>
            <li>
              <strong>Choose Zep</strong> when you want temporal,
              entity-level structure over your data and graph queries against
              it.
            </li>
            <li>
              <strong>Choose OMEM</strong> when someone can ask you to prove
              why the agent believed and did what it did: agents that act for
              clients, security reviews, EU AI Act Article 12 exposure.
            </li>
            <li>
              <strong>Or run two.</strong> A recall layer behind the model and
              OMEM in front of the action is a coherent architecture, not a
              compromise.
            </li>
          </ul>

          <div className="mt-10 flex flex-wrap gap-3">
            <ButtonLink href="/docs/quickstart">Try OMEM in five minutes</ButtonLink>
            <ButtonLink href="/accountability" variant="secondary">
              The accountability side
            </ButtonLink>
          </div>
        </article>
      </Section>
    </MarketingShell>
  );
}
