import Link from "next/link";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section, CodeBlock, ButtonLink } from "@/components/marketing/ui";

export const metadata = {
  title: "Agent memory in Python, with receipts",
  description:
    "Add memory to an AI agent in Python: beliefs with evidence, contradictions surfaced instead of overwritten, updates that keep history, and why() for every fact. Runs locally with zero dependencies.",
};

export default function Guide() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <article className="prose-omem max-w-3xl">
          <div className="tech-label mb-3">Guide</div>
          <h1 className="display text-3xl">Agent memory in Python, with receipts</h1>

          <p className="lede">
            Most agent memory is a list of facts, and when two of them disagree
            the newer one silently wins. This guide sets up memory that works
            like testimony instead: every belief carries evidence, disagreement
            stays visible, and anything can answer{" "}
            <code className="mono text-fg">why</code>.
          </p>

          <h2>Install</h2>
          <CodeBlock label="One package, one command" single={`pip install omem-infrastructure\nomem-server`} />
          <p className="mt-3 text-note text-muted">
            Zero runtime dependencies (CI fails the build if one appears),
            SQLite by default, works air-gapped. The first run prints your
            project id and API key.
          </p>

          <h2>Remember, and ask why</h2>
          <CodeBlock label="Beliefs, not rows" single={`from omem import Memory

mem = Memory(api_key="omem_sk_...", project="proj_...",
             base_url="http://127.0.0.1:8787")

a = mem.remember("agent:support", "customer:alice", "prefers_annual_billing")

mem.believes("customer:alice", "prefers_annual_billing")
# -> "BELIEVED_TRUE"

mem.why(a["id"])
# -> who said it, when, its evidence, and anything that contradicts it`} />

          <h2>Disagreement stays on the record</h2>
          <CodeBlock label="A contradiction is not a race" single={`mem.remember("agent:sales", "customer:alice", "not:prefers_annual_billing")

mem.conflicts()
# -> both sides, each with its observations, agents and recency.
#    Nothing was overwritten; nothing was decided by timestamp.`} />
          <p>
            Claims named <code className="mono text-fg">X</code> and{" "}
            <code className="mono text-fg">not:X</code> are declared mutually
            exclusive automatically; anything else conflicts only if you declare
            it. The engine never resolves a disagreement on its own, because
            arrival order is not evidence.
          </p>

          <h2>Take things back, completely</h2>
          <CodeBlock label="Retraction cascades" single={`mem.declare_rule(when=[("works_at", "fwd"), ("owns", "rev")],
                 then=("involves", "rev"))
mem.infer()          # concludes from what is believed

mem.retract(assertion_id, agent="agent:support")
# the fact is withdrawn, and every conclusion resting on it
# is withdrawn in the same request, cascade included`} />
          <p>
            History survives all of it. Supersede a fact and the old value keeps
            the interval it was believed; retract one and the record shows what
            was withdrawn and when. The whole state rebuilds from an append-only
            log, and <code className="mono text-fg">omem-verify</code> proves the
            state follows from the log instead of asserting it.
          </p>

          <h2>Where to go next</h2>
          <p>
            The <Link href="/docs/quickstart">quickstart</Link> takes this to a
            running dashboard in about a minute. Using LangGraph? The{" "}
            <Link href="/guides/langgraph-long-term-memory">LangGraph guide</Link>{" "}
            plugs this engine into the standard store interface. Using Claude?
            The <Link href="/guides/mcp-memory-server">MCP guide</Link> is one
            JSON block.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href="/docs/quickstart">Quickstart</ButtonLink>
            <ButtonLink href="https://github.com/troybrandonc-bit/Omem" variant="secondary" external>
              Source on GitHub
            </ButtonLink>
          </div>
        </article>
      </Section>
    </MarketingShell>
  );
}
