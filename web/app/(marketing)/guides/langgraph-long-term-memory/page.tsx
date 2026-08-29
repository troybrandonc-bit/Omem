import Link from "next/link";
import { MarketingShell } from "@/components/marketing/chrome";
import { Section, CodeBlock, ButtonLink } from "@/components/marketing/ui";

export const metadata = {
  title: "Long-term memory for a LangGraph agent",
  description:
    "Give a LangGraph agent long-term memory through the standard BaseStore interface, with history that survives updates and a why() for every memory. Complete working setup in a few minutes.",
};

export default function Guide() {
  return (
    <MarketingShell>
      <Section className="page-y">
        <article className="prose-omem max-w-3xl">
          <div className="tech-label mb-3">Guide</div>
          <h1 className="display text-3xl">Long-term memory for a LangGraph agent</h1>

          <p className="lede">
            LangGraph gives your agent a store for memory that survives across
            threads. The built-in ones are key-value stores: <code className="mono text-fg">put</code>{" "}
            overwrites, <code className="mono text-fg">delete</code> erases. Correct
            for a cache, wrong for memory, because the question you will
            actually ask later is &ldquo;what did the agent believe last week,
            and what changed it&rdquo;. This guide wires the same interface to a
            backend that keeps the history.
          </p>

          <h2>Setup</h2>
          <p>Two installs and one command:</p>
          <CodeBlock label="Install and start the server" single={`pip install "omem-infrastructure[langgraph]"\nomem-server`} />
          <p className="mt-3 text-note text-muted">
            <code className="mono text-fg">omem-server</code> prints a project id
            and API key on first run and serves a dashboard on the same port.
            SQLite underneath, no other dependencies, runs offline.
          </p>

          <h2>The store</h2>
          <CodeBlock label="An OmemStore is a BaseStore" single={`from omem import Memory
from omem.integrations.langgraph_store import OmemStore

store = OmemStore(Memory(
    api_key="omem_sk_...",       # printed on first run
    project="proj_...",
    base_url="http://127.0.0.1:8787",
))

store.put(("memories", "alice"), "billing", {"text": "prefers annual billing"})
store.get(("memories", "alice"), "billing").value
# -> {"text": "prefers annual billing"}`} />
          <p>
            Hand it to <code className="mono text-fg">create_react_agent(..., store=store)</code>{" "}
            or any LangGraph graph, exactly as you would hand it an{" "}
            <code className="mono text-fg">InMemoryStore</code>. Cross-thread
            memory works as before.
          </p>

          <h2>What the second write does</h2>
          <CodeBlock label="Update the same key" single={`store.put(("memories", "alice"), "billing", {"text": "switched to monthly"})`} />
          <p>
            In a key-value store the annual preference now no longer exists,
            anywhere. Here it is <strong>superseded</strong>: the old value stays
            on the record with the moment it stopped being believed, and the
            dashboard shows both, with the interval each was held and which
            write ended it. <code className="mono text-fg">delete</code> works the
            same way: the key stops resolving, the history of what it held
            survives. Every write is attributed, so{" "}
            <code className="mono text-fg">mem.why(assertion_id)</code> answers
            where a memory came from.
          </p>

          <h2>Honest limitations</h2>
          <p>
            Vector search over the store interface is not implemented yet;{" "}
            <code className="mono text-fg">search(query=...)</code> raises rather
            than quietly returning unranked results. Every operation is a
            network round trip to a real server, where InMemoryStore is a dict.
            Use this where the audit trail is worth more than the microseconds.
          </p>

          <h2>Where to go next</h2>
          <p>
            The engine underneath does more than the store interface exposes:
            contradiction tracking, declared inference rules whose conclusions
            are withdrawn when premises die, and a benchmark for whether memory
            systems assert things nobody told them. Start with the{" "}
            <Link href="/docs/quickstart">quickstart</Link>, or read the{" "}
            <Link href="/guides/agent-memory-python">Python guide</Link> for the
            full belief-tracking surface.
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
