import { CodeBlock } from "@/components/marketing/ui";

export const metadata = { title: "SDK / OMEM" };

const VERBS = [
  { verb: "remember", sig: "remember(agent, *, about, claim, because=None)", d: "Record a belief, optionally grounded in events." },
  { verb: "believes", sig: "believes(about, claim) -> State", d: "The four-valued belief state at the current time." },
  { verb: "why", sig: "why(about, claim) -> Provenance", d: "Evidence, grounding, interval, and contradictions." },
  { verb: "history", sig: "history(about, claim) -> [Belief]", d: "The ordered revision chain for a belief." },
  { verb: "revise", sig: "revise(belief, *, to, by)", d: "Supersede a belief; closes the prior interval." },
  { verb: "forget", sig: "forget(belief, *, by)", d: "Retract a belief (recorded, never destroyed)." },
  { verb: "as_of", sig: "as_of(T).believes(...)", d: "Run any query as memory stood at time T." },
];

export default function Sdk() {
  return (
    <article className="max-w-2xl">
      <div className="tech-label mb-4">SDK</div>
      <h1 className="display text-[36px]">One ergonomic surface, six languages</h1>
      <p className="mt-3 text-pretty leading-relaxed text-muted">
        The SDK speaks the language of an agent remembering things. Each verb maps 1:1 to an
        operation in the OMEM standard. There are no hidden semantics, and you can always drop
        to the raw operations when you need to.
      </p>

      <h2 className="mt-10 text-lg font-semibold">The verbs</h2>
      <div className="mt-4 overflow-hidden rounded-lg border">
        <div className="grid grid-cols-[8rem_1fr] border-b bg-panel tech-label">
          <div className="px-4 py-2.5">Verb</div>
          <div className="px-4 py-2.5">What it does</div>
        </div>
        {VERBS.map((v, i) => (
          <div key={v.verb} className={`grid grid-cols-[8rem_1fr] items-start ${i < VERBS.length - 1 ? "border-b" : ""}`}>
            <div className="px-4 py-3">
              <span className="mono rounded bg-[color:var(--accent)]/10 px-1.5 py-0.5 text-xs text-accent">{v.verb}</span>
            </div>
            <div className="px-4 py-3">
              <div className="mono text-2xs text-muted">{v.sig}</div>
              <div className="mt-0.5 text-sm">{v.d}</div>
            </div>
          </div>
        ))}
      </div>

      <h2 className="mt-10 text-lg font-semibold">The same call, everywhere</h2>
      <div className="mt-4">
        <CodeBlock tabs={[
          { label: "Python", code: `import omem\nmem = omem.Client()\n\nmem.remember(\n    mem.agent("support-bot@v2.1"),\n    about=mem.entity("customer:alice"),\n    claim="prefers_email_over_phone",\n    because=[mem.event("ticket:8842")],\n)\n\nmem.believes(mem.entity("customer:alice"),\n             "prefers_email_over_phone")   # BELIEVED_TRUE` },
          { label: "TypeScript", code: `import { Omem } from "@omem/sdk";\nconst mem = new Omem();\n\nawait mem.remember(mem.agent("support-bot@v2.1"), {\n  about: mem.entity("customer:alice"),\n  claim: "prefers_email_over_phone",\n  because: [mem.event("ticket:8842")],\n});\n\nawait mem.believes(mem.entity("customer:alice"),\n                   "prefers_email_over_phone");` },
          { label: "Go", code: `mem := omem.New()\n\nmem.Remember(ctx, omem.Claim{\n    Agent:       "support-bot@v2.1",\n    Subjects:    []string{"customer:alice"},\n    Proposition: "prefers_email_over_phone",\n    Because:     []string{"ticket:8842"},\n})\n\nstate, _ := mem.Believes(ctx,\n    "customer:alice", "prefers_email_over_phone")` },
          { label: "curl", code: `curl https://api.omem.dev/v1/assertions \\\n  -H "Authorization: Bearer sk_live_..." \\\n  -H "Content-Type: application/json" \\\n  -d '{\n    "agent": "support-bot@v2.1",\n    "subjects": ["customer:alice"],\n    "proposition": "prefers_email_over_phone",\n    "because": ["ticket:8842"]\n  }'` },
        ]} />
      </div>

      <div className="mt-8 rounded-md border-l-2 border-l-accent bg-panel px-4 py-3 text-sm text-muted">
        Prototyping offline? <span className="mono text-fg">Client(embedded=True)</span> runs the
        reference engine in-process: identical semantics, zero network, no key. Flip to cloud by
        removing one argument.
      </div>
    </article>
  );
}
