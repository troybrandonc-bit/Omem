import Link from "next/link";
import { CodeBlock } from "@/components/marketing/ui";
import { ArrowRight } from "lucide-react";

export const metadata = { title: "Quickstart / OMEM Cloud" };

const STEPS = [
  { title: "Install the SDK", body: "The embedded engine runs offline with full semantics. No key is needed to start.",
    code: [{ label: "Python", code: "pip install omem" }, { label: "TypeScript", code: "npm i @omem/sdk" }] },
  { title: "Create a client", body: "Point at the cloud with your key, or run fully in-process while prototyping.",
    code: [{ label: "Python", code: `import omem\n\nmem = omem.Client()            # OMEM_API_KEY from env\n# mem = omem.Client(embedded=True)   # offline, no key` }] },
  { title: "Remember a belief", body: "Attribute the claim to an agent and, optionally, ground it in an event.",
    code: [{ label: "Python", code: `alice = mem.entity("customer:alice")\nbot   = mem.agent("support-bot@v2.1")\n\nmem.remember(bot, about=alice,\n    claim="prefers_email_over_phone",\n    because=[mem.event("ticket:8842")])` }] },
  { title: "Query what it believes", body: "Returns a four-valued state: believed_true, believed_false, contradicted, or unknown.",
    code: [{ label: "Python", code: `mem.believes(alice, "prefers_email_over_phone")\n# -> BELIEVED_TRUE` }] },
  { title: "Ask why", body: "Get the evidence, the interval, and any contradictions, the same data the dashboard renders.",
    code: [{ label: "Python", code: `mem.why(alice, "prefers_email_over_phone")\n# -> grounded in ticket:8842 / believed since t=1 / no contradictions` }] },
];

export default function Quickstart() {
  return (
    <article className="max-w-2xl">
      <div className="tech-label mb-4">Quickstart</div>
      <h1 className="display text-[36px]">Your first memory in five minutes</h1>
      <p className="mt-3 text-pretty leading-relaxed text-muted">
        Store a belief, query it, and see why it&apos;s believed. Every snippet below is real and
        runs against the same API the dashboard uses.
      </p>

      <ol className="mt-10 space-y-10">
        {STEPS.map((s, i) => (
          <li key={i} className="relative border-l pl-8">
            <span className="absolute -left-[13px] top-0 grid h-6 w-6 place-items-center rounded-full border bg-bg text-2xs font-semibold">{i + 1}</span>
            <h2 className="font-semibold">{s.title}</h2>
            <p className="mt-1 text-sm text-muted">{s.body}</p>
            <div className="mt-3"><CodeBlock tabs={s.code} /></div>
          </li>
        ))}
      </ol>

      <div className="mt-14 border-t pt-8">
        <h3 className="font-medium">See it in the dashboard</h3>
        <p className="mt-1 text-sm text-muted">Your belief appears live in the Memory Inspector. Open the &quot;why&quot; view to trace its provenance and scrub through time.</p>
        <div className="mt-4 flex gap-3">
          <Link href="/overview" className="inline-flex items-center gap-1.5 rounded-md border border-fg bg-fg px-3 py-1.5 text-[13px] font-medium text-bg transition-colors hover:bg-transparent hover:text-fg">
            Open dashboard <ArrowRight className="h-3.5 w-3.5" />
          </Link>
          <Link href="/playground" className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-[13px] transition-colors hover:bg-bg">Playground</Link>
        </div>
      </div>
    </article>
  );
}
