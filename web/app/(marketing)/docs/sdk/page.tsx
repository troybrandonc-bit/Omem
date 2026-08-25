import { CodeBlock } from "@/components/marketing/ui";

export const metadata = {
  title: "SDK",
  description: "Seven verbs, each mapping 1:1 to an operation in the OMEM standard.",
};

const VERBS = [
  { verb: "remember", sig: "remember(agent, *, about, claim, because=None)", d: "Record a belief, optionally grounded in events." },
  { verb: "believes", sig: "believes(about, claim) -> State", d: "The four-valued belief state at the current time." },
  { verb: "why", sig: "why(about, claim) -> Provenance", d: "Evidence, grounding, interval, and contradictions." },
  { verb: "history", sig: "history(about, claim) -> [Belief]", d: "The ordered revision chain for a belief." },
  { verb: "revise", sig: "revise(belief, *, to, by)", d: "Supersede a belief; closes the prior interval." },
  { verb: "forget", sig: "forget(belief, *, by)", d: "Retract a belief (recorded, never destroyed)." },
  { verb: "as_of", sig: "as_of(T).believes(...)", d: "Run any query as memory stood at time T." },
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
      <h1 className="display text-2xl">Seven verbs, one memory model</h1>
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
            { label: "TypeScript", code: `import { Memory } from "./sdk/typescript/src/index";\n\nconst mem = new Memory({\n  apiKey: "omem_sk_...",\n  baseUrl: "http://127.0.0.1:8787",\n  project: "proj_...",\n});\n\nawait mem.remember({\n  agent: "support-bot",\n  about: "customer:alice",\n  claim: "prefers_annual_billing",\n});\n\nawait mem.believes({\n  about: "customer:alice",\n  claim: "prefers_annual_billing",\n});   // 'BELIEVED_TRUE'` },
            { label: "curl", code: `curl http://127.0.0.1:8787/v1/assertions \\\n  -H "Authorization: Bearer omem_sk_..." \\\n  -H "Content-Type: application/json" \\\n  -d '{\n    "agent": "support-bot",\n    "subjects": ["customer:alice"],\n    "proposition": "prefers_annual_billing",\n    "assertion_time": "now"\n  }'` },
          ]} />
      </div>

      {/* An aside, marked as one. It was a bare div with a left border, which is
          a visual convention a screen reader does not have. */}
      <aside className="mt-10 rounded-md border border-l-2 border-l-[color:var(--accent)] bg-panel px-4 py-4 text-note text-muted">
        <strong className="font-medium text-fg">The TypeScript SDK is not on npm yet.</strong>{" "}
        It lives in <span className="mono text-fg">sdk/typescript/</span> and is
        used from source. It lags the Python SDK;{" "}
        <span className="mono text-fg">test_parity.mjs</span> runs against a live
        server and reports what is missing.
      </aside>
    </article>
  );
}
