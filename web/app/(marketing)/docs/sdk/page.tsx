import { CodeBlock } from "@/components/marketing/ui";

export const metadata = {
  title: "SDK",
  description: "The verbs the Python client exposes, with the signatures it actually has.",
};

/* Every signature here is copied from sdk/python/omem/__init__.py rather than
 * described from memory. The previous table listed history(), revise(),
 * forget() and as_of() as verbs; none of the four exists on the client, so
 * anyone who followed this page got an AttributeError. why() was also given as
 * why(about, claim) when it takes an assertion id.
 *
 * Superseding and retracting ARE real operations, but they live on the HTTP API
 * (POST /v1/assertions/{id}/supersede and /retract) and the Python client does
 * not wrap them yet. Time travel is a PARAMETER, as_of= on recall(), not a verb.
 * Both are said plainly below instead of being implied by a signature that does
 * not resolve. */
const VERBS = [
  { verb: "remember", sig: "remember(agent, about, claim, because=None, scope=None)", d: "Record a belief, optionally grounded in events." },
  { verb: "believes", sig: "believes(about, claim) -> State", d: "The four-valued belief state at the current time." },
  { verb: "why", sig: "why(assertion_id) -> Provenance", d: "Evidence, grounding, interval, and contradictions." },
  { verb: "recall", sig: "recall(about=None, *, agent=None, context=None, as_of=None, limit=10)", d: "Retrieve what is relevant, with belief state and conflicts attached." },
  { verb: "contradict", sig: "contradict(claim_a, claim_b)", d: "Declare two claims opposed. OMEM never infers this." },
  { verb: "observe", sig: "observe(agent, interaction, source=None, scope=None)", d: "Feed a raw interaction; OMEM decides what becomes memory." },
  { verb: "about", sig: "about(entity) -> [Belief]", d: "Every open belief whose subject includes this entity." },
  { verb: "share", sig: "share(assertion_id, scope, granted_by=None)", d: "Promote a memory's visibility: org, team:<id>, agent:<id>, user:<id>." },
];

/* The verb table was a CSS grid of <div>s with a fake header row, so a screen
 * reader met fourteen unrelated cells and no column headers, and there was no
 * way to know which signature belonged to which verb. It is a <table> now, which
 * is what it always was. The heading also claimed "six languages" above a list
 * of seven verbs and four code tabs — the number was wrong twice over.
 */

export default function Sdk() {
  return (
    <article className="max-w-read">
      <div className="tech-label mb-3">SDK</div>
      <h1 className="display text-2xl">Eight verbs, one memory model</h1>
      <p className="lede mt-4">
        The SDK speaks the language of an agent remembering things. Each verb maps
        1:1 to an operation in the OMEM standard. There are no hidden semantics,
        and you can always drop to the raw operations when you need to.
      </p>

      <h2 className="mt-12 text-lg font-semibold">The verbs</h2>
      <div className="mt-4 overflow-x-auto rounded-md border">
        <table className="w-full text-left text-note">
          <caption className="sr-only">OMEM SDK verbs, their signatures, and what each does</caption>
          <thead>
            <tr>
              <th scope="col" className="tech-label border-b bg-raised px-4 py-2.5">Verb</th>
              <th scope="col" className="tech-label border-b bg-raised px-4 py-2.5">Signature and effect</th>
            </tr>
          </thead>
          <tbody>
            {VERBS.map(v => (
              <tr key={v.verb} className="border-b last:border-b-0">
                <th scope="row" className="whitespace-nowrap px-4 py-3 align-top">
                  <span className="mono rounded bg-accentBg px-1.5 py-0.5 text-xs font-medium text-accent">{v.verb}</span>
                </th>
                <td className="px-4 py-3">
                  <div className="mono text-caption text-muted">{v.sig}</div>
                  <div className="mt-1.5 text-note">{v.d}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2 className="mt-12 text-lg font-semibold">The same call, everywhere</h2>
      {/* These three are copied from working calls. What was here before was an
          aspirational API: `omem.Client()` and `mem.entity()/mem.event()` were
          never written, the TypeScript tab imported `Omem` where the SDK
          exports `Memory`, the curl tab pointed at api.omem.dev (which does not
          resolve) with an `sk_live_` key format OMEM does not issue, and there
          was a Go tab for an SDK that does not exist. */}
      <div className="mt-4">
        <CodeBlock label="Recording and querying a belief"
          tabs={[
            { label: "Python", code: `from omem import Memory\n\nmem = Memory(api_key="omem_sk_...",\n             base_url="http://127.0.0.1:8787",\n             project="proj_...")\n\nmem.remember(agent="support-bot",\n             about="customer:alice",\n             claim="prefers_annual_billing")\n\nmem.believes(about="customer:alice",\n             claim="prefers_annual_billing")   # 'BELIEVED_TRUE'` },
            { label: "TypeScript", code: `import { Memory } from "@omem/sdk";\n\nconst mem = new Memory({\n  apiKey: "omem_sk_...",\n  baseUrl: "http://127.0.0.1:8787",\n  project: "proj_...",\n});\n\nawait mem.remember({\n  agent: "support-bot",\n  about: "customer:alice",\n  claim: "prefers_annual_billing",\n});\n\nawait mem.believes({\n  about: "customer:alice",\n  claim: "prefers_annual_billing",\n});   // 'BELIEVED_TRUE'` },
            { label: "curl", code: `curl http://127.0.0.1:8787/v1/assertions \\\n  -H "Authorization: Bearer omem_sk_..." \\\n  -H "Content-Type: application/json" \\\n  -d '{\n    "agent": "support-bot",\n    "subjects": ["customer:alice"],\n    "proposition": "prefers_annual_billing",\n    "assertion_time": "now"\n  }'` },
          ]} />
      </div>

      {/* An aside, marked as one. It was a bare div with a left border, which is
          a visual convention a screen reader does not have. */}
      <aside className="mt-10 rounded-md border border-l-2 border-l-[color:var(--accent)] bg-panel px-4 py-4 text-note text-muted">
        <strong className="font-medium text-fg">The TypeScript SDK lags this one.</strong>{" "}
        It is on npm as <span className="mono text-fg">@omem/sdk</span>, but it
        does not yet cover the whole Python surface.{" "}
        <span className="mono text-fg">npm test</span> in{" "}
        <span className="mono text-fg">sdk/typescript/</span> runs it against a
        live server and reports what is missing. Superseding and retracting are
        HTTP routes rather than client methods on either SDK, and time travel is
        the <span className="mono text-fg">as_of</span> parameter on{" "}
        <span className="mono text-fg">recall</span>, not a verb of its own.
      </aside>
    </article>
  );
}
