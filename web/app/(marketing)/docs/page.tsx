import Link from "next/link";
import { CodeBlock } from "@/components/marketing/ui";
import { ArrowRight } from "lucide-react";

export const metadata = { title: "Docs / OMEM" };

export default function DocsIntro() {
  return (
    <article className="prose-omem max-w-2xl">
      <div className="tech-label mb-4">Documentation</div>
      <h1 className="display text-[36px]">Memory that answers for itself</h1>
      <p className="mt-4 text-pretty leading-relaxed text-muted">
        OMEM is a memory layer for AI agents that answers for itself. You store beliefs; OMEM tracks who claimed what, when, on what
        basis, and whether anything contradicts it, so you can always answer <em>why</em> your
        agent believes something.
      </p>
      <p className="mt-4 leading-relaxed text-muted">
        You don&apos;t need to learn the underlying memory model to be productive. The SDK speaks
        in <span className="mono text-fg">remember</span>, <span className="mono text-fg">believes</span>,
        {" "}<span className="mono text-fg">why</span>, and <span className="mono text-fg">history</span>.
        The rigorous machinery of provenance graphs, belief intervals, and contradiction states runs underneath.
      </p>

      <h2 className="mt-10 text-lg font-semibold">Install</h2>
      <div className="mt-3">
        <CodeBlock tabs={[
          { label: "Python", code: "pip install omem" },
          { label: "TypeScript", code: "npm i @omem/sdk" },
        ]} />
      </div>

      <h2 className="mt-12 text-[15px] font-medium">What you get</h2>
      <div className="mt-5 border-t">
        {[
          ["PROVENANCE", "Every belief traces to the events and derivations that produced it."],
          ["TIME", "Query what your agent knew at any point in time, deterministically."],
          ["CONTRADICTION", "Conflicting claims resolve to a state, never a silent overwrite."],
          ["HISTORY", "Append-only. Revisions and retractions are recorded and auditable."],
        ].map(([k, d]) => (
          <div key={k} className="spec-row border-b py-4">
            <div className="text-xs font-medium text-accent">{k}</div>
            <p className="text-[14px] leading-relaxed text-muted">{d}</p>
          </div>
        ))}
      </div>

      <div className="mt-10 flex items-center gap-4">
        <Link href="/docs/quickstart" className="inline-flex items-center gap-1.5 rounded-md border border-fg bg-fg px-4 py-2 text-[13px] font-medium text-bg transition-colors hover:bg-transparent hover:text-fg">
          Quickstart <ArrowRight className="h-4 w-4" />
        </Link>
        <Link href="/docs/sdk" className="text-sm text-accent hover:underline">SDK overview →</Link>
      </div>
    </article>
  );
}
