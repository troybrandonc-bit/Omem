import { CodeBlock, ButtonLink, SpecList } from "@/components/marketing/ui";
import { ArrowRight } from "lucide-react";

export const metadata = {
  title: "Documentation",
  description: "OMEM is a memory layer for AI agents that answers for itself. Start here.",
};

/* `.prose-omem` was referenced by this page and had never been defined in
 * globals.css, so every paragraph, heading and list here rendered at browser
 * defaults — Times-ish leading, no measure, no rhythm — inside a design system
 * that had opinions about all three. It is a real class now. */

const WHAT = [
  { k: "Provenance", d: "Every belief traces to the events and derivations that produced it." },
  { k: "Time", d: "Query what your agent knew at any point in time, deterministically." },
  { k: "Contradiction", d: "Conflicting claims resolve to a state, never a silent overwrite." },
  { k: "History", d: "Append-only. Revisions and retractions are recorded and auditable." },
];

export default function DocsIntro() {
  return (
    <article className="prose-omem">
      <div className="tech-label mb-3">Documentation</div>
      <h1 className="display text-3xl">Memory that answers for itself</h1>

      <p className="lede">
        OMEM is a memory layer for AI agents. You store beliefs; OMEM tracks who
        claimed what, when, on what basis, and whether anything contradicts it, so
        you can always answer <em>why</em> your agent believes something.
      </p>

      <p>
        You don&rsquo;t need to learn the underlying memory model to be
        productive. The SDK speaks in <code className="mono text-fg">remember</code>,{" "}
        <code className="mono text-fg">believes</code>,{" "}
        <code className="mono text-fg">why</code>, and{" "}
        <code className="mono text-fg">history</code>. The machinery of provenance
        graphs, belief intervals and contradiction states runs underneath.
      </p>

      <h2>Install</h2>
      {/* The package is `omem-infrastructure`. This block said `pip install
          omem`, which is a different project on PyPI, and `npm i @omem/sdk`,
          which has never been published. Both were the first command a new
          reader ran. */}
      <CodeBlock label="Install the SDK" tabs={[
        { label: "Python", code: "pip install omem-infrastructure" },
      ]} />
      <p className="mt-3 text-note text-muted">
        There is also a TypeScript SDK,{" "}
        <code className="mono text-fg">npm install @omem/sdk</code>, and a
        LangGraph store adapter for LangChain agents,{" "}
        <code className="mono text-fg">pip install &quot;omem-infrastructure[langgraph]&quot;</code>.
        The TypeScript SDK does not yet cover the whole Python surface; the gap
        is tracked in <code className="mono text-fg">CONTRIBUTING.md</code>.
      </p>

      <h2>What you get</h2>
      <SpecList items={WHAT} tone="fg" />

      <div className="mt-12 flex flex-wrap items-center gap-3">
        <ButtonLink href="/docs/quickstart">
          Quickstart <ArrowRight className="h-4 w-4" aria-hidden="true" />
        </ButtonLink>
        <ButtonLink href="/docs/sdk" variant="secondary">SDK overview</ButtonLink>
      </div>
    </article>
  );
}
